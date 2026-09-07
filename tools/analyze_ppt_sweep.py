#!/usr/bin/env python3
"""Analyze JSONL telemetry from chestnut_telemetry_logger.py.

Groups samples by observed GPU powerLimitW and reports thermal/noise proxy and
link-health metrics. This tool intentionally does not change the GPU PPT.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def percentile(xs, p):
  if not xs:
    return math.nan
  ys = sorted(xs)
  if len(ys) == 1:
    return ys[0]
  k = (len(ys) - 1) * p / 100.0
  f = math.floor(k)
  c = math.ceil(k)
  if f == c:
    return ys[int(k)]
  return ys[f] * (c - k) + ys[c] * (k - f)


def safe_mean(xs):
  return statistics.fmean(xs) if xs else math.nan


def load(path):
  rows = []
  for line in Path(path).read_text(encoding="utf-8").splitlines():
    if line.strip():
      rows.append(json.loads(line))
  return rows


def summarize(rows):
  groups = defaultdict(list)
  for r in rows:
    c = r.get("chestnut", {})
    limit = c.get("powerLimitW")
    if limit is None:
      continue
    groups[round(float(limit))].append(r)

  result = []
  for limit, rs in sorted(groups.items(), reverse=True):
    temps = [float(r["chestnut"]["tempC"]) for r in rs]
    mems = [float(r["chestnut"]["memoryTempC"]) for r in rs]
    powers = [float(r["chestnut"]["powerDrawW"]) for r in rs]
    fans = [float(r["chestnut"]["fanSpeedRpm"]) for r in rs]
    volts = [float(r["chestnut"]["supplyVoltageMv"]) / 1000.0 for r in rs]
    currents = [float(r["chestnut"]["supplyCurrentMa"]) / 1000.0 for r in rs]
    faults = sum(bool(r["chestnut"].get("supplyFault")) for r in rs)
    pcie_bad = sum(int(r["chestnut"].get("pcieLtssm", 0)) != 0x78 for r in rs)
    model_dead = sum(not bool(r.get("model", {}).get("alive", False)) for r in rs)
    result.append({
      "ppt_w": limit,
      "samples": len(rs),
      "power_avg_w": safe_mean(powers),
      "gpu_temp_p95_c": percentile(temps, 95),
      "mem_temp_p95_c": percentile(mems, 95),
      "fan_avg_rpm": safe_mean(fans),
      "fan_p95_rpm": percentile(fans, 95),
      "supply_v_min": min(volts) if volts else math.nan,
      "supply_a_p95": percentile(currents, 95),
      "supply_faults": faults,
      "pcie_bad_samples": pcie_bad,
      "model_dead_samples": model_dead,
    })
  return result


def fmt(x, digits=1):
  if isinstance(x, float) and math.isnan(x):
    return "-"
  return f"{x:.{digits}f}" if isinstance(x, float) else str(x)


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("input")
  ap.add_argument("--csv", default="")
  args = ap.parse_args()
  out = summarize(load(args.input))
  if not out:
    raise SystemExit("No usable samples")

  headers = ["PPT", "N", "Pavg", "GPU95", "MEM95", "FanAvg", "Fan95", "Vmin", "A95", "Fault", "PCIeBad", "ModelDead"]
  print("\t".join(headers))
  for r in out:
    print("\t".join([
      str(r["ppt_w"]), str(r["samples"]), fmt(r["power_avg_w"]), fmt(r["gpu_temp_p95_c"]),
      fmt(r["mem_temp_p95_c"]), fmt(r["fan_avg_rpm"], 0), fmt(r["fan_p95_rpm"], 0),
      fmt(r["supply_v_min"], 2), fmt(r["supply_a_p95"], 2), str(r["supply_faults"]),
      str(r["pcie_bad_samples"]), str(r["model_dead_samples"]),
    ]))

  if args.csv:
    import csv
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
      w = csv.DictWriter(f, fieldnames=list(out[0]))
      w.writeheader(); w.writerows(out)


if __name__ == "__main__":
  main()
