# EGPU-Future 개발 현황

작성일: 2026-09-07

## 현재 구현 완료

### 1. Chestnut telemetry logger

`tools/chestnut_telemetry_logger.py`

openpilot 환경에서 다음을 JSONL로 기록한다.

- GPU hotspot / memory temperature
- GPU power draw / observed power limit
- GPU usage / clock / fan RPM
- Chestnut supply voltage / current / fault
- PCIe LTSSM
- Chestnut presence
- modelV2 alive/valid
- vehicle speed / standstill

이 도구는 **읽기 전용**이며 GPU PPT나 차량 제어 값을 변경하지 않는다.

### 2. PPT sweep 분석기

`tools/analyze_ppt_sweep.py`

관측된 `powerLimitW`별로 평균 GPU power, GPU/VRAM p95 온도, fan RPM, minimum supply voltage, p95 supply current, supply fault, PCIe abnormal sample, model dead sample을 집계한다.

현재 버전은 PPT를 자동으로 변경하지 않는다.

### 3. eGPU recovery state machine

`egpu_future/recovery_state_machine.py`

상태:

```text
DISCONNECTED
  → POWER_WAIT
  → USB_READY
  → PCIE_READY
  → MODEL_WARMUP
  → ACTIVE
  ↔ DERATED
  → FALLBACK
  → RETRY_WAIT
  → MODEL_WARMUP
```

기본 연구값:

- power valid: >= 5000 mV
- proactive GPU derate: 90 °C
- proactive memory derate: 85 °C
- hard GPU fallback: 100 °C
- hard memory fallback: 95 °C

90/85 °C는 comma 공식 기준이 아니라 EGPU-Future의 초기 연구값이다.

### 4. Recovery telemetry simulator

`tools/replay_recovery_state.py`

실제/가상 telemetry JSONL을 recovery state machine에 재생하여 power loss, USB/PCIe fault, thermal fault, model/deadline fault가 기대 상태로 전이되는지 확인한다.

### 5. Shadow disagreement metric

`egpu_future/shadow_metrics.py`

openpilot의 `modelV2.action`에 존재하는:

- desiredCurvature
- desiredAcceleration
- shouldStop

을 기준으로 small/big model 차이를 계산한다.

연구용 disagreement score는 안전점수가 아니다. 이벤트 우선순위 선별용이다.

### 6. Scenario tagger

`egpu_future/scenario_tagger.py`

현재 최소 태그:

- standstill
- creep
- hard_decel
- hard_accel
- curve
- sharp_curve
- lead_present
- close_lead
- closing_fast
- no_lead
- cruise

향후 cut-in, lead acquired/lost, lane merge, cone/construction 등 vision/model 정보를 쓰는 태그를 추가한다.

### 7. Offline shadow-run comparator

`tools/compare_shadow_runs.py`

small/big action JSONL을 timestamp 기준으로 pairing한 뒤:

- curvature absolute/relative difference
- acceleration difference
- shouldStop mismatch
- disagreement score
- scenario tags

를 계산하여 `shadow_events.jsonl`에 significant event만 저장한다.

### 8. Model action capture

`tools/capture_model_actions.py`

현재 실행 중인 stock modeld의 `modelV2.action`을 차량제어와 독립적으로 읽어서 JSONL로 저장한다.

주의: stock modeld는 같은 순간 big/small을 모두 publish하지 않는다. 따라서 이 도구만으로 live dual-model shadow가 완성되는 것은 아니다.

### 9. Latency profiler

`tools/latency_profiler.py`

JSONL의 latency field를 기준으로:

- mean
- p50
- p95
- p99
- max
- deadline miss count/rate

를 계산한다.

현재 기본 deadline은 50 ms이며 이는 20 Hz nominal model period와 맞춘 분석 기본값이다. 실제 안전/제어 deadline으로 간주하지 않는다.

### 10. Shadow event summary

`tools/summarize_shadow_events.py`

저장된 disagreement event를 scenario tag, stop mismatch, score 중심으로 요약한다.

---

# 현재 확인된 openpilot 제약

현재 stock `modeld`는 `modelV2`와 `drivingModelData`를 publish하지만, 제어경로에서는 big 또는 small 중 현재 active model 하나의 결과를 publish한다.

따라서 **진짜 live dual-model shadow runner**는 다음 중 하나가 필요하다.

1. 별도 `shadow_modeld`가 camera frame을 받아 small model을 추가 실행하거나,
2. stock modeld 내부에 non-controlling shadow inference path를 추가하거나,
3. 동일 route/frame을 replay하여 small/big을 별도 실행하고 offline pairing한다.

초기 안전성과 재현성 때문에 3 → 1 → 2 순서를 권장한다.

---

# 아직 구현하지 않은 것

## A. GPU PPT 자동 제어

`tinygrad` AMD SMU에는 `set_power_limit(watts)`가 존재하지만 아직 자동제어와 연결하지 않았다.

순서:

```text
read-only logging
 → 수동 PPT sweep
 → stable operating envelope 확정
 → advisory controller
 → shadow automatic controller
 → 충분한 검증 후 제한적 자동 적용
```

## B. True live dual-model shadow runner

다음 핵심 개발 항목이다.

목표:

- 동일 camera frame에 small/big inference
- big 또는 shadow output은 차량제어에 사용하지 않음
- frameId / camera timestamp / inference latency / action 동시 기록
- disagreement event 자동 저장
- active model에 영향이 없도록 process/resource isolation

## C. End-to-end latency instrumentation

최종적으로 필요한 timestamp:

```text
camera SOF/EOF
 → frame available
 → preprocessing start/end
 → USB transfer/enqueue
 → GPU complete
 → model output publish
 → control consume
 → CAN send
```

평균 FPS보다 p95/p99 latency와 deadline miss가 핵심이다.

---

# Fault-injection test matrix

| ID | fault | 기대 동작 |
|---|---|---|
| F01 | Chestnut missing | DISCONNECTED 유지, small model |
| F02 | 12 V 늦게 인가 | POWER_WAIT 후 초기화 후보 |
| F03 | crank voltage drop | FALLBACK, stable power 후 retry |
| F04 | USB disconnect | 즉시 FALLBACK |
| F05 | PCIe link loss | 즉시 FALLBACK |
| F06 | telemetry invalid | FALLBACK |
| F07 | GPU warm | DERATED |
| F08 | GPU/VRAM hard temp | FALLBACK |
| F09 | model warmup timeout | FALLBACK → RETRY_WAIT |
| F10 | inference deadline 반복 위반 | FALLBACK |
| F11 | 전원 복구 | debounce 이후 safe retry |

---

# 싼타페 TM 실차 단계

대상차량:

**더 뉴 싼타페 TM 2021 / D2.2 / 2WD / 5인승 / 프레스티지 / 조수석 전동·통풍시트**

Chestnut 장착 후 순서:

1. passenger footwell temporary rigid tray
2. OEM 12 V outlet + comma supplied power cable
3. read-only telemetry 30/60/120분
4. cold/warm start 및 ISG stop-restart 기록
5. heat-soak 기록
6. 수동 PPT sweep
7. fan RPM / cabin dBA / model latency 비교
8. quiet/efficient operating point 선정
9. 이후 조수석 하부 최종 bracket 검토

---

# 다음 구현 순서

1. route/replay 기반 small/big action extractor
2. frameId 기반 deterministic pairing
3. true `shadow_modeld` prototype 설계
4. camera/model inference timestamp instrumentation
5. lead acquired/lost, cut-in, merge 등 scenario tag 확장
6. route health report 자동 생성
7. 이후 advisory PPT controller

원칙은 **관측 가능성 → 재현 가능한 replay 비교 → shadow 실행 → fault recovery → 자동 최적화** 순이다.
