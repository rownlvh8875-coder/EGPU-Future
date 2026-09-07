"""Standalone, fail-open metadata tap for ajouatom/Carrot modeld integration.

Designed to be copied into:
  openpilot/selfdrive/modeld/egpu_future_shadow_tap.py

The active model path must never wait for the research receiver. The tap can be
enabled either by EGPU_FUTURE_SHADOW_TAP=1 at process start or dynamically by
creating the control file (default: /tmp/egpu_future_shadow_tap.enable). Dynamic
state is polled at a low rate so T1/T2/T3 commissioning can switch the metadata
tap without repeatedly restarting modeld.
"""
from __future__ import annotations

import json
import os
import socket
import time
from typing import Any


PROTOCOL_VERSION = 1
DEFAULT_SOCKET_PATH = "/tmp/egpu_future_shadow_input.sock"
DEFAULT_CONTROL_PATH = "/tmp/egpu_future_shadow_tap.enable"
MAX_PACKET_BYTES = 8192
DEFAULT_CONTROL_POLL_SECONDS = 0.25


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
  """Best-effort non-blocking sender for active-model input metadata.

  `enabled=` is a static test/commissioning override. When omitted, environment
  force-enable OR the control-file state determines whether the socket is open.
  The caller must never branch vehicle-control/model behavior on send results.
  """

  def __init__(self, enabled: bool | None = None, socket_path: str | None = None,
               control_path: str | None = None, control_poll_seconds: float | None = None):
    self._static_enabled = None if enabled is None else bool(enabled)
    self._env_enabled = _enabled_from_env()
    self.socket_path = socket_path or os.getenv("EGPU_FUTURE_SHADOW_SOCKET", DEFAULT_SOCKET_PATH)
    self.control_path = control_path or os.getenv("EGPU_FUTURE_SHADOW_CONTROL_FILE", DEFAULT_CONTROL_PATH)
    if control_poll_seconds is None:
      try:
        control_poll_seconds = float(os.getenv("EGPU_FUTURE_SHADOW_CONTROL_POLL", str(DEFAULT_CONTROL_POLL_SECONDS)))
      except ValueError:
        control_poll_seconds = DEFAULT_CONTROL_POLL_SECONDS
    self.control_poll_seconds = max(0.02, float(control_poll_seconds))

    self.enabled = False
    self.calls = 0
    self.sent = 0
    self.dropped = 0
    self.encode_errors = 0
    self.control_checks = 0
    self.state_changes = 0
    self.last_encode_send_us = 0.0
    self.max_encode_send_us = 0.0
    self._last_control_check = 0.0
    self._sock: socket.socket | None = None
    self._refresh_enabled(force=True)

  def _desired_enabled(self) -> bool:
    if self._static_enabled is not None:
      return self._static_enabled
    return self._env_enabled or os.path.exists(self.control_path)

  def _set_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if enabled == self.enabled:
      return
    self.enabled = enabled
    self.state_changes += 1
    if enabled:
      self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
      self._sock.setblocking(False)
    elif self._sock is not None:
      self._sock.close()
      self._sock = None

  def _refresh_enabled(self, force: bool = False) -> None:
    if self._static_enabled is not None:
      if force:
        self._set_enabled(self._static_enabled)
      return
    now = time.monotonic()
    if not force and now - self._last_control_check < self.control_poll_seconds:
      return
    self._last_control_check = now
    self.control_checks += 1
    self._set_enabled(self._desired_enabled())

  def send(self, *, model: Any, meta_main: Any, meta_extra: Any, state_frame_id: int,
           v_ego: float, transform_main: Any, transform_extra: Any,
           inputs: dict[str, Any]) -> bool:
    self.calls += 1
    self._refresh_enabled()
    if not self.enabled or self._sock is None:
      return False

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
      "envEnabled": self._env_enabled,
      "dynamicControl": self._static_enabled is None,
      "socketPath": self.socket_path,
      "controlPath": self.control_path,
      "controlPollSeconds": self.control_poll_seconds,
      "calls": self.calls,
      "sent": self.sent,
      "dropped": self.dropped,
      "encodeErrors": self.encode_errors,
      "controlChecks": self.control_checks,
      "stateChanges": self.state_changes,
      "lastEncodeSendUs": self.last_encode_send_us,
      "maxEncodeSendUs": self.max_encode_send_us,
    }

  def close(self) -> None:
    if self._sock is not None:
      self._sock.close()
      self._sock = None
    self.enabled = False
