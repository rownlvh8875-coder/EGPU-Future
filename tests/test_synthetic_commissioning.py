from egpu_future.interference import latency_stats_ms
from egpu_future.qualification import build_t0_t3_report
from egpu_future.synthetic_commissioning import generate_case, predefined_case


def _run(name: str):
  case = predefined_case(name)
  data = generate_case(case)
  stats = {
    stage: latency_stats_ms(rows, deadline_ms=50.0, require_big=True)
    for stage, rows in data["stages"].items()
  }
  report = build_t0_t3_report(
    t0=stats["T0"],
    t1=stats["T1"],
    t2=stats["T2"],
    t3=stats["T3"],
    limits=data["limits"],
    t3_tap_probe=data["tapSummary"],
  )
  return case, report


def test_synthetic_pass_case():
  case, report = _run("pass")
  assert report.overall_status.value == case.expected_status == "PASS"


def test_synthetic_latency_failure():
  case, report = _run("fail_latency")
  assert report.overall_status.value == case.expected_status == "FAIL"


def test_synthetic_transport_failure():
  case, report = _run("fail_transport")
  assert report.overall_status.value == case.expected_status == "FAIL"


def test_synthetic_frame_gap_failure():
  case, report = _run("fail_gap")
  assert report.overall_status.value == case.expected_status == "FAIL"


def test_synthetic_missing_policy_holds():
  case, report = _run("hold_no_policy")
  assert report.overall_status.value == case.expected_status == "HOLD"


def test_synthetic_sample_shortage_holds():
  case, report = _run("hold_samples")
  assert report.overall_status.value == case.expected_status == "HOLD"
