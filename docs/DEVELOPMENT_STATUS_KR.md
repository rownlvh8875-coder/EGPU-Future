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

예시:

```bash
python3 tools/chestnut_telemetry_logger.py \
  --output /data/media/0/chestnut_telemetry.jsonl \
  --hz 2 \
  --duration 3600
```

## 2. PPT sweep 분석기

`tools/analyze_ppt_sweep.py`

관측된 `powerLimitW`별로 다음을 집계한다.

- 평균 GPU power
- GPU/VRAM p95 temperature
- fan 평균/p95 RPM
- minimum supply voltage
- p95 supply current
- supply fault count
- PCIe 비정상 sample
- model dead sample

예시:

```bash
python3 tools/analyze_ppt_sweep.py chestnut_telemetry.jsonl --csv ppt_summary.csv
```

중요: 현재 버전은 PPT를 자동으로 변경하지 않는다. PPT 변경은 별도 실험 단계에서 사람이 승인한 값으로 시행한다.

## 3. eGPU recovery state machine

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

현재 정책은 openpilot의 기존 hard thermal 기준과 연구용 proactive derate 기준을 분리한다.

기본 연구값:

- power valid: >= 5000 mV (Chestnut status 코드와 동일한 판단 기준)
- proactive GPU derate: 90 °C
- proactive memory derate: 85 °C
- hard GPU fallback: 100 °C
- hard memory fallback: 95 °C

90/85 °C는 comma 공식 기준이 아니라 EGPU-Future의 초기 연구값이다. 실차 데이터로 조정한다.

Recovery logic은 openpilot과 독립된 pure Python으로 먼저 검증하고, 충분한 fault-injection test 후에만 modeld/hardwared integration을 검토한다.

## 4. Big/Small disagreement analyzer

`tools/disagreement_analyzer.py`

동일 시점의 small/big 모델 action을 CSV로 받아 다음 차이를 계산한다.

- desired curvature 차이
- desired acceleration 차이
- shouldStop 판단 차이
- 종합 disagreement score

목적은 big model이 실제로 유리한 long-tail scene을 자동 추출하기 위한 것이다.

현재 openpilot stock `modeld`는 big과 small을 항상 동시에 publish하는 구조가 아니므로, 다음 단계에서 shadow-output capture 방법을 별도로 구현한다.

---

# 아직 구현하지 않은 것

## A. GPU PPT 자동 제어

`tinygrad` AMD SMU에는 `set_power_limit(watts)`가 존재하지만 아직 자동제어와 연결하지 않았다.

이유:

1. RX 9060에서 유효한 최소/최대 범위를 실측해야 함
2. PPT 변경 중 inference deadline 영향 확인 필요
3. 잘못된 thermal control이 오히려 모델 지연을 유발할 수 있음
4. 차량 주행 중 자동 power tuning 전에 bench/parked test가 필요함

따라서 순서:

```text
read-only logging
 → 수동 PPT sweep
 → stable operating envelope 확정
 → advisory controller
 → shadow automatic controller
 → 충분한 검증 후 제한적 자동 적용
```

## B. Big/Small dual-model live shadow runner

현재 최우선 다음 개발 항목이다.

목표:

- 동일 camera frame에 small/big model inference
- big output은 차량제어에 사용하지 않는 shadow mode
- timestamp / inference latency / action output 동시 기록
- disagreement event 자동 저장

초기에는 vehicle command path와 완전히 분리한다.

## C. End-to-end latency profiler

필요 timestamp:

```text
camera SOF/EOF
 → frame available
 → preprocessing start/end
 → GPU enqueue
 → GPU complete
 → model output
 → control consume
 → CAN send
```

Chestnut의 핵심 평가는 평균 FPS가 아니라 p95/p99 end-to-end latency와 deadline miss rate로 수행한다.

---

# Fault-injection test matrix

Recovery state machine은 다음을 순서대로 시험한다.

| ID | fault | 기대 동작 |
|---|---|---|
| F01 | Chestnut missing | DISCONNECTED 유지, small model |
| F02 | 12 V 늦게 인가 | POWER_WAIT 후 자동 초기화 후보 |
| F03 | crank voltage drop | FALLBACK, stable power 후 retry |
| F04 | USB disconnect | 즉시 FALLBACK |
| F05 | PCIe link loss | 즉시 FALLBACK |
| F06 | telemetry invalid | FALLBACK |
| F07 | GPU warm | DERATED |
| F08 | GPU/VRAM hard temp | FALLBACK |
| F09 | model warmup timeout | FALLBACK → RETRY_WAIT |
| F10 | inference deadline 반복 위반 | FALLBACK |
| F11 | 전원 복구 | 일정 debounce 이후 safe retry |

주행제어와 연결하기 전 bench/replay test에서 모두 통과해야 한다.

---

# 싼타페 TM 실차 단계

대상차량:

**더 뉴 싼타페 TM 2021 / D2.2 / 2WD / 5인승 / 프레스티지 / 조수석 전동·통풍시트**

실차 장착 전에는 현재 코드만 개발한다.

Chestnut 도착/장착 후 순서:

1. passenger footwell temporary rigid tray
2. OEM 12 V outlet + comma supplied power cable
3. read-only telemetry 30/60/120분
4. cold start / warm start / ISG stop-restart 기록
5. heat-soak 조건 기록
6. 수동 PPT sweep
7. fan RPM / cabin dBA / model latency 비교
8. 최적 operating point 선정
9. 이후 조수석 하부 최종 bracket 검토

---

# 다음 구현 순서

1. `shadow_runner` 설계 및 최소 구현
2. model inference latency timestamp capture
3. disagreement event schema 확정
4. scenario tagger 연결
5. recovery state-machine simulator/CLI
6. read-only route health report 자동 생성
7. 이후에만 advisory PPT controller 구현

원칙은 **먼저 관측 가능성(observability), 그 다음 fault recovery, 마지막에 자동 최적화**다.
