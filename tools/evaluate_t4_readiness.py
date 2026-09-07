#!/usr/bin/env python3
"""Evaluate whether measured evidence is sufficient to begin parked T4."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.t4_readiness import T4Policy, decision_to_dict, evaluate_t4_readiness


def load_json(path: Path | None) -> dict | None:
  if path is None:
    return None
  return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
  ap = argparse.ArgumentParser(description="Gate entry to the first parked/offroad shadow-inference experiment")
  ap.add_argument("--qualification", type=Path, required=True)
  ap.add_argument("--manifest", type=Path, required=True)
  ap.add_argument("--source-compatibility", type=Path, required=True)
  ap.add_argument("--max-hz", type=float, default=5.0)
  ap.add_argument("--output", type=Path, default=Path("t4_readiness.json"))
  args = ap.parse_args()

  decision = evaluate_t4_readiness(
    qualification=load_json(args.qualification),
    manifest=load_json(args.manifest),
    source_compatibility=load_json(args.source_compatibility),
    policy=T4Policy(max_hz=args.max_hz),
  )
  data = decision_to_dict(decision)
  text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
  print(text, end="")
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(text, encoding="utf-8")
  return 0 if decision.status.value == "PASS" else 2


if __name__ == "__main__":
  raise SystemExit(main())
