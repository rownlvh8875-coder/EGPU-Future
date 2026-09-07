from integrations.carrot_wip_integrated.runtime.s4b_qualification import S4BQualificationPolicy, qualify_s4b, qualification_to_dict


def policy():
  return S4BQualificationPolicy(min_probe_runs=100)


def good_kwargs():
  return dict(
    interference_gate={"status": "PASS"},
    probe_summary={"runs": 200, "shadowErrors": 0, "guardStops": 0},
    hardware_summary={"newUsbLinkErrors": 0, "supplyFaultSamples": 0},
    active_fallback_observed=False,
    source_restored=True,
    policy=policy(),
  )


def test_pass_never_authorizes_control_or_quality_comparison():
  result = qualify_s4b(**good_kwargs())
  assert result.status == "PASS"
  payload = qualification_to_dict(result)
  assert payload["controlAuthorization"] is False
  assert payload["qualityComparisonAuthorization"] is False
  assert payload["nextIfPass"] == "S4C_PARKED_20HZ_PLAN_ONLY"


def test_missing_policy_holds():
  kwargs = good_kwargs(); kwargs["policy"] = None
  assert qualify_s4b(**kwargs).status == "HOLD"


def test_insufficient_samples_holds_not_fails():
  kwargs = good_kwargs(); kwargs["probe_summary"] = {"runs": 50, "shadowErrors": 0, "guardStops": 0}
  result = qualify_s4b(**kwargs)
  assert result.status == "HOLD"
  assert "insufficient_probe_runs" in result.reasons


def test_interference_fail_is_fail():
  kwargs = good_kwargs(); kwargs["interference_gate"] = {"status": "FAIL"}
  result = qualify_s4b(**kwargs)
  assert result.status == "FAIL"


def test_shadow_error_supply_fault_fallback_or_restore_failure_fails():
  cases = [
    ("probe_summary", {"runs": 200, "shadowErrors": 1, "guardStops": 0}, "shadow_errors_exceeded"),
    ("hardware_summary", {"newUsbLinkErrors": 0, "supplyFaultSamples": 1}, "supply_fault_observed"),
    ("active_fallback_observed", True, "active_egpu_fallback_observed"),
    ("source_restored", False, "source_not_restored"),
  ]
  for key, value, reason in cases:
    kwargs = good_kwargs(); kwargs[key] = value
    result = qualify_s4b(**kwargs)
    assert result.status == "FAIL"
    assert reason in result.reasons
