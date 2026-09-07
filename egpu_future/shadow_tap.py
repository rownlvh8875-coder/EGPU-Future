"""Non-blocking local tap for exact shadow-model input metadata.

The sender is designed to be called from an active model process.  It uses a
UNIX datagram socket in non-blocking mode and treats every send failure as a
shadow-only drop.  It never retries or waits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
from typing import Iterable


PROTOCOL_VERSION = 1
DEFAULT_SOCKET_PATH = "/tmp/egpu_future_shadow_input.sock"
MAX_PACKET_BYTES = 8192


@dataclass(frozen=True)
class ShadowInputSnapshot:
  frame_id: int
  frame_id_extra: int
  camera_sof_ns: int
  camera_eof_ns: int
  active_backend: str
  v_ego: float
  main_transform: tuple[float, ...]
  extra_transform: tuple[float, ...]
  desire_pulse: tuple[float, ...]
  traffic_convention: tuple[float, ...]
  action_t: tuple[float, ...]
  created_mono_ns: int

  def validate(self) -> None:
    if self.frame_id <= 0:
      raise ValueError("frame_id must be positive")
    if self.frame_id_extra <= 0:
      raise ValueError("frame_id_extra must be positive")
    if len(self.main_transform) != 9 or len(self.extra_transform) != 9:
      raise ValueError("transforms must contain exactly 9 floats")
    if len(self.traffic_convention) != 2:
      raise ValueError("traffic_convention must contain exactly 2 floats")
    if len(self.action_t) != 2:
      raise ValueError("action_t must contain exactly 2 floats")
    if not self.desire_pulse:
      raise ValueError("desire_pulse must not be empty")


def _floats(values: Iterable[float]) -> tuple[float, ...]:
  return tuple(float(v) for v in values)


def encode_snapshot(snapshot: ShadowInputSnapshot) -> bytes:
  snapshot.validate()
  payload = {"version": PROTOCOL_VERSION, **asdict(snapshot)}
  dat = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
  if len(dat) > MAX_PACKET_BYTES:
    raise ValueError(f"shadow tap packet too large: {len(dat)} bytes")
  return dat


def decode_snapshot(dat: bytes) -> ShadowInputSnapshot:
  if len(dat) > MAX_PACKET_BYTES:
    raise ValueError("shadow tap packet exceeds maximum size")
  payload = json.loads(dat.decode("utf-8"))
  if payload.get("version") != PROTOCOL_VERSION:
    raise ValueError(f"unsupported shadow tap protocol version: {payload.get('version')!r}")
  snap = ShadowInputSnapshot(
    frame_id=int(payload["frame_id"]),
    frame_id_extra=int(payload["frame_id_extra"]),
    camera_sof_ns=int(payload["camera_sof_ns"]),
    camera_eof_ns=int(payload["camera_eof_ns"]),
    active_backend=str(payload["active_backend"]),
    v_ego=float(payload["v_ego"]),
    main_transform=_floats(payload["main_transform"]),
    extra_transform=_floats(payload["extra_transform"]),
    desire_pulse=_floats(payload["desire_pulse"]),
    traffic_convention=_floats(payload["traffic_convention"]),
    action_t=_floats(payload["action_t"]),
    created_mono_ns=int(payload["created_mono_ns"]),
  )
  snap.validate()
  return snap


class NonBlockingShadowTapSender:
  """Best-effort sender.  `send()` never blocks or retries."""

  def __init__(self, path: str = DEFAULT_SOCKET_PATH):
    self.path = path
    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    self.sock.setblocking(False)
    self.sent = 0
    self.dropped = 0

  def send(self, snapshot: ShadowInputSnapshot) -> bool:
    try:
      self.sock.sendto(encode_snapshot(snapshot), self.path)
      self.sent += 1
      return True
    except (BlockingIOError, FileNotFoundError, ConnectionRefusedError, OSError, ValueError):
      self.dropped += 1
      return False

  def close(self) -> None:
    self.sock.close()


class ShadowTapReceiver:
  """Receive and drain input snapshots, retaining only the newest packet."""

  def __init__(self, path: str = DEFAULT_SOCKET_PATH):
    self.path = path
    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    self.sock.setblocking(False)
    try:
      os.unlink(path)
    except FileNotFoundError:
      pass
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    self.sock.bind(path)
    self.received = 0
    self.decode_errors = 0
    self.superseded = 0

  def recv_latest(self) -> ShadowInputSnapshot | None:
    latest: ShadowInputSnapshot | None = None
    while True:
      try:
        dat = self.sock.recv(MAX_PACKET_BYTES)
      except BlockingIOError:
        break
      self.received += 1
      try:
        decoded = decode_snapshot(dat)
      except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        self.decode_errors += 1
        continue
      if latest is not None:
        self.superseded += 1
      latest = decoded
    return latest

  def close(self) -> None:
    try:
      self.sock.close()
    finally:
      try:
        os.unlink(self.path)
      except FileNotFoundError:
        pass

  def __enter__(self) -> "ShadowTapReceiver":
    return self

  def __exit__(self, exc_type, exc, tb) -> None:
    self.close()
