#!/usr/bin/env python3
"""Receive real modeld shadow-tap metadata without running any inference."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from egpu_future.interference import percentile
from egpu_future.shadow_tap import DEFAULT_SOCKET_PATH, ShadowTapReceiver


def main() -> int:
  ap = argparse.ArgumentParser(description="Tap-only commissioning receiver; no model inference")
  ap.add_argument("--socket", default=DEFAULT_SOCKET_PATH)
  ap.add_argument("--duration", type=float, default=60.0)
  ap.add_argument("--output", type=Path, default=Path("/tmp/egpu_future_tap_probe.jsonl"))
  ap.add_argument("--summary-output", type=Path, default=Path("/tmp/egpu_future_tap_probe_summary.json"))
  ap.add_argument("--flush-every", type=int, default=20)
  args = ap.parse_args()
  if args.duration <= 0:
    raise SystemExit("--duration must be > 0")
  if args.flush_every <= 0:
    raise SystemExit("--flush-every must be > 0")

  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.summary_output.parent.mkdir(parents=True, exist_ok=True)
  started = time.monotonic()
  saved = 0
  receiver_latencies_ms: list[float] = []
  frame_ids: list[int] = []
  with args.output.open("w", encoding="utf-8", buffering=1) as out, ShadowTapReceiver(args.socket) as receiver:
    while time.monotonic() - started < args.duration:
      snap = receiver.recv_latest()
      if snap is None:
        time.sleep(0.001)
        continue
      receiver_ns = time.monotonic_ns()
      row = asdict(snap)
      row["receiver_mono_ns"] = receiver_ns
      out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
      saved += 1
      frame_ids.append(snap.frame_id)
      if snap.created_mono_ns > 0 and receiver_ns >= snap.created_mono_ns:
        receiver_latencies_ms.append((receiver_ns - snap.created_mono_ns) / 1e6)
      if saved % args.flush_every == 0:
        out.flush()

    frame_gaps = sum(max(0, b - a - 1) for a, b in zip(frame_ids, frame_ids[1:]) if b > a)
    duplicate_or_old = sum(b <= a for a, b in zip(frame_ids, frame_ids[1:]))
    summary = {
      "durationSeconds": time.monotonic() - started,
      "packetsReceived": receiver.received,
      "recordsSaved": saved,
      "supersededPackets": receiver.superseded,
      "decodeErrors": receiver.decode_errors,
      "saveCoverage": saved / receiver.received if receiver.received else 0.0,
      "frameGapCount": frame_gaps,
      "duplicateOrOldFrameTransitions": duplicate_or_old,
      "transportLatencyMs": {
        "samples": len(receiver_latencies_ms),
        "mean": sum(receiver_latencies_ms) / len(receiver_latencies_ms) if receiver_latencies_ms else None,
        "p50": percentile(receiver_latencies_ms, 0.50),
        "p95": percentile(receiver_latencies_ms, 0.95),
        "p99": percentile(receiver_latencies_ms, 0.99),
        "max": max(receiver_latencies_ms) if receiver_latencies_ms else None,
      },
      "output": str(args.output),
      "summaryOutput": str(args.summary_output),
      "note": "This probe performs no driving-model or YOLO inference.",
    }

  args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(summary, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
