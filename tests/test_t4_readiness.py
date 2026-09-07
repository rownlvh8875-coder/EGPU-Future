import pytest

from egpu_future.t4_readiness import ReadinessStatus, T4Policy, evaluate_t4_readiness


def _pass_inputs():
  qualification = {"overallStatus": "PASS"}
  manifest = {
    "status": "COMPLETED_RUNTIME_RESTORED",
    "restore": {"targetFilesClean": True},
    "finalBootId": "boot-b",
  }
  source = {
    "status": "CODE_EQUIVALENT_HEAD_DRIFT",
    "codeCompatible": True,
  }
  return qualification, manifest, source


def test_t4_pass_requires_all_prerequisites():
  q, m, s = _pass_inputs()
  decision = evaluate_t4_readiness(qualification=q, manifest=m, source_compatibility=s)
  assert decision.status == ReadinessStatus.PASS
  assert not decision.reasons


def test_failed_t0_t3_blocks_t4():
  _, m, s = _pass_inputs()
  decision = evaluate_t4_readiness(
    qualification={"overallStatus": "FAIL"}, manifest=m, source_compatibility=s
  )
  assert decision.status == ReadinessStatus.FAIL
  assert "t0_t3_qualification_failed" in decision.reasons


def test_missing_final_reboot_holds_t4():
  q, m, s = _pass_inputs()
  del m["finalBootId"]
  m["status"] = "SOURCE_RESTORED_FINAL_REBOOT_RECOMMENDED"
  decision = evaluate_t4_readiness(qualification=q, manifest=m, source_compatibility=s)
  assert decision.status == ReadinessStatus.HOLD
  assert "final_runtime_restore_not_verified" in decision.reasons
  assert "final_reboot_evidence_missing" in decision.reasons


def test_source_review_required_holds_t4():
  q, m, _ = _pass_inputs()
  decision = evaluate_t4_readiness(
    qualification=q,
    manifest=m,
    source_compatibility={"status": "REVIEW_REQUIRED", "codeCompatible": False},
  )
  assert decision.status == ReadinessStatus.HOLD
  assert "source_review_required" in decision.reasons


def test_bad_first_t4_policy_rejected():
  with pytest.raises(ValueError):
    T4Policy(max_hz=10.0).validate()
  with pytest.raises(ValueError):
    T4Policy(stationary_only=False).validate()
