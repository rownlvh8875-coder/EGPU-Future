#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def percentile(vals: list[float], q: float) -> float:
  if not vals:
    return float('nan')
  xs = sorted(vals)
  i = min(len(xs) - 1, max(0, round((len(xs) - 1) * q)))
  return xs[i]


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument('jsonl', type=Path)
  ap.add_argument('--field', default='latencyMs', help='latency field name in each JSON object')
  ap.add_argument('--deadline-ms', type=float, default=50.0)
  args = ap.parse_args()

  vals: list[float] = []
  with args.jsonl.open() as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      row = json.loads(line)
      v = row.get(args.field)
      if v is not None:
        vals.append(float(v))

  if not vals:
    raise SystemExit(f'no values for field {args.field}')

  misses = sum(v > args.deadline_ms for v in vals)
  print(f'n={len(vals)}')
  print(f'mean_ms={statistics.fmean(vals):.3f}')
  print(f'p50_ms={percentile(vals, 0.50):.3f}')
  print(f'p95_ms={percentile(vals, 0.95):.3f}')
  print(f'p99_ms={percentile(vals, 0.99):.3f}')
  print(f'max_ms={max(vals):.3f}')
  print(f'deadline_ms={args.deadline_ms:.3f}')
  print(f'deadline_misses={misses}')
  print(f'deadline_miss_rate={(misses/len(vals)*100):.3f}%')


if __name__ == '__main__':
  main()
