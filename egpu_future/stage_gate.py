"""Explicit, policy-driven stage gate for active-model interference evidence.

There are deliberately no project-wide latency thresholds in this module.
Limits must be supplied by the experiment owner after a baseline is measured.
Missing policy/evidence yields HOLD rather than silently passing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from egpu_future.interference import compare_latency_stats


class GateStatus(str, Enum):
  PASS = "PASS"
  HOLD = "HOLD"
  FAIL = "FAIL"


@dataclass(frozen=True)
class InterferenceLimits:
  min_samples_each: int
  max_p99_increase_ms: float
  max_max_increase_ms: float
  max_deadline_miss_rate_delta: float
  max_frame_age_gt1_delta: int
  max_frame_gap_count_delta: int

  def validate(self) -> None:
    if self.min_samples_each <= 0:
      raise ValueError("min_samples_each must be > 0")
    if self.max_p99_increase_ms < 0 or self.max_max_increase_ms < 0:
      raise ValueError("latency increase limits must be >= 0")
    if self.max_deadline_miss_rate_delta < 0:
      raise ValueError("deadline miss rate delta limit must be >= 0")
    if self.max_frame_age_gt1_delta < 0 or self.max_frame_gap_count_delta < 0:
      raise ValueError("frame delta limits must be >= 0")


@dataclass(frozen=True)
class GateDecision:
  status: GateStatus
  reasons: tuple[str, ...]
  checks: dict[str, dict]
  deltas: dict


def evaluate_interference_gate(baseline: dict, candidate: dict,
                               limits: InterferenceLimits | None) -> GateDecision:
  deltas = compare_latency_stats(baseline, candidate)
  if limits is None:
    return GateDecision(GateStatus.HOLD, ("explicit_limits_required",), {}, deltas)
  limits.validate()

  reasons: list[str] = []
  checks: dict[str, dict] = {}

  baseline_samples = int(baseline.get("samples", 0) or 0)
  candidate_samples = int(candidate.get("samples", 0) or 0)
  if baseline_samples < limits.min_samples_each:
    reasons.append("insufficient_baseline_samples")
  if candidate_samples < limits.min_samples_each:
    reasons.append("insufficient_candidate_samples")
  if reasons:
    return GateDecision(GateStatus.HOLD, tuple(reasons), checks, deltas)

  def add_check(name: str, actual, limit, comparison: str = "<=") -> None:
    if actual is None:
      reasons.append(f"missing_{name}")
      checks[name] = {"actual": None, "limit": limit, "pass": False}
      return
    passed = actual <= limit
    checks[name] = {"actual": actual, "limit": limit, "comparison": comparison, "pass": passed}
    if not passed:
      reasons.append(f"{name}_exceeded")

  add_check("p99_increase_ms", deltas["p99"]["absoluteMs"], limits.max_p99_increase_ms)
  add_check("max_increase_ms", deltas["max"]["absoluteMs"], limits.max_max_increase_ms)
  add_check("deadline_miss_rate_delta", deltas["deadlineMissRateDelta"], limits.max_deadline_miss_rate_delta)
  add_check("frame_age_gt1_delta", deltas["frameAgeGt1Delta"], limits.max_frame_age_gt1_delta)
  add_check("frame_gap_count_delta", deltas["frameGapCountDelta"], limits.max_frame_gap_count_delta)

  if any(reason.startswith("missing_") for reason in reasons):
    status = GateStatus.HOLD
  elif reasons:
    status = GateStatus.FAIL
  else:
    status = GateStatus.PASS
  return GateDecision(status, tuple(reasons), checks, deltas)
