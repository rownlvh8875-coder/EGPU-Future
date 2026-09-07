#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cereal.messaging as messaging


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument('--output', type=Path, required=True)
  ap.add_argument('--duration', type=float, default=0.0, help='seconds, 0 = until Ctrl-C')
  ap.add_argument('--source-label', default='active_model')
  args = ap.parse_args()

  sm = messaging.SubMaster(['modelV2', 'carState'])
  start = time.monotonic()
  last_frame_id = None

  args.output.parent.mkdir(parents=True, exist_ok=True)
  with args.output.open('w') as out:
    while True:
      sm.update(1000)
      if args.duration > 0 and time.monotonic() - start >= args.duration:
        break
      if not sm.updated['modelV2']:
        continue

      m = sm['modelV2']
      c = sm['carState']
      frame_id = int(getattr(m, 'frameId', 0))
      if last_frame_id == frame_id and frame_id != 0:
        continue
      last_frame_id = frame_id

      action = m.action
      row = {
        't': time.monotonic(),
        'source': args.source_label,
        'frameId': frame_id,
        'valid': bool(sm.valid['modelV2']),
        'desiredCurvature': float(action.desiredCurvature),
        'desiredAcceleration': float(action.desiredAcceleration),
        'shouldStop': bool(action.shouldStop),
        'speedMps': float(c.vEgo),
        'standstill': bool(c.standstill),
      }
      out.write(json.dumps(row) + '\n')
      out.flush()


if __name__ == '__main__':
  main()
