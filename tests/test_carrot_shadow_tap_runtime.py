import socket

from egpu_future.shadow_tap import decode_snapshot
from integrations.carrot.egpu_future_shadow_tap import EgpuFutureShadowTap


class Obj:
  pass


def payload_objects():
  model = Obj()
  model.usbgpu = True
  main = Obj()
  main.frame_id = 101
  main.timestamp_sof = 1_000
  main.timestamp_eof = 2_000
  extra = Obj()
  extra.frame_id = 102
  extra.timestamp_sof = 1_100
  extra.timestamp_eof = 2_100
  inputs = {
    "desire_pulse": [0.0, 1.0],
    "traffic_convention": [1.0, 0.0],
    "action_t": [0.1, 0.2],
  }
  return model, main, extra, inputs


def send(tap):
  model, main, extra, inputs = payload_objects()
  return tap.send(
    model=model,
    meta_main=main,
    meta_extra=extra,
    state_frame_id=104,
    v_ego=12.5,
    transform_main=[1.0] * 9,
    transform_extra=[2.0] * 9,
    inputs=inputs,
  )


def test_disabled_tap_is_fast_noop(tmp_path):
  tap = EgpuFutureShadowTap(enabled=False, socket_path=str(tmp_path / "missing.sock"))
  assert tap.enabled is False
  assert send(tap) is False
  assert tap.stats()["calls"] == 1
  assert tap.stats()["sent"] == 0
  assert tap.stats()["dropped"] == 0


def test_enabled_tap_is_protocol_compatible(tmp_path):
  path = str(tmp_path / "shadow.sock")
  recv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
  recv.bind(path)
  recv.settimeout(1.0)

  tap = EgpuFutureShadowTap(enabled=True, socket_path=path)
  assert send(tap) is True
  snap = decode_snapshot(recv.recv(8192))
  assert snap.frame_id == 101
  assert snap.frame_id_extra == 102
  assert snap.state_frame_id == 104
  assert snap.active_backend == "big"
  assert snap.v_ego == 12.5
  assert snap.action_t == (0.1, 0.2)
  assert tap.stats()["sent"] == 1

  tap.close()
  recv.close()


def test_dynamic_control_file_enables_without_restart(tmp_path, monkeypatch):
  monkeypatch.delenv("EGPU_FUTURE_SHADOW_TAP", raising=False)
  sock_path = str(tmp_path / "shadow.sock")
  control = tmp_path / "enable"
  recv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
  recv.bind(sock_path)
  recv.settimeout(1.0)

  tap = EgpuFutureShadowTap(
    socket_path=sock_path,
    control_path=str(control),
    control_poll_seconds=0.02,
  )
  assert tap.enabled is False
  assert send(tap) is False

  control.write_text("1\n", encoding="utf-8")
  # Force the low-rate poll for deterministic unit testing.
  tap._last_control_check = 0.0
  assert send(tap) is True
  assert tap.enabled is True
  snap = decode_snapshot(recv.recv(8192))
  assert snap.frame_id == 101

  control.unlink()
  tap._last_control_check = 0.0
  assert send(tap) is False
  assert tap.enabled is False
  assert tap.stats()["stateChanges"] >= 2

  tap.close()
  recv.close()
