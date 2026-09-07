"""Pure-Python helpers for stationary T0-T3 commissioning."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationarySnapshot:
  v_ego: float
  standstill: bool
  selfdrive_active: bool
  gear: str | None = None


def evaluate_stationary_guard(snapshot: StationarySnapshot, *, require_park: bool = True,
                              max_abs_speed_mps: float = 0.10) -> tuple[bool, tuple[str, ...]]:
  reasons: list[str] = []
  if abs(float(snapshot.v_ego)) > max_abs_speed_mps:
    reasons.append("vehicle_speed_nonzero")
  if not snapshot.standstill:
    reasons.append("carstate_not_standstill")
  if snapshot.selfdrive_active:
    reasons.append("selfdrive_active")
  if require_park and snapshot.gear is not None and snapshot.gear.lower() not in {"park", "p"}:
    reasons.append("gear_not_park")
  return not reasons, tuple(reasons)


@dataclass
class FrameContinuityCounter:
  last_frame_id: int | None = None
  samples: int = 0
  duplicate_or_old: int = 0
  gap_frames: int = 0

  def observe(self, frame_id: int) -> None:
    if frame_id <= 0:
      return
    self.samples += 1
    if self.last_frame_id is not None:
      if frame_id <= self.last_frame_id:
        self.duplicate_or_old += 1
      elif frame_id > self.last_frame_id + 1:
        self.gap_frames += frame_id - self.last_frame_id - 1
    self.last_frame_id = frame_id

  def summary(self) -> dict[str, int]:
    return {
      "samples": self.samples,
      "duplicateOrOldTransitions": self.duplicate_or_old,
      "gapFrames": self.gap_frames,
      "lastFrameId": self.last_frame_id or 0,
    }
