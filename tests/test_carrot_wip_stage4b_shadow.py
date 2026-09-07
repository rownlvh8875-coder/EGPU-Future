from types import SimpleNamespace

import pytest

from integrations.carrot_wip_integrated.runtime.s4b_commissioning import ParkedState, S4BConfig, evaluate_s4b_admission
from integrations.carrot_wip_integrated.runtime.shadow_tap import IntegratedShadowSnapshot, decode_snapshot, encode_snapshot, normalize_gear


def snapshot(**overrides):
  data = dict(
    frame_id=100,
    frame_id_extra=100,
    state_frame_id=100,
    camera_sof_ns=1_000_000,
    camera_eof_ns=2_000_000,
    active_backend="egpu",
    v_ego=0.0,
    standstill=True,
    gear="park",
    lat_active=False,
    long_active=False,
    main_transform=(1.0,) * 9,
    extra_transform=(1.0,) * 9,
    desire_pulse=(0.0, 1.0),
    traffic_convention=(1.0, 0.0),
    action_t=(0.1, 0.2),
    created_mono_ns=3_000_000,
  )
  data.update(overrides)
  return IntegratedShadowSnapshot(**data)


def test_snapshot_roundtrip_and_stationary_guard():
  src = snapshot()
  assert src.stationary_guard_ok is True
  assert decode_snapshot(encode_snapshot(src)) == src


@pytest.mark.parametrize("changes", [
  {"v_ego": 0.02},
  {"standstill": False},
  {"gear": "drive"},
  {"lat_active": True},
  {"long_active": True},
])
def test_stationary_guard_rejects_motion_or_control(changes):
  assert snapshot(**changes).stationary_guard_ok is False


def test_gear_normalization_accepts_capnp_style_park():
  assert normalize_gear("GearShifter.park") == "park"
  assert normalize_gear("park") == "park"
  assert normalize_gear("GearShifter.drive") == "drive"


def test_protocol_rejects_nonfinite_model_metadata():
  with pytest.raises(ValueError, match="non-finite"):
    snapshot(v_ego=float("nan")).validate()


def test_s4b_ready_only_with_readiness_source_and_parked_state():
  result = evaluate_s4b_admission(
    readiness={"status": "PASS"},
    source_compatible=True,
    parked=ParkedState(0.0, True, "park", False, False),
  )
  assert result.allowed is True
  assert result.status == "READY_FOR_MANUAL_5HZ"
  assert result.control_authorization is False


def test_s4b_holds_without_readiness():
  result = evaluate_s4b_admission(
    readiness={"status": "HOLD"}, source_compatible=True,
    parked=ParkedState(0.0, True, "park", False, False),
  )
  assert result.allowed is False
  assert "t4_readiness_not_pass" in result.reasons


def test_s4b_holds_if_controls_activate_or_vehicle_moves():
  result = evaluate_s4b_admission(
    readiness={"status": "PASS"}, source_compatible=True,
    parked=ParkedState(1.0, False, "drive", True, True),
  )
  assert result.allowed is False
  assert "vehicle_not_stationary" in result.reasons
  assert "gear_not_park" in result.reasons
  assert "controls_active" in result.reasons


def test_s4b_never_allows_above_5hz_or_controls_publish():
  with pytest.raises(ValueError, match="<=5 Hz"):
    S4BConfig(max_hz=5.1).validate()
  with pytest.raises(ValueError, match="may not publish"):
    S4BConfig(controls_publish=True).validate()
  with pytest.raises(ValueError, match="manager-autostarted"):
    S4BConfig(manager_autostart=True).validate()
