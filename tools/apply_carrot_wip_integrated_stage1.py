#!/usr/bin/env python3
"""Dry-run/apply/revert Stage-1 observer patch to a local carrot-wip checkout."""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import py_compile
import shutil
import subprocess

from egpu_future.carrot_wip_integrated_patch import (
  PINNED_CARROT_WIP_HEAD,
  PINNED_MODELD_BLOB,
  TARGET_MODELD_PATH,
  TARGET_OBSERVER_PATH,
  patch_modeld_text,
  strip_integration_blocks,
  verify_control_path_unchanged,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OBSERVER_SOURCE = PROJECT_ROOT / "integrations/carrot_wip_integrated/runtime/egpu_integration_observer.py"


def git(repo: Path, *args: str) -> str:
  p = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
  if p.returncode != 0:
    raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
  return p.stdout.strip()


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("repo", type=Path, help="local ajouatom/openpilot carrot-wip checkout")
  mode = ap.add_mutually_exclusive_group()
  mode.add_argument("--apply", action="store_true", help="write Stage-1 patch; default is dry-run")
  mode.add_argument("--revert", action="store_true", help="remove only Stage-1 marker blocks and observer runtime")
  ap.add_argument("--allow-head-drift", action="store_true",
                  help="allow different HEAD only when pinned modeld blob still matches")
  args = ap.parse_args()

  repo = args.repo.resolve()
  modeld_path = repo / TARGET_MODELD_PATH
  observer_target = repo / TARGET_OBSERVER_PATH
  if not modeld_path.is_file():
    raise SystemExit(f"missing modeld.py: {modeld_path}")

  head = git(repo, "rev-parse", "HEAD")
  if head != PINNED_CARROT_WIP_HEAD and not args.allow_head_drift:
    raise SystemExit(f"carrot-wip HEAD mismatch got={head} expected={PINNED_CARROT_WIP_HEAD}")

  current = modeld_path.read_text(encoding="utf-8")

  if args.revert:
    restored = strip_integration_blocks(current)
    if restored == current:
      raise SystemExit("Stage-1 observer markers not found")
    # The stripped source must be the exact reviewed carrot-wip modeld.
    tmp = modeld_path.with_suffix(".egpu-integrated-verify.py")
    try:
      tmp.write_text(restored, encoding="utf-8")
      restored_blob = git(repo, "hash-object", str(tmp.relative_to(repo)))
    finally:
      try:
        tmp.unlink()
      except FileNotFoundError:
        pass
    if restored_blob != PINNED_MODELD_BLOB:
      raise SystemExit(f"revert result blob mismatch got={restored_blob} expected={PINNED_MODELD_BLOB}")
    modeld_path.write_text(restored, encoding="utf-8")
    if observer_target.exists():
      observer_target.unlink()
    print(f"reverted=true\nhead={head}\nmodeldBlob={restored_blob}")
    return 0

  if "EGPU-INTEGRATED OBSERVER" in current:
    raise SystemExit("Stage-1 observer patch already present")
  blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  if blob != PINNED_MODELD_BLOB:
    raise SystemExit(f"modeld blob mismatch got={blob} expected={PINNED_MODELD_BLOB}; re-review source before patching")
  if not OBSERVER_SOURCE.is_file():
    raise SystemExit(f"missing observer source: {OBSERVER_SOURCE}")
  if args.apply:
    dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_OBSERVER_PATH)
    if dirty:
      raise SystemExit(f"refusing dirty targets:\n{dirty}")
    if observer_target.exists():
      raise SystemExit(f"observer runtime already exists: {observer_target}")

  patched = patch_modeld_text(current)
  verify_control_path_unchanged(current, patched)
  diff = "".join(difflib.unified_diff(
    current.splitlines(keepends=True), patched.splitlines(keepends=True),
    fromfile=f"a/{TARGET_MODELD_PATH}", tofile=f"b/{TARGET_MODELD_PATH}",
  ))
  print(f"head={head}\nmodeldBlob={blob}\ncontrolPathVerification=PASS")
  print(diff, end="" if diff.endswith("\n") else "\n")

  if not args.apply:
    print("dryRun=true")
    return 0

  observer_target.parent.mkdir(parents=True, exist_ok=True)
  try:
    shutil.copyfile(OBSERVER_SOURCE, observer_target)
    modeld_path.write_text(patched, encoding="utf-8")
    py_compile.compile(str(observer_target), doraise=True)
    py_compile.compile(str(modeld_path), doraise=True)
    verify_control_path_unchanged(current, modeld_path.read_text(encoding="utf-8"))
  except Exception:
    modeld_path.write_text(current, encoding="utf-8")
    try:
      observer_target.unlink()
    except FileNotFoundError:
      pass
    raise

  print("apply=true\npostWriteVerification=PASS")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
