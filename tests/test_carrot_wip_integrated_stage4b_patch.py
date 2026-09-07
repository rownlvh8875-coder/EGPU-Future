from egpu_future.carrot_wip_integrated_patch import patch_modeld_text, strip_integration_blocks
from egpu_future.carrot_wip_integrated_stage2_patch import patch_stage2_text, strip_stage2_blocks
from egpu_future.carrot_wip_integrated_stage4b_patch import patch_stage4b_text, strip_stage4b_blocks, verify_stage4b_path_unchanged


SOURCE = '''#!/usr/bin/env python3
import time
from openpilot.selfdrive.modeld.constants import ModelConstants, Plan


def main():
  params = Params()
  usbgpu_pkl_path = usbgpu_compiled_path()
  model = small_model
  meta_main = Obj(); meta_main.frame_id = 10
  meta_extra = Obj(); meta_extra.frame_id = 10
  frame_id = 10
  v_ego = 0.0
  model_transform_main = model_transform_extra = []
  inputs = {"desire_pulse": [], "traffic_convention": [], "action_t": []}
  prepare_only = False
  sm = {"carState": Obj(), "carControl": Obj()}

    mt1 = time.perf_counter()
    try:
      model_output = model.run(bufs, transforms, inputs, prepare_only)
    except Exception:
      if not params.get_bool("UsbGpuActive") or small_model is None:
        raise
      cloudlog.exception("eGPU model failed, falling back to internal GPU")
      params.put_bool("UsbGpuActive", False)
      model = small_model
      run_count = 0
      # Run the already-loaded internal model for this same camera frame. A
      # missing modelV2 frame during fallback can otherwise cascade into a
      # misleading communication/CAN error while selfdrived waits for modeld.
      model_output = model.run(bufs, transforms, inputs, prepare_only)
    mt2 = time.perf_counter()
    model_execution_time = mt2 - mt1

    if model_output is not None:
      pm.send('modelV2', modelv2_send)
'''


def test_stage4b_layers_after_stage2_and_restores_every_layer():
  s1 = patch_modeld_text(SOURCE)
  s2 = patch_stage2_text(s1)
  s4b = patch_stage4b_text(s2)
  verify_stage4b_path_unchanged(s2, s4b)
  assert strip_stage4b_blocks(s4b) == s2
  assert strip_stage2_blocks(strip_stage4b_blocks(s4b)) == s1
  assert strip_integration_blocks(strip_stage2_blocks(strip_stage4b_blocks(s4b))) == SOURCE
  assert 'if not prepare_only:' in s4b
  assert 'car_state=sm["carState"]' in s4b
  assert 'car_control=sm["carControl"]' in s4b


def test_stage4b_does_not_change_same_frame_fallback():
  s1 = patch_modeld_text(SOURCE)
  s2 = patch_stage2_text(s1)
  s4b = patch_stage4b_text(s2)
  required = '''      # Run the already-loaded internal model for this same camera frame. A
      # missing modelV2 frame during fallback can otherwise cascade into a
      # misleading communication/CAN error while selfdrived waits for modeld.
      model_output = model.run(bufs, transforms, inputs, prepare_only)'''
  assert required in s4b
