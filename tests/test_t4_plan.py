import pytest

from egpu_future.t4_plan import T4PlanConfig, build_t4_plan, plan_to_dict, render_markdown


def test_t4_plan_requires_pass_readiness():
  with pytest.raises(ValueError, match="PASS"):
    build_t4_plan({"status": "HOLD"})


def test_t4_plan_is_bounded_and_control_isolated():
  plan = build_t4_plan({"status": "PASS"}, T4PlanConfig(max_hz=5.0, duration_seconds=90.0))
  data = plan_to_dict(plan)
  assert data["status"] == "READY_TO_EXECUTE_MANUALLY"
  assert data["config"]["max_hz"] == 5.0
  assert data["config"]["control_isolated"] is True
  text = render_markdown(plan)
  assert "PROFILE=1" in text
  assert "control output: prohibited" in text
  assert "Do not combine T4 with YOLO" in text


def test_t4_plan_rejects_unsafe_first_experiment_config():
  with pytest.raises(ValueError):
    build_t4_plan({"status": "PASS"}, T4PlanConfig(max_hz=10.0))
  with pytest.raises(ValueError):
    build_t4_plan({"status": "PASS"}, T4PlanConfig(control_isolated=False))
  with pytest.raises(ValueError):
    build_t4_plan({"status": "PASS"}, T4PlanConfig(profile_enabled=False))
