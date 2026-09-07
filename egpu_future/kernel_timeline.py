"""Correlate host-aligned tinygrad kernel ranges with shadow model calls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
  host = row.get("hostTimestampsNs") or {}
  frame_id = int(row.get("frameId", 0) or 0)
  try:
    start_ns = int(host["modelCallStart"])
    end_ns = int(host["inferenceDone"])
  except (KeyError, TypeError, ValueError):
    return None
  if frame_id <= 0 or start_ns <= 0 or end_ns < start_ns:
    return None
  enqueue = host.get("deviceEnqueued")
  try:
    enqueue_us = float(enqueue) / 1000.0 if enqueue is not None else None
  except (TypeError, ValueError):
    enqueue_us = None
  return ModelWindow(frame_id, start_ns / 1000.0, end_ns / 1000.0, enqueue_us)


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
