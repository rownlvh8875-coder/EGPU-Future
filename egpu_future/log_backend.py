"""Backend labelling helpers for logs whose modelV2.big field is absent/unset."""
from __future__ import annotations


def resolve_big_flag(observed_big: bool, backend_label: str = "auto") -> tuple[bool, str]:
  label = backend_label.strip().lower()
  if label == "auto":
    return bool(observed_big), "modelV2.big"
  if label == "big":
    return True, "forced_big"
  if label == "small":
    return False, "forced_small"
  raise ValueError(f"unsupported backend label: {backend_label!r}")
