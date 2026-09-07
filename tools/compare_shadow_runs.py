#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.shadow_metrics import ActionSample, Thresholds, compare_actions
from egpu_future.scenario_tagger import SceneSample, tag_scene


def load_jsonl(path: Path) -> list[dict]:
  rows = []
  with path.open() as f:
    for line in f:
      line = line.strip()
      if line:
        rows.append(json.loads(line))
  return rows


def nearest(rows: list[dict], t: float, max_dt: float) -> dict | None:
  if not rows:
    return None
  best = min(rows, key=lambda r: abs(float(r['t']) - t))
  return best if abs(float(best['t']) - t) <= max_dt else None


def action_from(row: dict) -> ActionSample:
  return ActionSample(
    t=float(row['t']),
    curvature=float(row['desiredCurvature']),
    acceleration=float(row['desiredAcceleration']),
    should_stop=bool(row.get('shouldStop', False)),
    speed_mps=float(row['speedMps']) if row.get('speedMps') is not None else None,
  )


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument('small_jsonl', type=Path)
  ap.add_argument('big_jsonl', type=Path)
  ap.add_argument('--max-dt', type=float, default=0.075)
  ap.add_argument('--events', type=Path, default=Path('shadow_events.jsonl'))
  ap.add_argument('--curvature-abs', type=float, default=0.003)
  ap.add_argument('--curvature-rel', type=float, default=0.25)
  ap.add_argument('--accel-abs', type=float, default=0.50)
  args = ap.parse_args()

  small = load_jsonl(args.small_jsonl)
  big = load_jsonl(args.big_jsonl)
  th = Thresholds(args.curvature_abs, args.curvature_rel, args.accel_abs)

  matched = significant = 0
  scores: list[float] = []
  with args.events.open('w') as out:
    for srow in small:
      brow = nearest(big, float(srow['t']), args.max_dt)
      if brow is None:
        continue
      matched += 1
      sa, ba = action_from(srow), action_from(brow)
      d = compare_actions(sa, ba, th)
      scores.append(d.score)
      if not d.significant:
        continue
      significant += 1

      scene = SceneSample(
        speed_mps=float(srow.get('speedMps') or 0.0),
        acceleration_mps2=srow.get('vehicleAccelMps2'),
        curvature=sa.curvature,
        standstill=bool(srow.get('standstill', False)),
        lead_present=srow.get('leadPresent'),
        lead_distance_m=srow.get('leadDistanceM'),
        lead_rel_speed_mps=srow.get('leadRelSpeedMps'),
      )
      event = {
        't': sa.t,
        'dt': float(brow['t']) - sa.t,
        'small': srow,
        'big': brow,
        'metrics': {
          'curvatureAbs': d.curvature_abs,
          'curvatureRel': d.curvature_rel,
          'accelAbs': d.accel_abs,
          'stopMismatch': d.stop_mismatch,
          'score': d.score,
        },
        'tags': tag_scene(scene),
      }
      out.write(json.dumps(event, ensure_ascii=False) + '\n')

  mean_score = sum(scores) / len(scores) if scores else 0.0
  print(f'matched={matched}')
  print(f'significant={significant}')
  print(f'significant_rate={(significant/matched*100 if matched else 0):.2f}%')
  print(f'mean_score={mean_score:.3f}')
  print(f'events={args.events}')


if __name__ == '__main__':
  main()
