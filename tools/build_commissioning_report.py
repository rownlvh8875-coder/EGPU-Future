#!/usr/bin/env python3
"""Build one T0-T3 qualification report from active-model and tap evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.interference import latency_stats_ms
from egpu_future.qualification import build_t0_t3_report, render_markdown, report_to_dict
from egpu_future.stage_gate import InterferenceLimits


def load_jsonl(path: Path | None) -> list[dict] | None:
  if path is None:
    return None
  rows: list[dict] = []
  for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      rows.append(json.loads(line))
    except json.JSONDecodeError as exc:
      raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
  return rows


def load_limits(path: Path | None) -> InterferenceLimits | None:
  if path is None:
    return None
  raw = json.loads(path.read_text(encoding="utf-8"))
  return InterferenceLimits(
    min_samples_each=int(raw["minSamplesEach"]),
    max_p99_increase_ms=float(raw["maxP99IncreaseMs"]),
    max_max_increase_ms=float(raw["maxMaxIncreaseMs"]),
    max_deadline_miss_rate_delta=float(raw["maxDeadlineMissRateDelta"]),
    max_frame_age_gt1_delta=int(raw["maxFrameAgeGt1Delta"]),
    max_frame_gap_count_delta=int(raw["maxFrameGapCountDelta"]),
  )


def stats(path: Path | None, deadline_ms: float, require_big: bool) -> dict | None:
  rows = load_jsonl(path)
  if rows is None:
    return None
  return latency_stats_ms(rows, deadline_ms=deadline_ms, require_big=require_big)


def main() -> int:
  ap = argparse.ArgumentParser(description="Build T0-T3 Carrot eGPU commissioning qualification report")
  ap.add_argument("--t0", type=Path, required=True, help="original active-model baseline action JSONL")
  ap.add_argument("--t1", type=Path, default=None, help="patch installed, tap disabled")
  ap.add_argument("--t2", type=Path, default=None, help="tap enabled, receiver absent")
  ap.add_argument("--t3", type=Path, default=None, help="tap enabled + receiver, no inference")
  ap.add_argument("--t3-tap-summary", type=Path, default=None, help="JSON summary from shadow_tap_receiver_probe.py")
  ap.add_argument("--limits", type=Path, default=None, help="explicit experiment gate policy JSON; missing policy yields HOLD")
  ap.add_argument("--deadline-ms", type=float, default=50.0, help="research reporting deadline, not an official comma safety limit")
  ap.add_argument("--all-backends", action="store_true", help="include fallback/small rows; default selects rows labelled big")
  ap.add_argument("--json-output", type=Path, default=Path("commissioning_qualification.json"))
  ap.add_argument("--md-output", type=Path, default=Path("commissioning_qualification.md"))
  args = ap.parse_args()

  require_big = not args.all_backends
  t0 = stats(args.t0, args.deadline_ms, require_big)
  t1 = stats(args.t1, args.deadline_ms, require_big)
  t2 = stats(args.t2, args.deadline_ms, require_big)
  t3 = stats(args.t3, args.deadline_ms, require_big)
  tap_summary = json.loads(args.t3_tap_summary.read_text(encoding="utf-8")) if args.t3_tap_summary else None

  report = build_t0_t3_report(
    t0=t0,
    t1=t1,
    t2=t2,
    t3=t3,
    limits=load_limits(args.limits),
    t3_tap_probe=tap_summary,
  )
  data = report_to_dict(report)
  data["configuration"] = {
    "researchDeadlineMs": args.deadline_ms,
    "backendScope": "all" if args.all_backends else "big_only",
    "limitsPath": str(args.limits) if args.limits else None,
  }

  args.json_output.parent.mkdir(parents=True, exist_ok=True)
  args.md_output.parent.mkdir(parents=True, exist_ok=True)
  args.json_output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  args.md_output.write_text(render_markdown(report), encoding="utf-8")

  print(json.dumps({
    "overallStatus": report.overall_status.value,
    "json": str(args.json_output),
    "markdown": str(args.md_output),
  }, ensure_ascii=False, indent=2))
  return 0 if report.overall_status.value == "PASS" else 2


if __name__ == "__main__":
  raise SystemExit(main())
