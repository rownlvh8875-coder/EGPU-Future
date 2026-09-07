import pytest

from egpu_future.log_backend import resolve_big_flag


def test_auto_uses_observed_field():
  assert resolve_big_flag(True, "auto") == (True, "modelV2.big")
  assert resolve_big_flag(False, "auto") == (False, "modelV2.big")


def test_forced_backend_labels():
  assert resolve_big_flag(False, "big") == (True, "forced_big")
  assert resolve_big_flag(True, "small") == (False, "forced_small")


def test_invalid_backend_label_rejected():
  with pytest.raises(ValueError):
    resolve_big_flag(False, "gpu")
