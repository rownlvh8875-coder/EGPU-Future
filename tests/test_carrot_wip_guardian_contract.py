from integrations.carrot_wip_integrated.runtime.guardian_contract import (
  ActionSnapshot,
  GuardianPolicy,
  assess_guardian,
  assessment_to_dict,
)


def snap(*, frame=100, age=0, ms=35.0, curv=0.001, accel=0.1, stop=False, backend="egpu", t=10.0):
  return ActionSnapshot(frame, age, ms, curv, accel, stop, backend, t)


def test_nominal_evidence_never_authorizes_control():
  result = assess_guardian(
    active=snap(backend="egpu"),
    shadow=snap(backend="qcom", curv=0.0011, accel=0.12),
    hardware={"valid": True, "timestampMonoS": 9.5, "supplyFault": False},
  )
  assert result.evidence_eligible is True
  assert result.analysis_status == "OBSERVE"
  assert result.control_authorization is False
  assert result.shadow_publish_to_controls is False
  payload = assessment_to_dict(result)
  assert payload["controlAuthorization"] is False
  assert payload["shadowPublishToControls"] is False


def test_frame_mismatch_is_hard_hold():
  result = assess_guardian(
    active=snap(frame=10),
    shadow=snap(frame=11, backend="qcom"),
    hardware={"valid": True, "timestampMonoS": 9.5},
  )
  assert "frame_mismatch" in result.hard_issues
  assert result.evidence_eligible is False
  assert result.analysis_status == "HOLD"
  assert result.frame_id is None


def test_stale_and_execution_policy_are_hard_issues():
  policy = GuardianPolicy(max_frame_age=1, max_execution_ms=45.0)
  result = assess_guardian(
    active=snap(age=2, ms=50),
    shadow=snap(age=3, ms=55, backend="qcom"),
    hardware={"valid": True, "timestampMonoS": 9.9},
    policy=policy,
  )
  assert "active_frame_stale" in result.hard_issues
  assert "shadow_frame_stale" in result.hard_issues
  assert "active_execution_over_policy" in result.hard_issues
  assert "shadow_execution_over_policy" in result.hard_issues


def test_disagreement_is_review_not_control_switch():
  result = assess_guardian(
    active=snap(curv=0.001, accel=0.0, stop=False),
    shadow=snap(curv=0.010, accel=-1.0, stop=True, backend="qcom"),
    hardware={"valid": True, "timestampMonoS": 9.9},
  )
  assert result.hard_issues == ()
  assert "curvature_disagreement" in result.review_issues
  assert "acceleration_disagreement" in result.review_issues
  assert "stop_decision_mismatch" in result.review_issues
  assert result.analysis_status == "REVIEW"
  assert result.control_authorization is False


def test_supply_fault_is_hard_hold():
  result = assess_guardian(
    active=snap(),
    shadow=snap(backend="qcom"),
    hardware={"valid": True, "timestampMonoS": 9.9, "supplyFault": True},
  )
  assert "egpu_supply_fault" in result.hard_issues
  assert result.analysis_status == "HOLD"


def test_missing_or_invalid_hardware_is_review_only_by_default():
  missing = assess_guardian(active=snap(), shadow=snap(backend="qcom"), hardware=None)
  assert "hardware_evidence_missing" in missing.review_issues
  assert missing.evidence_eligible is True

  invalid = assess_guardian(
    active=snap(), shadow=snap(backend="qcom"),
    hardware={"valid": False, "timestampMonoS": 9.9},
  )
  assert "hardware_telemetry_invalid" in invalid.review_issues
  assert invalid.evidence_eligible is True


def test_stale_hardware_is_hard_hold_when_timestamps_available():
  result = assess_guardian(
    active=snap(t=20.0),
    shadow=snap(backend="qcom", t=20.0),
    hardware={"valid": True, "timestampMonoS": 10.0},
    policy=GuardianPolicy(max_hardware_age_s=5.0),
  )
  assert "hardware_evidence_stale" in result.hard_issues


def test_same_backend_is_marked_for_review():
  result = assess_guardian(
    active=snap(backend="qcom"),
    shadow=snap(backend="qcom"),
    hardware={"valid": True, "timestampMonoS": 9.9},
  )
  assert "same_backend_comparison" in result.review_issues
