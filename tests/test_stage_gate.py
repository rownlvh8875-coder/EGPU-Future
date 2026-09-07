import pytest

from egpu_future.stage_gate import GateStatus, InterferenceLimits, evaluate_interference_gate


def stats(samples=100, p99=40.0, max_ms=45.0, miss_rate=0.0, age=0, gaps=0):
  return {
    "samples": samples,
    "meanMs": 35.0,
    "p50Ms": 35.0,
    "p95Ms": 38.0,
    "p99Ms": p99,
    "maxMs": max_ms,
    "deadlineMissRate": miss_rate,
    "frameAgeGt1": age,
    "frameGapCount": gaps,
  }


def limits():
  return InterferenceLimits(
    min_samples_each=50,
    max_p99_increase_ms=2.0,
    max_max_increase_ms=5.0,
    max_deadline_miss_rate_delta=0.001,
    max_frame_age_gt1_delta=0,
    max_frame_gap_count_delta=0,
  )


def test_missing_policy_holds():
  d = evaluate_interference_gate(stats(), stats(), None)
  assert d.status == GateStatus.HOLD
  assert "explicit_limits_required" in d.reasons


def test_insufficient_samples_holds():
  d = evaluate_interference_gate(stats(samples=10), stats(samples=10), limits())
  assert d.status == GateStatus.HOLD
  assert "insufficient_baseline_samples" in d.reasons


def test_within_explicit_limits_passes():
  d = evaluate_interference_gate(stats(), stats(p99=41.0, max_ms=48.0), limits())
  assert d.status == GateStatus.PASS
  assert not d.reasons


def test_exceeded_tail_latency_fails():
  d = evaluate_interference_gate(stats(), stats(p99=43.0, max_ms=51.0), limits())
  assert d.status == GateStatus.FAIL
  assert "p99_increase_ms_exceeded" in d.reasons
  assert "max_increase_ms_exceeded" in d.reasons


def test_limits_validate():
  with pytest.raises(ValueError):
    InterferenceLimits(0, 1.0, 1.0, 0.0, 0, 0).validate()
