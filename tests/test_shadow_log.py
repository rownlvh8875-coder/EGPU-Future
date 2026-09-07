from egpu_future.shadow_log import normalize_shadow_output


def row(eligible=True):
  return {
    "type": "shadow_output",
    "frameId": 123,
    "stateFrameId": 124,
    "frameAge": 1,
    "cameraTimestampEofNs": 2_000_000_000,
    "shadowBackend": "small",
    "comparisonEligible": eligible,
    "continuityStreak": 50,
    "vEgo": 11.5,
    "action": {
      "desiredCurvature": 0.001,
      "desiredAcceleration": -0.2,
      "shouldStop": False,
    },
    "timing": {
      "model_call_total_ms": 31.0,
      "capture_to_done_ms": 42.0,
    },
  }


def test_normalize_eligible_shadow_output():
  n = normalize_shadow_output(row())
  assert n is not None
  assert n["frameId"] == 123
  assert n["frameAge"] == 1
  assert n["modelExecutionTimeS"] == 0.031
  assert n["desiredCurvature"] == 0.001
  assert n["desiredAcceleration"] == -0.2
  assert n["big"] is False
  assert n["shadowOnly"] is True
  assert n["logMonoTimeS"] == 2.0


def test_ineligible_filtered_by_default():
  assert normalize_shadow_output(row(False)) is None
  n = normalize_shadow_output(row(False), eligible_only=False)
  assert n is not None
  assert n["comparisonEligible"] is False


def test_non_output_event_filtered():
  assert normalize_shadow_output({"type": "startup"}) is None
