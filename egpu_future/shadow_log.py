"""Normalize live shadow_modeld JSONL into the existing action-row schema."""
from __future__ import annotations


def normalize_shadow_output(row: dict, eligible_only: bool = True) -> dict | None:
  if row.get("type") != "shadow_output":
    return None
  if eligible_only and not bool(row.get("comparisonEligible", False)):
    return None

  action = row.get("action") or {}
  timing = row.get("timing") or {}
  frame_id = int(row.get("frameId", 0) or 0)
  if frame_id <= 0:
    return None

  model_ms = timing.get("model_call_total_ms")
  if model_ms is None:
    return None

  eof_ns = int(row.get("cameraTimestampEofNs", 0) or 0)
  return {
    "frameId": frame_id,
    "frameAge": 0,
    "modelExecutionTimeS": float(model_ms) / 1000.0,
    "desiredCurvature": float(action["desiredCurvature"]),
    "desiredAcceleration": float(action["desiredAcceleration"]),
    "shouldStop": bool(action.get("shouldStop", False)),
    "speedMps": float(row["vEgo"]) if row.get("vEgo") is not None else None,
    "logMonoTimeS": eof_ns / 1e9 if eof_ns > 0 else 0.0,
    "big": row.get("shadowBackend") == "big",
    "shadowOnly": True,
    "comparisonEligible": bool(row.get("comparisonEligible", False)),
    "continuityStreak": int(row.get("continuityStreak", 0) or 0),
    "captureToDoneMs": timing.get("capture_to_done_ms"),
  }
