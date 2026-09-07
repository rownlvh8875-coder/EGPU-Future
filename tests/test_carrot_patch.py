import pytest

from egpu_future.carrot_patch import patch_modeld_text, patch_summary, strip_integration_blocks, verify_control_path_unchanged


SOURCE = '''#!/usr/bin/env python3
import time
import numpy as np
from openpilot.selfdrive.modeld.constants import ModelConstants, Plan


def main():
  params = Params()
  usbgpu_pkl_path = usbgpu_compiled_path()
  prepare_only = False
  model_transform_main = np.zeros((3, 3))
  model_transform_extra = np.zeros((3, 3))
  frame_id = 1
  v_ego = 0.0
  meta_main = meta_extra = None
  bufs = transforms = inputs = {}

    mt1 = time.perf_counter()
    try:
      model_output = model.run(bufs, transforms, inputs, prepare_only)
    except Exception:
      cloudlog.exception("eGPU model failed, falling back to internal GPU")
      model = small_model
      model_output = model.run(bufs, transforms, inputs, prepare_only)
    pm.send('modelV2', modelv2_send)
'''


def test_patch_is_marker_limited_and_reversible():
  patched = patch_modeld_text(SOURCE)
  summary = patch_summary(patched)
  assert summary.complete
  verify_control_path_unchanged(SOURCE, patched)
  assert strip_integration_blocks(patched) == SOURCE
  assert "if not prepare_only:" in patched
  assert "shadow_tap.send(" in patched
  assert "state_frame_id=frame_id" in patched
  # Dynamic control is internal to the standalone sender; active model logic
  # never branches on the tap result.
  assert "if shadow_tap.enabled" not in patched


def test_patch_is_idempotent_when_complete():
  patched = patch_modeld_text(SOURCE)
  assert patch_modeld_text(patched) == patched


def test_missing_anchor_is_rejected():
  with pytest.raises(ValueError, match="import"):
    patch_modeld_text(SOURCE.replace("from openpilot.selfdrive.modeld.constants import ModelConstants, Plan\n", ""))


def test_partial_marker_patch_is_rejected():
  partial = SOURCE + "\n# EGPU-FUTURE SHADOW TAP IMPORT BEGIN\n"
  with pytest.raises(ValueError, match="partial"):
    patch_modeld_text(partial)
