"""Correlate host-aligned tinygrad kernel ranges with shadow model calls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from egpu_future.interference import percentile
from egpu_future.tinygrad_profile import KernelRange, union_busy_us


@dataclass(frozen=True)
class ModelWindow:
  frame_id: int
  start_us: float
  end_us: float
  enqueue_us: float | None = None

  @property
  def duration_ms(self) -> float:
    return (self.end_us - self.start_us) / 1000.0


def model_window_from_shadow_event(row: dict) -> ModelWindow | None:
  if row.get("type") != "shadow_output":
    return None
  frame_id = int(row.get("frameId", 0) or 0)
  if frame_id <= 0:
    return None

  host = row.get("hostTimestampsNs") or {}
  try:
    start_ns = int(host["modelCallStart"])
    end_ns = int(host["inferenceDone"])
    if start_ns > 0 and end_ns >= start_ns:
      enqueue = host.get("deviceEnqueued")
      try:
        enqueue_us = float(enqueue) / 1000.0 if enqueue is not None else None
      except (TypeError, ValueError):
        enqueue_us = None
      return ModelWindow(frame_id, start_ns / 1000.0, end_ns / 1000.0, enqueue_us)
  except (KeyError, TypeError, ValueError):
    pass

  timing = row.get("timing") or {}
  try:
    eof_ns = int(row["cameraTimestampEofNs"])
    capture_to_done_ms = float(timing["capture_to_done_ms"])
    model_call_ms = float(timing["model_call_total_ms"])
  except (KeyError, TypeError, ValueError):
    return None
  end_us = eof_ns / 1000.0 + capture_to_done_ms * 1000.0
  start_us = end_us - model_call_ms * 1000.0
  if start_us <= 0 or end_us < start_us:
    return None
  call_to_enqueue_ms = timing.get("call_to_enqueue_ms")
  try:
    enqueue_us = start_us + float(call_to_enqueue_ms) * 1000.0 if call_to_enqueue_ms is not None else None
  except (TypeError, ValueError):
    enqueue_us = None
  return ModelWindow(frame_id, start_us, end_us, enqueue_us)


def correlate_window(window: ModelWindow, kernels: list[KernelRange], tolerance_us: float = 50.0) -> dict:
  selected = [
    k for k in kernels
    if k.end_us >= window.start_us - tolerance_us and k.start_us <= window.end_us + tolerance_us
  ]
  selected.sort(key=lambda k: (k.start_us, k.end_us, k.name))
  if not selected:
    return {
      "frameId": window.frame_id,
      "modelCallMs": window.duration_ms,
      "kernelCount": 0,
      "firstKernelDelayMs": None,
      "enqueueToFirstKernelMs": None,
      "kernelEnvelopeMs": None,
      "kernelBusyMs": 0.0,
      "afterLastKernelMs": None,
      "coveredByHardwareProfile": False,
    }

  first = selected[0]
  last = max(selected, key=lambda k: k.end_us)
  first_delay = (first.start_us - window.start_us) / 1000.0
  enqueue_delay = ((first.start_us - window.enqueue_us) / 1000.0) if window.enqueue_us is not None else None
  after_last = (window.end_us - last.end_us) / 1000.0
  return {
    "frameId": window.frame_id,
    "modelCallMs": window.duration_ms,
    "kernelCount": len(selected),
    "firstKernelDelayMs": first_delay,
    "enqueueToFirstKernelMs": enqueue_delay,
    "kernelEnvelopeMs": (last.end_us - first.start_us) / 1000.0,
    "kernelBusyMs": union_busy_us(selected) / 1000.0,
    "afterLastKernelMs": after_last,
    "coveredByHardwareProfile": True,
    "firstKernel": first.name,
    "lastKernel": last.name,
  }


def correlate_windows(windows: Iterable[ModelWindow], kernels: list[KernelRange], tolerance_us: float = 50.0) -> list[dict]:
  return [correlate_window(w, kernels, tolerance_us=tolerance_us) for w in windows]


def _metric(rows: list[dict], key: str) -> dict:
  vals = [float(r[key]) for r in rows if r.get(key) is not None]
  return {
    "samples": len(vals),
    "meanMs": sum(vals) / len(vals) if vals else None,
    "p50Ms": percentile(vals, 0.50),
    "p95Ms": percentile(vals, 0.95),
    "p99Ms": percentile(vals, 0.99),
    "maxMs": max(vals) if vals else None,
  }


def summarize_correlations(rows: list[dict]) -> dict:
  covered = [r for r in rows if r.get("coveredByHardwareProfile")]
  return {
    "frames": len(rows),
    "coveredFrames": len(covered),
    "coverage": len(covered) / len(rows) if rows else 0.0,
    "kernelCountTotal": sum(int(r.get("kernelCount", 0) or 0) for r in covered),
    "modelCall": _metric(rows, "modelCallMs"),
    "firstKernelDelay": _metric(covered, "firstKernelDelayMs"),
    "enqueueToFirstKernel": _metric(covered, "enqueueToFirstKernelMs"),
    "kernelEnvelope": _metric(covered, "kernelEnvelopeMs"),
    "kernelBusy": _metric(covered, "kernelBusyMs"),
    "afterLastKernel": _metric(covered, "afterLastKernelMs"),
  }
