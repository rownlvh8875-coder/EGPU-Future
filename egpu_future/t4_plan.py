"""Generate a non-executing parked T4 experiment plan from PASS readiness evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class T4PlanConfig:
  max_hz: float = 5.0
  duration_seconds: float = 60.0
  profile_enabled: bool = True
  stationary_only: bool = True
  selfdrive_inactive_required: bool = True
  manual_start: bool = True
  control_isolated: bool = True

  def validate(self) -> None:
    if self.max_hz <= 0 or self.max_hz > 5.0:
      raise ValueError("first parked T4 must use >0 and <=5 Hz")
    if self.duration_seconds <= 0:
      raise ValueError("duration_seconds must be >0")
    if not self.profile_enabled:
      raise ValueError("first parked T4 requires PROFILE=1")
    if not self.stationary_only or not self.selfdrive_inactive_required:
      raise ValueError("first parked T4 must remain stationary with selfdrive inactive")
    if not self.manual_start or not self.control_isolated:
      raise ValueError("first parked T4 must be manual-start and control-isolated")


@dataclass(frozen=True)
class T4ExperimentStep:
  id: str
  title: str
  action: str
  expected_evidence: tuple[str, ...]
  stop_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class T4ExperimentPlan:
  status: str
  config: T4PlanConfig
  steps: tuple[T4ExperimentStep, ...]
  notes: tuple[str, ...]


def build_t4_plan(readiness: dict, config: T4PlanConfig | None = None) -> T4ExperimentPlan:
  config = config or T4PlanConfig()
  config.validate()
  if str(readiness.get("status", "")) != "PASS":
    raise ValueError("T4 experiment plan requires a PASS t4_readiness.json")

  steps = (
    T4ExperimentStep(
      "P0",
      "Freeze evidence",
      "Archive T0-T3 qualification, finalized manifest, source compatibility, and T4 readiness JSON before modifying source again.",
      ("immutable input-evidence copy", "current source HEAD/blob snapshot"),
    ),
    T4ExperimentStep(
      "P1",
      "Re-apply metadata tap",
      "Apply only the reviewed EGPU-Future Carrot metadata tap. Do not add shadow inference to manager/process_config.",
      ("patch dry-run diff", "control-path byte-for-byte restore verification", "patched source hashes"),
      ("critical source blob mismatch", "dirty target files", "patch verification failure"),
    ),
    T4ExperimentStep(
      "P2",
      "Full reboot boundary",
      "Perform a full device reboot so manager imports the patched modeld source; verify boot_id changed and eGPU returns active while parked.",
      ("new boot_id", "UsbGpuActive=true", "modelV2 healthy", "stationary guard PASS"),
      ("vehicle moves", "selfdrive active", "eGPU inactive", "modelV2 unhealthy"),
    ),
    T4ExperimentStep(
      "P3",
      "Record active baseline",
      "With tap disabled and no shadow process, record a same-session active-big baseline immediately before T4 load.",
      ("active_before.jsonl", "temperature/power snapshot", "frame continuity"),
      ("frame gaps above experiment policy", "eGPU fallback", "thermal/power fault"),
    ),
    T4ExperimentStep(
      "P4",
      "Run parked shadow at bounded rate",
      f"Enable metadata tap and manually run control-isolated shadow_modeld at {config.max_hz:g} Hz for {config.duration_seconds:g}s with PROFILE=1. Publish JSONL only; never modelV2/controls.",
      ("shadow.jsonl", "trusted tinygrad profile.pkl", "active_during.jsonl", "tap summary"),
      ("vehicle moves", "selfdrive active", "active model deadline/tail anomaly", "QCOM memory/thermal anomaly", "shadow exception", "eGPU fallback"),
    ),
    T4ExperimentStep(
      "P5",
      "Post-load active baseline",
      "Stop shadow cleanly, disable tap, then record active-big latency again in the same thermal/session context.",
      ("active_after.jsonl", "post-load temperature/power snapshot"),
    ),
    T4ExperimentStep(
      "P6",
      "Analyze interference and QCOM kernels",
      "Compare before/during/after active latency and correlate shadow model-call windows with host-aligned QCOM HCQ hardware kernel ranges.",
      ("active interference report", "shadow kernel frame map", "QCOM kernel summary", "skip/coverage summary"),
    ),
    T4ExperimentStep(
      "P7",
      "Restore source",
      "Disable tap, restore original modeld.py byte-for-byte, remove tap runtime, then perform a final reboot and source compatibility check.",
      ("restored Git blob", "clean target files", "final boot_id", "source compatibility JSON"),
    ),
  )

  notes = (
    "T4 is a parked/offroad load experiment only; PASS does not authorize public-road shadow inference.",
    "PROFILE=1 itself may add overhead, so active before/during/after evidence must be interpreted in that experimental context.",
    "Do not combine T4 with YOLO, RoadSeg, compilation, or another QCOM worker; isolate one workload at a time.",
    "Do not infer a safe 20 Hz configuration from a successful 5 Hz experiment.",
  )
  return T4ExperimentPlan("READY_TO_EXECUTE_MANUALLY", config, steps, notes)


def plan_to_dict(plan: T4ExperimentPlan) -> dict:
  return {
    "status": plan.status,
    "config": asdict(plan.config),
    "steps": [asdict(step) for step in plan.steps],
    "notes": list(plan.notes),
  }


def render_markdown(plan: T4ExperimentPlan) -> str:
  lines = [
    "# EGPU-Future T4 Parked 5 Hz Experiment Plan",
    "",
    f"**Plan status: {plan.status}**",
    "",
    f"- max shadow rate: {plan.config.max_hz:g} Hz",
    f"- duration: {plan.config.duration_seconds:g} s",
    "- PROFILE=1: required",
    "- stationary/selfdrive inactive: required",
    "- control output: prohibited",
    "",
  ]
  for step in plan.steps:
    lines += [f"## {step.id} — {step.title}", "", step.action, "", "Evidence:"]
    lines += [f"- {item}" for item in step.expected_evidence]
    if step.stop_conditions:
      lines += ["", "Stop conditions:"] + [f"- {item}" for item in step.stop_conditions]
    lines.append("")
  lines += ["## Notes", ""] + [f"- {n}" for n in plan.notes]
  return "\n".join(lines) + "\n"
