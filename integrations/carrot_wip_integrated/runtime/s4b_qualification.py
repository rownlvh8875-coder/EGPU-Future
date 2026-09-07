"""Policy-driven qualification for the parked Stage-4B 5 Hz load probe.

No empirical interference thresholds are invented here. Active-path latency
limits must already have been evaluated by the shared interference stage gate.
Missing policy/evidence produces HOLD.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class S4BQualificationPolicy:
  min_probe_runs: int
  max_shadow_errors: int = 0
  max_guard_stops: int = 0
  max_new_usb_link_errors: int = 0
  require_no_active_fallback: bool = True
  require_source_restore: bool = True

  def validate(self) -> None:
    if self.min_probe_runs <= 0:
      raise ValueError("min_probe_runs must be >0")
    for name, value in (
      ("max_shadow_errors", self.max_shadow_errors),
      ("max_guard_stops", self.max_guard_stops),
      ("max_new_usb_link_errors", self.max_new_usb_link_errors),
    ):
      if value < 0:
        raise ValueError(f"{name} must be >=0")


@dataclass(frozen=True)
class S4BQualification:
  status: str
  reasons: tuple[str, ...]
  checks: dict[str, dict[str, Any]]
  control_authorization: bool = False
  quality_comparison_authorization: bool = False


def qualify_s4b(*, interference_gate: dict[str, Any] | None, probe_summary: dict[str, Any] | None,
                hardware_summary: dict[str, Any] | None, active_fallback_observed: bool | None,
                source_restored: bool | None, policy: S4BQualificationPolicy | None) -> S4BQualification:
  if policy is None:
    return S4BQualification("HOLD", ("explicit_s4b_policy_required",), {})
  policy.validate()
  reasons: list[str] = []
  checks: dict[str, dict[str, Any]] = {}

  if interference_gate is None:
    reasons.append("interference_gate_missing")
  else:
    gate_status = str(interference_gate.get("status", ""))
    checks["interferenceGate"] = {"actual": gate_status, "required": "PASS", "pass": gate_status == "PASS"}
    if gate_status == "FAIL": reasons.append("interference_gate_failed")
    elif gate_status != "PASS": reasons.append("interference_gate_not_pass")

  if probe_summary is None:
    reasons.append("probe_summary_missing")
  else:
    runs = int(probe_summary.get("runs", 0) or 0)
    errors = int(probe_summary.get("shadowErrors", probe_summary.get("shadow_errors", 0)) or 0)
    guard = int(probe_summary.get("guardStops", probe_summary.get("guard_stops", 0)) or 0)
    checks["probeRuns"] = {"actual": runs, "minimum": policy.min_probe_runs, "pass": runs >= policy.min_probe_runs}
    checks["shadowErrors"] = {"actual": errors, "maximum": policy.max_shadow_errors, "pass": errors <= policy.max_shadow_errors}
    checks["guardStops"] = {"actual": guard, "maximum": policy.max_guard_stops, "pass": guard <= policy.max_guard_stops}
    if runs < policy.min_probe_runs: reasons.append("insufficient_probe_runs")
    if errors > policy.max_shadow_errors: reasons.append("shadow_errors_exceeded")
    if guard > policy.max_guard_stops: reasons.append("guard_stops_exceeded")

  if hardware_summary is None:
    reasons.append("hardware_summary_missing")
  else:
    new_link_errors = int(hardware_summary.get("newUsbLinkErrors", 0) or 0)
    supply_faults = int(hardware_summary.get("supplyFaultSamples", 0) or 0)
    checks["newUsbLinkErrors"] = {"actual": new_link_errors, "maximum": policy.max_new_usb_link_errors,
                                  "pass": new_link_errors <= policy.max_new_usb_link_errors}
    checks["supplyFaultSamples"] = {"actual": supply_faults, "maximum": 0, "pass": supply_faults == 0}
    if new_link_errors > policy.max_new_usb_link_errors: reasons.append("usb_link_errors_exceeded")
    if supply_faults > 0: reasons.append("supply_fault_observed")

  if active_fallback_observed is None:
    reasons.append("active_fallback_evidence_missing")
  elif policy.require_no_active_fallback and active_fallback_observed:
    reasons.append("active_egpu_fallback_observed")
  checks["activeFallback"] = {"actual": active_fallback_observed, "required": False,
                               "pass": active_fallback_observed is False if policy.require_no_active_fallback else True}

  if source_restored is None:
    reasons.append("source_restore_evidence_missing")
  elif policy.require_source_restore and not source_restored:
    reasons.append("source_not_restored")
  checks["sourceRestored"] = {"actual": source_restored, "required": True,
                               "pass": source_restored is True if policy.require_source_restore else True}

  # Missing/incomplete evidence is HOLD. Explicit exceeded/failure conditions are FAIL.
  fail_tokens = {
    "interference_gate_failed", "shadow_errors_exceeded", "guard_stops_exceeded", "usb_link_errors_exceeded",
    "supply_fault_observed", "active_egpu_fallback_observed", "source_not_restored",
  }
  status = "FAIL" if any(r in fail_tokens for r in reasons) else ("HOLD" if reasons else "PASS")
  return S4BQualification(status, tuple(dict.fromkeys(reasons)), checks, False, False)


def qualification_to_dict(result: S4BQualification) -> dict[str, Any]:
  return {
    "stage": "S4B",
    "status": result.status,
    "reasons": list(result.reasons),
    "checks": result.checks,
    "controlAuthorization": False,
    "qualityComparisonAuthorization": False,
    "nextIfPass": "S4C_PARKED_20HZ_PLAN_ONLY",
  }
