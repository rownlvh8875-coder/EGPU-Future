from egpu_future.frame_pairing import PairingConfig, pair_records


def row(frame_id, t):
  return {"frameId": frame_id, "t": t}


def test_frame_id_is_primary_and_one_to_one():
  small = [row(10, 1.00), row(11, 1.05), row(12, 1.10)]
  big = [row(11, 8.00), row(10, 9.00), row(12, 7.00)]
  result = pair_records(small, big)
  assert [p.small["frameId"] for p in result.pairs] == [10, 11, 12]
  assert all(p.method == "frameId" for p in result.pairs)
  assert not result.small_unmatched
  assert not result.big_unmatched


def test_duplicate_frame_ids_pair_in_stable_order():
  small = [row(7, 1.00), row(7, 1.01)]
  big = [row(7, 2.00), row(7, 2.01)]
  result = pair_records(small, big)
  assert len(result.pairs) == 2
  assert result.duplicate_small_frame_ids == {7: 2}
  assert result.duplicate_big_frame_ids == {7: 2}
  assert result.pairs[0].small["t"] == 1.00
  assert result.pairs[0].big["t"] == 2.00


def test_timestamp_fallback_does_not_reuse_big_sample():
  small = [row(0, 1.000), row(0, 1.015)]
  big = [row(0, 1.003)]
  result = pair_records(small, big, PairingConfig(timestamp_fallback=True, max_timestamp_delta_s=0.030, ambiguity_margin_s=0.0))
  assert len(result.pairs) == 1
  assert len(result.small_unmatched) == 1
  assert len(result.big_unmatched) == 0


def test_ambiguous_timestamp_match_is_rejected():
  small = [row(0, 1.000)]
  big = [row(0, 0.996), row(0, 1.004)]
  result = pair_records(small, big, PairingConfig(timestamp_fallback=True, max_timestamp_delta_s=0.030, ambiguity_margin_s=0.005))
  assert len(result.pairs) == 0
  assert len(result.small_unmatched) == 1
  assert len(result.big_unmatched) == 2
