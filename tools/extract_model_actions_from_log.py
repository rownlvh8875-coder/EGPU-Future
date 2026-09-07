#!/usr/bin/env python3
"""Extract modelV2 actions and nearby vehicle context from an openpilot rlog/qlog.

Run this inside an openpilot checkout/environment. The output schema is shared
with capture_model_actions.py and is intended for small-vs-big route replay
comparison.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpilot.tools.lib.logreader import LogReader


def _safe_float(value, default=None):
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _lead_context(radar_state) -> dict:
  if radar_state is None:
    return {}
  try:
    lead = radar_state.leadOne
    present = bool(lead.present)
    return {
      "leadPresent": present,
      "leadDistanceM": float(lead.dRel) if present else None,
      "leadRelSpeedMps": float(lead.vRel) if present else None,
      "leadModelProb": float(lead.modelProb) if present else None,
      "leadRadarMatched": bool(lead.radar) if present else None,
    }
  except Exception:
    return {}


def main() -> None:
  ap = argparse.ArgumentParser(description="Extract modelV2 action samples from openpilot logs")
  ap.add_argument("log", help="local rlog/qlog(.bz2/.zst), URL, or route identifier supported by LogReader")
  ap.add_argument("--output", type=Path, required=True)
  ap.add_argument("--source-label", default="replay")
  args = ap.parse_args()

  latest_car = None
  latest_radar = None
  seen_frame_ids: set[int] = set()
  duplicate_frame_ids = 0
  emitted = 0

  args.output.parent.mkdir(parents=True, exist_ok=True)
  with args.output.open("w", encoding="utf-8") as out:
    for evt in LogReader(args.log, sort_by_time=True, only_union_types=True):
      which = evt.which()
      if which == "carState":
        latest_car = evt.carState
        continue
      if which == "radarState":
        latest_radar = evt.radarState
        continue
      if which != "modelV2":
        continue

      model = evt.modelV2
      frame_id = int(model.frameId)
      if frame_id in seen_frame_ids:
        duplicate_frame_ids += 1
      seen_frame_ids.add(frame_id)

      action = model.action
      speed = _safe_float(getattr(latest_car, "vEgo", None)) if latest_car is not None else None
      accel = _safe_float(getattr(latest_car, "aEgo", None)) if latest_car is not None else None
      standstill = bool(getattr(latest_car, "standstill", False)) if latest_car is not None else None
      row = {
        "source": args.source_label,
        "logMonoTimeNs": int(evt.logMonoTime),
        "logMonoTimeS": float(evt.logMonoTime) / 1e9,
        "frameId": frame_id,
        "frameIdExtra": int(getattr(model, "frameIdExtra", 0)),
        "frameAge": int(getattr(model, "frameAge", 0)),
        "modelExecutionTimeS": _safe_float(getattr(model, "modelExecutionTime", None)),
        "big": bool(getattr(model, "big", False)),
        "desiredCurvature": float(action.desiredCurvature),
        "desiredAcceleration": float(action.desiredAcceleration),
        "shouldStop": bool(action.shouldStop),
        "speedMps": speed,
        "vehicleAccelMps2": accel,
        "standstill": standstill,
      }
      row.update(_lead_context(latest_radar))
      out.write(json.dumps(row, ensure_ascii=False) + "\n")
      emitted += 1

  print(f"emitted={emitted}")
  print(f"duplicate_frame_ids={duplicate_frame_ids}")
  print(f"output={args.output}")


if __name__ == "__main__":
  main()
