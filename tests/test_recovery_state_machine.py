from egpu_future.recovery_state_machine import (
  EgpuState,
  Health,
  Policy,
  RecoveryStateMachine,
  carrot_usbgpu_policy,
  official_chestnut_policy,
)


def h(**kw):
  base = dict(
    chestnut_present=True,
    supply_voltage_mv=12000,
    supply_fault=False,
    usb_ok=True,
    pcie_ok=True,
    telemetry_ok=True,
    gpu_temp_c=60.0,
    memory_temp_c=60.0,
    model_alive=False,
    model_ready=False,
    deadline_ok=True,
    user_enabled=True,
  )
  base.update(kw)
  return Health(**base)


def drive_to_warmup(sm):
  # Discover device, stabilize power/USB, stabilize PCIe, then begin warmup.
  for _ in range(32):
    sm.update(h())
    if sm.state == EgpuState.PCIE_READY:
      break
  assert sm.state == EgpuState.PCIE_READY
  sm.update(h())
  assert sm.state == EgpuState.MODEL_WARMUP


def test_nominal_start_to_active():
  sm = RecoveryStateMachine(Policy(stable_power_ticks=2, stable_link_ticks=2))
  drive_to_warmup(sm)
  sm.update(h(model_alive=True, model_ready=True))
  assert sm.state == EgpuState.ACTIVE


def test_power_loss_forces_fallback():
  sm = RecoveryStateMachine(Policy(stable_power_ticks=1, stable_link_ticks=1))
  drive_to_warmup(sm)
  sm.update(h(model_alive=True, model_ready=True))
  assert sm.state == EgpuState.ACTIVE
  sm.update(h(supply_voltage_mv=0))
  assert sm.state == EgpuState.FALLBACK
  assert sm.last_reason == "power_lost"


def test_thermal_derate_then_hard_fallback():
  sm = RecoveryStateMachine(Policy(stable_power_ticks=1, stable_link_ticks=1))
  drive_to_warmup(sm)
  sm.update(h(model_alive=True, model_ready=True, gpu_temp_c=91.0))
  assert sm.state == EgpuState.DERATED
  sm.update(h(model_alive=True, model_ready=True, gpu_temp_c=101.0))
  assert sm.state == EgpuState.FALLBACK


def test_safe_retry_after_wait():
  p = Policy(stable_power_ticks=1, stable_link_ticks=1, retry_wait_ticks=2)
  sm = RecoveryStateMachine(p)
  drive_to_warmup(sm)
  sm.update(h(model_alive=True, model_ready=True))
  sm.update(h(deadline_ok=False, model_alive=True, model_ready=True))
  assert sm.state == EgpuState.FALLBACK
  sm.update(h())
  assert sm.state == EgpuState.RETRY_WAIT
  sm.update(h())
  sm.update(h())
  assert sm.state == EgpuState.MODEL_WARMUP


def test_intentional_disable_does_not_enter_retry_loop():
  sm = RecoveryStateMachine(Policy(stable_power_ticks=1, stable_link_ticks=1))
  drive_to_warmup(sm)
  sm.update(h(model_alive=True, model_ready=True))
  assert sm.state == EgpuState.ACTIVE
  for _ in range(10):
    sm.update(h(user_enabled=False, model_alive=True, model_ready=True))
    assert sm.state == EgpuState.DISABLED
    assert sm.last_reason == "user_disabled"


def test_reenable_is_explicit_before_hardware_discovery():
  sm = RecoveryStateMachine()
  sm.update(h(user_enabled=False))
  assert sm.state == EgpuState.DISABLED
  sm.update(h(user_enabled=True))
  assert sm.state == EgpuState.DISCONNECTED
  assert sm.last_reason == "user_enabled"
  sm.update(h(user_enabled=True))
  assert sm.state == EgpuState.POWER_WAIT


def test_official_and_carrot_power_profiles_are_distinct():
  official = official_chestnut_policy()
  carrot = carrot_usbgpu_policy()
  assert official.powered_voltage_mv == 5000
  assert carrot.powered_voltage_mv == 8000

  # 7 V is considered powered by the current official Chestnut threshold but
  # not by the current Carrot USB-GPU threshold.
  official_sm = RecoveryStateMachine(official_chestnut_policy(stable_power_ticks=1))
  carrot_sm = RecoveryStateMachine(carrot_usbgpu_policy(stable_power_ticks=1))
  official_sm.update(h(supply_voltage_mv=7000))
  carrot_sm.update(h(supply_voltage_mv=7000))
  assert official_sm.state == EgpuState.POWER_WAIT
  assert carrot_sm.state == EgpuState.POWER_WAIT
  official_sm.update(h(supply_voltage_mv=7000))
  carrot_sm.update(h(supply_voltage_mv=7000))
  assert official_sm.state == EgpuState.USB_READY
  assert carrot_sm.state == EgpuState.POWER_WAIT
