#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.interference import compare_latency_stats, latency_stats_ms


def load_jsonl(path: Path) -> list[dict]:
  rows: list[dict] = []
  for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      rows.append(json.loads(line))
    except json.JSONDecodeError as exc:
      raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
  return rows


def main() -> None:
  ap = argparse.ArgumentParser(description="Compare active model latency before/after enabling shadow_modeld")
  ap.add_argument("baseline_jsonl", type=Path, help="active modelV2 action rows with shadow OFF")
  ap.add_argument("shadow_on_jsonl", type=Path, help="active modelV2 action rows with shadow ON")
  ap.add_argument("--deadline-ms", type=float, default=50.0,
                  help="research reporting deadline only; not an official openpilot safety limit")
  ap.add_argument("--all-backends", action="store_true", help="include small/fallback rows; default compares big rows only")
  ap.add_argument("--output", type=Path, default=None)
  args = ap.parse_args()

  require_big = not args.all_backends
  baseline = latency_stats_ms(load_jsonl(args.baseline_jsonl), args.deadline_ms, require_big=require_big)
  shadow_on = latency_stats_ms(load_jsonl(args.shadow_on_jsonl), args.deadline_ms, require_big=require_big)
  report = {
    "scope": "all_backends" if args.all_backends else "big_only",
    "researchDeadlineMs": args.deadline_ms,
    "baseline": baseline,
    "shadowOn": shadow_on,
    "delta": compare_latency_stats(baseline, shadow_on),
    "interpretation": (
      "This report is descriptive. It does not auto-declare GO/STOP because acceptable interference "
      "must be set from measured platform baselines and control-path requirements."
    ),
  }

  text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
  print(text, end="")
  if args.output is not None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
  main()
