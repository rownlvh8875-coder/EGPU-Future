#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument('events_jsonl', type=Path)
  args = ap.parse_args()

  tags = Counter()
  n = 0
  scores: list[float] = []
  stop_mismatch = 0
  with args.events_jsonl.open() as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      row = json.loads(line)
      n += 1
      tags.update(row.get('tags', []))
      metrics = row.get('metrics', {})
      if metrics.get('score') is not None:
        scores.append(float(metrics['score']))
      if metrics.get('stopMismatch'):
        stop_mismatch += 1

  print(f'events={n}')
  print(f'stop_mismatch={stop_mismatch}')
  if scores:
    print(f'mean_score={sum(scores)/len(scores):.3f}')
    print(f'max_score={max(scores):.3f}')
  print('tags:')
  for tag, count in tags.most_common():
    print(f'  {tag}: {count}')


if __name__ == '__main__':
  main()
