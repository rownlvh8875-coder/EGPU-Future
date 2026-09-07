#!/usr/bin/env python3
"""Log comma/openpilot Chestnut telemetry to JSONL.

Run on a comma device with openpilot available in PYTHONPATH.
This tool is read-only: it does not change GPU power limits or vehicle controls.
"""
from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path


def parse_args():
  p = argparse.ArgumentParser()
  p.add_argument("--output", default="chestnut_telemetry.jsonl")
  p.add_argument("--hz", type=float, default=2.0, help="sampling rate; chestnutState metrics update slower than model loop")
  p.add_argument("--duration", type=float, default=0.0, help="seconds; 0 means until Ctrl-C")
  return p.parse_args()


def _enum_name(v):
  try:
    return str(v)
  except Exception:
    return None


def main():
  args = parse_args()
  if args.hz <= 0:
    raise SystemExit("--hz must be > 0")

  try:
    import openpilot.cereal.messaging as messaging
  except Exception as e:
    raise SystemExit("This logger must run in an openpilot environment") from e

  services = ["chestnutState", "deviceState", "carState", "modelV2"]
  sm = messaging.SubMaster(services)
  out = Path(args.output)
  out.parent.mkdir(parents=True, exist_ok=True)
  period = 1.0 / args.hz
  start = time.monotonic()
  running = True

  def stop(*_):
    nonlocal running
    running = False

  signal.signal(signal.SIGINT, stop)
  signal.signal(signal.SIGTERM, stop)

  with out.open("a", encoding="utf-8", buffering=1) as f:
    while running:
      tick = time.monotonic()
      sm.update(0)
      c = sm["chestnutState"]
      d = sm["deviceState"]
      car = sm["carState"]

      row = {
        "ts_unix": time.time(),
        "ts_mono": tick,
        "alive": {s: bool(sm.alive[s]) for s in services},
        "valid": {s: bool(sm.valid[s]) for s in services},
        "chestnut": {
          "tempC": float(c.tempC),
          "memoryTempC": float(c.memoryTempC),
          "powerDrawW": float(c.powerDrawW),
          "powerLimitW": float(c.powerLimitW),
          "gpuUsagePercent": float(c.gpuUsagePercent),
          "gpuClockMhz": float(c.gpuClockMhz),
          "fanSpeedRpm": float(c.fanSpeedRpm),
          "supplyVoltageMv": int(c.supplyVoltage),
          "supplyCurrentMa": int(c.supplyCurrent),
          "supplyFault": bool(c.supplyFault),
          "pcieLtssm": int(c.pcieLtssm),
        },
        "device": {
          "thermalStatus": _enum_name(d.thermalStatus),
          "chestnutPresent": bool(d.chestnutPresent),
        },
        "vehicle": {
          "vEgo": float(car.vEgo),
          "standstill": bool(car.standstill),
        },
        "model": {
          "alive": bool(sm.alive["modelV2"]),
          "valid": bool(sm.valid["modelV2"]),
        },
      }
      f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

      if args.duration > 0 and time.monotonic() - start >= args.duration:
        break
      delay = period - (time.monotonic() - tick)
      if delay > 0:
        time.sleep(delay)

  print(out)


if __name__ == "__main__":
  main()
