"""Pure admission policy for the first Carrot-WIP integrated live-shadow experiment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class S4BConfig:
  max_hz: float = 5.0
  duration_s: float = 60.0
  manual_start: bool = True
  manager_autostart: bool = False
  controls_publish: bool = False
  require_park: bool = True
  require_standstill: bool = True
  require_controls_inactive: bool = True
  require_readiness_pass: bool = True

  def validate(self) -> None:
    if not 0 < float(self.max_hz) <= 5.0:
      raise ValueError("first S4B experiment must use >0 and <=5 Hz")
    if float(self.duration_s) <= 0:
      raise ValueError("duration_s must be positive")
    if not self.manual_start or self.manager_autostart:
      raise ValueError("S4B must be manual-start and must not be manager-autostarted")
    if self.controls_publish:
      raise ValueError("S4B shadow process may not publish controls/modelV2")
    if not self.require_park or not self.require_standstill or not self.require_controls_inactive:
      raise ValueError("S4B must require park, standstill, and inactive controls")


@dataclass(frozen=True)
class ParkedState:
  v_ego: float
  standstill: bool
  gear: str
  lat_active: bool
  long_active: bool

  @property
  def safe_for_shadow(self) -> bool:
    return bool(self.standstill) and abs(float(self.v_ego)) < 0.01 and str(self.gear).lower() == "park" and not self.lat_active and not self.long_active


@dataclass(frozen=True)
class S4BAdmission:
  allowed: bool
  status: str
  reasons: tuple[str, ...]
  max_hz: float
  control_authorization: bool = False


def evaluate_s4b_admission(*, readiness: dict[str, Any] | None, source_compatible: bool,
                           parked: ParkedState, config: S4BConfig | None = None) -> S4BAdmission:
  cfg = config or S4BConfig()
  cfg.validate()
  reasons: list[str] = []
  if cfg.require_readiness_pass and (readiness is None or str(readiness.get("status", "")) != "PASS"):
    reasons.append("t4_readiness_not_pass")
  if not source_compatible:
    reasons.append("source_not_reviewed_compatible")
  if not parked.safe_for_shadow:
    if not parked.standstill or abs(float(parked.v_ego)) >= 0.01:
      reasons.append("vehicle_not_stationary")
    if str(parked.gear).lower() != "park":
      reasons.append("gear_not_park")
    if parked.lat_active or parked.long_active:
      reasons.append("controls_active")
  allowed = not reasons
  return S4BAdmission(
    allowed=allowed,
    status="READY_FOR_MANUAL_5HZ" if allowed else "HOLD",
    reasons=tuple(dict.fromkeys(reasons)),
    max_hz=float(cfg.max_hz),
    control_authorization=False,
  )
