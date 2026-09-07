import pytest

from egpu_future.carrot_wip_integrated_patch import (
  patch_modeld_text,
  patch_summary,
  strip_integration_blocks,
  verify_control_path_unchanged,
)


SOURCE = '''#!/usr/bin/env python3
import time
from openpilot.selfdrive.modeld.constants import ModelConstants, Plan


def main():
  params = Params()
  usbgpu_pkl_path = usbgpu_compiled_path()
  model = small_model
  meta_main = Obj()
  meta_main.frame_id = 10
  frame_id = 10
  bufs = transforms = inputs = {}
  prepare_only = False

    mt1 = time.perf_counter()
    try:
      model_output = model.run(bufs, transforms, inputs, prepare_only)
    except Exception:
      if not params.get_bool("UsbGpuActive") or small_model is None:
        raise
      cloudlog.exception("eGPU model failed, falling back to internal GPU")
      params.put_bool("UsbGpuActive", False)
      model = small_model
      # Run the already-loaded internal model for this same camera frame. A
      # missing modelV2 frame during fallback can otherwise cascade into a
      # misleading communication/CAN error while selfdrived waits for modeld.
      model_output = model.run(bufs, transforms, inputs, prepare_only)
    mt2 = time.perf_counter()
    model_execution_time = mt2 - mt1

    if model_output is not None:
      pm.send('modelV2', modelv2_send)
'''


def test_stage1_patch_is_complete_and_byte_reversible():
  patched = patch_modeld_text(SOURCE)
  assert patch_summary(patched).complete
  verify_control_path_unchanged(SOURCE, patched)
  assert strip_integration_blocks(patched) == SOURCE
  assert 'egpu_attempted_backend = "egpu"' in patched
  assert 'egpu_observer.note_fallback' in patched
  assert 'active_backend="egpu"' in patched


def test_patch_is_idempotent_only_when_complete():
  patched = patch_modeld_text(SOURCE)
  assert patch_modeld_text(patched) == patched


def test_partial_patch_is_rejected():
  with pytest.raises(ValueError, match="partial"):
    patch_modeld_text(SOURCE + "\n# EGPU-INTEGRATED OBSERVER IMPORT BEGIN\n")


def test_missing_same_frame_fallback_anchor_is_rejected():
  broken = SOURCE.replace("      # Run the already-loaded internal model for this same camera frame. A\n", "")
  with pytest.raises(ValueError, match="same-frame fallback"):
    patch_modeld_text(broken)
