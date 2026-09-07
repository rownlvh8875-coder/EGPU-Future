from types import SimpleNamespace

from egpu_future.tinygrad_profile import normalize_profile_event, normalize_profile_events, summarize_kernel_ranges


def test_normalize_profile_event_object_and_dict():
  obj = SimpleNamespace(device="QCOM", name="kernel_a", st=1000, en=2500)
  row = normalize_profile_event(obj)
  assert row is not None
  assert row.device == "QCOM"
  assert row.duration_ms == 1.5

  row2 = normalize_profile_event({"device": "AMD", "name": "kernel_b", "st": 10, "en": 20})
  assert row2 is not None
  assert row2.duration_ms == 0.01


def test_filter_and_invalid_ranges():
  events = [
    {"device": "QCOM", "name": "a", "st": 0, "en": 1000},
    {"device": "AMD", "name": "b", "st": 0, "en": 2000},
    {"device": "QCOM", "name": "bad", "st": 20, "en": 10},
  ]
  rows = normalize_profile_events(events, device_prefix="QCOM")
  assert [r.name for r in rows] == ["a"]


def test_summary_union_busy_and_top_kernels():
  rows = normalize_profile_events([
    {"device": "QCOM", "name": "conv", "st": 0, "en": 2000},
    {"device": "QCOM", "name": "conv", "st": 1500, "en": 3000},
    {"device": "QCOM", "name": "matmul", "st": 4000, "en": 5000},
  ])
  s = summarize_kernel_ranges(rows)
  assert s["samples"] == 3
  assert s["spanMs"] == 5.0
  assert s["unionBusyMs"] == 4.0
  assert s["unionBusyPercent"] == 80.0
  assert s["kernelStats"]["maxMs"] == 2.0
  assert s["topKernels"][0]["name"] == "conv"
  assert s["topKernels"][0]["samples"] == 2
