#!/usr/bin/env python3
"""Build/validate Stage-3 QCOM/eGPU model-slot metadata without loading a model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrations.carrot_wip_integrated.runtime.model_slots import (
  ModelSlotRegistry,
  builtin_qcom_slot,
  egpu_slot_from_carrot_manifest,
  registry_to_dict,
  write_registry,
)


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("--carrot-big-manifest", type=Path,
                  help="JSON object with Carrot model_id/filename/size/sha256; omit for qcom-only registry")
  ap.add_argument("--output", type=Path, default=Path("model_slots.json"))
  ap.add_argument("--qcom-generation", type=int, default=0)
  ap.add_argument("--egpu-generation", type=int, default=0)
  ap.add_argument("--nominal-hz", type=float, default=20.0)
  ap.add_argument("--egpu-ref", default=None)
  args = ap.parse_args()

  qcom = builtin_qcom_slot(generation=args.qcom_generation, nominal_hz=args.nominal_hz)
  egpu = None
  if args.carrot_big_manifest is not None:
    manifest = json.loads(args.carrot_big_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
      raise SystemExit("Carrot big manifest must be a JSON object")
    egpu = egpu_slot_from_carrot_manifest(
      manifest,
      ref=args.egpu_ref,
      generation=args.egpu_generation,
      nominal_hz=args.nominal_hz,
    )

  registry = ModelSlotRegistry(qcom=qcom, egpu=egpu)
  registry.validate()
  write_registry(args.output, registry)
  print(json.dumps(registry_to_dict(registry), ensure_ascii=False, indent=2, sort_keys=True))
  print(f"output={args.output}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
