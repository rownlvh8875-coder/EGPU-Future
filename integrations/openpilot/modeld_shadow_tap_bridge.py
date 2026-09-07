"""Tiny best-effort bridge intended for research integration with openpilot modeld.

This file does not patch openpilot by itself.  The active modeld can construct
one bridge and call `send()` immediately before its normal `model.run()` call.
All failures are swallowed and counted; the active path must never wait for the
shadow process.
"""
from __future__ import annotations

import time
from typing import Any

from egpu_future.shadow_tap import NonBlockingShadowTapSender, ShadowInputSnapshot


class ModeldShadowTapBridge:
  def __init__(self, socket_path: str):
    self.sender = NonBlockingShadowTapSender(socket_path)
    self.calls = 0
    self.failures = 0
    self.last_encode_send_us = 0.0
    self.max_encode_send_us = 0.0

  @staticmethod
  def _flat(values: Any) -> tuple[float, ...]:
    return tuple(float(v) for v in values.reshape(-1))

  @staticmethod
  def _is_big_model(model: Any) -> bool:
    # Official openpilot currently exposes ModelState.chestnut.  The Carrot
    # eGPU branch analyzed by this project uses ModelState.usbgpu instead.
    if hasattr(model, "chestnut"):
      return bool(getattr(model, "chestnut"))
    return bool(getattr(model, "usbgpu", False))

  def send(self, *, model: Any, meta_main: Any, meta_extra: Any, state_frame_id: int,
           v_ego: float, transform_main: Any, transform_extra: Any, inputs: dict[str, Any]) -> bool:
    start = time.perf_counter_ns()
    self.calls += 1
    ok = False
    try:
      snapshot = ShadowInputSnapshot(
        frame_id=int(meta_main.frame_id),
        frame_id_extra=int(meta_extra.frame_id),
        state_frame_id=int(state_frame_id),
        camera_sof_ns=int(meta_main.timestamp_sof),
        camera_eof_ns=int(meta_main.timestamp_eof),
        active_backend="big" if self._is_big_model(model) else "small",
        v_ego=float(v_ego),
        main_transform=self._flat(transform_main),
        extra_transform=self._flat(transform_extra),
        desire_pulse=self._flat(inputs["desire_pulse"]),
        traffic_convention=self._flat(inputs["traffic_convention"]),
        action_t=self._flat(inputs["action_t"]),
        created_mono_ns=time.monotonic_ns(),
      )
      ok = self.sender.send(snapshot)
    except Exception:
      # This bridge is intentionally fail-open for the active driving model.
      ok = False
    if not ok:
      self.failures += 1
    elapsed_us = (time.perf_counter_ns() - start) / 1000.0
    self.last_encode_send_us = elapsed_us
    self.max_encode_send_us = max(self.max_encode_send_us, elapsed_us)
    return ok

  def close(self) -> None:
    self.sender.close()
