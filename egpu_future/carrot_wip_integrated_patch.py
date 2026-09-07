"""Reversible Stage-1 patch for the Carrot-WIP integrated eGPU branch."""
from __future__ import annotations

from dataclasses import dataclass


PINNED_CARROT_WIP_HEAD = "b2a2db5590f28af420ed01e75c145ddb8ddd90d6"
PINNED_MODELD_BLOB = "e4de3eb2236f6bb0c54c87666099147311602f4f"
TARGET_MODELD_PATH = "openpilot/selfdrive/modeld/modeld.py"
TARGET_OBSERVER_PATH = "openpilot/selfdrive/modeld/egpu_integration_observer.py"

IMPORT_BLOCK = """# EGPU-INTEGRATED OBSERVER IMPORT BEGIN\nfrom openpilot.selfdrive.modeld.egpu_integration_observer import EgpuIntegrationObserver\n# EGPU-INTEGRATED OBSERVER IMPORT END\n"""

INIT_BLOCK = """  # EGPU-INTEGRATED OBSERVER INIT BEGIN\n  egpu_observer = EgpuIntegrationObserver()\n  # EGPU-INTEGRATED OBSERVER INIT END\n"""

ATTEMPT_BLOCK = """    # EGPU-INTEGRATED OBSERVER ATTEMPT BEGIN\n    egpu_attempted_backend = \"egpu\" if bool(getattr(model, \"usbgpu\", False)) else \"qcom\"\n    # EGPU-INTEGRATED OBSERVER ATTEMPT END\n"""

FALLBACK_BLOCK = """      # EGPU-INTEGRATED OBSERVER FALLBACK BEGIN\n      egpu_observer.note_fallback(frame_id=meta_main.frame_id, reason=\"runtime_model_execution_failed\")\n      # EGPU-INTEGRATED OBSERVER FALLBACK END\n"""

OBSERVE_BLOCK = """    # EGPU-INTEGRATED OBSERVER SAMPLE BEGIN\n    egpu_observer.observe(\n      frame_id=meta_main.frame_id,\n      state_frame_id=frame_id,\n      attempted_backend=egpu_attempted_backend,\n      active_backend=\"egpu\" if bool(getattr(model, \"usbgpu\", False)) else \"qcom\",\n      model_execution_s=model_execution_time,\n    )\n    # EGPU-INTEGRATED OBSERVER SAMPLE END\n"""


@dataclass(frozen=True)
class PatchSummary:
  imports: int
  init: int
  attempt: int
  fallback: int
  sample: int

  @property
  def complete(self) -> bool:
    return (self.imports, self.init, self.attempt, self.fallback, self.sample) == (1, 1, 1, 1, 1)


def patch_summary(source: str) -> PatchSummary:
  return PatchSummary(
    source.count("EGPU-INTEGRATED OBSERVER IMPORT BEGIN"),
    source.count("EGPU-INTEGRATED OBSERVER INIT BEGIN"),
    source.count("EGPU-INTEGRATED OBSERVER ATTEMPT BEGIN"),
    source.count("EGPU-INTEGRATED OBSERVER FALLBACK BEGIN"),
    source.count("EGPU-INTEGRATED OBSERVER SAMPLE BEGIN"),
  )


def _insert_once(source: str, anchor: str, replacement: str, name: str) -> str:
  count = source.count(anchor)
  if count != 1:
    raise ValueError(f"expected exactly one {name} anchor, found {count}")
  return source.replace(anchor, replacement, 1)


def patch_modeld_text(source: str) -> str:
  existing = patch_summary(source)
  if any((existing.imports, existing.init, existing.attempt, existing.fallback, existing.sample)):
    if existing.complete:
      return source
    raise ValueError(f"partial integrated observer patch detected: {existing}")

  import_anchor = "from openpilot.selfdrive.modeld.constants import ModelConstants, Plan\n"
  source = _insert_once(source, import_anchor, import_anchor + IMPORT_BLOCK, "import")

  init_anchor = "  params = Params()\n  usbgpu_pkl_path = usbgpu_compiled_path()\n"
  source = _insert_once(source, init_anchor,
                        "  params = Params()\n" + INIT_BLOCK + "  usbgpu_pkl_path = usbgpu_compiled_path()\n",
                        "observer init")

  attempt_anchor = "    mt1 = time.perf_counter()\n    try:\n      model_output = model.run(bufs, transforms, inputs, prepare_only)\n"
  source = _insert_once(source, attempt_anchor, ATTEMPT_BLOCK + attempt_anchor, "model attempt")

  fallback_anchor = (
    "      # Run the already-loaded internal model for this same camera frame. A\n"
    "      # missing modelV2 frame during fallback can otherwise cascade into a\n"
    "      # misleading communication/CAN error while selfdrived waits for modeld.\n"
    "      model_output = model.run(bufs, transforms, inputs, prepare_only)\n"
  )
  source = _insert_once(source, fallback_anchor, FALLBACK_BLOCK + fallback_anchor, "same-frame fallback")

  sample_anchor = "    model_execution_time = mt2 - mt1\n\n    if model_output is not None:\n"
  source = _insert_once(source, sample_anchor,
                        "    model_execution_time = mt2 - mt1\n" + OBSERVE_BLOCK + "\n    if model_output is not None:\n",
                        "model execution sample")

  summary = patch_summary(source)
  if not summary.complete:
    raise AssertionError(f"generated incomplete patch: {summary}")
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


def strip_integration_blocks(source: str) -> str:
  for begin, end in (
    ("# EGPU-INTEGRATED OBSERVER IMPORT BEGIN", "# EGPU-INTEGRATED OBSERVER IMPORT END"),
    ("# EGPU-INTEGRATED OBSERVER INIT BEGIN", "# EGPU-INTEGRATED OBSERVER INIT END"),
    ("# EGPU-INTEGRATED OBSERVER ATTEMPT BEGIN", "# EGPU-INTEGRATED OBSERVER ATTEMPT END"),
    ("# EGPU-INTEGRATED OBSERVER FALLBACK BEGIN", "# EGPU-INTEGRATED OBSERVER FALLBACK END"),
    ("# EGPU-INTEGRATED OBSERVER SAMPLE BEGIN", "# EGPU-INTEGRATED OBSERVER SAMPLE END"),
  ):
    source = _strip_block(source, begin, end)
  return source


def verify_control_path_unchanged(original: str, patched: str) -> None:
  summary = patch_summary(patched)
  if not summary.complete:
    raise ValueError(f"patch markers incomplete: {summary}")
  if strip_integration_blocks(patched) != original:
    raise ValueError("removing observer markers does not restore original modeld.py byte-for-byte")

  for landmark in (
    "model_output = model.run(bufs, transforms, inputs, prepare_only)",
    'cloudlog.exception("eGPU model failed, falling back to internal GPU")',
    'params.put_bool("UsbGpuActive", False)',
    "model = small_model",
    "pm.send('modelV2', modelv2_send)",
  ):
    if landmark not in patched:
      raise ValueError(f"control/fallback landmark disappeared: {landmark}")
