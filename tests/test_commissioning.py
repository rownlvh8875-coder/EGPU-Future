from egpu_future.commissioning import FrameContinuityCounter, StationarySnapshot, evaluate_stationary_guard


def test_stationary_guard_passes_parked_inactive():
  ok, reasons = evaluate_stationary_guard(StationarySnapshot(0.0, True, False, "park"))
  assert ok is True
  assert reasons == ()


def test_stationary_guard_rejects_motion_active_and_drive():
  ok, reasons = evaluate_stationary_guard(StationarySnapshot(0.5, False, True, "drive"))
  assert ok is False
  assert "vehicle_speed_nonzero" in reasons
  assert "carstate_not_standstill" in reasons
  assert "selfdrive_active" in reasons
  assert "gear_not_park" in reasons


def test_stationary_guard_allows_unknown_gear_if_other_conditions_safe():
  ok, reasons = evaluate_stationary_guard(StationarySnapshot(0.0, True, False, None))
  assert ok is True
  assert reasons == ()


def test_frame_continuity_counter():
  c = FrameContinuityCounter()
  for frame_id in (10, 11, 14, 14, 15):
    c.observe(frame_id)
  s = c.summary()
  assert s["samples"] == 5
  assert s["gapFrames"] == 2
  assert s["duplicateOrOldTransitions"] == 1
  assert s["lastFrameId"] == 15
