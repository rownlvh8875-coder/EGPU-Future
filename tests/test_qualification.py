from egpu_future.qualification import build_t0_t3_report, render_markdown, report_to_dict
from egpu_future.stage_gate import GateStatus, InterferenceLimits


def stats(samples=100, p99=40.0, max_ms=45.0, miss=0.0, age=0, gaps=0):
  return {
    "samples": samples,
    "meanMs": 35.0,
    "p50Ms": 35.0,
    "p95Ms": 38.0,
    "p99Ms": p99,
    "maxMs": max_ms,
    "deadlineMissRate": miss,
    "frameAgeGt1": age,
    "frameGapCount": gaps,
  }


LIMITS = InterferenceLimits(
  min_samples_each=50,
  max_p99_increase_ms=2.0,
  max_max_increase_ms=5.0,
  max_deadline_miss_rate_delta=0.01,
  max_frame_age_gt1_delta=0,
  max_frame_gap_count_delta=0,
)


def test_missing_limits_holds_progression():
  report = build_t0_t3_report(t0=stats(), t1=stats(), t2=stats(), t3=stats(), limits=None)
  assert report.overall_status == GateStatus.HOLD
  assert report.phases[0].status == GateStatus.PASS
  assert all(p.status == GateStatus.HOLD for p in report.phases[1:])


def test_t0_t3_pass_with_clean_tap_probe():
  probe = {"packetsReceived": 100, "recordsSaved": 95, "decodeErrors": 0, "supersededPackets": 5, "saveCoverage": 0.95}
  report = build_t0_t3_report(t0=stats(), t1=stats(p99=41.0), t2=stats(p99=41.5), t3=stats(p99=41.0), limits=LIMITS, t3_tap_probe=probe)
  assert report.overall_status == GateStatus.PASS
  assert report.phases[-1].status == GateStatus.PASS
  data = report_to_dict(report)
  assert data["overallStatus"] == "PASS"
  md = render_markdown(report)
  assert "T3 Tap Receiver" in md
  assert "Overall: PASS" in md


def test_t3_decode_error_fails_even_if_latency_passes():
  probe = {"packetsReceived": 10, "recordsSaved": 10, "decodeErrors": 1}
  report = build_t0_t3_report(t0=stats(), t1=stats(), t2=stats(), t3=stats(), limits=LIMITS, t3_tap_probe=probe)
  assert report.overall_status == GateStatus.FAIL
  assert "tap_decode_errors" in report.phases[-1].reasons


def test_latency_limit_failure_propagates():
  probe = {"packetsReceived": 10, "recordsSaved": 10, "decodeErrors": 0}
  report = build_t0_t3_report(t0=stats(), t1=stats(), t2=stats(p99=44.0), t3=stats(), limits=LIMITS, t3_tap_probe=probe)
  assert report.overall_status == GateStatus.FAIL
  assert report.phases[2].status == GateStatus.FAIL


def test_missing_t0_holds_all_phases():
  report = build_t0_t3_report(t0=None, t1=stats(), t2=stats(), t3=stats(), limits=LIMITS)
  assert report.overall_status == GateStatus.HOLD
  assert all(p.status == GateStatus.HOLD for p in report.phases)
