from types import SimpleNamespace
import json

from integrations.carrot_wip_integrated.runtime.egpu_hardware_telemetry import (
  EgpuHardwareTelemetry,
  normalize_smu_metrics,
)


class ArrayLike:
  def __init__(self, values):
    self.values = list(values)

  def __getitem__(self, index):
    return self.values[index]


def test_normalize_consumer_rdna_metrics_prefers_ppt_limit():
  smu_mod = SimpleNamespace(TEMP_HOTSPOT=0, TEMP_MEM=1)
  nested = SimpleNamespace(
    AvgTemperature=ArrayLike([76, 82]),
    AverageSocketPower=118,
    dGPU_W_MAX=132,
    AverageGfxActivity=64,
    AverageGfxclkFrequencyPreDs=2410,
    AverageGfxclkFrequencyPostDs=750,
    AvgFanRpm=1325,
  )
  metrics = SimpleNamespace(SmuMetrics=nested)

  out = normalize_smu_metrics(metrics=metrics, smu_mod=smu_mod, ip_version=(14, 0, 2), ppt_limit_w=120)
  assert out == {
    "tempC": 76.0,
    "memoryTempC": 82.0,
    "powerDrawW": 118.0,
    "powerLimitW": 120.0,
    "gpuUsagePercent": 64.0,
    "gpuClockMhz": 2410.0,
    "fanSpeedRpm": 1325.0,
  }


def test_normalize_consumer_idle_uses_post_ds_clock():
  smu_mod = SimpleNamespace(TEMP_HOTSPOT=0, TEMP_MEM=1)
  metrics = SimpleNamespace(SmuMetrics=SimpleNamespace(
    AvgTemperature=ArrayLike([55, 61]),
    AverageSocketPower=31,
    dGPU_W_MAX=132,
    AverageGfxActivity=2,
    AverageGfxclkFrequencyPreDs=2200,
    AverageGfxclkFrequencyPostDs=420,
    AvgFanRpm=0,
  ))
  out = normalize_smu_metrics(metrics=metrics, smu_mod=smu_mod, ip_version=(14, 0, 2))
  assert out["gpuClockMhz"] == 420.0
  assert out["powerLimitW"] == 132.0


def test_normalize_q10_metrics():
  q = lambda value: int(value) << 10
  metrics = SimpleNamespace(
    MaxSocketTemperature=q(71),
    MaxHbmTemperature=q(79),
    SocketPower=q(244),
    SocketPowerLimit=q(500),
    SocketGfxBusy=q(88),
    GfxclkFrequency=[q(1800)],
  )
  out = normalize_smu_metrics(metrics=metrics, smu_mod=SimpleNamespace(), ip_version=(13, 0, 12))
  assert out["tempC"] == 71
  assert out["memoryTempC"] == 79
  assert out["powerDrawW"] == 244
  assert out["powerLimitW"] == 500.0
  assert out["gpuUsagePercent"] == 88
  assert out["gpuClockMhz"] == 1800
  assert "fanSpeedRpm" not in out


def test_invalid_numeric_fields_are_not_serialized():
  smu_mod = SimpleNamespace(TEMP_HOTSPOT=0, TEMP_MEM=1)
  metrics = SimpleNamespace(SmuMetrics=SimpleNamespace(
    AvgTemperature=ArrayLike([float("nan"), float("inf")]),
    AverageSocketPower=float("nan"),
    dGPU_W_MAX=132,
    AverageGfxActivity=0,
    AverageGfxclkFrequencyPreDs=float("nan"),
    AverageGfxclkFrequencyPostDs=500,
    AvgFanRpm=None,
  ))
  out = normalize_smu_metrics(metrics=metrics, smu_mod=smu_mod, ip_version=(14, 0, 2))
  assert "tempC" not in out
  assert "memoryTempC" not in out
  assert "powerDrawW" not in out
  assert out["powerLimitW"] == 132.0
  assert out["gpuClockMhz"] == 500.0


def test_disabled_worker_does_not_start(tmp_path):
  path = tmp_path / "hardware.json"
  worker = EgpuHardwareTelemetry(enabled=False, state_path=path, interval_s=0.5)
  worker.start()
  assert worker._thread is None
  assert not path.exists()


def test_worker_contains_collection_and_write_failures(monkeypatch, tmp_path):
  import integrations.carrot_wip_integrated.runtime.egpu_hardware_telemetry as hw

  parent_file = tmp_path / "not_a_directory"
  parent_file.write_text("x", encoding="utf-8")
  path = parent_file / "hardware.json"
  monkeypatch.setattr(hw, "collect_hardware_snapshot", lambda: {"schemaVersion": 1, "valid": True})

  worker = EgpuHardwareTelemetry(enabled=True, state_path=path, interval_s=0.5)
  worker.start()
  assert worker._thread is not None
  worker._thread.join(0.2)
  worker.stop(0.2)
  # A write failure is contained in the background thread and never escapes to modeld.
  assert worker.status.errors >= 1


def test_worker_writes_json(monkeypatch, tmp_path):
  import integrations.carrot_wip_integrated.runtime.egpu_hardware_telemetry as hw

  path = tmp_path / "hardware.json"
  monkeypatch.setattr(hw, "collect_hardware_snapshot", lambda: {
    "schemaVersion": 1,
    "valid": True,
    "tempC": 70.0,
    "powerDrawW": 105.0,
  })
  worker = EgpuHardwareTelemetry(enabled=True, state_path=path, interval_s=0.5)
  worker.start()
  for _ in range(20):
    if path.exists():
      break
    import time
    time.sleep(0.01)
  worker.stop(0.2)
  data = json.loads(path.read_text(encoding="utf-8"))
  assert data["valid"] is True
  assert data["tempC"] == 70.0
  assert worker.status.samples >= 1
