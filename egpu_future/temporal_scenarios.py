"""Temporal scenario tags for replay/shadow hard-case mining.

These tags are observational heuristics. In particular, `cut_in_candidate_heuristic`
is not cut-in ground truth; it only marks a close, closing lead acquisition that
should be reviewed against video/raw radar/lane geometry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalSceneSample:
  t_s: float
  speed_mps: float
  standstill: bool
  lead_present: bool | None = None
  lead_distance_m: float | None = None
  lead_rel_speed_mps: float | None = None
  small_should_stop: bool | None = None
  big_should_stop: bool | None = None


class TemporalScenarioTracker:
  def __init__(self):
    self.prev: TemporalSceneSample | None = None

  def reset(self) -> None:
    self.prev = None

  def observe(self, cur: TemporalSceneSample) -> list[str]:
    tags: list[str] = []
    prev = self.prev
    self.prev = cur
    if prev is None:
      return tags

    dt = cur.t_s - prev.t_s
    chronological = dt > 0

    if prev.lead_present is False and cur.lead_present is True:
      tags.append("lead_acquired")
      if cur.lead_distance_m is not None and cur.lead_distance_m < 30.0:
        tags.append("close_lead_acquisition")
      if (
        cur.lead_distance_m is not None and cur.lead_distance_m < 30.0
        and cur.lead_rel_speed_mps is not None and cur.lead_rel_speed_mps < -1.0
      ):
        tags.append("cut_in_candidate_heuristic")

    if prev.lead_present is True and cur.lead_present is False:
      tags.append("lead_lost")

    if cur.lead_present is True and prev.lead_present is True:
      if (
        prev.lead_distance_m is not None and cur.lead_distance_m is not None
        and prev.lead_distance_m >= 15.0 > cur.lead_distance_m
      ):
        tags.append("close_lead_entry")

      if chronological and prev.lead_distance_m is not None and cur.lead_distance_m is not None and dt <= 1.0:
        range_rate = (cur.lead_distance_m - prev.lead_distance_m) / dt
        if range_rate <= -5.0:
          tags.append("rapid_range_closure")

      if (
        prev.lead_rel_speed_mps is not None and cur.lead_rel_speed_mps is not None
        and prev.lead_rel_speed_mps >= -5.0 > cur.lead_rel_speed_mps
      ):
        tags.append("closing_fast_onset")

    if not prev.standstill and cur.standstill:
      tags.append("standstill_entry")
    elif prev.standstill and not cur.standstill:
      tags.append("standstill_exit")

    if prev.small_should_stop is False and cur.small_should_stop is True:
      tags.append("small_stop_onset")
    if prev.big_should_stop is False and cur.big_should_stop is True:
      tags.append("big_stop_onset")

    prev_mismatch = (
      prev.small_should_stop is not None
      and prev.big_should_stop is not None
      and prev.small_should_stop != prev.big_should_stop
    )
    cur_mismatch = (
      cur.small_should_stop is not None
      and cur.big_should_stop is not None
      and cur.small_should_stop != cur.big_should_stop
    )
    if not prev_mismatch and cur_mismatch:
      tags.append("stop_disagreement_onset")
    elif prev_mismatch and not cur_mismatch:
      tags.append("stop_disagreement_resolved")

    return tags
