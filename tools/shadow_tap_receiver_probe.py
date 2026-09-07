#!/usr/bin/env python3
"""Receive real modeld shadow-tap metadata without running any inference."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from egpu_future.shadow_tap import DEFAULT_SOCKET_PATH, ShadowTapReceiver


def main() -> int:
  ap = argparse.ArgumentParser(description="Tap-only commissioning receiver; no model inference")
  ap.add_argument("--socket", default=DEFAULT_SOCKET_PATH)
  ap.add_argument("--duration", type=float, default=60.0)
  ap.add_argument("--output", type=Path, default=Path("/tmp/egpu_future_tap_probe.jsonl"))
  ap.add_argument("--flush-every", type=int, default=20)
  args = ap.parse_args()
  if args.duration <= 0:
    raise SystemExit("--duration must be > 0")
  if args.flush_every <= 0:
    raise SystemExit("--flush-every must be > 0")

  args.output.parent.mkdir(parents=True, exist_ok=True)
  started = time.monotonic()
  saved = 0
  with args.output.open("w", encoding="utf-8", buffering=1) as out, ShadowTapReceiver(args.socket) as receiver:
    while time.monotonic() - started < args.duration:
      snap = receiver.recv_latest()
      if snap is None:
        time.sleep(0.001)
        continue
      row = asdict(snap)
      row["receiver_mono_ns"] = time.monotonic_ns()
      out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
      saved += 1
      if saved % args.flush_every == 0:
        out.flush()

    summary = {
      "durationSeconds": time.monotonic() - started,
      "packetsReceived": receiver.received,
      "recordsSaved": saved,
      "supersededPackets": receiver.superseded,
      "decodeErrors": receiver.decode_errors,
      "saveCoverage": saved / receiver.received if receiver.received else 0.0,
      "output": str(args.output),
      "note": "This probe performs no driving-model or YOLO inference.",
    }

  print(json.dumps(summary, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
