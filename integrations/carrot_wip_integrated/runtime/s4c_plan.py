"""Plan-only gate for S4C parked 20 Hz temporal comparison.

A plan can be generated only from a PASS S4B qualification. This module does
not run a model or authorize controls.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class S4CConfig:
  hz: float = 20.0
  duration_s: float = 60.0
  settle_frames: int = 40
  manual_start: bool = True
  manager_autostart: bool = False
  stationary_only: bool = True
  controls_inactive_required: bool = True
  controls_publish: bool = False

  def validate(self) -> None:
    if float(self.hz) != 20.0:
      raise ValueError("S4C temporal comparison plan requires exactly 20 Hz")
    if not 0 < float(self.duration_s) <= 300:
      raise ValueError("S4C duration must be >0 and <=300 seconds")
    if self.settle_frames < 1:
      raise ValueError("settle_frames must be >=1")
    if not self.manual_start or self.manager_autostart:
      raise ValueError("S4C must remain manual-start and not manager-autostarted")
    if not self.stationary_only or not self.controls_inactive_required:
      raise ValueError("S4C must stay stationary with controls inactive")
    if self.controls_publish:
      raise ValueError("S4C shadow may not publish control/modelV2 output")


@dataclass(frozen=True)
class S4CPlan:
  status: str
  config: S4CConfig
  prerequisites: tuple[str, ...]
  steps: tuple[str, ...]
  prohibitions: tuple[str, ...]
  control_authorization: bool = False


def build_s4c_plan(*, s4b_qualification: dict[str, Any], source_compatible: bool, config: S4CConfig | None = None) -> S4CPlan:
  cfg = config or S4CConfig(); cfg.validate()
  if str(s4b_qualification.get("status", "")) != "PASS":
    raise ValueError("S4C plan requires S4B qualification PASS")
  if not source_compatible:
    raise ValueError("S4C plan requires current reviewed-compatible source")
  if bool(s4b_qualification.get("controlAuthorization", False)):
    raise ValueError("unexpected control authorization in S4B evidence")

  prerequisites = (
    "S4B qualification PASS with explicit interference limits",
    "source compatibility PASS immediately before experiment",
    "vehicle parked/standstill and lat/long controls inactive",
    "active eGPU model stable with no fallback",
    "S2 telemetry healthy and timestamped",
  )
  steps = (
    "freeze S4B evidence and current source hashes",
    "record same-session active eGPU baseline with shadow off",
    "start manual QCOM shadow at exact upstream 20 Hz cadence; do not add a second 50 ms limiter",
    f"discard behavioral comparisons until at least {cfg.settle_frames} consecutive frameIds establish temporal continuity",
    "pair active/shadow by exact frameId and validate freshness/nonfinite/timing",
    "record disagreement events only for continuity-eligible frames",
    "measure active latency/interference during the same interval",
    "stop shadow, record post baseline, restore source, reboot, verify hashes",
  )
  prohibitions = (
    "no public-road execution",
    "no modelV2/controls publication from shadow",
    "no manager autostart",
    "no YOLO/RoadSeg/other QCOM workload simultaneously",
    "no automatic model hot-swap",
    "no steering/braking authority changes",
  )
  return S4CPlan("PLAN_READY_MANUAL_PARKED_ONLY", cfg, prerequisites, steps, prohibitions, False)


def plan_to_dict(plan: S4CPlan) -> dict[str, Any]:
  return {
    "stage": "S4C",
    "status": plan.status,
    "config": asdict(plan.config),
    "prerequisites": list(plan.prerequisites),
    "steps": list(plan.steps),
    "prohibitions": list(plan.prohibitions),
    "controlAuthorization": False,
    "publicRoadAuthorization": False,
  }
