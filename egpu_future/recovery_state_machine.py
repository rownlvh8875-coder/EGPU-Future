"""Pure-Python recovery state machine for Chestnut-class eGPU research.

This module is deliberately independent of openpilot so it can be unit-tested
before any integration with modeld/hardwared. It never sends vehicle commands.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class EgpuState(Enum):
  DISCONNECTED = auto()
  POWER_WAIT = auto()
  USB_READY = auto()
  PCIE_READY = auto()
  MODEL_WARMUP = auto()
  ACTIVE = auto()
  DERATED = auto()
  FALLBACK = auto()
  RETRY_WAIT = auto()


@dataclass(frozen=True)
class Health:
  chestnut_present: bool
  supply_voltage_mv: int
  supply_fault: bool
  usb_ok: bool
  pcie_ok: bool
  telemetry_ok: bool
  gpu_temp_c: float
  memory_temp_c: float
  model_alive: bool
  model_ready: bool
  deadline_ok: bool = True


@dataclass
class Policy:
  powered_voltage_mv: int = 5000
  derate_gpu_temp_c: float = 90.0
  derate_memory_temp_c: float = 85.0
  hard_gpu_temp_c: float = 100.0
  hard_memory_temp_c: float = 95.0
  stable_power_ticks: int = 3
  stable_link_ticks: int = 3
  retry_wait_ticks: int = 20
  max_warmup_ticks: int = 120


class RecoveryStateMachine:
  def __init__(self, policy: Policy | None = None):
    self.policy = policy or Policy()
    self.state = EgpuState.DISCONNECTED
    self._power_good = 0
    self._link_good = 0
    self._retry_ticks = 0
    self._warmup_ticks = 0
    self.last_reason = "init"

  def _power_ok(self, h: Health) -> bool:
    return h.chestnut_present and not h.supply_fault and h.supply_voltage_mv >= self.policy.powered_voltage_mv

  def _hard_thermal_fault(self, h: Health) -> bool:
    return h.gpu_temp_c >= self.policy.hard_gpu_temp_c or h.memory_temp_c >= self.policy.hard_memory_temp_c

  def _should_derate(self, h: Health) -> bool:
    return h.gpu_temp_c >= self.policy.derate_gpu_temp_c or h.memory_temp_c >= self.policy.derate_memory_temp_c

  def update(self, h: Health) -> EgpuState:
    p = self.policy

    if not h.chestnut_present:
      self._reset_counters()
      self.state = EgpuState.DISCONNECTED
      self.last_reason = "chestnut_missing"
      return self.state

    power_ok = self._power_ok(h)
    self._power_good = self._power_good + 1 if power_ok else 0

    if not power_ok:
      self._link_good = 0
      self._warmup_ticks = 0
      if self.state in (EgpuState.ACTIVE, EgpuState.DERATED, EgpuState.MODEL_WARMUP, EgpuState.PCIE_READY):
        self.state = EgpuState.FALLBACK
        self.last_reason = "power_lost"
      else:
        self.state = EgpuState.POWER_WAIT
        self.last_reason = "power_unstable"
      return self.state

    if self._hard_thermal_fault(h):
      self.state = EgpuState.FALLBACK
      self.last_reason = "hard_thermal_fault"
      self._retry_ticks = 0
      return self.state

    if self.state == EgpuState.DISCONNECTED:
      self.state = EgpuState.POWER_WAIT
      self.last_reason = "device_seen"
      return self.state

    if self.state == EgpuState.POWER_WAIT:
      if self._power_good >= p.stable_power_ticks:
        self.state = EgpuState.USB_READY if h.usb_ok else EgpuState.POWER_WAIT
        self.last_reason = "power_stable" if h.usb_ok else "waiting_usb"
      return self.state

    if not h.usb_ok:
      self.state = EgpuState.FALLBACK
      self.last_reason = "usb_lost"
      self._retry_ticks = 0
      return self.state

    if self.state == EgpuState.USB_READY:
      if h.pcie_ok:
        self._link_good += 1
        if self._link_good >= p.stable_link_ticks:
          self.state = EgpuState.PCIE_READY
          self.last_reason = "pcie_stable"
      else:
        self._link_good = 0
        self.last_reason = "waiting_pcie"
      return self.state

    if not h.pcie_ok:
      self.state = EgpuState.FALLBACK
      self.last_reason = "pcie_lost"
      self._retry_ticks = 0
      return self.state

    if self.state == EgpuState.PCIE_READY:
      self.state = EgpuState.MODEL_WARMUP
      self._warmup_ticks = 0
      self.last_reason = "begin_model_warmup"
      return self.state

    if self.state == EgpuState.MODEL_WARMUP:
      self._warmup_ticks += 1
      if h.model_ready and h.model_alive and h.telemetry_ok and h.deadline_ok:
        self.state = EgpuState.DERATED if self._should_derate(h) else EgpuState.ACTIVE
        self.last_reason = "model_active"
      elif self._warmup_ticks >= p.max_warmup_ticks:
        self.state = EgpuState.FALLBACK
        self.last_reason = "warmup_timeout"
        self._retry_ticks = 0
      return self.state

    if self.state in (EgpuState.ACTIVE, EgpuState.DERATED):
      if not h.telemetry_ok:
        self.state = EgpuState.FALLBACK
        self.last_reason = "telemetry_invalid"
      elif not h.model_alive or not h.deadline_ok:
        self.state = EgpuState.FALLBACK
        self.last_reason = "model_or_deadline_failure"
      elif self._should_derate(h):
        self.state = EgpuState.DERATED
        self.last_reason = "thermal_derate"
      else:
        self.state = EgpuState.ACTIVE
        self.last_reason = "healthy"
      return self.state

    if self.state == EgpuState.FALLBACK:
      self.state = EgpuState.RETRY_WAIT
      self._retry_ticks = 0
      self.last_reason = "fallback_latched"
      return self.state

    if self.state == EgpuState.RETRY_WAIT:
      self._retry_ticks += 1
      if self._retry_ticks >= p.retry_wait_ticks and power_ok and h.usb_ok and h.pcie_ok:
        self.state = EgpuState.MODEL_WARMUP
        self._warmup_ticks = 0
        self.last_reason = "safe_retry"
      return self.state

    return self.state

  def _reset_counters(self):
    self._power_good = 0
    self._link_good = 0
    self._retry_ticks = 0
    self._warmup_ticks = 0
