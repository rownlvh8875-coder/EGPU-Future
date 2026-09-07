from egpu_future.temporal_scenarios import TemporalSceneSample, TemporalScenarioTracker


def s(t, *, lead=None, dist=None, rel=None, standstill=False, small_stop=False, big_stop=False):
  return TemporalSceneSample(
    t_s=t,
    speed_mps=0.0 if standstill else 15.0,
    standstill=standstill,
    lead_present=lead,
    lead_distance_m=dist,
    lead_rel_speed_mps=rel,
    small_should_stop=small_stop,
    big_should_stop=big_stop,
  )


def test_lead_acquired_lost_and_cut_in_candidate_heuristic():
  tr = TemporalScenarioTracker()
  assert tr.observe(s(0.0, lead=False)) == []
  tags = tr.observe(s(0.05, lead=True, dist=22.0, rel=-3.0))
  assert "lead_acquired" in tags
  assert "close_lead_acquisition" in tags
  assert "cut_in_candidate_heuristic" in tags
  tags = tr.observe(s(0.10, lead=False))
  assert "lead_lost" in tags


def test_close_lead_and_closing_onsets():
  tr = TemporalScenarioTracker()
  tr.observe(s(0.0, lead=True, dist=20.0, rel=-2.0))
  tags = tr.observe(s(0.5, lead=True, dist=14.0, rel=-6.0))
  assert "close_lead_entry" in tags
  assert "rapid_range_closure" in tags
  assert "closing_fast_onset" in tags


def test_standstill_and_stop_disagreement_transitions():
  tr = TemporalScenarioTracker()
  tr.observe(s(0.0, lead=False, standstill=False, small_stop=False, big_stop=False))
  tags = tr.observe(s(0.05, lead=False, standstill=True, small_stop=False, big_stop=True))
  assert "standstill_entry" in tags
  assert "big_stop_onset" in tags
  assert "stop_disagreement_onset" in tags

  tags = tr.observe(s(0.10, lead=False, standstill=False, small_stop=True, big_stop=True))
  assert "standstill_exit" in tags
  assert "small_stop_onset" in tags
  assert "stop_disagreement_resolved" in tags


def test_first_sample_and_nonchronological_range_do_not_invent_transition_rate():
  tr = TemporalScenarioTracker()
  assert tr.observe(s(1.0, lead=True, dist=30.0, rel=-1.0)) == []
  tags = tr.observe(s(0.9, lead=True, dist=10.0, rel=-2.0))
  assert "rapid_range_closure" not in tags
