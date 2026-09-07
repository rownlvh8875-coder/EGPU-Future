#!/usr/bin/env python3
"""Create a non-executing T4 parked-shadow plan from PASS readiness evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.t4_plan import T4PlanConfig, build_t4_plan, plan_to_dict, render_markdown


def main() -> int:
  ap = argparse.ArgumentParser(description="Build the parked/offroad T4 experiment plan")
  ap.add_argument("readiness", type=Path, help="PASS t4_readiness.json")
  ap.add_argument("--max-hz", type=float, default=5.0)
  ap.add_argument("--duration", type=float, default=60.0)
  ap.add_argument("--json-output", type=Path, default=Path("t4_experiment_plan.json"))
  ap.add_argument("--md-output", type=Path, default=Path("t4_experiment_plan.md"))
  args = ap.parse_args()

  readiness = json.loads(args.readiness.read_text(encoding="utf-8"))
  plan = build_t4_plan(readiness, T4PlanConfig(max_hz=args.max_hz, duration_seconds=args.duration))
  data = plan_to_dict(plan)

  args.json_output.parent.mkdir(parents=True, exist_ok=True)
  args.md_output.parent.mkdir(parents=True, exist_ok=True)
  args.json_output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  args.md_output.write_text(render_markdown(plan), encoding="utf-8")
  print(json.dumps({
    "status": plan.status,
    "json": str(args.json_output),
    "markdown": str(args.md_output),
  }, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
