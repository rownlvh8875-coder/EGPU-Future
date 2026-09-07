#!/usr/bin/env python3
"""Control-isolated openpilot shadow-model prototype.

Current supported production-like research mode:
  active Chestnut/big model + shadow on-device/small model.

The process publishes no cereal services and never sends vehicle commands.  It
requires exact input snapshots from `ModeldShadowTapBridge` and writes shadow
results to JSONL for later frameId pairing with the active modelV2 log.

This file targets the current commaai/openpilot modeld API and is intentionally
manual-start only.  Do not add it to manager/process_config until resource and
latency measurements prove that it cannot perturb the active model path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

import openpilot.cereal.messaging as messaging
from openpilot.cereal import log
from openpilot.cereal.visionipc import VisionStreamType
from msgq.visionipc import VisionIpcClient
from openpilot.selfdrive.modeld.modeld import FrameMeta, ModelState, get_action_from_model

from egpu_future.shadow_runtime import AdmissionPolicy, Backend, ContinuityTracker, ShadowAdmissionController, TimingTrace
from egpu_future.shadow_tap import DEFAULT_SOCKET_PATH, ShadowInputSnapshot, ShadowTapReceiver


SHADOW_SCHEMA_VERSION = 1


def _backend(value: str) -> Backend:
  try:
    return Backend(value)
  except ValueError:
    return Backend.UNKNOWN


def _apply_resource_isolation(nice_value: int, cpu_affinity: str | None) -> dict:
  result = {"nice_requested": nice_value, "nice_applied": False, "cpu_affinity": None}
  try:
    os.nice(nice_value)
    result["nice_applied"] = True
  except OSError:
    pass

  if cpu_affinity and hasattr(os, "sched_setaffinity"):
    try:
      cpus = {int(v.strip()) for v in cpu_affinity.split(",") if v.strip()}
      if cpus:
        os.sched_setaffinity(0, cpus)
        result["cpu_affinity"] = sorted(cpus)
    except (OSError, ValueError):
      pass
  return result


def _write_event(out, event: dict, flush: bool = False) -> None:
  event.setdefault("schemaVersion", SHADOW_SCHEMA_VERSION)
  event.setdefault("shadowOnly", True)
  event.setdefault("controlEligible", False)
  out.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
  if flush:
    out.flush()


def _find_streams() -> tuple[VisionStreamType, bool]:
  while True:
    available = VisionIpcClient.available_streams("camerad", block=False)
    if available:
      use_extra = VisionStreamType.VISION_STREAM_WIDE_ROAD in available and VisionStreamType.VISION_STREAM_NARROW_ROAD in available
      main_wide = VisionStreamType.VISION_STREAM_NARROW_ROAD not in available
      main = VisionStreamType.VISION_STREAM_WIDE_ROAD if main_wide else VisionStreamType.VISION_STREAM_NARROW_ROAD
      return main, use_extra
    time.sleep(0.1)


def _connect_client(stream: VisionStreamType) -> VisionIpcClient:
  # conflate=True is deliberate: shadow work may be dropped, but must never
  # build a camera backlog that competes with the active model.
  client = VisionIpcClient("camerad", stream, True)
  while not client.connect(False):
    time.sleep(0.1)
  return client


def _recv_exact(client: VisionIpcClient, target_frame_id: int, max_reads: int = 8):
  last_meta = None
  for _ in range(max_reads):
    buf = client.recv()
    if buf is None:
      return None, last_meta, "no_frame"
    meta = FrameMeta(client)
    last_meta = meta
    if meta.frame_id == target_frame_id:
      return buf, meta, None
    if meta.frame_id > target_frame_id:
      return None, meta, "camera_advanced"
  return None, last_meta, "target_not_reached"


def _record_skip(out, snap: ShadowInputSnapshot, reason: str, extra: dict | None = None) -> None:
  event = {
    "type": "skip",
    "frameId": snap.frame_id,
    "frameIdExtra": snap.frame_id_extra,
    "activeBackend": snap.active_backend,
    "shadowBackend": "small",
    "reason": reason,
    "tapCreatedMonoNs": snap.created_mono_ns,
  }
  if extra:
    event.update(extra)
  _write_event(out, event)


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("--tap-socket", default=DEFAULT_SOCKET_PATH)
  ap.add_argument("--output", default="/tmp/egpu_future_shadow_modeld.jsonl")
  ap.add_argument("--max-hz", type=float, default=20.0,
                  help="20 Hz for temporal comparison; lower values are load-probe only")
  ap.add_argument("--settle-frames", type=int, default=40,
                  help="consecutive shadow frames required before comparisonEligible")
  ap.add_argument("--nice", type=int, default=10,
                  help="positive process niceness increment; shadow must remain lower priority")
  ap.add_argument("--cpu-affinity", default=None, help="optional comma-separated CPU ids")
  ap.add_argument("--flush-every", type=int, default=20)
  args = ap.parse_args()

  if args.max_hz <= 0:
    raise SystemExit("--max-hz must be > 0")
  if args.settle_frames < 1:
    raise SystemExit("--settle-frames must be >= 1")

  isolation = _apply_resource_isolation(args.nice, args.cpu_affinity)
  out_path = Path(args.output)
  out_path.parent.mkdir(parents=True, exist_ok=True)

  main_stream, use_extra = _find_streams()
  main_client = _connect_client(main_stream)
  extra_client = _connect_client(VisionStreamType.VISION_STREAM_WIDE_ROAD) if use_extra else None

  # Only the on-device model is supported by this first live prototype.  This
  # avoids a second process contending for Chestnut/USB resources.
  shadow_backend = Backend.SMALL
  admission = ShadowAdmissionController(shadow_backend, AdmissionPolicy(max_hz=args.max_hz, require_opposite_backend=True))
  continuity = ContinuityTracker(args.settle_frames)
  prev_action = log.ModelDataV2.Action()

  model = None
  events_since_flush = 0

  with out_path.open("a", encoding="utf-8", buffering=1) as out, ShadowTapReceiver(args.tap_socket) as tap:
    _write_event(out, {"type": "startup", "shadowBackend": shadow_backend.value, "maxHz": args.max_hz,
                       "settleFrames": args.settle_frames, "resourceIsolation": isolation}, flush=True)

    while True:
      snap = tap.recv_latest()
      if snap is None:
        time.sleep(0.001)
        continue

      active_backend = _backend(snap.active_backend)
      decision = admission.decide(snap.frame_id, active_backend, time.monotonic_ns())
      if not decision.accepted:
        continuity = ContinuityTracker(args.settle_frames)
        prev_action = log.ModelDataV2.Action()
        _record_skip(out, snap, decision.reason.value)
        continue

      # Defer model allocation until a big-model active frame is actually seen.
      # Merely launching this research process should not consume QCOM model
      # resources while the active model is already small/fallback.
      if model is None:
        load_start = time.monotonic_ns()
        model = ModelState(main_client.width, main_client.height, False)
        model.warmup()
        _write_event(out, {"type": "model_loaded", "shadowBackend": "small",
                           "loadMs": (time.monotonic_ns() - load_start) / 1e6}, flush=True)
        # The frame that triggered model loading is too old to compare.
        continuity = ContinuityTracker(args.settle_frames)
        prev_action = log.ModelDataV2.Action()
        _record_skip(out, snap, "model_loaded_on_this_frame")
        continue

      buf_main, meta_main, miss = _recv_exact(main_client, snap.frame_id)
      if miss is not None or buf_main is None or meta_main is None:
        continuity = ContinuityTracker(args.settle_frames)
        prev_action = log.ModelDataV2.Action()
        _record_skip(out, snap, f"main_{miss}", {"observedFrameId": None if meta_main is None else meta_main.frame_id})
        continue

      if use_extra:
        assert extra_client is not None
        buf_extra, meta_extra, miss_extra = _recv_exact(extra_client, snap.frame_id_extra)
        if miss_extra is not None or buf_extra is None or meta_extra is None:
          continuity = ContinuityTracker(args.settle_frames)
          prev_action = log.ModelDataV2.Action()
          _record_skip(out, snap, f"extra_{miss_extra}", {"observedFrameId": None if meta_extra is None else meta_extra.frame_id})
          continue
      else:
        buf_extra, meta_extra = buf_main, meta_main

      # Require the tap metadata to describe the exact camera buffers we are
      # about to process.  Any mismatch is a shadow drop, never a reason to
      # delay or alter the active model.
      if meta_main.frame_id != snap.frame_id or meta_extra.frame_id != snap.frame_id_extra:
        continuity = ContinuityTracker(args.settle_frames)
        prev_action = log.ModelDataV2.Action()
        _record_skip(out, snap, "frame_identity_mismatch")
        continue

      frame_received_ns = time.monotonic_ns()
      main_tfm = np.asarray(snap.main_transform, dtype=np.float32).reshape(3, 3)
      extra_tfm = np.asarray(snap.extra_transform, dtype=np.float32).reshape(3, 3)
      bufs = {name: buf_extra if "big" in name else buf_main for name in model.vision_input_names}
      transforms = {name: extra_tfm if "big" in name else main_tfm for name in model.vision_input_names}
      inputs = {
        "desire_pulse": np.asarray(snap.desire_pulse, dtype=np.float32).copy(),
        "traffic_convention": np.asarray(snap.traffic_convention, dtype=np.float32).copy(),
        "action_t": np.asarray(snap.action_t, dtype=np.float32).copy(),
      }

      model_call_start_ns = time.monotonic_ns()
      device_enqueued_ns = None

      def after_enqueue() -> None:
        nonlocal device_enqueued_ns
        device_enqueued_ns = time.monotonic_ns()

      try:
        model_output = model.run(bufs, transforms, inputs, after_enqueue)
      except Exception as exc:
        inference_done_ns = time.monotonic_ns()
        continuity = ContinuityTracker(args.settle_frames)
        prev_action = log.ModelDataV2.Action()
        _write_event(out, {
          "type": "shadow_error",
          "frameId": snap.frame_id,
          "activeBackend": snap.active_backend,
          "shadowBackend": "small",
          "error": repr(exc),
          "modelCallMs": (inference_done_ns - model_call_start_ns) / 1e6,
        }, flush=True)
        return 2

      inference_done_ns = time.monotonic_ns()
      action = get_action_from_model(model_output, prev_action, float(snap.action_t[0]), float(snap.action_t[1]), snap.v_ego)
      prev_action = action
      continuity_result = continuity.observe(snap.frame_id)

      record_stamp_ns = time.monotonic_ns()
      trace = TimingTrace(
        camera_sof_ns=snap.camera_sof_ns,
        camera_eof_ns=snap.camera_eof_ns,
        frame_received_ns=frame_received_ns,
        model_call_start_ns=model_call_start_ns,
        device_enqueued_ns=device_enqueued_ns,
        inference_done_ns=inference_done_ns,
        record_written_ns=record_stamp_ns,
      )
      timing = trace.metrics_ms()
      comparison_eligible = (
        active_backend == Backend.BIG
        and continuity_result.eligible
        and trace.ordered()
        and continuity_result.gap_frames == 0
      )

      event = {
        "type": "shadow_output",
        "frameId": snap.frame_id,
        "frameIdExtra": snap.frame_id_extra,
        "cameraTimestampSofNs": snap.camera_sof_ns,
        "cameraTimestampEofNs": snap.camera_eof_ns,
        "tapCreatedMonoNs": snap.created_mono_ns,
        "activeBackend": active_backend.value,
        "shadowBackend": shadow_backend.value,
        "comparisonEligible": comparison_eligible,
        "continuityStreak": continuity_result.streak,
        "gapFrames": continuity_result.gap_frames,
        "vEgo": snap.v_ego,
        "action": {
          "desiredCurvature": float(action.desiredCurvature),
          "desiredAcceleration": float(action.desiredAcceleration),
          "shouldStop": bool(action.shouldStop),
        },
        "timing": timing,
        "timingOrdered": trace.ordered(),
      }
      events_since_flush += 1
      _write_event(out, event, flush=events_since_flush >= args.flush_every)
      if events_since_flush >= args.flush_every:
        events_since_flush = 0

  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except KeyboardInterrupt:
    raise SystemExit(0)
