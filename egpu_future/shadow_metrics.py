from __future__ import annotations

from dataclasses import dataclass
from math import fabs


@dataclass(frozen=True)
class ActionSample:
  t: float
  curvature: float
  acceleration: float
  should_stop: bool
  speed_mps: float | None = None


@dataclass(frozen=True)
class Thresholds:
  curvature_abs: float = 0.003
  curvature_rel: float = 0.25
  accel_abs: float = 0.50
  stop_mismatch_weight: float = 2.0


@dataclass(frozen=True)
class Disagreement:
  curvature_abs: float
  curvature_rel: float
  accel_abs: float
  stop_mismatch: bool
  score: float
  significant: bool


def compare_actions(a: ActionSample, b: ActionSample, th: Thresholds = Thresholds()) -> Disagreement:
  curv_abs = fabs(a.curvature - b.curvature)
  denom = max(fabs(a.curvature), fabs(b.curvature), 1e-4)
  curv_rel = curv_abs / denom
  accel_abs = fabs(a.acceleration - b.acceleration)
  stop_mismatch = a.should_stop != b.should_stop

  # Dimensionless research score. It is not a safety metric.
  score = max(curv_abs / max(th.curvature_abs, 1e-9), curv_rel / max(th.curvature_rel, 1e-9))
  score += accel_abs / max(th.accel_abs, 1e-9)
  if stop_mismatch:
    score += th.stop_mismatch_weight

  significant = (
    (curv_abs >= th.curvature_abs and curv_rel >= th.curvature_rel)
    or accel_abs >= th.accel_abs
    or stop_mismatch
  )
  return Disagreement(curv_abs, curv_rel, accel_abs, stop_mismatch, score, significant)
