#!/usr/bin/env python3
"""Analyze trusted tinygrad PROFILE=1 output without modifying tinygrad.

Run inside the same openpilot/tinygrad Python environment that created the
profile. Pickle is executable data: never use this tool on an untrusted file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle

from egpu_future.tinygrad_profile import summarize_profile_events


def main() -> None:
  ap = argparse.ArgumentParser(description="Summarize tinygrad HCQ hardware kernel timestamps")
  ap.add_argument("profile", type=Path, help="trusted tinygrad profile.pkl produced with PROFILE=1")
  ap.add_argument("--device-prefix", default="QCOM", help="QCOM, AMD, etc.")
  ap.add_argument("--include-subdevices", action="store_true",
                  help="include names such as QCOM:COPY; default QCOM analysis selects exact hardware device only")
  ap.add_argument("--top", type=int, default=20)
  ap.add_argument("--output", type=Path, default=None)
  args = ap.parse_args()
  if args.top < 0:
    raise SystemExit("--top must be >= 0")

  with args.profile.open("rb") as f:
    events = pickle.load(f)  # trusted local tinygrad output only

  report = {
    "profilePath": str(args.profile),
    "warning": "Loaded trusted local pickle. Do not analyze untrusted pickle files.",
    **summarize_profile_events(
      events,
      device_prefix=args.device_prefix,
      top_n=args.top,
      include_subdevices=args.include_subdevices,
    ),
  }
  text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
  print(text, end="")
  if args.output is not None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
  main()
