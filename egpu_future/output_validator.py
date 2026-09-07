"""Research validator for candidate eGPU model outputs.

This is intentionally *not* a vehicle safety gate and never sends commands.
It exists to reject obviously stale/late/invalid shadow outputs before they are
used for comparison, evaluation, or any later control-integration research.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from egpu_future.shadow_metrics import ActionSample, Disagreement, Thresholds, compare_actions


@dataclass(frozen=True)
class CandidateOutput:
  frame_id: int
  frame_age: int
  model_execution_time_s: float
  action: ActionSample


@dataclass(frozen=True)
class ValidatorPolicy:
  # 45 ms is an EGPU-Future research starting point for a nominal 50 ms model
  # period, not an official comma safety threshold. It must be replaced by
  # measured end-to-end deadline budgets before any control-path experiment.
  max_model_execution_time_s: float = 0.045
  max_frame_age: int = 1
  action_thresholds: Thresholds = field(default_factory=Thresholds)


@dataclass(frozen=True)
class ValidationResult:
  hard_issues: tuple[str, ...]
  review_issues: tuple[str, ...]
  disagreement: Disagreement

  @property
  def valid_for_shadow_analysis(self) -> bool:
    return not self.hard_issues

  @property
  def needs_human_review(self) -> bool:
    return bool(self.review_issues) or self.disagreement.significant


def validate_candidate(reference: CandidateOutput, candidate: CandidateOutput,
                       policy: ValidatorPolicy | None = None) -> ValidationResult:
  """Compare a candidate eGPU output with a reference/on-device output.

  Hard issues reject the candidate from deterministic shadow analysis because
  the comparison itself is unreliable (wrong frame, stale frame, late result,
  non-finite action). Action disagreement is retained as a review signal rather
  than being silently discarded; those events are exactly what the project
  wants to mine.
  """
  p = policy or ValidatorPolicy()
  hard: list[str] = []
  review: list[str] = []

  if reference.frame_id <= 0 or candidate.frame_id <= 0:
    hard.append("missing_frame_id")
  elif reference.frame_id != candidate.frame_id:
    hard.append("frame_id_mismatch")

  if candidate.frame_age < 0 or candidate.frame_age > p.max_frame_age:
    hard.append("candidate_frame_stale")

  if not isfinite(candidate.model_execution_time_s) or candidate.model_execution_time_s < 0:
    hard.append("invalid_execution_time")
  elif candidate.model_execution_time_s > p.max_model_execution_time_s:
    hard.append("candidate_deadline_miss")

  action_values = (
    candidate.action.curvature,
    candidate.action.acceleration,
    reference.action.curvature,
    reference.action.acceleration,
  )
  if not all(isfinite(v) for v in action_values):
    hard.append("nonfinite_action")

  disagreement = compare_actions(reference.action, candidate.action, p.action_thresholds)
  if disagreement.significant:
    review.append("action_disagreement")
  if disagreement.stop_mismatch:
    review.append("stop_decision_mismatch")

  return ValidationResult(tuple(dict.fromkeys(hard)), tuple(dict.fromkeys(review)), disagreement)
