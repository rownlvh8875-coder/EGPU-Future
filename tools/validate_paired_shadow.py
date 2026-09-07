#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.output_validator import CandidateOutput, ValidatorPolicy, validate_candidate
from egpu_future.shadow_metrics import ActionSample, Thresholds


def candidate(row: dict) -> CandidateOutput:
  return CandidateOutput(
    frame_id=int(row.get("frameId", 0) or 0),
    frame_age=int(row.get("frameAge", 0) or 0),
    model_execution_time_s=float(row.get("modelExecutionTimeS", 0.0) or 0.0),
    action=ActionSample(
      t=float(row.get("logMonoTimeS", row.get("t", 0.0)) or 0.0),
      curvature=float(row["desiredCurvature"]),
      acceleration=float(row["desiredAcceleration"]),
      should_stop=bool(row.get("shouldStop", False)),
      speed_mps=float(row["speedMps"]) if row.get("speedMps") is not None else None,
    ),
  )


def main() -> None:
  ap = argparse.ArgumentParser(description="Validate paired small/big shadow outputs before analysis")
  ap.add_argument("paired_jsonl", type=Path)
  ap.add_argument("--max-execution-ms", type=float, default=45.0)
  ap.add_argument("--max-frame-age", type=int, default=1)
  ap.add_argument("--curvature-abs", type=float, default=0.003)
  ap.add_argument("--curvature-rel", type=float, default=0.25)
  ap.add_argument("--accel-abs", type=float, default=0.50)
  ap.add_argument("--issues", type=Path, default=Path("shadow_validation_issues.jsonl"))
  args = ap.parse_args()

  policy = ValidatorPolicy(
    max_model_execution_time_s=args.max_execution_ms / 1000.0,
    max_frame_age=args.max_frame_age,
    action_thresholds=Thresholds(
      curvature_abs=args.curvature_abs,
      curvature_rel=args.curvature_rel,
      accel_abs=args.accel_abs,
    ),
  )

  total = valid = hard_rejected = review = 0
  issue_counts: dict[str, int] = {}
  args.issues.parent.mkdir(parents=True, exist_ok=True)
  with args.issues.open("w", encoding="utf-8") as out:
    for line in args.paired_jsonl.read_text(encoding="utf-8").splitlines():
      if not line.strip():
        continue
      total += 1
      pair = json.loads(line)
      small = candidate(pair["small"])
      big = candidate(pair["big"])
      result = validate_candidate(small, big, policy)
      if result.valid_for_shadow_analysis:
        valid += 1
      else:
        hard_rejected += 1
      if result.needs_human_review:
        review += 1
      for issue in (*result.hard_issues, *result.review_issues):
        issue_counts[issue] = issue_counts.get(issue, 0) + 1
      if result.hard_issues or result.review_issues:
        out.write(json.dumps({
          "frameId": pair.get("frameId"),
          "pairMethod": pair.get("pairMethod"),
          "hardIssues": result.hard_issues,
          "reviewIssues": result.review_issues,
          "disagreement": {
            "curvatureAbs": result.disagreement.curvature_abs,
            "curvatureRel": result.disagreement.curvature_rel,
            "accelAbs": result.disagreement.accel_abs,
            "stopMismatch": result.disagreement.stop_mismatch,
            "score": result.disagreement.score,
          },
        }, ensure_ascii=False) + "\n")

  summary = {
    "total": total,
    "validForShadowAnalysis": valid,
    "hardRejected": hard_rejected,
    "needsReview": review,
    "issueCounts": issue_counts,
    "maxExecutionMs": args.max_execution_ms,
    "maxFrameAge": args.max_frame_age,
  }
  print(json.dumps(summary, ensure_ascii=False, indent=2))
  print(f"issues={args.issues}")


if __name__ == "__main__":
  main()
