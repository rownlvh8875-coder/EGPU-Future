"""Standalone, fail-open metadata tap for ajouatom/Carrot modeld integration.

This file is designed to be copied into:
  openpilot/selfdrive/modeld/egpu_future_shadow_tap.py

It intentionally depends only on the Python standard library. The active modeld
must never wait for the research receiver. Enabling is explicit through the
`EGPU_FUTURE_SHADOW_TAP=1` environment variable; default behavior is disabled.
"""
from __future__ import annotations

import json
import os
import socket
import time
from typing import Any


PROTOCOL_VERSION = 1
DEFAULT_SOCKET_PATH = "/tmp/egpu_future_shadow_input.sock"
MAX_PACKET_BYTES = 8192


def _enabled_from_env() -> bool:
  return os.getenv("EGPU_FUTURE_SHADOW_TAP", "0").strip().lower() in {"1", "true", "yes", "on"}


def _flat(values: Any) -> list[float]:
  try:
    return [float(v) for v in values.reshape(-1)]
  except AttributeError:
    return [float(v) for v in values]


def _active_backend(model: Any) -> str:
  return "big" if bool(getattr(model, "usbgpu", getattr(model, "chestnut", False))) else "small"


class EgpuFutureShadowTap:
  """Best-effort non-blocking sender for active model input metadata.

  The caller may inspect counters for commissioning, but must never branch the
  active vehicle-control/model behavior on the result of `send()`.
  """

  def __init__(self, enabled: bool | None = None, socket_path: str | None = None):
    self.enabled = _enabled_from_env() if enabled is None else bool(enabled)
    self.socket_path = socket_path or os.getenv("EGPU_FUTURE_SHADOW_SOCKET", DEFAULT_SOCKET_PATH)
    self.calls = 0
    self.sent = 0
    self.dropped = 0
    self.encode_errors = 0
    self.last_encode_send_us = 0.0
    self.max_encode_send_us = 0.0
    self._sock: socket.socket | None = None
    if self.enabled:
      self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
      self._sock.setblocking(False)

  def send(self, *, model: Any, meta_main: Any, meta_extra: Any, state_frame_id: int,
           v_ego: float, transform_main: Any, transform_extra: Any,
           inputs: dict[str, Any]) -> bool:
    if not self.enabled or self._sock is None:
      return False

    self.calls += 1
    started = time.perf_counter_ns()
    ok = False
    try:
      payload = {
        "version": PROTOCOL_VERSION,
        "frame_id": int(meta_main.frame_id),
        "frame_id_extra": int(meta_extra.frame_id),
        "state_frame_id": int(state_frame_id),
        "camera_sof_ns": int(meta_main.timestamp_sof),
        "camera_eof_ns": int(meta_main.timestamp_eof),
        "active_backend": _active_backend(model),
        "v_ego": float(v_ego),
        "main_transform": _flat(transform_main),
        "extra_transform": _flat(transform_extra),
        "desire_pulse": _flat(inputs["desire_pulse"]),
        "traffic_convention": _flat(inputs["traffic_convention"]),
        "action_t": _flat(inputs["action_t"]),
        "created_mono_ns": time.monotonic_ns(),
      }
      dat = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
      if len(dat) > MAX_PACKET_BYTES:
        raise ValueError(f"shadow tap packet too large: {len(dat)} bytes")
      self._sock.sendto(dat, self.socket_path)
      self.sent += 1
      ok = True
    except (BlockingIOError, FileNotFoundError, ConnectionRefusedError, OSError):
      self.dropped += 1
    except (KeyError, TypeError, ValueError, OverflowError):
      self.encode_errors += 1
      self.dropped += 1
    finally:
      elapsed_us = (time.perf_counter_ns() - started) / 1000.0
      self.last_encode_send_us = elapsed_us
      self.max_encode_send_us = max(self.max_encode_send_us, elapsed_us)
    return ok

  def stats(self) -> dict[str, int | float | bool | str]:
    return {
      "enabled": self.enabled,
      "socketPath": self.socket_path,
      "calls": self.calls,
      "sent": self.sent,
      "dropped": self.dropped,
      "encodeErrors": self.encode_errors,
      "lastEncodeSendUs": self.last_encode_send_us,
      "maxEncodeSendUs": self.max_encode_send_us,
    }

  def close(self) -> None:
    if self._sock is not None:
      self._sock.close()
      self._sock = None
