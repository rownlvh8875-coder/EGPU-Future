"""Pure-Python metrics for active-model baseline vs shadow-on comparisons."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


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


def latency_stats_ms(rows: list[dict], deadline_ms: float = 50.0, require_big: bool = True) -> dict:
  selected: list[dict] = []
  values: list[float] = []
  frame_ages: list[int] = []
  frame_ids: list[int] = []

  for row in rows:
    if require_big and not bool(row.get("big", False)):
      continue
    try:
      sec = float(row.get("modelExecutionTimeS"))
    except (TypeError, ValueError):
      continue
    if not isfinite(sec) or sec < 0:
      continue
    selected.append(row)
    values.append(sec * 1000.0)
    try:
      frame_ages.append(int(row.get("frameAge", 0) or 0))
    except (TypeError, ValueError):
      pass
    try:
      fid = int(row.get("frameId", 0) or 0)
      if fid > 0:
        frame_ids.append(fid)
    except (TypeError, ValueError):
      pass

  misses = sum(v > deadline_ms for v in values)
  gaps = 0
  duplicate_or_old = 0
  if frame_ids:
    for a, b in zip(frame_ids, frame_ids[1:]):
      if b <= a:
        duplicate_or_old += 1
      elif b > a + 1:
        gaps += b - a - 1

  return {
    "samples": len(values),
    "meanMs": sum(values) / len(values) if values else None,
    "p50Ms": percentile(values, 0.50),
    "p95Ms": percentile(values, 0.95),
    "p99Ms": percentile(values, 0.99),
    "maxMs": max(values) if values else None,
    "deadlineMs": deadline_ms,
    "deadlineMisses": misses,
    "deadlineMissRate": misses / len(values) if values else 0.0,
    "frameAgeGt0": sum(v > 0 for v in frame_ages),
    "frameAgeGt1": sum(v > 1 for v in frame_ages),
    "frameAgeMax": max(frame_ages) if frame_ages else None,
    "frameGapCount": gaps,
    "duplicateOrOldFrameTransitions": duplicate_or_old,
  }


def _delta(before: float | None, after: float | None) -> dict:
  if before is None or after is None:
    return {"absoluteMs": None, "relativePercent": None}
  absolute = after - before
  relative = absolute / before * 100.0 if before != 0 else None
  return {"absoluteMs": absolute, "relativePercent": relative}


def compare_latency_stats(baseline: dict, shadow_on: dict) -> dict:
  return {
    "mean": _delta(baseline.get("meanMs"), shadow_on.get("meanMs")),
    "p50": _delta(baseline.get("p50Ms"), shadow_on.get("p50Ms")),
    "p95": _delta(baseline.get("p95Ms"), shadow_on.get("p95Ms")),
    "p99": _delta(baseline.get("p99Ms"), shadow_on.get("p99Ms")),
    "max": _delta(baseline.get("maxMs"), shadow_on.get("maxMs")),
    "deadlineMissRateDelta": shadow_on.get("deadlineMissRate", 0.0) - baseline.get("deadlineMissRate", 0.0),
    "frameAgeGt1Delta": shadow_on.get("frameAgeGt1", 0) - baseline.get("frameAgeGt1", 0),
    "frameGapCountDelta": shadow_on.get("frameGapCount", 0) - baseline.get("frameGapCount", 0),
  }
