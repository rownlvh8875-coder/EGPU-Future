#!/usr/bin/env python3
"""Replay Chestnut/USB-GPU telemetry through the EGPU-Future recovery state machine.

This is an offline simulator. It does not modify openpilot or vehicle control.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from egpu_future.recovery_state_machine import (
  Health,
  RecoveryStateMachine,
  carrot_usbgpu_policy,
  official_chestnut_policy,
)


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("input", help="JSONL from chestnut_telemetry_logger.py or compatible logger")
  ap.add_argument("--output", default="recovery_transitions.jsonl")
  ap.add_argument("--profile", choices=("official", "carrot"), default="official",
                  help="power/recovery research profile; official=5000mV, carrot=8000mV current source thresholds")
  ap.add_argument("--disabled", action="store_true", help="simulate intentional user disable")
  args = ap.parse_args()

  policy = official_chestnut_policy() if args.profile == "official" else carrot_usbgpu_policy()
  sm = RecoveryStateMachine(policy)
  prev = sm.state
  transitions = 0

  with Path(args.output).open("w", encoding="utf-8") as out:
    for i, line in enumerate(Path(args.input).read_text(encoding="utf-8").splitlines()):
      if not line.strip():
        continue
      r = json.loads(line)
      c = r.get("chestnut", r.get("usbgpu", {}))
      d = r.get("device", {})
      m = r.get("model", {})
      alive = r.get("alive", {})
      valid = r.get("valid", {})
      h = Health(
        chestnut_present=bool(d.get("chestnutPresent", d.get("usbgpuPresent", False))),
        supply_voltage_mv=int(c.get("supplyVoltageMv", c.get("voltageMv", 0))),
        supply_fault=bool(c.get("supplyFault", c.get("fault", True))),
        usb_ok=bool(alive.get("chestnutState", alive.get("usbgpuState", False))),
        pcie_ok=int(c.get("pcieLtssm", 0)) == 0x78,
        telemetry_ok=bool(valid.get("chestnutState", valid.get("usbgpuState", False))),
        gpu_temp_c=float(c.get("tempC", 0.0)),
        memory_temp_c=float(c.get("memoryTempC", 0.0)),
        model_alive=bool(m.get("alive", False)),
        model_ready=bool(m.get("valid", False)),
        deadline_ok=bool(m.get("deadlineOk", True)),
        user_enabled=not args.disabled,
      )
      state = sm.update(h)
      if state != prev:
        transitions += 1
        event = {
          "sample": i,
          "ts_unix": r.get("ts_unix"),
          "profile": args.profile,
          "powered_voltage_mv": policy.powered_voltage_mv,
          "from": prev.name,
          "to": state.name,
          "reason": sm.last_reason,
          "gpu_temp_c": h.gpu_temp_c,
          "memory_temp_c": h.memory_temp_c,
          "supply_voltage_mv": h.supply_voltage_mv,
          "supply_fault": h.supply_fault,
          "pcie_ok": h.pcie_ok,
          "model_alive": h.model_alive,
        }
        out.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"{i}: {prev.name} -> {state.name} ({sm.last_reason})")
        prev = state

  print(f"profile={args.profile} powered_voltage_mv={policy.powered_voltage_mv}")
  print(f"transitions={transitions} output={args.output}")


if __name__ == "__main__":
  main()
