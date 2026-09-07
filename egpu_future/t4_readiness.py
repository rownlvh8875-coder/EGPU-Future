"""T4 (parked 5 Hz shadow inference) entry gate.

This gate does not certify driving safety.  It only decides whether the project
has enough prerequisite evidence to begin the next parked/offroad experiment.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReadinessStatus(str, Enum):
  PASS = "PASS"
  HOLD = "HOLD"
  FAIL = "FAIL"


@dataclass(frozen=True)
class T4Policy:
  max_hz: float = 5.0
  stationary_only: bool = True
  selfdrive_inactive_required: bool = True
  control_isolated_required: bool = True
  manual_start_required: bool = True
  profile_required: bool = True

  def validate(self) -> None:
    if self.max_hz <= 0 or self.max_hz > 5.0:
      raise ValueError("first T4 policy must use >0 and <=5 Hz")
    if not self.stationary_only:
      raise ValueError("first T4 policy must remain stationary-only")
    if not self.selfdrive_inactive_required:
      raise ValueError("first T4 policy must require selfdrive inactive")
    if not self.control_isolated_required:
      raise ValueError("first T4 policy must remain control-isolated")
    if not self.manual_start_required:
      raise ValueError("first T4 policy must remain manual-start")
    if not self.profile_required:
      raise ValueError("first T4 policy must require PROFILE=1 hardware evidence")


@dataclass(frozen=True)
class T4ReadinessDecision:
  status: ReadinessStatus
  reasons: tuple[str, ...]
  checks: dict[str, bool | str | float | None]


def evaluate_t4_readiness(
  *,
  qualification: dict | None,
  manifest: dict | None,
  source_compatibility: dict | None,
  policy: T4Policy | None = None,
) -> T4ReadinessDecision:
  policy = policy or T4Policy()
  policy.validate()

  reasons: list[str] = []
  checks: dict[str, bool | str | float | None] = {
    "t4MaxHz": policy.max_hz,
    "stationaryOnly": policy.stationary_only,
    "selfdriveInactiveRequired": policy.selfdrive_inactive_required,
    "controlIsolatedRequired": policy.control_isolated_required,
    "manualStartRequired": policy.manual_start_required,
    "profileRequired": policy.profile_required,
  }

  if qualification is None:
    reasons.append("t0_t3_qualification_required")
    checks["qualificationStatus"] = None
  else:
    q_status = str(qualification.get("overallStatus", ""))
    checks["qualificationStatus"] = q_status
    if q_status == "FAIL":
      reasons.append("t0_t3_qualification_failed")
    elif q_status != "PASS":
      reasons.append("t0_t3_qualification_not_passed")

  if manifest is None:
    reasons.append("commissioning_manifest_required")
    checks["manifestStatus"] = None
  else:
    m_status = str(manifest.get("status", ""))
    checks["manifestStatus"] = m_status
    if m_status != "COMPLETED_RUNTIME_RESTORED":
      reasons.append("final_runtime_restore_not_verified")
    restore = manifest.get("restore") or {}
    if restore.get("failed"):
      reasons.append("source_restore_failed")
    if "finalBootId" not in manifest:
      reasons.append("final_reboot_evidence_missing")

  if source_compatibility is None:
    reasons.append("source_compatibility_evidence_required")
    checks["sourceCompatibility"] = None
  else:
    sc_status = str(source_compatibility.get("status", ""))
    code_compatible = bool(source_compatibility.get("codeCompatible", False))
    checks["sourceCompatibility"] = sc_status
    checks["sourceCodeCompatible"] = code_compatible
    if not code_compatible:
      reasons.append("source_review_required")

  if "t0_t3_qualification_failed" in reasons or "source_restore_failed" in reasons:
    status = ReadinessStatus.FAIL
  elif reasons:
    status = ReadinessStatus.HOLD
  else:
    status = ReadinessStatus.PASS

  return T4ReadinessDecision(status, tuple(dict.fromkeys(reasons)), checks)


def decision_to_dict(decision: T4ReadinessDecision) -> dict:
  return {
    "status": decision.status.value,
    "reasons": list(decision.reasons),
    "checks": decision.checks,
    "meaning": (
      "PASS only permits the next parked/offroad 5 Hz shadow experiment. "
      "It is not permission for public-road use or control integration."
    ),
  }
