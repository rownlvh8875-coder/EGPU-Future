"""Deterministic synthetic T0-T3 evidence for end-to-end pipeline regression.

Synthetic evidence is never a substitute for vehicle measurements.  It exists
only to prove that the analysis/qualification machinery produces expected
PASS/HOLD/FAIL behavior before precious commissioning time is spent on-device.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from egpu_future.stage_gate import InterferenceLimits


@dataclass(frozen=True)
class SyntheticCommissioningCase:
  name: str
  expected_status: str
  t0_ms: float
  t1_delta_ms: float
  t2_delta_ms: float
  t3_delta_ms: float
  samples: int = 240
  t3_decode_errors: int = 0
  t3_frame_gap_every: int | None = None
  use_limits: bool = True


def demo_limits() -> InterferenceLimits:
  # Demonstration/test values only.  These are deliberately local to the
  # synthetic harness and must never be presented as real-vehicle limits.
  return InterferenceLimits(
    min_samples_each=200,
    max_p99_increase_ms=2.0,
    max_max_increase_ms=3.0,
    max_deadline_miss_rate_delta=0.01,
    max_frame_age_gt1_delta=0,
    max_frame_gap_count_delta=0,
  )


def predefined_case(name: str) -> SyntheticCommissioningCase:
  cases = {
    "pass": SyntheticCommissioningCase("pass", "PASS", 36.0, 0.15, 0.35, 0.55),
    "fail_latency": SyntheticCommissioningCase("fail_latency", "FAIL", 36.0, 0.15, 0.35, 4.5),
    "fail_transport": SyntheticCommissioningCase("fail_transport", "FAIL", 36.0, 0.15, 0.35, 0.55, t3_decode_errors=2),
    "fail_gap": SyntheticCommissioningCase("fail_gap", "FAIL", 36.0, 0.15, 0.35, 0.55, t3_frame_gap_every=80),
    "hold_no_policy": SyntheticCommissioningCase("hold_no_policy", "HOLD", 36.0, 0.15, 0.35, 0.55, use_limits=False),
    "hold_samples": SyntheticCommissioningCase("hold_samples", "HOLD", 36.0, 0.15, 0.35, 0.55, samples=40),
  }
  if name not in cases:
    raise KeyError(f"unknown synthetic case: {name}")
  return cases[name]


def _jitter_ms(index: int) -> float:
  # Bounded deterministic pseudo-jitter with no random dependency.
  return 0.35 * math.sin(index * 0.37) + 0.15 * math.sin(index * 0.071)


def generate_stage_rows(
  stage: str,
  samples: int,
  base_ms: float,
  *,
  frame_gap_every: int | None = None,
) -> list[dict]:
  rows: list[dict] = []
  frame_id = 1000
  for i in range(samples):
    if frame_gap_every is not None and i > 0 and i % frame_gap_every == 0:
      frame_id += 2
    else:
      frame_id += 1
    exec_ms = max(0.1, base_ms + _jitter_ms(i))
    rows.append({
      "source": stage,
      "frameId": frame_id,
      "frameIdExtra": frame_id,
      "frameAge": 0,
      "modelExecutionTimeS": exec_ms / 1000.0,
      "big": True,
      "backendLabelSource": "synthetic",
      "usbGpuActive": True,
      "valid": True,
      "desiredCurvature": 0.001,
      "desiredAcceleration": 0.0,
      "shouldStop": False,
      "speedMps": 0.0,
      "standstill": True,
      "selfdriveActive": False,
      "gear": "park",
    })
  return rows


def generate_case(case: SyntheticCommissioningCase) -> dict:
  stages = {
    "T0": generate_stage_rows("T0", case.samples, case.t0_ms),
    "T1": generate_stage_rows("T1", case.samples, case.t0_ms + case.t1_delta_ms),
    "T2": generate_stage_rows("T2", case.samples, case.t0_ms + case.t2_delta_ms),
    "T3": generate_stage_rows(
      "T3",
      case.samples,
      case.t0_ms + case.t3_delta_ms,
      frame_gap_every=case.t3_frame_gap_every,
    ),
  }
  tap_summary = {
    "durationSeconds": 12.0,
    "packetsReceived": case.samples,
    "recordsSaved": case.samples,
    "supersededPackets": 0,
    "decodeErrors": case.t3_decode_errors,
    "saveCoverage": 1.0,
    "frameGapCount": 0,
    "duplicateOrOldFrameTransitions": 0,
    "transportLatencyMs": {
      "samples": case.samples,
      "p50Ms": 0.08,
      "p95Ms": 0.14,
      "p99Ms": 0.18,
      "maxMs": 0.24,
    },
    "synthetic": True,
  }
  return {
    "case": case,
    "stages": stages,
    "tapSummary": tap_summary,
    "limits": demo_limits() if case.use_limits else None,
  }
