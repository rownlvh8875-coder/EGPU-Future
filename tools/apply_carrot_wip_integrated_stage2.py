#!/usr/bin/env python3
"""Dry-run/apply/revert Stage-2 telemetry layer on an already Stage-1 patched carrot-wip checkout."""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import py_compile
import shutil
import subprocess

from egpu_future.carrot_wip_integrated_patch import (
  PINNED_CARROT_WIP_HEAD,
  TARGET_MODELD_PATH,
  patch_summary as stage1_summary,
)
from egpu_future.carrot_wip_integrated_stage2_patch import (
  TARGET_TELEMETRY_PATH,
  patch_stage2_text,
  stage2_patch_summary,
  strip_stage2_blocks,
  verify_stage2_path_unchanged,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_SOURCE = PROJECT_ROOT / "integrations/carrot_wip_integrated/runtime/egpu_hardware_telemetry.py"


def git(repo: Path, *args: str) -> str:
  p = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
  if p.returncode != 0:
    raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
  return p.stdout.strip()


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("repo", type=Path, help="local carrot-wip checkout with Stage-1 observer already applied")
  mode = ap.add_mutually_exclusive_group()
  mode.add_argument("--apply", action="store_true", help="write Stage-2 telemetry patch; default is dry-run")
  mode.add_argument("--revert", action="store_true", help="remove only Stage-2 telemetry markers/runtime")
  ap.add_argument("--allow-head-drift", action="store_true",
                  help="allow a different HEAD only after separately reviewing the Carrot integration baseline")
  args = ap.parse_args()

  repo = args.repo.resolve()
  modeld_path = repo / TARGET_MODELD_PATH
  telemetry_target = repo / TARGET_TELEMETRY_PATH
  if not modeld_path.is_file():
    raise SystemExit(f"missing modeld.py: {modeld_path}")

  head = git(repo, "rev-parse", "HEAD")
  if head != PINNED_CARROT_WIP_HEAD and not args.allow_head_drift:
    raise SystemExit(f"carrot-wip HEAD mismatch got={head} expected={PINNED_CARROT_WIP_HEAD}")

  current = modeld_path.read_text(encoding="utf-8")
  if not stage1_summary(current).complete:
    raise SystemExit("Stage-2 requires the complete Stage-1 integrated observer patch first")

  if args.revert:
    summary = stage2_patch_summary(current)
    if not summary.complete:
      raise SystemExit("complete Stage-2 telemetry markers not found")
    restored = strip_stage2_blocks(current)
    verify_stage2_path_unchanged(restored, current)
    modeld_path.write_text(restored, encoding="utf-8")
    if telemetry_target.exists():
      telemetry_target.unlink()
    print(f"revertedStage2=true\nhead={head}\nstage1Preserved=true")
    return 0

  existing = stage2_patch_summary(current)
  if any((existing.imports, existing.init)):
    raise SystemExit(f"Stage-2 telemetry patch already or partially present: {existing}")
  if not TELEMETRY_SOURCE.is_file():
    raise SystemExit(f"missing telemetry source: {TELEMETRY_SOURCE}")

  if args.apply:
    dirty = git(repo, "status", "--porcelain", "--", TARGET_TELEMETRY_PATH)
    if dirty:
      raise SystemExit(f"refusing dirty telemetry target:\n{dirty}")
    if telemetry_target.exists():
      raise SystemExit(f"telemetry runtime already exists: {telemetry_target}")

  patched = patch_stage2_text(current)
  verify_stage2_path_unchanged(current, patched)
  diff = "".join(difflib.unified_diff(
    current.splitlines(keepends=True), patched.splitlines(keepends=True),
    fromfile=f"a/{TARGET_MODELD_PATH}", tofile=f"b/{TARGET_MODELD_PATH}",
  ))
  print(f"head={head}\nstage1Present=true\nstage2PathVerification=PASS")
  print(diff, end="" if diff.endswith("\n") else "\n")

  if not args.apply:
    print("dryRun=true")
    return 0

  telemetry_target.parent.mkdir(parents=True, exist_ok=True)
  try:
    shutil.copyfile(TELEMETRY_SOURCE, telemetry_target)
    modeld_path.write_text(patched, encoding="utf-8")
    py_compile.compile(str(telemetry_target), doraise=True)
    py_compile.compile(str(modeld_path), doraise=True)
    verify_stage2_path_unchanged(current, modeld_path.read_text(encoding="utf-8"))
  except Exception:
    modeld_path.write_text(current, encoding="utf-8")
    try:
      telemetry_target.unlink()
    except FileNotFoundError:
      pass
    raise

  print("applyStage2=true\npostWriteVerification=PASS")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
