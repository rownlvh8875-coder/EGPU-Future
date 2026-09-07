from egpu_future.kernel_timeline import ModelWindow, correlate_window, model_window_from_shadow_event, summarize_correlations
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


def test_model_window_reconstructed_from_existing_timing_fields():
  row = {
    "type": "shadow_output",
    "frameId": 20,
    "cameraTimestampEofNs": 10_000_000,
    "timing": {
      "capture_to_done_ms": 8.0,
      "model_call_total_ms": 5.0,
      "call_to_enqueue_ms": 1.5,
    },
  }
  w = model_window_from_shadow_event(row)
  assert w is not None
  assert w.start_us == 13_000.0
  assert w.end_us == 18_000.0
  assert w.enqueue_us == 14_500.0


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


def test_summarize_correlations():
  rows = [
    {"modelCallMs": 10.0, "kernelCount": 2, "firstKernelDelayMs": 1.0, "enqueueToFirstKernelMs": 0.5,
     "kernelEnvelopeMs": 7.0, "kernelBusyMs": 6.0, "afterLastKernelMs": 2.0, "coveredByHardwareProfile": True},
    {"modelCallMs": 11.0, "kernelCount": 0, "firstKernelDelayMs": None, "enqueueToFirstKernelMs": None,
     "kernelEnvelopeMs": None, "kernelBusyMs": 0.0, "afterLastKernelMs": None, "coveredByHardwareProfile": False},
  ]
  s = summarize_correlations(rows)
  assert s["frames"] == 2
  assert s["coveredFrames"] == 1
  assert s["coverage"] == 0.5
  assert s["kernelCountTotal"] == 2
  assert s["modelCall"]["p50Ms"] == 10.5
  assert s["kernelBusy"]["meanMs"] == 6.0
