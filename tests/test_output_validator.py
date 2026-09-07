from egpu_future.output_validator import CandidateOutput, ValidatorPolicy, validate_candidate
from egpu_future.shadow_metrics import ActionSample


def candidate(frame_id=100, frame_age=0, execution=0.020, curvature=0.001, accel=0.0, stop=False):
  return CandidateOutput(
    frame_id=frame_id,
    frame_age=frame_age,
    model_execution_time_s=execution,
    action=ActionSample(t=1.0, curvature=curvature, acceleration=accel, should_stop=stop),
  )


def test_clean_candidate_is_valid_for_shadow_analysis():
  result = validate_candidate(candidate(), candidate(curvature=0.0015, accel=0.1))
  assert result.valid_for_shadow_analysis
  assert not result.hard_issues


def test_wrong_frame_is_hard_issue():
  result = validate_candidate(candidate(frame_id=100), candidate(frame_id=101))
  assert not result.valid_for_shadow_analysis
  assert "frame_id_mismatch" in result.hard_issues


def test_stale_or_late_candidate_is_hard_issue():
  policy = ValidatorPolicy(max_model_execution_time_s=0.040, max_frame_age=1)
  result = validate_candidate(candidate(), candidate(frame_age=2, execution=0.060), policy)
  assert "candidate_frame_stale" in result.hard_issues
  assert "candidate_deadline_miss" in result.hard_issues


def test_action_disagreement_is_retained_for_review_not_dropped():
  result = validate_candidate(candidate(curvature=0.001, accel=0.0), candidate(curvature=0.020, accel=-1.5, stop=True))
  assert result.valid_for_shadow_analysis
  assert result.needs_human_review
  assert "action_disagreement" in result.review_issues
  assert "stop_decision_mismatch" in result.review_issues
