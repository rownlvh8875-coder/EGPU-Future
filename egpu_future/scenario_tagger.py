from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SceneSample:
  speed_mps: float
  acceleration_mps2: float | None = None
  curvature: float | None = None
  standstill: bool = False
  lead_present: bool | None = None
  lead_distance_m: float | None = None
  lead_rel_speed_mps: float | None = None


def tag_scene(s: SceneSample) -> list[str]:
  tags: list[str] = []

  if s.standstill or s.speed_mps < 0.3:
    tags.append("standstill")
  elif s.speed_mps < 3.0:
    tags.append("creep")

  if s.acceleration_mps2 is not None:
    if s.acceleration_mps2 <= -2.0:
      tags.append("hard_decel")
    elif s.acceleration_mps2 >= 2.0:
      tags.append("hard_accel")

  if s.curvature is not None:
    ac = abs(s.curvature)
    if ac >= 0.015:
      tags.append("sharp_curve")
    elif ac >= 0.007:
      tags.append("curve")

  if s.lead_present is True:
    tags.append("lead_present")
    if s.lead_distance_m is not None and s.lead_distance_m < 15.0:
      tags.append("close_lead")
    if s.lead_rel_speed_mps is not None and s.lead_rel_speed_mps < -5.0:
      tags.append("closing_fast")
  elif s.lead_present is False:
    tags.append("no_lead")

  return tags or ["cruise"]
