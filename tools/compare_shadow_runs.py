#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.frame_pairing import PairingConfig, pair_records
from egpu_future.shadow_metrics import ActionSample, Thresholds, compare_actions
from egpu_future.scenario_tagger import SceneSample, tag_scene


def load_jsonl(path: Path) -> list[dict]:
  rows = []
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


def action_from(row: dict) -> ActionSample:
  t = row.get("logMonoTimeS", row.get("t", 0.0))
  return ActionSample(
    t=float(t),
    curvature=float(row['desiredCurvature']),
    acceleration=float(row['desiredAcceleration']),
    should_stop=bool(row.get('shouldStop', False)),
    speed_mps=float(row['speedMps']) if row.get('speedMps') is not None else None,
  )


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument('small_jsonl', type=Path)
  ap.add_argument('big_jsonl', type=Path)
  ap.add_argument('--timestamp-fallback', action='store_true', help='only for data without usable frameId')
  ap.add_argument('--max-dt', type=float, default=0.030)
  ap.add_argument('--ambiguity-margin', type=float, default=0.005)
  ap.add_argument('--events', type=Path, default=Path('shadow_events.jsonl'))
  ap.add_argument('--curvature-abs', type=float, default=0.003)
  ap.add_argument('--curvature-rel', type=float, default=0.25)
  ap.add_argument('--accel-abs', type=float, default=0.50)
  args = ap.parse_args()

  small = load_jsonl(args.small_jsonl)
  big = load_jsonl(args.big_jsonl)
  pairing = pair_records(small, big, PairingConfig(
    timestamp_fallback=args.timestamp_fallback,
    max_timestamp_delta_s=args.max_dt,
    ambiguity_margin_s=args.ambiguity_margin,
  ))
  th = Thresholds(args.curvature_abs, args.curvature_rel, args.accel_abs)

  significant = 0
  scores: list[float] = []
  args.events.parent.mkdir(parents=True, exist_ok=True)
  with args.events.open('w', encoding='utf-8') as out:
    for pair in pairing.pairs:
      srow, brow = pair.small, pair.big
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
        'frameId': int(srow.get('frameId', 0) or brow.get('frameId', 0) or 0),
        'pairMethod': pair.method,
        'deltaS': pair.delta_s,
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

  matched = len(pairing.pairs)
  mean_score = sum(scores) / len(scores) if scores else 0.0
  print(f'matched={matched}')
  print(f'small_unmatched={len(pairing.small_unmatched)}')
  print(f'big_unmatched={len(pairing.big_unmatched)}')
  print(f'significant={significant}')
  print(f'significant_rate={(significant/matched*100 if matched else 0):.2f}%')
  print(f'mean_score={mean_score:.3f}')
  print(f'events={args.events}')


if __name__ == '__main__':
  main()
