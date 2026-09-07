"""Reversible Stage-2 telemetry patch layered on the reviewed Stage-1 Carrot-WIP patch."""
from __future__ import annotations

from dataclasses import dataclass

from egpu_future.carrot_wip_integrated_patch import patch_summary as stage1_summary


TARGET_TELEMETRY_PATH = "openpilot/selfdrive/modeld/egpu_hardware_telemetry.py"

TELEMETRY_IMPORT_BLOCK = """# EGPU-INTEGRATED TELEMETRY IMPORT BEGIN\nfrom openpilot.selfdrive.modeld.egpu_hardware_telemetry import EgpuHardwareTelemetry\n# EGPU-INTEGRATED TELEMETRY IMPORT END\n"""

TELEMETRY_INIT_BLOCK = """  # EGPU-INTEGRATED TELEMETRY INIT BEGIN\n  egpu_hardware_telemetry = EgpuHardwareTelemetry()\n  egpu_hardware_telemetry.start()\n  # EGPU-INTEGRATED TELEMETRY INIT END\n"""


@dataclass(frozen=True)
class Stage2PatchSummary:
  imports: int
  init: int

  @property
  def complete(self) -> bool:
    return (self.imports, self.init) == (1, 1)


def stage2_patch_summary(source: str) -> Stage2PatchSummary:
  return Stage2PatchSummary(
    source.count("EGPU-INTEGRATED TELEMETRY IMPORT BEGIN"),
    source.count("EGPU-INTEGRATED TELEMETRY INIT BEGIN"),
  )


def _insert_once(source: str, anchor: str, replacement: str, name: str) -> str:
  count = source.count(anchor)
  if count != 1:
    raise ValueError(f"expected exactly one {name} anchor, found {count}")
  return source.replace(anchor, replacement, 1)


def patch_stage2_text(stage1_source: str) -> str:
  if not stage1_summary(stage1_source).complete:
    raise ValueError("Stage-2 requires a complete reviewed Stage-1 observer patch")

  existing = stage2_patch_summary(stage1_source)
  if any((existing.imports, existing.init)):
    if existing.complete:
      return stage1_source
    raise ValueError(f"partial Stage-2 telemetry patch detected: {existing}")

  import_anchor = "# EGPU-INTEGRATED OBSERVER IMPORT END\n"
  source = _insert_once(stage1_source, import_anchor, import_anchor + TELEMETRY_IMPORT_BLOCK, "telemetry import")

  init_anchor = "  # EGPU-INTEGRATED OBSERVER INIT END\n"
  source = _insert_once(source, init_anchor, init_anchor + TELEMETRY_INIT_BLOCK, "telemetry init")

  summary = stage2_patch_summary(source)
  if not summary.complete:
    raise AssertionError(f"generated incomplete Stage-2 patch: {summary}")
  return source


def _strip_block(source: str, begin: str, end: str) -> str:
  begin_pos = source.find(begin)
  if begin_pos < 0:
    return source
  end_pos = source.find(end, begin_pos)
  if end_pos < 0:
    raise ValueError(f"unterminated marker block: {begin}")
  end_pos += len(end)
  line_start = source.rfind("\n", 0, begin_pos) + 1
  if end_pos < len(source) and source[end_pos] == "\n":
    end_pos += 1
  return source[:line_start] + source[end_pos:]


def strip_stage2_blocks(source: str) -> str:
  for begin, end in (
    ("# EGPU-INTEGRATED TELEMETRY IMPORT BEGIN", "# EGPU-INTEGRATED TELEMETRY IMPORT END"),
    ("# EGPU-INTEGRATED TELEMETRY INIT BEGIN", "# EGPU-INTEGRATED TELEMETRY INIT END"),
  ):
    source = _strip_block(source, begin, end)
  return source


def verify_stage2_path_unchanged(stage1_source: str, stage2_source: str) -> None:
  summary = stage2_patch_summary(stage2_source)
  if not summary.complete:
    raise ValueError(f"Stage-2 markers incomplete: {summary}")
  if strip_stage2_blocks(stage2_source) != stage1_source:
    raise ValueError("removing Stage-2 markers does not restore Stage-1 modeld.py byte-for-byte")

  # Stage-2 may observe hardware but must not touch model execution/fallback/control landmarks.
  for landmark in (
    'cloudlog.exception("eGPU model failed, falling back to internal GPU")',
    'params.put_bool("UsbGpuActive", False)',
    "model = small_model",
    "model_output = model.run(bufs, transforms, inputs, prepare_only)",
    "pm.send('modelV2', modelv2_send)",
  ):
    if landmark not in stage2_source:
      raise ValueError(f"control/fallback landmark disappeared: {landmark}")
