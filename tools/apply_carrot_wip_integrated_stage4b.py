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
  TARGET_SHADOW_TAP_PATH, patch_stage4b_text, patch_summary,
  strip_stage4b_blocks, verify_stage4b_path_unchanged,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = PROJECT_ROOT / "integrations/carrot_wip_integrated/runtime/shadow_tap.py"


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

  repo = args.repo.resolve(); modeld = repo / TARGET_MODELD_PATH; target = repo / TARGET_SHADOW_TAP_PATH
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
    if target.exists(): target.unlink()
    print("revertedStage4B=true\ncontrolPathPreserved=true")
    return 0

  if any((patch_summary(current).imports, patch_summary(current).init, patch_summary(current).send)):
    raise SystemExit(f"S4B patch already/partially present: {patch_summary(current)}")
  patched = patch_stage4b_text(current); verify_stage4b_path_unchanged(current, patched)
  diff = "".join(difflib.unified_diff(current.splitlines(True), patched.splitlines(True), fromfile=f"a/{TARGET_MODELD_PATH}", tofile=f"b/{TARGET_MODELD_PATH}"))
  print(f"head={head}\nstage4bPathVerification=PASS")
  print(diff, end="" if diff.endswith("\n") else "\n")
  if not args.apply:
    print("dryRun=true"); return 0
  if target.exists(): raise SystemExit(f"runtime already exists: {target}")
  try:
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(RUNTIME_SOURCE, target); modeld.write_text(patched, encoding="utf-8")
    py_compile.compile(str(target), doraise=True); py_compile.compile(str(modeld), doraise=True)
    verify_stage4b_path_unchanged(current, modeld.read_text(encoding="utf-8"))
  except Exception:
    modeld.write_text(current, encoding="utf-8")
    try: target.unlink()
    except FileNotFoundError: pass
    raise
  print("applyStage4B=true\nmanagerAutostart=false\nshadowControlsPublish=false")
  return 0


if __name__ == "__main__": raise SystemExit(main())
