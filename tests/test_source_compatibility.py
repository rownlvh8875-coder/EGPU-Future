from egpu_future.source_compatibility import (
  CRITICAL_BLOBS,
  SourceCompatibility,
  evaluate_source_compatibility,
)


def test_exact_reviewed_head_passes():
  result = evaluate_source_compatibility(
    "1310ed43fe70a903d31589295f4dabe37649dab2",
    dict(CRITICAL_BLOBS),
  )
  assert result.status == SourceCompatibility.EXACT_REVIEWED_HEAD
  assert result.code_compatible is True
  assert not result.mismatched_blobs


def test_unreviewed_head_with_identical_critical_blobs_is_code_equivalent():
  result = evaluate_source_compatibility("new-doc-only-head", dict(CRITICAL_BLOBS))
  assert result.status == SourceCompatibility.CODE_EQUIVALENT_HEAD_DRIFT
  assert result.code_compatible is True


def test_one_critical_blob_change_requires_review():
  observed = dict(CRITICAL_BLOBS)
  observed["openpilot/selfdrive/modeld/modeld.py"] = "changed"
  result = evaluate_source_compatibility("new-head", observed)
  assert result.status == SourceCompatibility.REVIEW_REQUIRED
  assert result.code_compatible is False
  assert "openpilot/selfdrive/modeld/modeld.py" in result.mismatched_blobs


def test_missing_critical_path_requires_review():
  observed = dict(CRITICAL_BLOBS)
  del observed["tinygrad_repo/tinygrad/runtime/ops_qcom.py"]
  result = evaluate_source_compatibility("new-head", observed)
  assert result.status == SourceCompatibility.REVIEW_REQUIRED
  assert "tinygrad_repo/tinygrad/runtime/ops_qcom.py" in result.missing_paths
