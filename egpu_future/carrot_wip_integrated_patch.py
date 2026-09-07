"""Reversible Stage-1 patch for the Carrot-WIP integrated eGPU branch."""
from __future__ import annotations

from dataclasses import dataclass


# 6f4c00e6 is one commit after the original S0 review. That commit only changed
# Hyundai PV5/navigation-speed files and left every pinned eGPU/modeld critical
# blob unchanged, so the reviewed modeld boundary remains the same.
PINNED_CARROT_WIP_HEAD = "6f4c00e625dc3d41d3776427a272a5c3fed75e6c"
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
  summary = patch_summary(source)
  if any((summary.imports, summary.init, summary.attempt, summary.fallback, summary.sample)):
    if summary.complete:
      return source
    raise ValueError(f"partial integrated observer patch detected: {summary}")

  import_anchor = "from openpilot.selfdrive.modeld.constants import ModelConstants, Plan\n"
  source = _insert_once(source, import_anchor, import_anchor + IMPORT_BLOCK, "observer import")

  init_anchor = "  params = Params()\n  usbgpu_pkl_path = usbgpu_compiled_path()\n"
  source = _insert_once(
    source,
    init_anchor,
    "  params = Params()\n" + INIT_BLOCK + "  usbgpu_pkl_path = usbgpu_compiled_path()\n",
    "observer init",
  )

  attempt_anchor = "    mt1 = time.perf_counter()\n    try:\n      model_output = model.run(bufs, transforms, inputs, prepare_only)\n"
  source = _insert_once(source, attempt_anchor, ATTEMPT_BLOCK + attempt_anchor, "model attempt")

  fallback_anchor = "      model = small_model\n      run_count = 0\n      # Run the already-loaded internal model for this same camera frame. A\n"
  source = _insert_once(
    source,
    fallback_anchor,
    "      model = small_model\n      run_count = 0\n" + FALLBACK_BLOCK + "      # Run the already-loaded internal model for this same camera frame. A\n",
    "same-frame fallback",
  )

  sample_anchor = "    mt2 = time.perf_counter()\n    model_execution_time = mt2 - mt1\n\n    if model_output is not None:\n"
  source = _insert_once(
    source,
    sample_anchor,
    "    mt2 = time.perf_counter()\n    model_execution_time = mt2 - mt1\n" + OBSERVE_BLOCK + "\n    if model_output is not None:\n",
    "observer sample",
  )

  result = patch_summary(source)
  if not result.complete:
    raise AssertionError(f"generated incomplete observer patch: {result}")
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
    raise ValueError(f"observer patch markers incomplete: {summary}")
  restored = strip_integration_blocks(patched)
  if restored != original:
    raise ValueError("removing integrated observer markers does not restore modeld.py byte-for-byte")

  required = (
    'model_output = model.run(bufs, transforms, inputs, prepare_only)',
    'cloudlog.exception("eGPU model failed, falling back to internal GPU")',
    'params.put_bool("UsbGpuActive", False)',
    'model = small_model',
    "pm.send('modelV2', modelv2_send)",
  )
  for line in required:
    if line not in patched:
      raise ValueError(f"control/fallback landmark disappeared: {line}")
