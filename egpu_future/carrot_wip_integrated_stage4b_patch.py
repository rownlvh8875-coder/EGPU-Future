"""Reversible Stage-4B parked shadow-tap patch layered on S1+S2 modeld."""
from __future__ import annotations

from dataclasses import dataclass

from egpu_future.carrot_wip_integrated_patch import patch_summary as stage1_summary
from egpu_future.carrot_wip_integrated_stage2_patch import stage2_patch_summary


TARGET_SHADOW_TAP_PATH = "openpilot/selfdrive/modeld/egpu_integrated_shadow_tap.py"

IMPORT_BLOCK = """# EGPU-INTEGRATED SHADOW TAP IMPORT BEGIN\nfrom openpilot.selfdrive.modeld.egpu_integrated_shadow_tap import IntegratedShadowTap\n# EGPU-INTEGRATED SHADOW TAP IMPORT END\n"""
INIT_BLOCK = """  # EGPU-INTEGRATED SHADOW TAP INIT BEGIN\n  egpu_integrated_shadow_tap = IntegratedShadowTap()\n  # EGPU-INTEGRATED SHADOW TAP INIT END\n"""
SEND_BLOCK = """    # EGPU-INTEGRATED SHADOW TAP SEND BEGIN\n    if not prepare_only:\n      egpu_integrated_shadow_tap.send(\n        model=model, meta_main=meta_main, meta_extra=meta_extra, state_frame_id=frame_id, v_ego=v_ego,\n        car_state=sm[\"carState\"], car_control=sm[\"carControl\"],\n        transform_main=model_transform_main, transform_extra=model_transform_extra, inputs=inputs,\n      )\n    # EGPU-INTEGRATED SHADOW TAP SEND END\n"""


@dataclass(frozen=True)
class Stage4BPatchSummary:
  imports: int
  init: int
  send: int

  @property
  def complete(self) -> bool:
    return (self.imports, self.init, self.send) == (1, 1, 1)


def patch_summary(source: str) -> Stage4BPatchSummary:
  return Stage4BPatchSummary(
    source.count("EGPU-INTEGRATED SHADOW TAP IMPORT BEGIN"),
    source.count("EGPU-INTEGRATED SHADOW TAP INIT BEGIN"),
    source.count("EGPU-INTEGRATED SHADOW TAP SEND BEGIN"),
  )


def _insert_once(source: str, anchor: str, replacement: str, name: str) -> str:
  n = source.count(anchor)
  if n != 1:
    raise ValueError(f"expected exactly one {name} anchor, found {n}")
  return source.replace(anchor, replacement, 1)


def patch_stage4b_text(stage2_source: str) -> str:
  if not stage1_summary(stage2_source).complete or not stage2_patch_summary(stage2_source).complete:
    raise ValueError("Stage-4B requires complete Stage-1 and Stage-2 patches")
  current = patch_summary(stage2_source)
  if any((current.imports, current.init, current.send)):
    if current.complete:
      return stage2_source
    raise ValueError(f"partial Stage-4B patch detected: {current}")

  import_anchor = "# EGPU-INTEGRATED TELEMETRY IMPORT END\n"
  source = _insert_once(stage2_source, import_anchor, import_anchor + IMPORT_BLOCK, "shadow tap import")
  init_anchor = "  # EGPU-INTEGRATED TELEMETRY INIT END\n"
  source = _insert_once(source, init_anchor, init_anchor + INIT_BLOCK, "shadow tap init")
  send_anchor = "    # EGPU-INTEGRATED OBSERVER ATTEMPT BEGIN\n"
  source = _insert_once(source, send_anchor, SEND_BLOCK + send_anchor, "pre-model shadow tap send")

  result = patch_summary(source)
  if not result.complete:
    raise AssertionError(f"generated incomplete Stage-4B patch: {result}")
  return source


def _strip_block(source: str, begin: str, end: str) -> str:
  a = source.find(begin)
  if a < 0:
    return source
  b = source.find(end, a)
  if b < 0:
    raise ValueError(f"unterminated marker block: {begin}")
  b += len(end)
  line_start = source.rfind("\n", 0, a) + 1
  if b < len(source) and source[b] == "\n":
    b += 1
  return source[:line_start] + source[b:]


def strip_stage4b_blocks(source: str) -> str:
  for begin, end in (
    ("# EGPU-INTEGRATED SHADOW TAP IMPORT BEGIN", "# EGPU-INTEGRATED SHADOW TAP IMPORT END"),
    ("# EGPU-INTEGRATED SHADOW TAP INIT BEGIN", "# EGPU-INTEGRATED SHADOW TAP INIT END"),
    ("# EGPU-INTEGRATED SHADOW TAP SEND BEGIN", "# EGPU-INTEGRATED SHADOW TAP SEND END"),
  ):
    source = _strip_block(source, begin, end)
  return source


def verify_stage4b_path_unchanged(stage2_source: str, stage4b_source: str) -> None:
  if not patch_summary(stage4b_source).complete:
    raise ValueError("Stage-4B markers incomplete")
  if strip_stage4b_blocks(stage4b_source) != stage2_source:
    raise ValueError("removing Stage-4B markers does not restore Stage-2 modeld.py byte-for-byte")
  for landmark in (
    'model_output = model.run(bufs, transforms, inputs, prepare_only)',
    'cloudlog.exception("eGPU model failed, falling back to internal GPU")',
    'model = small_model',
    "pm.send('modelV2', modelv2_send)",
  ):
    if landmark not in stage4b_source:
      raise ValueError(f"control/fallback landmark disappeared: {landmark}")
