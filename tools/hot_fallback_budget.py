#!/usr/bin/env python3
"""Evaluate whether same-frame big->small hot fallback fits a model deadline.

Input is paired_shadow.jsonl from pair_shadow_runs.py. This tool is offline and
never changes vehicle control. The conservative default assumes the big-model
failure is only detected after its recorded modelExecutionTimeS has elapsed,
then adds the small-model execution time and a fixed handoff overhead.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def percentile(values: list[float], q: float) -> float:
  if not values:
    return math.nan
  xs = sorted(values)
  if len(xs) == 1:
    return xs[0]
  pos = (len(xs) - 1) * q
  lo = int(math.floor(pos))
  hi = int(math.ceil(pos))
  if lo == hi:
    return xs[lo]
  w = pos - lo
  return xs[lo] * (1.0 - w) + xs[hi] * w


def execution_time(row: dict) -> float | None:
  value = row.get("modelExecutionTimeS")
  if value is None:
    return None
  try:
    value = float(value)
  except (TypeError, ValueError):
    return None
  if not math.isfinite(value) or value < 0:
    return None
  return value


def main() -> None:
  ap = argparse.ArgumentParser(description="Evaluate same-frame eGPU->small-model hot fallback deadline feasibility")
  ap.add_argument("paired_jsonl", type=Path)
  ap.add_argument("--budget-ms", type=float, default=50.0,
                  help="research model-cycle budget; 50 ms corresponds to nominal 20 Hz")
  ap.add_argument("--handoff-overhead-ms", type=float, default=2.0,
                  help="assumed software handoff/scheduling overhead; replace with measured value")
  ap.add_argument("--primary-failure-fraction", type=float, default=1.0,
                  help="fraction of big execution elapsed before failure is detected; 1.0 is conservative")
  ap.add_argument("--events", type=Path, default=Path("hot_fallback_deadline_misses.jsonl"))
  args = ap.parse_args()

  if not 0.0 <= args.primary_failure_fraction <= 1.0:
    raise SystemExit("--primary-failure-fraction must be between 0 and 1")

  budget_s = args.budget_ms / 1000.0
  overhead_s = args.handoff_overhead_ms / 1000.0
  totals: list[float] = []
  big_times: list[float] = []
  small_times: list[float] = []
  misses = 0
  skipped = 0
  total_rows = 0

  args.events.parent.mkdir(parents=True, exist_ok=True)
  with args.events.open("w", encoding="utf-8") as miss_out:
    for line in args.paired_jsonl.read_text(encoding="utf-8").splitlines():
      if not line.strip():
        continue
      total_rows += 1
      row = json.loads(line)
      big_t = execution_time(row.get("big", {}))
      small_t = execution_time(row.get("small", {}))
      if big_t is None or small_t is None:
        skipped += 1
        continue
      fail_detect_s = big_t * args.primary_failure_fraction
      total_s = fail_detect_s + overhead_s + small_t
      totals.append(total_s)
      big_times.append(big_t)
      small_times.append(small_t)
      if total_s > budget_s:
        misses += 1
        miss_out.write(json.dumps({
          "frameId": row.get("frameId"),
          "pairMethod": row.get("pairMethod"),
          "bigExecutionMs": big_t * 1000.0,
          "smallExecutionMs": small_t * 1000.0,
          "assumedFailureDetectMs": fail_detect_s * 1000.0,
          "handoffOverheadMs": args.handoff_overhead_ms,
          "fallbackTotalMs": total_s * 1000.0,
          "budgetMs": args.budget_ms,
        }, ensure_ascii=False) + "\n")

  usable = len(totals)
  result = {
    "inputRows": total_rows,
    "usableRows": usable,
    "skippedRows": skipped,
    "budgetMs": args.budget_ms,
    "handoffOverheadMs": args.handoff_overhead_ms,
    "primaryFailureFraction": args.primary_failure_fraction,
    "deadlineMisses": misses,
    "deadlineMissRate": misses / usable if usable else None,
    "bigExecutionMs": {
      "p50": percentile(big_times, 0.50) * 1000.0,
      "p95": percentile(big_times, 0.95) * 1000.0,
      "p99": percentile(big_times, 0.99) * 1000.0,
    },
    "smallExecutionMs": {
      "p50": percentile(small_times, 0.50) * 1000.0,
      "p95": percentile(small_times, 0.95) * 1000.0,
      "p99": percentile(small_times, 0.99) * 1000.0,
    },
    "sameFrameFallbackTotalMs": {
      "p50": percentile(totals, 0.50) * 1000.0,
      "p95": percentile(totals, 0.95) * 1000.0,
      "p99": percentile(totals, 0.99) * 1000.0,
      "max": max(totals) * 1000.0 if totals else None,
    },
  }
  print(json.dumps(result, ensure_ascii=False, indent=2))
  print(f"miss_events={args.events}")


if __name__ == "__main__":
  main()
