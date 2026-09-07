"""Classify local Carrot source compatibility against reviewed code blobs.

Branch HEAD alone is not a sufficient integration boundary for a fast-moving
experimental branch. A documentation-only commit can legitimately move HEAD
without changing the code paths EGPU-Future relies on. Conversely, one
critical code blob changing is enough to require re-review.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SourceCompatibility(str, Enum):
  EXACT_REVIEWED_HEAD = "EXACT_REVIEWED_HEAD"
  CODE_EQUIVALENT_HEAD_DRIFT = "CODE_EQUIVALENT_HEAD_DRIFT"
  REVIEW_REQUIRED = "REVIEW_REQUIRED"


# These blobs were independently re-read on 2026-09-07 at the then-current
# carrot-egpu-yolo tip 1310ed43... . They intentionally cover only code that
# materially affects commissioning, model publication, manager reload behavior,
# and QCOM hardware profiling assumptions.
REVIEWED_HEADS = {
  "2c508b1dde53b9a996546993e1c7b5b74b489541",
  "1310ed43fe70a903d31589295f4dabe37649dab2",
}

CRITICAL_BLOBS = {
  "openpilot/selfdrive/modeld/modeld.py": "e4de3eb2236f6bb0c54c87666099147311602f4f",
  "openpilot/selfdrive/modeld/fill_model_msg.py": "1bffbcc5202d64e42b3832a4ab9ee0f72ff85bd1",
  "openpilot/system/manager/process.py": "a4b548fe597cb27ca38962b3e1cba52ca861eaab",
  "openpilot/system/manager/process_config.py": "f96c53dbdf9d0cb2670f0ccdeca8faf96ef8b735",
  "openpilot/system/manager/manager.py": "15c518989e3f056376656a4409d55c29fd621f08",
  "launch_chffrplus.sh": "d49e055b572a1789ea841c3c6717183fc0b21d30",
  "tinygrad_repo/tinygrad/runtime/support/hcq.py": "9d87005226f4141a77eb956abb38c50c3d2fb203",
  "tinygrad_repo/tinygrad/runtime/ops_qcom.py": "6eb3dc25b576385db6574aec7a9660deaa489ec3",
}


@dataclass(frozen=True)
class SourceCompatibilityResult:
  status: SourceCompatibility
  head: str
  mismatched_blobs: dict[str, dict[str, str | None]]
  missing_paths: tuple[str, ...]
  notes: tuple[str, ...]

  @property
  def code_compatible(self) -> bool:
    return self.status in {
      SourceCompatibility.EXACT_REVIEWED_HEAD,
      SourceCompatibility.CODE_EQUIVALENT_HEAD_DRIFT,
    }


def evaluate_source_compatibility(
  head: str,
  observed_blobs: dict[str, str | None],
  *,
  reviewed_heads: set[str] | None = None,
  critical_blobs: dict[str, str] | None = None,
) -> SourceCompatibilityResult:
  reviewed_heads = REVIEWED_HEADS if reviewed_heads is None else reviewed_heads
  critical_blobs = CRITICAL_BLOBS if critical_blobs is None else critical_blobs

  mismatched: dict[str, dict[str, str | None]] = {}
  missing: list[str] = []
  for path, expected in critical_blobs.items():
    observed = observed_blobs.get(path)
    if observed is None:
      missing.append(path)
      mismatched[path] = {"expected": expected, "observed": None}
    elif observed != expected:
      mismatched[path] = {"expected": expected, "observed": observed}

  if mismatched:
    notes = ["one_or_more_critical_code_blobs_changed"]
    if missing:
      notes.append("one_or_more_critical_paths_missing")
    return SourceCompatibilityResult(
      SourceCompatibility.REVIEW_REQUIRED,
      head,
      mismatched,
      tuple(sorted(missing)),
      tuple(notes),
    )

  if head in reviewed_heads:
    return SourceCompatibilityResult(
      SourceCompatibility.EXACT_REVIEWED_HEAD,
      head,
      {},
      (),
      ("head_and_all_critical_code_blobs_reviewed",),
    )

  return SourceCompatibilityResult(
    SourceCompatibility.CODE_EQUIVALENT_HEAD_DRIFT,
    head,
    {},
    (),
    (
      "head_changed_but_all_reviewed_critical_code_blobs_are_identical",
      "documentation_or_noncritical_changes_may_exist_and_are_not_implicitly_reviewed",
    ),
  )


def result_to_dict(result: SourceCompatibilityResult) -> dict:
  return {
    "status": result.status.value,
    "codeCompatible": result.code_compatible,
    "head": result.head,
    "reviewedHeads": sorted(REVIEWED_HEADS),
    "criticalBlobs": CRITICAL_BLOBS,
    "mismatchedBlobs": result.mismatched_blobs,
    "missingPaths": list(result.missing_paths),
    "notes": list(result.notes),
  }
