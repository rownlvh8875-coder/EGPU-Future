import hashlib
import json

import pytest

from integrations.carrot_wip_integrated.runtime.model_slots import (
  ModelArtifact,
  ModelSlot,
  ModelSlotRegistry,
  builtin_qcom_slot,
  egpu_slot_from_carrot_manifest,
  load_registry,
  registry_from_dict,
  registry_to_dict,
  verify_artifact,
  write_registry,
)


BIG_MANIFEST = {
  "model_id": "comma-pr38771-cinque-terre-68b5f8e4-e8d82173",
  "filename": "big_driving_supercombo.onnx",
  "size": 765950064,
  "sha256": "e8d821733be15ebe9e27498bc27ad8bbbd741980ece37d77f377294010b8ff28",
}


def test_builtin_qcom_and_carrot_egpu_manifest_make_valid_registry():
  qcom = builtin_qcom_slot(generation=10)
  egpu = egpu_slot_from_carrot_manifest(BIG_MANIFEST, generation=11, nominal_hz=20)
  registry = ModelSlotRegistry(qcom=qcom, egpu=egpu)
  registry.validate()
  assert registry.startup_preference(egpu_ready=True) == "egpu"
  assert registry.startup_preference(egpu_ready=False) == "qcom"
  payload = registry_to_dict(registry)
  assert payload["policy"] == {
    "runtimeHotSwap": False,
    "crossSlotFallback": False,
    "controlAuthorization": False,
  }
  assert payload["slots"]["egpu"]["artifact"]["sha256"] == BIG_MANIFEST["sha256"]


def test_nonbuiltin_slot_requires_hashed_artifact():
  slot = ModelSlot(
    slot="egpu",
    model_id="big",
    ref="big",
    backend="amd-usb",
    runner="tinygrad",
    generation=1,
    nominal_hz=20,
    source="test",
    artifact=None,
    builtin=False,
  )
  with pytest.raises(ValueError, match="hashed artifact"):
    slot.validate()


def test_stage3_cannot_authorize_control():
  slot = ModelSlot(
    slot="qcom",
    model_id="small",
    ref="small",
    backend="qcom",
    runner="tinygrad",
    generation=1,
    nominal_hz=20,
    source="test",
    builtin=True,
    control_eligible=True,
  )
  with pytest.raises(ValueError, match="control_eligible"):
    slot.validate()


def test_cross_slot_fallback_is_rejected():
  registry = ModelSlotRegistry(qcom=builtin_qcom_slot(), egpu=None, fallback_slot="egpu")
  with pytest.raises(ValueError, match="fixed to qcom"):
    registry.validate()


def test_egpu_slot_requires_egpu_backend():
  slot = ModelSlot(
    slot="egpu",
    model_id="big",
    ref="big",
    backend="qcom",
    runner="tinygrad",
    generation=1,
    nominal_hz=20,
    source="test",
    artifact=ModelArtifact("big.onnx", 1, "0" * 64),
  )
  with pytest.raises(ValueError, match="egpu slot"):
    slot.validate()


def test_registry_roundtrip(tmp_path):
  registry = ModelSlotRegistry(
    qcom=builtin_qcom_slot(),
    egpu=egpu_slot_from_carrot_manifest(BIG_MANIFEST),
  )
  path = tmp_path / "slots.json"
  write_registry(path, registry)
  loaded = load_registry(path)
  assert loaded == registry
  raw = json.loads(path.read_text(encoding="utf-8"))
  assert raw["schemaVersion"] == 1
  assert raw["fallbackSlot"] == "qcom"


def test_registry_rejects_control_authorization_from_json():
  registry = ModelSlotRegistry(
    qcom=builtin_qcom_slot(),
    egpu=egpu_slot_from_carrot_manifest(BIG_MANIFEST),
  )
  payload = registry_to_dict(registry)
  payload["slots"]["egpu"]["control_eligible"] = True
  with pytest.raises(ValueError, match="control_eligible"):
    registry_from_dict(payload)


def test_artifact_safe_basename_required():
  with pytest.raises(ValueError, match="safe basename"):
    ModelArtifact("../big.onnx", 10, "0" * 64).validate()


def test_verify_artifact_checks_size_and_sha(tmp_path):
  data = b"egpu-future-model-artifact"
  path = tmp_path / "artifact.bin"
  path.write_bytes(data)
  artifact = ModelArtifact(path.name, len(data), hashlib.sha256(data).hexdigest())
  assert verify_artifact(path, artifact)
  assert not verify_artifact(path, ModelArtifact(path.name, len(data) + 1, artifact.sha256))
  assert not verify_artifact(path, ModelArtifact(path.name, len(data), "0" * 64))
