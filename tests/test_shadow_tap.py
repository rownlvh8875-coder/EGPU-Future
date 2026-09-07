from pathlib import Path
import time

from egpu_future.shadow_tap import (
  NonBlockingShadowTapSender,
  ShadowInputSnapshot,
  ShadowTapReceiver,
  decode_snapshot,
  encode_snapshot,
)


def snap(frame_id=10):
  return ShadowInputSnapshot(
    frame_id=frame_id,
    frame_id_extra=frame_id,
    state_frame_id=frame_id + 1,
    camera_sof_ns=1_000_000_000 + frame_id,
    camera_eof_ns=1_010_000_000 + frame_id,
    active_backend="big",
    v_ego=12.3,
    main_transform=tuple(float(i) for i in range(9)),
    extra_transform=tuple(float(i + 10) for i in range(9)),
    desire_pulse=(0.0, 1.0, 0.0),
    traffic_convention=(1.0, 0.0),
    action_t=(0.25, 0.40),
    created_mono_ns=1_020_000_000 + frame_id,
  )


def test_round_trip():
  original = snap()
  decoded = decode_snapshot(encode_snapshot(original))
  assert decoded == original
  assert decoded.state_frame_id == 11


def test_sender_drops_when_receiver_missing(tmp_path):
  path = str(tmp_path / "missing.sock")
  sender = NonBlockingShadowTapSender(path)
  try:
    assert not sender.send(snap())
    assert sender.dropped == 1
  finally:
    sender.close()


def test_receiver_drains_to_latest(tmp_path):
  path = str(tmp_path / "shadow.sock")
  with ShadowTapReceiver(path) as receiver:
    sender = NonBlockingShadowTapSender(path)
    try:
      assert sender.send(snap(10))
      assert sender.send(snap(11))
      assert sender.send(snap(12))
      latest = None
      for _ in range(20):
        latest = receiver.recv_latest()
        if latest is not None:
          break
        time.sleep(0.005)
      assert latest is not None
      assert latest.frame_id == 12
      assert latest.state_frame_id == 13
      assert receiver.received == 3
      assert receiver.superseded == 2
    finally:
      sender.close()
  assert not Path(path).exists()
