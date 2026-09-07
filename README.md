# EGPU-Future

comma 4 + Chestnut/eGPU 이후의 openpilot 계열 자율주행 발전 방향을 조사하고, 실제 차량에서 검증 가능한 형태로 구현하는 연구 저장소입니다.

목표는 단순히 GPU를 달아 FPS를 올리는 것이 아닙니다.

**더 큰 driving/world model을 실차에서 사용할 수 있게 된 이후 센서·학습·안전·전원·열·통신·fallback·replay·live shadow 검증까지 포함한 vehicle-integrated autonomy architecture를 만드는 것**을 목표로 합니다.

---

## 핵심 방향: Guardian + Intelligence Sidecar

- **comma four / Guardian**: 카메라 입력, 차량 인터페이스, 상태추정, DMS, health/deadline 감시, small-model fallback
- **eGPU / Intelligence**: large driving model, 긴 temporal context, scene reasoning, 향후 world model
- **Safety/Output Validator**: frame freshness, latency, action disagreement, vehicle feasibility를 독립 검증
- **Learning Plane**: small/big disagreement, hard-case mining, replay/simulation, teacher→student distillation
- **차량 제어**: 차량별 actuator 한계와 panda/openpilot safety constraint 유지

**AI capability ≠ vehicle control capability**입니다. eGPU가 커져도 OEM EPS torque/angle-rate, longitudinal authority, 센서 blind spot은 자동으로 해결되지 않습니다.

---

# 현재 개발 단계

현재는 replay 비교를 넘어 **control-isolated live `shadow_modeld` prototype**까지 구현했습니다.

```text
replay small/big 비교
 → frameId deterministic pairing
 → freshness/deadline/action validator
 → eGPU recovery / same-frame fallback budget
 → live shadow input tap
 → control-isolated shadow small model
 → active-path interference 측정   ← 현재
 → 검증 후에만 다음 통합 단계 검토
```

현재 live 구조:

```text
camerad
  │
  ├────────→ active big modeld ─────────→ modelV2 → controls
  │                    │
  │                    │ non-blocking metadata tap
  │                    ▼
  └────────→ shadow small modeld ───────→ JSONL only
```

shadow output은 `modelV2`로 publish하지 않고 차량제어에 사용하지 않습니다.

상세: [True shadow_modeld Prototype](docs/SHADOW_MODELD_PROTOTYPE_KR.md)

---

# Chestnut이 바꾸는 것

comma.ai는 2026-08-12 Chestnut을 공개했습니다.

확인된 방향:

- comma four + 외장 desktop GPU
- 기존 on-device model 대비 약 30배 parameter, 약 100배 FLOPs라는 launch 설명
- Ready-to-Drive 구성의 AMD Radeon RX 9060 8GB
- passenger footwell 또는 passenger seat 아래 설치
- vehicle 12 V power 사용

정확성 메모:

- Chestnut launch blog는 `1B parameter`라고 표현
- 현재 openpilot 0.11.2 `RELEASES.md`는 **880M parameters**라고 명시

따라서 이 저장소에서는 **1B급 모델(공식 release-note 정확값 880M)**로 구분합니다.

comma.ai의 `Tesla HW4와 유사한 compute` 표현은 compute 비교이며 Tesla 전체 센서·전원·안전·차량제어 architecture와 동등하다는 독립검증 결과로 취급하지 않습니다.

---

# 다른 자율주행 프로젝트에서 가져올 부분

| 프로젝트 | 핵심 접근 | EGPU-Future 적용 |
|---|---|---|
| Tesla | fleet data + end-to-end + distillation + factory-integrated vision | big→small distillation, fleet learning loop |
| Wayve | end-to-end Embodied AI / foundation model | generalizable large driving/evaluator model |
| Waymo | camera+lidar+radar redundancy + simulation/world model | long-tail validation, world-model evaluation |
| Mobileye | True Redundancy + RSS | independent safety envelope |
| Autoware | modular validation + mixed criticality | intelligence와 guardian 분리 |
| Apollo | perception/prediction/planning/control 모듈화 | observability / fault localization |
| NVIDIA DRIVE | automotive-grade integrated compute/sensors | FLOPS보다 system integration이 중요 |

상세: [자율주행 아키텍처 비교](docs/AUTONOMY_ARCHITECTURE_COMPARISON_KR.md)

---

# ajouatom Carrot eGPU에서 확인한 중요한 아이디어

분석한 branch:

- `carrot-egpu-yolo`
- `thftgr/carrot-egpu`
- `thftgr/carrot-egpu-tg`

현재 `carrot-egpu-yolo`에서 특히 가치 있는 설계:

1. eGPU startup grace
2. PCIe readiness retry
3. model loader timeout/상태 observability
4. 사용자 의도적 disable과 fault 구분
5. eGPU runtime 실패 시 **이미 로드된 internal model로 같은 camera frame 재실행**
6. YOLO/RoadSeg/Lane 등 eGPU sidecar perception 실험

EGPU-Future에서는 전체 Carrot branch를 합치지 않고 기능 단위로 재구현합니다.

현재 반영:

- `EgpuState.DISABLED`
- official Chestnut power profile = 5000 mV
- current Carrot USB-GPU profile = 8000 mV
- deterministic frameId pairing
- frame freshness/deadline/action validator
- same-frame hot-fallback latency budget evaluator
- official/Carrot `modeld` API compatibility layer

상세: [ajouatom Carrot eGPU 브랜치 분석](docs/AJOUATOM_CARROT_EGPU_ANALYSIS_KR.md)

---

# RX 9060과 Chestnut만 가능한가?

**RX 9060만 가능한 것은 아닙니다.** comma는 Chestnut `eGPU dock only` 옵션을 자신의 GPU와 power supply로 사용할 수 있도록 판매합니다.

다만 현재 openpilot big-model 경로는:

- `USB+AMD` tinygrad backend
- Chestnut-specific USB ID/custom firmware
- AMD telemetry/SMU 접근

에 강하게 연결되어 있습니다.

따라서 현재 연구 우선순위:

- **Chestnut + RX 9060**: 공식 baseline
- **Chestnut + 다른 AMD GPU**: 검증 대상
- **NVIDIA GPU**: 현재 경로의 plug-and-play 지원으로 간주하지 않음
- **일반 USB4/Thunderbolt eGPU dock**: Chestnut drop-in 대체품으로 확인되지 않음

초기에는 **dock은 Chestnut으로 고정하고 GPU/PPT만 바꾸는 방식**이 원인분리에 가장 유리합니다.

상세: [GPU / eGPU Dock 호환성 분석](docs/GPU_DOCK_COMPATIBILITY_KR.md)

---

# 전원·발열·소음

RX 9060 공식 Typical Board Power는 **132 W**입니다.

단순 계산:

- 12 V 이상적: 약 11.0 A
- 12 V, 변환효율 90%라는 연구 가정: 약 12.2 A

하지만 GPU TBP 외에 Chestnut, 변환손실, 케이블/접점손실, transient가 존재하므로 12 V outlet의 정격과 단순 비교만으로 충분하지 않습니다.

장기 연구차량 전원 구조 후보:

```text
Vehicle low-voltage bus
 → source-side fuse
 → reverse-polarity/transient protection
 → automotive power stage
 → ACC/ignition controlled enable
 → low-voltage cutoff
 → voltage/current telemetry
 → Chestnut + GPU
```

GPU 열/소음은 fan만 키우기보다 **deadline을 만족하는 최저 PPT를 찾는 방식**을 우선합니다.

tinygrad AMD SMU에는 `set_power_limit(watts)`가 존재하지만 현재 EGPU-Future는 자동 PPT 변경을 차량 주행경로에 연결하지 않습니다.

순서:

```text
read-only logging
 → manual PPT sweep
 → stable operating envelope
 → advisory controller
 → shadow automatic controller
 → 충분한 검증 후 제한적 자동 적용 검토
```

상세:

- [차량용 eGPU 전원·발열·소음 통합설계](docs/VEHICLE_EGPU_POWER_THERMAL_INTEGRATION_KR.md)
- [Adaptive Power / Thermal / Noise Control](docs/CHESTNUT_POWER_THERMAL_CONTROL_DESIGN_KR.md)

---

# 적용 차량

실차 기준은 다음으로 확정했습니다.

**더 뉴 싼타페 TM / 2021년식 / Smartstream D2.2 디젤 / 2WD / 5인승 / 프레스티지 / 조수석 전동시트 + 통풍시트**

현재 권장 순서:

1. 조수석 발밑 rigid temporary tray에서 초기 검증
2. 순정 12 V outlet + comma power cable로 read-only 계측
3. cold/warm start + ISG stop/restart + heat soak 기록
4. manual PPT sweep
5. fan RPM / cabin dBA / latency 비교
6. 전원 안정성이 확인되면 순정 outlet 유지 여부 판단
7. 조수석 통풍 blower/duct, 전동시트 swept volume, SRS harness를 피한 최종 under-seat bracket 검토

한국형 VIN 기준 현대 GSW 도면의 최종 mm 치수/전용 전원선 설계는 실차 측정과 공식도면 확보 후 확정합니다.

상세:

- [2021 더 뉴 싼타페 TM D2.2 프레스티지 전용 설치안](docs/SANTAFE_TM_2021_D22_PRESTIGE_INSTALL_KR.md)
- [싼타페 일반 설치 검토](docs/SANTAFE_CHESTNUT_INSTALLATION_KR.md)

---

# 현재 구현된 연구 코드

## Telemetry / power

- `tools/chestnut_telemetry_logger.py`
- `tools/analyze_ppt_sweep.py`

## Recovery

- `egpu_future/recovery_state_machine.py`
- `tools/recovery_simulator.py`

현재 상태:

```text
DISABLED
DISCONNECTED
 → POWER_WAIT
 → USB_READY
 → PCIE_READY
 → MODEL_WARMUP
 → ACTIVE ↔ DERATED
 → FALLBACK
 → RETRY_WAIT
 → MODEL_WARMUP
```

## Replay small/big

- `tools/extract_model_actions_from_log.py`
- `egpu_future/frame_pairing.py`
- `tools/pair_shadow_runs.py`
- `egpu_future/shadow_metrics.py`
- `tools/compare_shadow_runs.py`
- `egpu_future/output_validator.py`
- `tools/validate_paired_shadow.py`
- `egpu_future/scenario_tagger.py`
- `tools/summarize_shadow_events.py`
- `tools/latency_profiler.py`
- `tools/hot_fallback_budget.py`

핵심은 **timestamp가 아니라 `modelV2.frameId`를 우선키로 small/big을 1:1 pairing**하는 것입니다.

실행 절차: [Small / Big Model Replay·Shadow 검증 절차](docs/SHADOW_REPLAY_PIPELINE_KR.md)

## Live shadow — 신규

Core:

- `egpu_future/shadow_runtime.py`
- `egpu_future/shadow_tap.py`
- `egpu_future/shadow_log.py`
- `egpu_future/interference.py`

openpilot integration:

- `integrations/openpilot/modeld_shadow_tap_bridge.py`

Runtime / analysis:

- `tools/shadow_modeld_prototype.py`
- `tools/normalize_shadow_modeld_log.py`
- `tools/summarize_shadow_modeld.py`
- `tools/benchmark_shadow_tap.py`
- `tools/compare_active_interference.py`

특징:

- shadow 결과는 JSONL only
- 차량제어 service publish 없음
- non-blocking/fail-open tap
- exact frameId + stateFrameId
- actual frameAge 보존
- same-backend guard
- latest-only/conflated backpressure
- official Chestnut / Carrot USB-GPU API 차이 처리
- active baseline vs shadow-on latency delta 분석

상세: [True shadow_modeld Prototype](docs/SHADOW_MODELD_PROTOTYPE_KR.md)

개발현황: [DEVELOPMENT_STATUS_KR.md](docs/DEVELOPMENT_STATUS_KR.md)

---

# 현재 live shadow의 중요한 제한

## QCOM small model 중복

현재 공식 Chestnut `modeld`는 big이 active여도 fallback용 small model을 warm 상태로 보유합니다. process-separated shadow prototype은 별도의 small model을 추가로 로드합니다.

따라서 실기기에서는 정확도보다 먼저:

- QCOM memory pressure
- QCOM scheduling contention
- active big p95/p99 latency delta
- active frame drop
- fallback small readiness

를 검증합니다.

## temporal state

5 Hz 등의 sampling은 load probe용이며 정확한 temporal 비교용이 아닙니다. 20 Hz 연속 처리와 continuity를 우선합니다.

## tap overhead

socket은 non-blocking이지만 JSON encode 비용은 active process에서 발생합니다. benchmark와 bridge 자체 µs 측정값으로 검증합니다.

---

# 검증 원칙

현재 `output_validator`는 raw tensor 전체의 단일 통계값 대신 다음을 분리합니다.

Hard issue:

- frameId mismatch
- stale frame
- non-finite action
- model execution deadline miss

Review event:

- desiredCurvature disagreement
- desiredAcceleration disagreement
- shouldStop mismatch

현재 45 ms execution threshold, proactive 90/85 °C derate 등은 **EGPU-Future 연구 초기값**이며 공식 comma safety 기준이 아닙니다.

---

# 자동 테스트

`.github/workflows/unit-tests.yml`

현재 pure-Python 영역에 대해 자동테스트:

- recovery state machine
- official/Carrot backend profiles
- user disable semantics
- deterministic frame pairing
- no sample reuse / ambiguity rejection
- output freshness/deadline/action validation
- shadow admission / continuity / backpressure
- tap encode/decode / missing receiver / latest drain
- live frameAge normalization
- official/Carrot backend detection
- active interference metric 계산
- Python compile check

hardware/openpilot integration test는 실제 openpilot/Chestnut 환경에서 별도로 수행합니다.

---

# 다음 개발 단계

1. **comma 장비에서 tap overhead 실측**
2. parked 5 Hz shadow load probe
3. parked/offroad 20 Hz continuity test
4. active big baseline vs shadow-on interference report
5. QCOM second-small memory/scheduling 검증
6. tinygrad-level enqueue/kernel completion timestamp
7. Carrot `prepare_only` hardware smoke test
8. lead acquired/lost, cut-in, merge, construction scenario 확장
9. sidecar YOLO/RoadSeg evidence schema
10. route health report / replay fault injection 자동화
11. 그 다음 advisory PPT controller

처음부터 eGPU/shadow 출력을 차량제어에 넣지 않습니다. **replay → control-isolated shadow → interference/recovery validation → staged integration** 순서로 진행합니다.

---

# 분석 문서

1. [EGPU 이후 자율주행 기술방향 종합분석](docs/EGPU_AUTONOMY_STRATEGY_KR.md)
2. [자율주행 아키텍처 비교](docs/AUTONOMY_ARCHITECTURE_COMPARISON_KR.md)
3. [차량용 eGPU 전원·발열·팬소음·신뢰성 통합 설계](docs/VEHICLE_EGPU_POWER_THERMAL_INTEGRATION_KR.md)
4. [Chestnut Adaptive Power / Thermal / Noise Control](docs/CHESTNUT_POWER_THERMAL_CONTROL_DESIGN_KR.md)
5. [싼타페 일반 설치 검토](docs/SANTAFE_CHESTNUT_INSTALLATION_KR.md)
6. [2021 싼타페 TM D2.2 프레스티지 전용 설치안](docs/SANTAFE_TM_2021_D22_PRESTIGE_INSTALL_KR.md)
7. [GPU / eGPU Dock 호환성 분석](docs/GPU_DOCK_COMPATIBILITY_KR.md)
8. [ajouatom Carrot eGPU 분석](docs/AJOUATOM_CARROT_EGPU_ANALYSIS_KR.md)
9. [Small / Big Replay·Shadow 파이프라인](docs/SHADOW_REPLAY_PIPELINE_KR.md)
10. [True shadow_modeld Prototype](docs/SHADOW_MODELD_PROTOTYPE_KR.md)
11. [개발 현황](docs/DEVELOPMENT_STATUS_KR.md)

---

# 주요 출처

- comma.ai Chestnut: https://blog.comma.ai/chestnut/
- Chestnut product/setup: https://comma.ai/shop/chestnut
- comma official openpilot: https://github.com/commaai/openpilot
- openpilot releases: https://github.com/commaai/openpilot/blob/master/RELEASES.md
- ajouatom/openpilot: https://github.com/ajouatom/openpilot
- tinygrad AMD runtime: https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/support/am/ip.py
- AMD RX 9060: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
- Hyundai owner/service resources: https://ownersmanual.hyundai.com/
- Tesla FSD evidence dashboard: https://www.tesla.com/fsd-evidence-dashboard
- Waymo: https://waymo.com/
- Wayve: https://wayve.ai/technology/
- Mobileye: https://www.mobileye.com/products/
- Autoware: https://github.com/autowarefoundation/openadkit

Last reviewed: 2026-09-07
