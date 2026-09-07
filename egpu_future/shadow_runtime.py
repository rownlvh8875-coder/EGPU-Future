"""Control-isolated runtime primitives for shadow-model research.

Nothing in this module sends vehicle commands.  It provides deterministic
admission, continuity, timing, and latest-only backpressure helpers that can be
unit-tested without openpilot or GPU hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar


class Backend(StrEnum):
  SMALL = "small"
  BIG = "big"
  UNKNOWN = "unknown"


class AdmissionReason(StrEnum):
  ACCEPT = "accept"
  ACTIVE_UNKNOWN = "active_unknown"
  SAME_BACKEND = "same_backend"
  RATE_LIMIT = "rate_limit"
  DUPLICATE_OR_OLD_FRAME = "duplicate_or_old_frame"


@dataclass(frozen=True)
class AdmissionPolicy:
  # comparison mode should normally use 20 Hz.  Lower values are useful only
  # for load/thermal probes because skipping inference breaks temporal parity.
  max_hz: float | None = 20.0
  require_opposite_backend: bool = True


@dataclass(frozen=True)
class AdmissionDecision:
  accepted: bool
  reason: AdmissionReason


class ShadowAdmissionController:
  def __init__(self, shadow_backend: Backend, policy: AdmissionPolicy | None = None):
    self.shadow_backend = shadow_backend
    self.policy = policy or AdmissionPolicy()
    self._last_accepted_ns: int | None = None
    self._last_seen_frame_id: int | None = None

  def decide(self, frame_id: int, active_backend: Backend, now_ns: int) -> AdmissionDecision:
    if self._last_seen_frame_id is not None and frame_id <= self._last_seen_frame_id:
      return AdmissionDecision(False, AdmissionReason.DUPLICATE_OR_OLD_FRAME)
    self._last_seen_frame_id = frame_id

    if active_backend == Backend.UNKNOWN:
      return AdmissionDecision(False, AdmissionReason.ACTIVE_UNKNOWN)
    if self.policy.require_opposite_backend and active_backend == self.shadow_backend:
      return AdmissionDecision(False, AdmissionReason.SAME_BACKEND)

    max_hz = self.policy.max_hz
    if max_hz is not None and max_hz > 0 and self._last_accepted_ns is not None:
      min_period_ns = int(1e9 / max_hz)
      if now_ns - self._last_accepted_ns < min_period_ns:
        return AdmissionDecision(False, AdmissionReason.RATE_LIMIT)

    self._last_accepted_ns = now_ns
    return AdmissionDecision(True, AdmissionReason.ACCEPT)


@dataclass(frozen=True)
class ContinuityResult:
  gap_frames: int
  streak: int
  eligible: bool
  reset: bool


class ContinuityTracker:
  """Track whether shadow inference has maintained consecutive frame history.

  A temporal model is not directly comparable after sampling gaps because its
  hidden state has evolved on a different sequence.  `eligible` becomes true
  only after `settle_frames` consecutive frame ids have been processed.
  """

  def __init__(self, settle_frames: int = 40):
    if settle_frames < 1:
      raise ValueError("settle_frames must be >= 1")
    self.settle_frames = settle_frames
    self.last_frame_id: int | None = None
    self.streak = 0

  def observe(self, frame_id: int) -> ContinuityResult:
    if frame_id <= 0:
      self.last_frame_id = None
      self.streak = 0
      return ContinuityResult(0, 0, False, True)

    if self.last_frame_id is None:
      self.last_frame_id = frame_id
      self.streak = 1
      return ContinuityResult(0, self.streak, self.streak >= self.settle_frames, True)

    delta = frame_id - self.last_frame_id
    self.last_frame_id = frame_id
    if delta == 1:
      self.streak += 1
      return ContinuityResult(0, self.streak, self.streak >= self.settle_frames, False)

    gap = max(0, delta - 1)
    self.streak = 1
    return ContinuityResult(gap, self.streak, False, True)


@dataclass(frozen=True)
class TimingTrace:
  camera_sof_ns: int
  camera_eof_ns: int
  frame_received_ns: int
  model_call_start_ns: int
  device_enqueued_ns: int | None
  inference_done_ns: int
  record_written_ns: int | None = None

  def ordered(self) -> bool:
    points = [self.camera_sof_ns, self.camera_eof_ns, self.frame_received_ns, self.model_call_start_ns]
    if self.device_enqueued_ns is not None:
      points.append(self.device_enqueued_ns)
    points.append(self.inference_done_ns)
    if self.record_written_ns is not None:
      points.append(self.record_written_ns)
    return all(b >= a for a, b in zip(points, points[1:]))

  def metrics_ms(self) -> dict[str, float | None]:
    def ms(a: int, b: int) -> float:
      return (b - a) / 1e6

    return {
      "capture_to_receive_ms": ms(self.camera_eof_ns, self.frame_received_ns),
      "receive_to_model_call_ms": ms(self.frame_received_ns, self.model_call_start_ns),
      "call_to_enqueue_ms": None if self.device_enqueued_ns is None else ms(self.model_call_start_ns, self.device_enqueued_ns),
      "enqueue_to_done_ms": None if self.device_enqueued_ns is None else ms(self.device_enqueued_ns, self.inference_done_ns),
      "model_call_total_ms": ms(self.model_call_start_ns, self.inference_done_ns),
      "capture_to_done_ms": ms(self.camera_eof_ns, self.inference_done_ns),
      "done_to_record_ms": None if self.record_written_ns is None else ms(self.inference_done_ns, self.record_written_ns),
    }


T = TypeVar("T")


class LatestOnlySlot(Generic[T]):
  """Single-slot queue: newest work replaces stale pending work.

  This is the intended shadow backpressure policy.  The active/control path is
  never allowed to wait for shadow work to drain.
  """

  def __init__(self):
    self._item: T | None = None
    self.replaced = 0

  def put(self, item: T) -> bool:
    replaced = self._item is not None
    if replaced:
      self.replaced += 1
    self._item = item
    return replaced

  def take(self) -> T | None:
    item = self._item
    self._item = None
    return item

  def peek(self) -> T | None:
    return self._item
