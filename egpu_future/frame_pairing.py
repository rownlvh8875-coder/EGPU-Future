"""Deterministic pairing for small/big model shadow outputs.

Primary key is modelV2.frameId. Timestamp fallback is optional and deliberately
strict so one big-model sample is never reused for multiple small-model samples.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PairingConfig:
  timestamp_fallback: bool = False
  max_timestamp_delta_s: float = 0.030
  ambiguity_margin_s: float = 0.005


@dataclass(frozen=True)
class PairedRecord:
  small: dict
  big: dict
  method: str
  delta_s: float


@dataclass(frozen=True)
class PairingResult:
  pairs: list[PairedRecord]
  small_unmatched: list[dict]
  big_unmatched: list[dict]
  duplicate_small_frame_ids: dict[int, int]
  duplicate_big_frame_ids: dict[int, int]


def _frame_id(row: dict) -> int:
  try:
    return int(row.get("frameId", 0) or 0)
  except (TypeError, ValueError):
    return 0


def _time_s(row: dict) -> float | None:
  value = row.get("logMonoTimeS", row.get("t"))
  if value is None:
    return None
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def _duplicate_counts(rows: Iterable[dict]) -> dict[int, int]:
  counts: dict[int, int] = defaultdict(int)
  for row in rows:
    fid = _frame_id(row)
    if fid > 0:
      counts[fid] += 1
  return {fid: count for fid, count in counts.items() if count > 1}


def pair_records(small_rows: list[dict], big_rows: list[dict], config: PairingConfig | None = None) -> PairingResult:
  cfg = config or PairingConfig()

  # Use deques so duplicate frame ids are paired in stable input order and each
  # record is consumed at most once.
  big_by_frame: dict[int, deque[int]] = defaultdict(deque)
  for idx, row in enumerate(big_rows):
    fid = _frame_id(row)
    if fid > 0:
      big_by_frame[fid].append(idx)

  used_big: set[int] = set()
  used_small: set[int] = set()
  pairs: list[PairedRecord] = []

  for sidx, srow in enumerate(small_rows):
    fid = _frame_id(srow)
    if fid <= 0 or not big_by_frame[fid]:
      continue
    bidx = big_by_frame[fid].popleft()
    brow = big_rows[bidx]
    st, bt = _time_s(srow), _time_s(brow)
    dt = (bt - st) if st is not None and bt is not None else 0.0
    pairs.append(PairedRecord(srow, brow, "frameId", dt))
    used_small.add(sidx)
    used_big.add(bidx)

  if cfg.timestamp_fallback:
    # Only unmatched rows participate. Matching is stable by small input order.
    # A match is accepted only when the closest candidate is within tolerance
    # and sufficiently separated from the second-closest candidate.
    candidate_big = [i for i, row in enumerate(big_rows) if i not in used_big and _time_s(row) is not None]
    for sidx, srow in enumerate(small_rows):
      if sidx in used_small:
        continue
      st = _time_s(srow)
      if st is None:
        continue
      ranked = sorted(
        ((abs((_time_s(big_rows[bidx]) or 0.0) - st), bidx) for bidx in candidate_big),
        key=lambda item: (item[0], item[1]),
      )
      if not ranked or ranked[0][0] > cfg.max_timestamp_delta_s:
        continue
      if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < cfg.ambiguity_margin_s:
        continue
      _, bidx = ranked[0]
      brow = big_rows[bidx]
      bt = _time_s(brow)
      assert bt is not None
      pairs.append(PairedRecord(srow, brow, "timestamp", bt - st))
      used_small.add(sidx)
      used_big.add(bidx)
      candidate_big.remove(bidx)

  pairs.sort(key=lambda p: (
    _frame_id(p.small) if _frame_id(p.small) > 0 else 2**63 - 1,
    _time_s(p.small) if _time_s(p.small) is not None else float("inf"),
  ))

  return PairingResult(
    pairs=pairs,
    small_unmatched=[row for i, row in enumerate(small_rows) if i not in used_small],
    big_unmatched=[row for i, row in enumerate(big_rows) if i not in used_big],
    duplicate_small_frame_ids=_duplicate_counts(small_rows),
    duplicate_big_frame_ids=_duplicate_counts(big_rows),
  )
