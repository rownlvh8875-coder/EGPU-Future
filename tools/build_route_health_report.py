#!/usr/bin/env python3
"""Build one descriptive route health report from existing pipeline artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.route_health import build_route_health_report, render_markdown, report_to_dict


def load_json(path: Path | None):
  return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path | None):
  if path is None:
    return None
  rows = []
  for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      rows.append(json.loads(line))
    except json.JSONDecodeError as exc:
      raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
  return rows


def main() -> int:
  ap = argparse.ArgumentParser(description="Aggregate pairing/validation/disagreement artifacts for one route")
  ap.add_argument("--pairing-summary", type=Path, required=True)
  ap.add_argument("--validation-issues", type=Path, required=True)
  ap.add_argument("--shadow-events", type=Path, required=True)
  ap.add_argument("--active-interference", type=Path, default=None)
  ap.add_argument("--shadow-runtime", type=Path, default=None)
  ap.add_argument("--json-output", type=Path, default=Path("route_health.json"))
  ap.add_argument("--md-output", type=Path, default=Path("route_health.md"))
  args = ap.parse_args()

  report = build_route_health_report(
    pairing_summary=load_json(args.pairing_summary),
    validation_issues=load_jsonl(args.validation_issues),
    shadow_events=load_jsonl(args.shadow_events),
    active_interference=load_json(args.active_interference),
    shadow_runtime=load_json(args.shadow_runtime),
  )
  data = report_to_dict(report)
  args.json_output.parent.mkdir(parents=True, exist_ok=True)
  args.md_output.parent.mkdir(parents=True, exist_ok=True)
  args.json_output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  args.md_output.write_text(render_markdown(report), encoding="utf-8")
  print(json.dumps({
    "evidenceCompleteness": report.evidence_completeness,
    "hardIssueObserved": report.validation.get("hardIssueObserved"),
    "significantEvents": report.disagreements.get("significantEvents"),
    "json": str(args.json_output),
    "markdown": str(args.md_output),
  }, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
