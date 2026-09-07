from egpu_future.kernel_timeline import ModelWindow, correlate_window, model_window_from_shadow_event
from egpu_future.tinygrad_profile import KernelRange


def test_model_window_from_shadow_event():
  row = {
    "type": "shadow_output",
    "frameId": 10,
    "hostTimestampsNs": {
      "modelCallStart": 1_000_000,
      "deviceEnqueued": 1_100_000,
      "inferenceDone": 5_000_000,
    },
  }
  w = model_window_from_shadow_event(row)
  assert w is not None
  assert w.frame_id == 10
  assert w.start_us == 1000.0
  assert w.end_us == 5000.0
  assert w.enqueue_us == 1100.0


def test_correlate_window_hardware_profile():
  w = ModelWindow(frame_id=7, start_us=1000, end_us=6000, enqueue_us=1200)
  kernels = [
    KernelRange("QCOM", "warp", 1500, 2500),
    KernelRange("QCOM", "policy", 3000, 5500),
    KernelRange("QCOM", "other", 7000, 7100),
  ]
  r = correlate_window(w, kernels)
  assert r["kernelCount"] == 2
  assert r["firstKernelDelayMs"] == 0.5
  assert r["enqueueToFirstKernelMs"] == 0.3
  assert r["kernelEnvelopeMs"] == 4.0
  assert r["kernelBusyMs"] == 3.5
  assert r["afterLastKernelMs"] == 0.5
  assert r["firstKernel"] == "warp"
  assert r["lastKernel"] == "policy"


def test_correlate_window_without_kernels():
  r = correlate_window(ModelWindow(1, 0, 1000), [])
  assert r["coveredByHardwareProfile"] is False
  assert r["kernelCount"] == 0
