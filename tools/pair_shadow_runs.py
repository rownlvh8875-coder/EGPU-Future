#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.frame_pairing import PairingConfig, pair_records


def load_jsonl(path: Path) -> list[dict]:
  rows: list[dict] = []
  with path.open(encoding="utf-8") as f:
    for line_no, line in enumerate(f, 1):
      line = line.strip()
      if not line:
        continue
      try:
        rows.append(json.loads(line))
      except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
  return rows


def main() -> None:
  ap = argparse.ArgumentParser(description="Pair small/big model outputs deterministically by frameId")
  ap.add_argument("small_jsonl", type=Path)
  ap.add_argument("big_jsonl", type=Path)
  ap.add_argument("--output", type=Path, default=Path("paired_shadow.jsonl"))
  ap.add_argument("--summary", type=Path, default=Path("paired_shadow_summary.json"))
  ap.add_argument("--timestamp-fallback", action="store_true")
  ap.add_argument("--max-dt", type=float, default=0.030)
  ap.add_argument("--ambiguity-margin", type=float, default=0.005)
  args = ap.parse_args()

  small = load_jsonl(args.small_jsonl)
  big = load_jsonl(args.big_jsonl)
  result = pair_records(small, big, PairingConfig(
    timestamp_fallback=args.timestamp_fallback,
    max_timestamp_delta_s=args.max_dt,
    ambiguity_margin_s=args.ambiguity_margin,
  ))

  args.output.parent.mkdir(parents=True, exist_ok=True)
  with args.output.open("w", encoding="utf-8") as out:
    for pair in result.pairs:
      row = {
        "frameId": int(pair.small.get("frameId", 0) or pair.big.get("frameId", 0) or 0),
        "pairMethod": pair.method,
        "deltaS": pair.delta_s,
        "small": pair.small,
        "big": pair.big,
      }
      out.write(json.dumps(row, ensure_ascii=False) + "\n")

  methods: dict[str, int] = {}
  for p in result.pairs:
    methods[p.method] = methods.get(p.method, 0) + 1
  summary = {
    "smallSamples": len(small),
    "bigSamples": len(big),
    "pairedSamples": len(result.pairs),
    "pairMethods": methods,
    "smallUnmatched": len(result.small_unmatched),
    "bigUnmatched": len(result.big_unmatched),
    "duplicateSmallFrameIds": result.duplicate_small_frame_ids,
    "duplicateBigFrameIds": result.duplicate_big_frame_ids,
    "timestampFallbackEnabled": args.timestamp_fallback,
    "maxTimestampDeltaS": args.max_dt,
    "ambiguityMarginS": args.ambiguity_margin,
  }
  args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

  print(json.dumps(summary, ensure_ascii=False, indent=2))
  print(f"paired={args.output}")
  print(f"summary={args.summary}")


if __name__ == "__main__":
  main()
