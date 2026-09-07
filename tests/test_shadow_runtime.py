from egpu_future.shadow_runtime import (
  AdmissionPolicy,
  AdmissionReason,
  Backend,
  ContinuityTracker,
  LatestOnlySlot,
  ShadowAdmissionController,
  TimingTrace,
)


def test_shadow_pauses_when_active_backend_matches():
  ctl = ShadowAdmissionController(Backend.SMALL, AdmissionPolicy(max_hz=None))
  d = ctl.decide(100, Backend.SMALL, 1_000_000_000)
  assert not d.accepted
  assert d.reason == AdmissionReason.SAME_BACKEND


def test_shadow_accepts_opposite_backend_and_rejects_old_frame():
  ctl = ShadowAdmissionController(Backend.SMALL, AdmissionPolicy(max_hz=None))
  assert ctl.decide(100, Backend.BIG, 1_000_000_000).accepted
  d = ctl.decide(100, Backend.BIG, 1_100_000_000)
  assert not d.accepted
  assert d.reason == AdmissionReason.DUPLICATE_OR_OLD_FRAME


def test_rate_limit_is_shadow_only():
  ctl = ShadowAdmissionController(Backend.SMALL, AdmissionPolicy(max_hz=5.0))
  assert ctl.decide(1, Backend.BIG, 1_000_000_000).accepted
  d = ctl.decide(2, Backend.BIG, 1_100_000_000)
  assert not d.accepted
  assert d.reason == AdmissionReason.RATE_LIMIT
  assert ctl.decide(3, Backend.BIG, 1_200_000_000).accepted


def test_continuity_resets_on_gap():
  tracker = ContinuityTracker(settle_frames=3)
  assert not tracker.observe(10).eligible
  assert not tracker.observe(11).eligible
  assert tracker.observe(12).eligible
  r = tracker.observe(15)
  assert r.reset
  assert r.gap_frames == 2
  assert not r.eligible
  assert not tracker.observe(16).eligible
  assert tracker.observe(17).eligible


def test_latest_only_slot_replaces_pending_item():
  slot = LatestOnlySlot[int]()
  assert not slot.put(1)
  assert slot.put(2)
  assert slot.replaced == 1
  assert slot.take() == 2
  assert slot.take() is None


def test_timing_trace_metrics_and_ordering():
  t = TimingTrace(
    camera_sof_ns=1_000_000_000,
    camera_eof_ns=1_010_000_000,
    frame_received_ns=1_012_000_000,
    model_call_start_ns=1_013_000_000,
    device_enqueued_ns=1_018_000_000,
    inference_done_ns=1_040_000_000,
    record_written_ns=1_041_000_000,
  )
  assert t.ordered()
  m = t.metrics_ms()
  assert m["capture_to_receive_ms"] == 2.0
  assert m["call_to_enqueue_ms"] == 5.0
  assert m["enqueue_to_done_ms"] == 22.0
  assert m["model_call_total_ms"] == 27.0
  assert m["capture_to_done_ms"] == 30.0
