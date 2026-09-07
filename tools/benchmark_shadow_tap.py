#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import time

from egpu_future.interference import percentile
from egpu_future.shadow_tap import NonBlockingShadowTapSender, ShadowInputSnapshot, ShadowTapReceiver, encode_snapshot


def sample(frame_id: int) -> ShadowInputSnapshot:
  return ShadowInputSnapshot(
    frame_id=frame_id,
    frame_id_extra=frame_id,
    state_frame_id=frame_id + 1,
    camera_sof_ns=time.monotonic_ns(),
    camera_eof_ns=time.monotonic_ns(),
    active_backend="big",
    v_ego=15.0,
    main_transform=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    extra_transform=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    desire_pulse=(0.0,) * 8,
    traffic_convention=(1.0, 0.0),
    action_t=(0.25, 0.40),
    created_mono_ns=time.monotonic_ns(),
  )


def stats_us(values: list[float]) -> dict:
  return {
    "samples": len(values),
    "meanUs": sum(values) / len(values) if values else None,
    "p50Us": percentile(values, 0.50),
    "p95Us": percentile(values, 0.95),
    "p99Us": percentile(values, 0.99),
    "maxUs": max(values) if values else None,
  }


def main() -> None:
  ap = argparse.ArgumentParser(description="Benchmark shadow tap JSON encoding and non-blocking local send")
  ap.add_argument("--iterations", type=int, default=5000)
  ap.add_argument("--warmup", type=int, default=200)
  args = ap.parse_args()
  if args.iterations < 1 or args.warmup < 0:
    raise SystemExit("invalid iteration count")

  encode_us: list[float] = []
  send_us: list[float] = []

  with tempfile.TemporaryDirectory() as td:
    path = f"{td}/shadow.sock"
    with ShadowTapReceiver(path) as receiver:
      sender = NonBlockingShadowTapSender(path)
      try:
        for i in range(args.warmup + args.iterations):
          snap = sample(i + 1)

          t0 = time.perf_counter_ns()
          encode_snapshot(snap)
          t1 = time.perf_counter_ns()

          t2 = time.perf_counter_ns()
          ok = sender.send(snap)
          t3 = time.perf_counter_ns()
          receiver.recv_latest()

          if not ok:
            raise RuntimeError("tap send dropped during benchmark")
          if i >= args.warmup:
            encode_us.append((t1 - t0) / 1000.0)
            send_us.append((t3 - t2) / 1000.0)
      finally:
        sender.close()

  report = {
    "iterations": args.iterations,
    "note": "sendUs includes snapshot validation + JSON encode + AF_UNIX non-blocking send; receiver drain is outside the timed interval",
    "encodeOnly": stats_us(encode_us),
    "senderEndToEnd": stats_us(send_us),
  }
  print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
