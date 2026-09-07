"""Generate and verify the minimal EGPU-Future metadata-tap patch for Carrot.

The patch is intentionally limited to three marked insertions in modeld.py:
1) one import,
2) one tap object construction after the first Params(),
3) one best-effort send immediately before the existing model.run timing block.

Removing the marked blocks must restore the original source byte-for-byte.
"""
from __future__ import annotations

from dataclasses import dataclass


PINNED_CARROT_HEAD = "2c508b1dde53b9a996546993e1c7b5b74b489541"
PINNED_MODELD_GIT_BLOB = "e4de3eb2236f6bb0c54c87666099147311602f4f"
TARGET_RUNTIME_PATH = "openpilot/selfdrive/modeld/egpu_future_shadow_tap.py"
TARGET_MODELD_PATH = "openpilot/selfdrive/modeld/modeld.py"

IMPORT_BLOCK = """# EGPU-FUTURE SHADOW TAP IMPORT BEGIN\nfrom openpilot.selfdrive.modeld.egpu_future_shadow_tap import EgpuFutureShadowTap\n# EGPU-FUTURE SHADOW TAP IMPORT END\n"""
INIT_BLOCK = """  # EGPU-FUTURE SHADOW TAP INIT BEGIN\n  shadow_tap = EgpuFutureShadowTap()\n  # EGPU-FUTURE SHADOW TAP INIT END\n"""
SEND_BLOCK = """    # EGPU-FUTURE SHADOW TAP SEND BEGIN\n    if shadow_tap.enabled and not prepare_only:\n      shadow_tap.send(\n        model=model,\n        meta_main=meta_main,\n        meta_extra=meta_extra,\n        state_frame_id=frame_id,\n        v_ego=v_ego,\n        transform_main=model_transform_main,\n        transform_extra=model_transform_extra,\n        inputs=inputs,\n      )\n    # EGPU-FUTURE SHADOW TAP SEND END\n\n"""


@dataclass(frozen=True)
class PatchSummary:
  imports_added: int
  init_blocks_added: int
  send_blocks_added: int

  @property
  def complete(self) -> bool:
    return self.imports_added == self.init_blocks_added == self.send_blocks_added == 1


def _insert_once(source: str, anchor: str, replacement: str, description: str) -> str:
  count = source.count(anchor)
  if count != 1:
    raise ValueError(f"expected exactly one {description} anchor, found {count}")
  return source.replace(anchor, replacement, 1)


def patch_modeld_text(source: str) -> str:
  if "EGPU-FUTURE SHADOW TAP IMPORT BEGIN" in source:
    # Idempotent only when all blocks are already present.
    summary = patch_summary(source)
    if not summary.complete:
      raise ValueError(f"partial EGPU-Future patch detected: {summary}")
    return source

  import_anchor = "from openpilot.selfdrive.modeld.constants import ModelConstants, Plan\n"
  source = _insert_once(source, import_anchor, import_anchor + IMPORT_BLOCK, "import")

  init_anchor = "  params = Params()\n  usbgpu_pkl_path = usbgpu_compiled_path()\n"
  source = _insert_once(
    source,
    init_anchor,
    "  params = Params()\n" + INIT_BLOCK + "  usbgpu_pkl_path = usbgpu_compiled_path()\n",
    "initial Params/usbgpu",
  )

  send_anchor = "    mt1 = time.perf_counter()\n    try:\n      model_output = model.run(bufs, transforms, inputs, prepare_only)\n"
  source = _insert_once(
    source,
    send_anchor,
    SEND_BLOCK + send_anchor,
    "model.run timing",
  )

  summary = patch_summary(source)
  if not summary.complete:
    raise AssertionError(f"generated incomplete patch: {summary}")
  return source


def patch_summary(source: str) -> PatchSummary:
  return PatchSummary(
    imports_added=source.count("EGPU-FUTURE SHADOW TAP IMPORT BEGIN"),
    init_blocks_added=source.count("EGPU-FUTURE SHADOW TAP INIT BEGIN"),
    send_blocks_added=source.count("EGPU-FUTURE SHADOW TAP SEND BEGIN"),
  )


def _strip_block(source: str, begin: str, end: str) -> str:
  begin_pos = source.find(begin)
  if begin_pos < 0:
    return source
  end_pos = source.find(end, begin_pos)
  if end_pos < 0:
    raise ValueError(f"unterminated marker block: {begin}")
  end_pos += len(end)
  # Marker strings do not contain their indentation. Remove the complete lines,
  # including a single trailing newline when present.
  line_start = source.rfind("\n", 0, begin_pos) + 1
  if end_pos < len(source) and source[end_pos] == "\n":
    end_pos += 1
  return source[:line_start] + source[end_pos:]


def strip_integration_blocks(patched: str) -> str:
  stripped = patched
  stripped = _strip_block(stripped, "# EGPU-FUTURE SHADOW TAP IMPORT BEGIN", "# EGPU-FUTURE SHADOW TAP IMPORT END")
  stripped = _strip_block(stripped, "# EGPU-FUTURE SHADOW TAP INIT BEGIN", "# EGPU-FUTURE SHADOW TAP INIT END")
  stripped = _strip_block(stripped, "# EGPU-FUTURE SHADOW TAP SEND BEGIN", "# EGPU-FUTURE SHADOW TAP SEND END")
  return stripped


def verify_control_path_unchanged(original: str, patched: str) -> None:
  summary = patch_summary(patched)
  if not summary.complete:
    raise ValueError(f"patch markers incomplete: {summary}")
  restored = strip_integration_blocks(patched)
  if restored != original:
    raise ValueError("removing EGPU-Future marker blocks does not restore original modeld.py byte-for-byte")

  required_original_lines = (
    'model_output = model.run(bufs, transforms, inputs, prepare_only)',
    'cloudlog.exception("eGPU model failed, falling back to internal GPU")',
    'model = small_model',
    'model_output = model.run(bufs, transforms, inputs, prepare_only)',
    "pm.send('modelV2', modelv2_send)",
  )
  for line in required_original_lines:
    if line not in patched:
      raise ValueError(f"control/fallback landmark disappeared: {line}")
