#!/usr/bin/env python3
"""Correlate shadow model-call windows with QCOM hardware kernel timestamps.

Run inside the openpilot/tinygrad environment that created profile.pkl.
The profile pickle must be trusted local output from tinygrad PROFILE=1.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle

from egpu_future.kernel_timeline import correlate_windows, model_window_from_shadow_event, summarize_correlations
from egpu_future.tinygrad_profile import device_clock_offsets_us, normalize_profile_events


def load_shadow(path: Path):
  windows = []
  total_outputs = 0
  for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    if row.get("type") == "shadow_output":
      total_outputs += 1
      window = model_window_from_shadow_event(row)
      if window is not None:
        windows.append(window)
  return total_outputs, windows


def main() -> None:
  ap = argparse.ArgumentParser(description="Map shadow frames to tinygrad hardware kernel ranges")
  ap.add_argument("shadow_jsonl", type=Path)
  ap.add_argument("profile", type=Path, help="trusted tinygrad profile.pkl from PROFILE=1")
  ap.add_argument("--device-prefix", default="QCOM")
  ap.add_argument("--tolerance-us", type=float, default=50.0)
  ap.add_argument("--frames-output", type=Path, default=Path("shadow_kernel_frames.jsonl"))
  ap.add_argument("--summary-output", type=Path, default=Path("shadow_kernel_summary.json"))
  args = ap.parse_args()
  if args.tolerance_us < 0:
    raise SystemExit("--tolerance-us must be >= 0")

  with args.profile.open("rb") as f:
    events = pickle.load(f)  # trusted local tinygrad output only

  total_outputs, windows = load_shadow(args.shadow_jsonl)
  kernels = normalize_profile_events(events, device_prefix=args.device_prefix, align_to_host=True)
  correlated = correlate_windows(windows, kernels, tolerance_us=args.tolerance_us)
  summary = {
    "shadowOutputs": total_outputs,
    "modelWindows": len(windows),
    "kernelRanges": len(kernels),
    "devicePrefix": args.device_prefix,
    "deviceClockOffsetsUs": {
      k: v for k, v in device_clock_offsets_us(events).items()
      if k.upper().startswith(args.device_prefix.upper())
    },
    "correlation": summarize_correlations(correlated),
    "timingBasis": "tinygrad HCQ hardware timestamps aligned to host monotonic using ProfileDeviceEvent.tdiff",
    "warning": "profile.pkl is trusted executable pickle data; never load untrusted files",
  }

  args.frames_output.parent.mkdir(parents=True, exist_ok=True)
  args.summary_output.parent.mkdir(parents=True, exist_ok=True)
  with args.frames_output.open("w", encoding="utf-8") as out:
    for row in correlated:
      out.write(json.dumps(row, ensure_ascii=False) + "\n")
  args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
