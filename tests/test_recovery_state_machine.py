from egpu_future.recovery_state_machine import EgpuState, Health, Policy, RecoveryStateMachine


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
  )
  base.update(kw)
  return Health(**base)


def drive_to_warmup(sm):
  sm.update(h())
  for _ in range(sm.policy.stable_power_ticks):
    sm.update(h())
  for _ in range(sm.policy.stable_link_ticks):
    sm.update(h())
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
