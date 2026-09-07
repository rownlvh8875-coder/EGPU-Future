from egpu_future.route_health import build_route_health_report, render_markdown, report_to_dict


def test_complete_route_health_report_aggregates_issues_and_temporal_tags():
  pairing = {
    "smallSamples": 100,
    "bigSamples": 98,
    "pairedSamples": 96,
    "pairMethods": {"frameId": 96},
    "smallUnmatched": 4,
    "bigUnmatched": 2,
    "duplicateSmallFrameIds": 0,
    "duplicateBigFrameIds": 0,
  }
  issues = [
    {"frameId": 10, "hardIssues": ["stale_frame"], "reviewIssues": []},
    {"frameId": 20, "hardIssues": [], "reviewIssues": ["acceleration_disagreement"]},
    {"frameId": 21, "hardIssues": [], "reviewIssues": ["acceleration_disagreement"]},
  ]
  events = [
    {"metrics": {"score": 2.0, "stopMismatch": False}, "tags": ["lead_acquired"], "temporalTags": ["lead_acquired"]},
    {"metrics": {"score": 5.0, "stopMismatch": True}, "tags": ["cut_in_candidate_heuristic"], "temporalTags": ["cut_in_candidate_heuristic", "stop_disagreement_onset"]},
  ]
  report = build_route_health_report(
    pairing_summary=pairing,
    validation_issues=issues,
    shadow_events=events,
  )
  data = report_to_dict(report)
  assert data["evidenceCompleteness"] == "COMPLETE"
  assert data["pairing"]["pairedSamples"] == 96
  assert data["validation"]["hardIssueFrames"] == 1
  assert data["validation"]["reviewIssueCounts"]["acceleration_disagreement"] == 2
  assert data["disagreements"]["significantEvents"] == 2
  assert data["disagreements"]["stopMismatchEvents"] == 1
  assert data["temporal"]["cutInCandidateHeuristicEvents"] == 1
  assert "not a safety PASS/FAIL" in render_markdown(report)


def test_missing_evidence_is_marked_incomplete_not_silently_zero_complete():
  report = build_route_health_report(
    pairing_summary=None,
    validation_issues=None,
    shadow_events=None,
  )
  data = report_to_dict(report)
  assert data["evidenceCompleteness"] == "INCOMPLETE"
  assert any("Missing evidence" in note for note in data["notes"])
