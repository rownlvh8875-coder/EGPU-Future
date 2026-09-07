#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.shadow_log import normalize_shadow_output


def main() -> None:
  ap = argparse.ArgumentParser(description="Normalize shadow_modeld JSONL into flat action rows")
  ap.add_argument("input", type=Path)
  ap.add_argument("--output", type=Path, default=Path("shadow_actions.jsonl"))
  ap.add_argument("--include-ineligible", action="store_true")
  args = ap.parse_args()

  total = emitted = skipped = 0
  args.output.parent.mkdir(parents=True, exist_ok=True)
  with args.output.open("w", encoding="utf-8") as out:
    for line_no, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
      if not line.strip():
        continue
      total += 1
      try:
        row = json.loads(line)
        normalized = normalize_shadow_output(row, eligible_only=not args.include_ineligible)
      except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{args.input}:{line_no}: invalid shadow row: {exc}") from exc
      if normalized is None:
        skipped += 1
        continue
      emitted += 1
      out.write(json.dumps(normalized, ensure_ascii=False) + "\n")

  print(json.dumps({"totalRows": total, "emitted": emitted, "skipped": skipped,
                    "eligibleOnly": not args.include_ineligible, "output": str(args.output)},
                   ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
