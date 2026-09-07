#!/usr/bin/env python3
"""Generate an S4C parked 20 Hz plan only from PASS S4B evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrations.carrot_wip_integrated.runtime.s4c_plan import S4CConfig, build_s4c_plan, plan_to_dict


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("s4b_qualification", type=Path)
  ap.add_argument("--source-compatible", action="store_true",
                  help="assert current source compatibility was separately rechecked immediately before planning")
  ap.add_argument("--duration", type=float, default=60.0)
  ap.add_argument("--settle-frames", type=int, default=40)
  ap.add_argument("--output", type=Path, default=Path("s4c_plan.json"))
  args = ap.parse_args()

  evidence = json.loads(args.s4b_qualification.read_text(encoding="utf-8"))
  if not isinstance(evidence, dict):
    raise SystemExit("S4B qualification must be a JSON object")

  plan = build_s4c_plan(
    s4b_qualification=evidence,
    source_compatible=args.source_compatible,
    config=S4CConfig(duration_s=args.duration, settle_frames=args.settle_frames),
  )
  payload = plan_to_dict(plan)
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(payload, ensure_ascii=False, indent=2))
  print(f"output={args.output}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
