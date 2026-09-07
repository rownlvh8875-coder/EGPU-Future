"""Aggregate one replay/shadow route into a descriptive health report.

This report intentionally does not invent pass/fail thresholds. It summarizes
evidence quality, pairing integrity, validator issues, disagreement events and
temporal scenario distribution so a route can be reviewed consistently.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from egpu_future.interference import percentile


@dataclass(frozen=True)
class RouteHealthReport:
  evidence_completeness: str
  pairing: dict
  validation: dict
  disagreements: dict
  temporal: dict
  active_interference: dict | None
  shadow_runtime: dict | None
  notes: tuple[str, ...]


def _score_stats(values: list[float]) -> dict:
  return {
    "samples": len(values),
    "mean": sum(values) / len(values) if values else None,
    "p50": percentile(values, 0.50),
    "p95": percentile(values, 0.95),
    "p99": percentile(values, 0.99),
    "max": max(values) if values else None,
  }


def build_route_health_report(
  *,
  pairing_summary: dict | None,
  validation_issues: list[dict] | None,
  shadow_events: list[dict] | None,
  active_interference: dict | None = None,
  shadow_runtime: dict | None = None,
) -> RouteHealthReport:
  missing = []
  if pairing_summary is None:
    missing.append("pairing_summary")
  if validation_issues is None:
    missing.append("validation_issues")
  if shadow_events is None:
    missing.append("shadow_events")
  completeness = "COMPLETE" if not missing else "INCOMPLETE"

  ps = pairing_summary or {}
  small = int(ps.get("smallSamples", 0) or 0)
  big = int(ps.get("bigSamples", 0) or 0)
  paired = int(ps.get("pairedSamples", 0) or 0)
  denominator = min(small, big) if small > 0 and big > 0 else 0
  pairing = {
    "smallSamples": small,
    "bigSamples": big,
    "pairedSamples": paired,
    "pairCoverageOfSmallerRun": paired / denominator if denominator else None,
    "pairMethods": ps.get("pairMethods", {}),
    "smallUnmatched": int(ps.get("smallUnmatched", 0) or 0),
    "bigUnmatched": int(ps.get("bigUnmatched", 0) or 0),
    "duplicateSmallFrameIds": int(ps.get("duplicateSmallFrameIds", 0) or 0),
    "duplicateBigFrameIds": int(ps.get("duplicateBigFrameIds", 0) or 0),
  }

  hard_counts: Counter[str] = Counter()
  review_counts: Counter[str] = Counter()
  hard_frames = set()
  review_frames = set()
  for issue in validation_issues or []:
    fid = int(issue.get("frameId", 0) or 0)
    hard = issue.get("hardIssues", []) or []
    review = issue.get("reviewIssues", []) or []
    hard_counts.update(str(x) for x in hard)
    review_counts.update(str(x) for x in review)
    if hard:
      hard_frames.add(fid)
    if review:
      review_frames.add(fid)
  validation = {
    "issueRows": len(validation_issues or []),
    "hardIssueFrames": len(hard_frames),
    "reviewIssueFrames": len(review_frames),
    "hardIssueCounts": dict(hard_counts.most_common()),
    "reviewIssueCounts": dict(review_counts.most_common()),
    "hardIssueObserved": bool(hard_frames),
  }

  tag_counts: Counter[str] = Counter()
  temporal_counts: Counter[str] = Counter()
  scores: list[float] = []
  stop_mismatch = 0
  for event in shadow_events or []:
    tag_counts.update(str(x) for x in (event.get("tags", []) or []))
    temporal_counts.update(str(x) for x in (event.get("temporalTags", []) or []))
    metrics = event.get("metrics", {}) or {}
    score = metrics.get("score")
    if score is not None:
      try:
        scores.append(float(score))
      except (TypeError, ValueError):
        pass
    if bool(metrics.get("stopMismatch", False)):
      stop_mismatch += 1

  events_n = len(shadow_events or [])
  disagreements = {
    "significantEvents": events_n,
    "significantRateOfPaired": events_n / paired if paired else None,
    "stopMismatchEvents": stop_mismatch,
    "score": _score_stats(scores),
    "tagCounts": dict(tag_counts.most_common()),
  }
  temporal = {
    "temporalTagCountsInSignificantEvents": dict(temporal_counts.most_common()),
    "cutInCandidateHeuristicEvents": temporal_counts.get("cut_in_candidate_heuristic", 0),
    "leadAcquiredEvents": temporal_counts.get("lead_acquired", 0),
    "leadLostEvents": temporal_counts.get("lead_lost", 0),
    "stopDisagreementOnsetEvents": temporal_counts.get("stop_disagreement_onset", 0),
  }

  notes = [
    "This is a descriptive route evidence report, not a safety PASS/FAIL decision.",
    "cut_in_candidate_heuristic requires independent video/radar/lane review.",
  ]
  if missing:
    notes.append("Missing evidence: " + ", ".join(missing))
  if hard_frames:
    notes.append("One or more validator hard-issue frames were observed and require root-cause review.")

  return RouteHealthReport(
    completeness,
    pairing,
    validation,
    disagreements,
    temporal,
    active_interference,
    shadow_runtime,
    tuple(notes),
  )


def report_to_dict(report: RouteHealthReport) -> dict[str, Any]:
  return {
    "evidenceCompleteness": report.evidence_completeness,
    "pairing": report.pairing,
    "validation": report.validation,
    "disagreements": report.disagreements,
    "temporal": report.temporal,
    "activeInterference": report.active_interference,
    "shadowRuntime": report.shadow_runtime,
    "notes": list(report.notes),
  }


def render_markdown(report: RouteHealthReport) -> str:
  p, v, d, t = report.pairing, report.validation, report.disagreements, report.temporal
  lines = [
    "# EGPU-Future Route Health Report",
    "",
    f"**Evidence completeness: {report.evidence_completeness}**",
    "",
    "## Pairing",
    "",
    f"- small / big / paired: {p.get('smallSamples')} / {p.get('bigSamples')} / {p.get('pairedSamples')}",
    f"- coverage of smaller run: {p.get('pairCoverageOfSmallerRun')}",
    f"- unmatched small / big: {p.get('smallUnmatched')} / {p.get('bigUnmatched')}",
    f"- duplicate frame IDs small / big: {p.get('duplicateSmallFrameIds')} / {p.get('duplicateBigFrameIds')}",
    "",
    "## Validation",
    "",
    f"- hard issue frames: {v.get('hardIssueFrames')}",
    f"- review issue frames: {v.get('reviewIssueFrames')}",
    f"- hard issues: {v.get('hardIssueCounts')}",
    f"- review issues: {v.get('reviewIssueCounts')}",
    "",
    "## Disagreement",
    "",
    f"- significant events: {d.get('significantEvents')}",
    f"- rate of paired frames: {d.get('significantRateOfPaired')}",
    f"- stop mismatch events: {d.get('stopMismatchEvents')}",
    f"- score p95 / p99 / max: {d.get('score', {}).get('p95')} / {d.get('score', {}).get('p99')} / {d.get('score', {}).get('max')}",
    "",
    "## Temporal scenarios in significant events",
    "",
    f"- lead acquired: {t.get('leadAcquiredEvents')}",
    f"- lead lost: {t.get('leadLostEvents')}",
    f"- cut-in candidate heuristic: {t.get('cutInCandidateHeuristicEvents')}",
    f"- stop disagreement onset: {t.get('stopDisagreementOnsetEvents')}",
    "",
    "## Notes",
    "",
  ]
  lines += [f"- {note}" for note in report.notes]
  return "\n".join(lines) + "\n"
