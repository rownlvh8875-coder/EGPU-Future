# Stage 2 — Carrot-WIP eGPU Hardware Telemetry

작성일: 2026-09-07

## 목적

`carrot-wip`의 eGPU primary driving model, startup/retry, same-frame QCOM fallback은 그대로 유지하면서 comma.ai Chestnut에서 검증된 하드웨어 관측 항목을 **읽기 전용**으로 추가한다.

이 단계는 eGPU를 제어하는 단계가 아니다.

```text
GPU 상태 읽기
  -> /data/egpu_integrated/hardware.json
  -> 연구/진단/commissioning

절대 연결하지 않음:
  -> modelV2 선택
  -> steering/braking
  -> panda safety
  -> PPT 자동변경
```

## 왜 modeld 20 Hz loop에서 직접 읽지 않는가

SMU table, USB bridge, PCIe LTSSM 조회는 정상일 때 짧더라도 순간적으로 지연될 수 있다.

따라서 다음 구조를 사용한다.

```text
modeld realtime loop
    |
    +---- driving inference 20 Hz
    |
    +---- EgpuHardwareTelemetry.start()
              |
              +-- daemon thread
                    |
                    +-- 2 s nominal interval
                    +-- SMU metrics read
                    +-- supply voltage/current read
                    +-- PCIe status read
                    +-- atomic JSON write
```

telemetry thread의 결과는 modeld가 다시 읽지 않는다.

즉 telemetry 실패/지연/파일쓰기 실패가 주행 판단의 입력이 되지 않는다.

## 활성화

기본값은 OFF다.

다음 중 하나로만 활성화한다.

```bash
export EGPU_INTEGRATED_TELEMETRY=1
```

또는:

```text
/data/egpu_integrated/telemetry_enabled
```

출력 기본 경로:

```text
/data/egpu_integrated/hardware.json
```

## 수집 항목

### AMD SMU

- `tempC` — hotspot temperature
- `memoryTempC` — memory/HBM temperature when exposed by SMU
- `powerDrawW` — socket power
- `powerLimitW` — current PPT limit when queryable, otherwise table limit
- `gpuUsagePercent`
- `gpuClockMhz`
- `fanSpeedRpm` when exposed

### Carrot USB bridge / power

- `supplyVoltageMv`
- `supplyCurrentMa`
- `supplyFault`
- `usbSpeedMbps`
- `usbLinkErrorCount`
- `firmwareCurrent`

### PCIe

- `pcieLtssm`

### observer 자체 상태

- `amdOpened`
- `valid`
- `errors`
- `sampleDurationMs`

## AMD device ownership 원칙

telemetry 때문에 GPU를 새로 열지 않는다.

```text
Device._opened_devices 에 AMD 없음
  -> AMD를 열지 않음
  -> supply/USB 정보만 가능한 범위에서 기록

modeld가 이미 AMD를 열었음
  -> 기존 Device["AMD"] 객체를 사용
  -> SMU/PCIe 읽기
```

이 원칙은 telemetry 때문에 eGPU 초기화 순서가 바뀌는 것을 방지한다.

## SMU table 호환

현재 `carrot-wip` tinygrad의 `am_smi.py`와 동일하게 SMU IP version별 table 차이를 구분한다.

- SMU 13.0.6: `MetricsTableV0_t`, Q10 fields
- SMU 13.0.12: `MetricsTable_t`, Q10 fields
- 그 외: `SmuMetricsExternal_t`

consumer RDNA 계열에서는 `SmuMetrics`의 hotspot/memory/power/activity/clock/fan 값을 사용한다.

PPT 조회는 `PPSMC_MSG_GetPptLimit`을 **읽기 명령으로만** 호출하며 실패 시 metrics table의 power limit으로 fallback한다.

`PPSMC_MSG_SetPptLimit`은 S2에서 사용하지 않는다.

## USB serialization

Carrot는 이미 다음 interprocess lock을 사용한다.

```text
/tmp/carrot_usbgpu_bus.lock
```

`usbgpu_bus_lock()`은 re-entrant이며 tinygrad USB transport와 Carrot cluster USB display가 같은 lock을 공유한다.

S2의 supply/PCIe 읽기도 이 lock을 사용한다. SMU read의 USB transaction도 tinygrad USB layer가 같은 lock을 사용한다.

따라서 별도 독자 USB locking 체계를 만들지 않는다.

## 출력 예시

```json
{
  "schemaVersion": 1,
  "timestampMonoS": 12345.67,
  "valid": true,
  "amdOpened": true,
  "tempC": 72.0,
  "memoryTempC": 78.0,
  "powerDrawW": 108.0,
  "powerLimitW": 120.0,
  "gpuUsagePercent": 71.0,
  "gpuClockMhz": 2380.0,
  "fanSpeedRpm": 1250.0,
  "supplyVoltageMv": 12180,
  "supplyCurrentMa": 9800,
  "supplyFault": false,
  "pcieLtssm": 120,
  "usbSpeedMbps": 5000,
  "usbLinkErrorCount": 0,
  "firmwareCurrent": true,
  "errors": [],
  "sampleDurationMs": 4.2
}
```

위 숫자는 schema 예시일 뿐 실제 차량/GPU 측정값이 아니다.

## Stage-2 patch layering

S2는 S1 위에만 적용한다.

```text
reviewed carrot-wip modeld
  -> S1 observer patch
  -> S2 telemetry patch
```

S2 marker를 제거하면 S1 source가 byte-for-byte 복원되어야 한다.
S1 marker까지 제거하면 원래 reviewed `carrot-wip/modeld.py`가 byte-for-byte 복원되어야 한다.

도구:

```text
tools/apply_carrot_wip_integrated_stage1.py
tools/apply_carrot_wip_integrated_stage2.py
```

## S2 완료 기준

- telemetry default OFF
- AMD device를 telemetry가 먼저 열지 않음
- 20 Hz model loop에서 hardware read를 수행하지 않음
- all hardware writes absent
- USB access uses Carrot locking path
- Stage-2 제거 시 exact S1 restore
- S1 제거 시 exact carrot-wip restore
- pure-Python normalization/worker/patch tests PASS

## 다음 단계

S2 이후에만 S3 model-slot metadata layer로 진행한다.

S3에서 할 일:

```text
QCOM slot
EGPU slot
  |
  +-- model ID/ref
  +-- hash
  +-- generation
  +-- nominal Hz
  +-- backend/runner
  +-- compatibility
```

중요하게도 S3도 처음에는 **모델 선택 metadata/검증 계층**만 만들고, 주행 중 자동 hot-swap은 만들지 않는다.
