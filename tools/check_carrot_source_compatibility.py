#!/usr/bin/env python3
"""Check a local Carrot checkout against reviewed EGPU-Future code blobs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from egpu_future.source_compatibility import CRITICAL_BLOBS, evaluate_source_compatibility, result_to_dict


def git(repo: Path, *args: str) -> str:
  p = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
  if p.returncode != 0:
    raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
  return p.stdout.strip()


def main() -> int:
  ap = argparse.ArgumentParser(description="Classify local Carrot source compatibility by critical git blobs")
  ap.add_argument("repo", type=Path)
  ap.add_argument("--output", type=Path, default=None)
  args = ap.parse_args()

  repo = args.repo.resolve()
  if not repo.is_dir():
    raise SystemExit(f"missing repo: {repo}")

  head = git(repo, "rev-parse", "HEAD")
  observed: dict[str, str | None] = {}
  for path in CRITICAL_BLOBS:
    p = repo / path
    observed[path] = git(repo, "hash-object", path) if p.is_file() else None

  result = evaluate_source_compatibility(head, observed)
  data = result_to_dict(result)
  text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
  print(text, end="")
  if args.output is not None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
  return 0 if result.code_compatible else 2


if __name__ == "__main__":
  raise SystemExit(main())
