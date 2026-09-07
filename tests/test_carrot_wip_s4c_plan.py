import pytest

from integrations.carrot_wip_integrated.runtime.s4c_plan import S4CConfig, build_s4c_plan, plan_to_dict


def s4b_pass():
  return {
    "stage": "S4B",
    "status": "PASS",
    "controlAuthorization": False,
    "qualityComparisonAuthorization": False,
  }


def test_s4c_plan_requires_s4b_pass_and_remains_control_isolated():
  plan = build_s4c_plan(s4b_qualification=s4b_pass(), source_compatible=True)
  assert plan.status == "PLAN_READY_MANUAL_PARKED_ONLY"
  assert plan.config.hz == 20.0
  assert plan.control_authorization is False
  payload = plan_to_dict(plan)
  assert payload["controlAuthorization"] is False
  assert payload["publicRoadAuthorization"] is False
  assert any("settle" in step or "consecutive" in step for step in payload["steps"])
  assert "no public-road execution" in payload["prohibitions"]


def test_s4c_plan_rejects_s4b_hold_or_fail():
  for status in ("HOLD", "FAIL", ""):
    evidence = s4b_pass(); evidence["status"] = status
    with pytest.raises(ValueError, match="S4B qualification PASS"):
      build_s4c_plan(s4b_qualification=evidence, source_compatible=True)


def test_s4c_plan_requires_current_source_compatibility():
  with pytest.raises(ValueError, match="reviewed-compatible source"):
    build_s4c_plan(s4b_qualification=s4b_pass(), source_compatible=False)


def test_s4c_plan_rejects_unexpected_control_authorization():
  evidence = s4b_pass(); evidence["controlAuthorization"] = True
  with pytest.raises(ValueError, match="unexpected control authorization"):
    build_s4c_plan(s4b_qualification=evidence, source_compatible=True)


def test_s4c_requires_exact_20hz():
  for hz in (5.0, 10.0, 19.9, 20.1):
    with pytest.raises(ValueError, match="exactly 20 Hz"):
      S4CConfig(hz=hz).validate()


def test_s4c_rejects_manager_autostart_and_control_publish():
  with pytest.raises(ValueError, match="manager-autostarted"):
    S4CConfig(manager_autostart=True).validate()
  with pytest.raises(ValueError, match="may not publish"):
    S4CConfig(controls_publish=True).validate()


def test_s4c_requires_stationary_controls_inactive():
  with pytest.raises(ValueError, match="stationary with controls inactive"):
    S4CConfig(stationary_only=False).validate()
  with pytest.raises(ValueError, match="stationary with controls inactive"):
    S4CConfig(controls_inactive_required=False).validate()


def test_s4c_plan_forbids_parallel_optional_qcom_workloads():
  payload = plan_to_dict(build_s4c_plan(s4b_qualification=s4b_pass(), source_compatible=True))
  prohibitions = "\n".join(payload["prohibitions"])
  assert "YOLO" in prohibitions
  assert "RoadSeg" in prohibitions
  assert "hot-swap" in prohibitions
