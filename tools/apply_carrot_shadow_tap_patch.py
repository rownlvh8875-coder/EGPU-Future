#!/usr/bin/env python3
"""Dry-run or apply the pinned minimal shadow-tap integration to a Carrot checkout.

Default is dry-run. `--apply` writes exactly two files in the target checkout:
- openpilot/selfdrive/modeld/modeld.py
- openpilot/selfdrive/modeld/egpu_future_shadow_tap.py

The tool refuses an unexpected branch HEAD/modeld blob or dirty target files by
default. It never edits vehicle controls, panda safety, or eGPU fallback logic.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import shutil
import subprocess

from egpu_future.carrot_patch import (
  PINNED_CARROT_HEAD,
  PINNED_MODELD_GIT_BLOB,
  TARGET_MODELD_PATH,
  TARGET_RUNTIME_PATH,
  patch_modeld_text,
  verify_control_path_unchanged,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = PROJECT_ROOT / "integrations/carrot/egpu_future_shadow_tap.py"


def git(repo: Path, *args: str) -> str:
  result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
  if result.returncode != 0:
    raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
  return result.stdout.strip()


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("repo", type=Path, help="local ajouatom/openpilot checkout")
  ap.add_argument("--apply", action="store_true", help="write files; default is dry-run")
  ap.add_argument("--allow-head-mismatch", action="store_true",
                  help="allow a different HEAD, but modeld blob/anchors must still match")
  ap.add_argument("--allow-modeld-mismatch", action="store_true",
                  help="expert-only: bypass pinned modeld blob check; marker/anchor verification still applies")
  args = ap.parse_args()

  repo = args.repo.resolve()
  modeld_path = repo / TARGET_MODELD_PATH
  runtime_target = repo / TARGET_RUNTIME_PATH
  if not modeld_path.is_file():
    raise SystemExit(f"missing target: {modeld_path}")
  if not RUNTIME_SOURCE.is_file():
    raise SystemExit(f"missing EGPU-Future runtime source: {RUNTIME_SOURCE}")

  head = git(repo, "rev-parse", "HEAD")
  if head != PINNED_CARROT_HEAD and not args.allow_head_mismatch:
    raise SystemExit(
      f"Carrot HEAD mismatch: got {head}, expected {PINNED_CARROT_HEAD}. "
      "Re-analyze the new branch tip before applying."
    )

  original = modeld_path.read_text(encoding="utf-8")
  if "EGPU-FUTURE SHADOW TAP" in original:
    raise SystemExit("target modeld.py already contains an EGPU-Future shadow-tap marker")

  modeld_blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  if modeld_blob != PINNED_MODELD_GIT_BLOB and not args.allow_modeld_mismatch:
    raise SystemExit(
      f"modeld blob mismatch: got {modeld_blob}, expected {PINNED_MODELD_GIT_BLOB}. "
      "Do not force this unless the new source was reviewed."
    )

  if args.apply:
    dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_RUNTIME_PATH)
    if dirty:
      raise SystemExit(f"refusing to modify dirty target files:\n{dirty}")
    if runtime_target.exists():
      raise SystemExit(f"refusing to overwrite existing runtime: {runtime_target}")

  patched = patch_modeld_text(original)
  verify_control_path_unchanged(original, patched)
  runtime_text = RUNTIME_SOURCE.read_text(encoding="utf-8")

  diff = "".join(difflib.unified_diff(
    original.splitlines(keepends=True),
    patched.splitlines(keepends=True),
    fromfile=f"a/{TARGET_MODELD_PATH}",
    tofile=f"b/{TARGET_MODELD_PATH}",
  ))
  print(f"targetHead={head}")
  print(f"modeldGitBlob={modeld_blob}")
  print(f"runtimeTarget={TARGET_RUNTIME_PATH}")
  print("controlPathVerification=PASS")
  print("\n--- modeld dry-run diff ---")
  print(diff, end="" if diff.endswith("\n") else "\n")

  if not args.apply:
    print("dryRun=true (no files changed)")
    return 0

  runtime_target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(RUNTIME_SOURCE, runtime_target)
  modeld_path.write_text(patched, encoding="utf-8")

  # Verify what was actually written.
  written = modeld_path.read_text(encoding="utf-8")
  verify_control_path_unchanged(original, written)
  print("apply=true")
  print("postWriteVerification=PASS")
  print("Next: compile/test while EGPU_FUTURE_SHADOW_TAP remains unset (disabled by default).")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
