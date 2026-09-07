#!/usr/bin/env python3
"""Dry-run/apply/revert the parked-only S4B metadata tap on S1+S2 Carrot-WIP."""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import py_compile
import shutil
import subprocess

from egpu_future.carrot_wip_integrated_patch import PINNED_CARROT_WIP_HEAD, TARGET_MODELD_PATH
from egpu_future.carrot_wip_integrated_stage2_patch import stage2_patch_summary
from egpu_future.carrot_wip_integrated_stage4b_patch import (
  TARGET_SHADOW_TAP_PATH, TARGET_SHADOW_PROBE_PATH, patch_stage4b_text, patch_summary,
  strip_stage4b_blocks, verify_stage4b_path_unchanged,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = PROJECT_ROOT / "integrations/carrot_wip_integrated/runtime/shadow_tap.py"
PROBE_SOURCE = PROJECT_ROOT / "tools/carrot_wip_s4b_shadow_probe.py"


def git(repo: Path, *args: str) -> str:
  p = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
  if p.returncode != 0:
    raise RuntimeError(p.stderr.strip())
  return p.stdout.strip()


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("repo", type=Path)
  mode = ap.add_mutually_exclusive_group()
  mode.add_argument("--apply", action="store_true")
  mode.add_argument("--revert", action="store_true")
  ap.add_argument("--allow-head-drift", action="store_true")
  args = ap.parse_args()

  repo = args.repo.resolve()
  modeld = repo / TARGET_MODELD_PATH
  tap_target = repo / TARGET_SHADOW_TAP_PATH
  probe_target = repo / TARGET_SHADOW_PROBE_PATH
  if not modeld.is_file(): raise SystemExit(f"missing {modeld}")
  head = git(repo, "rev-parse", "HEAD")
  if head != PINNED_CARROT_WIP_HEAD and not args.allow_head_drift:
    raise SystemExit(f"carrot-wip HEAD mismatch got={head} expected={PINNED_CARROT_WIP_HEAD}")
  current = modeld.read_text(encoding="utf-8")
  if not stage2_patch_summary(current).complete:
    raise SystemExit("S4B requires complete S1+S2 patch first")

  if args.revert:
    if not patch_summary(current).complete: raise SystemExit("complete S4B patch not found")
    restored = strip_stage4b_blocks(current)
    verify_stage4b_path_unchanged(restored, current)
    modeld.write_text(restored, encoding="utf-8")
    for path in (tap_target, probe_target):
      try: path.unlink()
      except FileNotFoundError: pass
    print("revertedStage4B=true\ncontrolPathPreserved=true\nmanualProbeRemoved=true")
    return 0

  summary = patch_summary(current)
  if any((summary.imports, summary.init, summary.send)):
    raise SystemExit(f"S4B patch already/partially present: {summary}")
  patched = patch_stage4b_text(current); verify_stage4b_path_unchanged(current, patched)
  diff = "".join(difflib.unified_diff(current.splitlines(True), patched.splitlines(True), fromfile=f"a/{TARGET_MODELD_PATH}", tofile=f"b/{TARGET_MODELD_PATH}"))
  print(f"head={head}\nstage4bPathVerification=PASS")
  print(diff, end="" if diff.endswith("\n") else "\n")
  if not args.apply:
    print(f"dryRun=true\nwouldInstallProbe={TARGET_SHADOW_PROBE_PATH}")
    return 0

  for path in (tap_target, probe_target):
    if path.exists(): raise SystemExit(f"target already exists: {path}")
  try:
    tap_target.parent.mkdir(parents=True, exist_ok=True)
    probe_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNTIME_SOURCE, tap_target)
    shutil.copyfile(PROBE_SOURCE, probe_target)
    modeld.write_text(patched, encoding="utf-8")
    py_compile.compile(str(tap_target), doraise=True)
    py_compile.compile(str(probe_target), doraise=True)
    py_compile.compile(str(modeld), doraise=True)
    verify_stage4b_path_unchanged(current, modeld.read_text(encoding="utf-8"))
  except Exception:
    modeld.write_text(current, encoding="utf-8")
    for path in (tap_target, probe_target):
      try: path.unlink()
      except FileNotFoundError: pass
    raise
  print(f"applyStage4B=true\nmanualProbe={TARGET_SHADOW_PROBE_PATH}\nmanagerAutostart=false\nshadowControlsPublish=false")
  return 0


if __name__ == "__main__": raise SystemExit(main())
