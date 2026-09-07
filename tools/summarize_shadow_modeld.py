#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def percentile(values: list[float], q: float) -> float | None:
  if not values:
    return None
  vals = sorted(values)
  if len(vals) == 1:
    return vals[0]
  pos = (len(vals) - 1) * q
  lo = int(pos)
  hi = min(lo + 1, len(vals) - 1)
  frac = pos - lo
  return vals[lo] * (1.0 - frac) + vals[hi] * frac


def stats(values: list[float]) -> dict:
  if not values:
    return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
  return {
    "count": len(values),
    "mean": sum(values) / len(values),
    "p50": percentile(values, 0.50),
    "p95": percentile(values, 0.95),
    "p99": percentile(values, 0.99),
    "max": max(values),
  }


def main() -> None:
  ap = argparse.ArgumentParser(description="Summarize control-isolated shadow_modeld JSONL")
  ap.add_argument("input", type=Path)
  ap.add_argument("--research-deadline-ms", type=float, default=50.0)
  args = ap.parse_args()

  event_types: Counter[str] = Counter()
  skip_reasons: Counter[str] = Counter()
  model_ms: list[float] = []
  capture_done_ms: list[float] = []
  eligible = 0
  outputs = 0
  ordered = 0
  frame_ids: list[int] = []

  for line_no, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      raise ValueError(f"{args.input}:{line_no}: invalid JSON: {exc}") from exc
    typ = str(row.get("type", "unknown"))
    event_types[typ] += 1
    if typ == "skip":
      skip_reasons[str(row.get("reason", "unknown"))] += 1
      continue
    if typ != "shadow_output":
      continue
    outputs += 1
    if row.get("comparisonEligible"):
      eligible += 1
    if row.get("timingOrdered"):
      ordered += 1
    try:
      frame_ids.append(int(row["frameId"]))
    except (KeyError, TypeError, ValueError):
      pass
    timing = row.get("timing") or {}
    if timing.get("model_call_total_ms") is not None:
      model_ms.append(float(timing["model_call_total_ms"]))
    if timing.get("capture_to_done_ms") is not None:
      capture_done_ms.append(float(timing["capture_to_done_ms"]))

  deadline = args.research_deadline_ms
  model_deadline_miss = sum(v > deadline for v in model_ms)
  capture_deadline_miss = sum(v > deadline for v in capture_done_ms)
  frame_span = (max(frame_ids) - min(frame_ids) + 1) if frame_ids else 0
  observed_frame_coverage = outputs / frame_span if frame_span > 0 else None

  summary = {
    "eventTypes": dict(event_types),
    "skipReasons": dict(skip_reasons),
    "shadowOutputs": outputs,
    "comparisonEligible": eligible,
    "comparisonEligibleRate": eligible / outputs if outputs else 0.0,
    "timingOrderedRate": ordered / outputs if outputs else 0.0,
    "observedFrameCoverage": observed_frame_coverage,
    "modelCallMs": stats(model_ms),
    "captureToDoneMs": stats(capture_done_ms),
    "researchDeadlineMs": deadline,
    "modelCallDeadlineMisses": model_deadline_miss,
    "modelCallDeadlineMissRate": model_deadline_miss / len(model_ms) if model_ms else 0.0,
    "captureToDoneDeadlineMisses": capture_deadline_miss,
    "captureToDoneDeadlineMissRate": capture_deadline_miss / len(capture_done_ms) if capture_done_ms else 0.0,
  }
  print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
