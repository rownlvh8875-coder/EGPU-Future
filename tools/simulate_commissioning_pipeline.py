#!/usr/bin/env python3
"""Run the T0-T3 qualification pipeline entirely on deterministic synthetic data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.interference import latency_stats_ms
from egpu_future.qualification import build_t0_t3_report, render_markdown, report_to_dict
from egpu_future.synthetic_commissioning import generate_case, predefined_case


def write_jsonl(path: Path, rows: list[dict]) -> None:
  with path.open("w", encoding="utf-8") as out:
    for row in rows:
      out.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
  ap = argparse.ArgumentParser(description="Exercise commissioning qualification with synthetic PASS/HOLD/FAIL evidence")
  ap.add_argument("case", choices=["pass", "fail_latency", "fail_transport", "fail_gap", "hold_no_policy", "hold_samples"])
  ap.add_argument("--output-dir", type=Path, default=Path("synthetic_commissioning"))
  ap.add_argument("--deadline-ms", type=float, default=50.0)
  args = ap.parse_args()

  case = predefined_case(args.case)
  data = generate_case(case)
  args.output_dir.mkdir(parents=True, exist_ok=True)

  stats = {}
  for stage, rows in data["stages"].items():
    write_jsonl(args.output_dir / f"{stage}.jsonl", rows)
    stats[stage] = latency_stats_ms(rows, args.deadline_ms, require_big=True)

  tap_path = args.output_dir / "T3_tap_summary.json"
  tap_path.write_text(json.dumps(data["tapSummary"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

  report = build_t0_t3_report(
    t0=stats["T0"],
    t1=stats["T1"],
    t2=stats["T2"],
    t3=stats["T3"],
    limits=data["limits"],
    t3_tap_probe=data["tapSummary"],
  )
  report_dict = report_to_dict(report)
  report_dict["synthetic"] = True
  report_dict["case"] = case.name
  report_dict["expectedStatus"] = case.expected_status
  (args.output_dir / "commissioning_qualification.json").write_text(
    json.dumps(report_dict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
  )
  (args.output_dir / "commissioning_qualification.md").write_text(render_markdown(report), encoding="utf-8")

  result = {
    "case": case.name,
    "expectedStatus": case.expected_status,
    "actualStatus": report.overall_status.value,
    "matchesExpected": report.overall_status.value == case.expected_status,
    "outputDir": str(args.output_dir),
    "warning": "Synthetic evidence validates software behavior only; it says nothing about real vehicle safety or performance.",
  }
  print(json.dumps(result, ensure_ascii=False, indent=2))
  return 0 if result["matchesExpected"] else 3


if __name__ == "__main__":
  raise SystemExit(main())
