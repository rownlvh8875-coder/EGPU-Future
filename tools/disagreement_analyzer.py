#!/usr/bin/env python3
"""Analyze time-aligned small/big model action logs.

Input CSV columns (minimum):
  ts,small_curvature,big_curvature,small_accel,big_accel
Optional:
  small_should_stop,big_should_stop,v_ego,scenario

The tool is offline-only and does not affect vehicle control.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def f(row, key, default=0.0):
  try:
    return float(row.get(key, default) or default)
  except (TypeError, ValueError):
    return default


def b(row, key):
  return str(row.get(key, "")).strip().lower() in {"1", "true", "yes", "y"}


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("input")
  ap.add_argument("--curvature-threshold", type=float, default=0.002)
  ap.add_argument("--accel-threshold", type=float, default=0.5)
  ap.add_argument("--output", default="disagreements.csv")
  args = ap.parse_args()

  rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8")))
  out = []
  for r in rows:
    dc = abs(f(r, "big_curvature") - f(r, "small_curvature"))
    da = abs(f(r, "big_accel") - f(r, "small_accel"))
    stop_diff = b(r, "big_should_stop") != b(r, "small_should_stop") if ("big_should_stop" in r or "small_should_stop" in r) else False
    score = dc / max(args.curvature_threshold, 1e-9) + da / max(args.accel_threshold, 1e-9) + (2.0 if stop_diff else 0.0)
    if dc >= args.curvature_threshold or da >= args.accel_threshold or stop_diff:
      rr = dict(r)
      rr.update({
        "curvature_diff": f"{dc:.8f}",
        "accel_diff": f"{da:.4f}",
        "stop_diff": int(stop_diff),
        "disagreement_score": f"{score:.3f}",
      })
      out.append(rr)

  out.sort(key=lambda r: float(r["disagreement_score"]), reverse=True)
  fields = list(out[0].keys()) if out else list(rows[0].keys()) + ["curvature_diff", "accel_diff", "stop_diff", "disagreement_score"] if rows else []
  with Path(args.output).open("w", newline="", encoding="utf-8") as fp:
    w = csv.DictWriter(fp, fieldnames=fields)
    w.writeheader()
    w.writerows(out)

  print(f"rows={len(rows)} disagreements={len(out)} output={args.output}")


if __name__ == "__main__":
  main()
