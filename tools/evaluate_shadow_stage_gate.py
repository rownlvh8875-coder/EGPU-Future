#!/usr/bin/env python3
"""Evaluate whether measured active-path interference permits the next stage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.interference import latency_stats_ms
from egpu_future.stage_gate import GateStatus, InterferenceLimits, evaluate_interference_gate


def load_jsonl(path: Path) -> list[dict]:
  rows: list[dict] = []
  with path.open(encoding="utf-8") as f:
    for line_no, line in enumerate(f, 1):
      if not line.strip():
        continue
      try:
        rows.append(json.loads(line))
      except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{line_no}: {exc}") from exc
  return rows


def main() -> int:
  ap = argparse.ArgumentParser(description="Policy-driven active-model interference stage gate")
  ap.add_argument("baseline_jsonl", type=Path)
  ap.add_argument("candidate_jsonl", type=Path)
  ap.add_argument("--deadline-ms", type=float, default=50.0,
                  help="analysis deadline only; not an official comma safety threshold")
  ap.add_argument("--include-all-backends", action="store_true",
                  help="do not require rows to be labelled big")
  ap.add_argument("--min-samples", type=int, required=True)
  ap.add_argument("--max-p99-increase-ms", type=float, required=True)
  ap.add_argument("--max-max-increase-ms", type=float, required=True)
  ap.add_argument("--max-deadline-miss-rate-delta", type=float, required=True)
  ap.add_argument("--max-frame-age-gt1-delta", type=int, required=True)
  ap.add_argument("--max-frame-gap-count-delta", type=int, required=True)
  ap.add_argument("--output", type=Path, default=None)
  args = ap.parse_args()

  baseline = latency_stats_ms(load_jsonl(args.baseline_jsonl), args.deadline_ms, require_big=not args.include_all_backends)
  candidate = latency_stats_ms(load_jsonl(args.candidate_jsonl), args.deadline_ms, require_big=not args.include_all_backends)
  limits = InterferenceLimits(
    min_samples_each=args.min_samples,
    max_p99_increase_ms=args.max_p99_increase_ms,
    max_max_increase_ms=args.max_max_increase_ms,
    max_deadline_miss_rate_delta=args.max_deadline_miss_rate_delta,
    max_frame_age_gt1_delta=args.max_frame_age_gt1_delta,
    max_frame_gap_count_delta=args.max_frame_gap_count_delta,
  )
  decision = evaluate_interference_gate(baseline, candidate, limits)
  report = {
    "status": decision.status.value,
    "reasons": decision.reasons,
    "limits": limits.__dict__,
    "baseline": baseline,
    "candidate": candidate,
    "deltas": decision.deltas,
    "checks": decision.checks,
    "note": "Thresholds are experiment-owner policy, not official comma safety limits.",
  }
  text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
  print(text, end="")
  if args.output:
    args.output.write_text(text, encoding="utf-8")

  return {GateStatus.PASS: 0, GateStatus.HOLD: 2, GateStatus.FAIL: 3}[decision.status]


if __name__ == "__main__":
  raise SystemExit(main())
