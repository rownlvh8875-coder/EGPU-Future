import pytest

from egpu_future.carrot_wip_integrated_patch import patch_modeld_text, strip_integration_blocks
from egpu_future.carrot_wip_integrated_stage2_patch import (
  patch_stage2_text,
  stage2_patch_summary,
  strip_stage2_blocks,
  verify_stage2_path_unchanged,
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


def test_stage2_layers_on_stage1_and_is_byte_reversible():
  stage1 = patch_modeld_text(SOURCE)
  stage2 = patch_stage2_text(stage1)
  assert stage2_patch_summary(stage2).complete
  verify_stage2_path_unchanged(stage1, stage2)
  assert strip_stage2_blocks(stage2) == stage1
  assert strip_integration_blocks(strip_stage2_blocks(stage2)) == SOURCE
  assert "EgpuHardwareTelemetry" in stage2
  assert "egpu_hardware_telemetry.start()" in stage2


def test_stage2_requires_complete_stage1():
  with pytest.raises(ValueError, match="Stage-2 requires"):
    patch_stage2_text(SOURCE)


def test_stage2_is_idempotent_only_when_complete():
  stage1 = patch_modeld_text(SOURCE)
  stage2 = patch_stage2_text(stage1)
  assert patch_stage2_text(stage2) == stage2


def test_partial_stage2_patch_is_rejected():
  stage1 = patch_modeld_text(SOURCE)
  broken = stage1.replace(
    "# EGPU-INTEGRATED OBSERVER IMPORT END\n",
    "# EGPU-INTEGRATED OBSERVER IMPORT END\n# EGPU-INTEGRATED TELEMETRY IMPORT BEGIN\n",
    1,
  )
  with pytest.raises(ValueError, match="partial"):
    patch_stage2_text(broken)
