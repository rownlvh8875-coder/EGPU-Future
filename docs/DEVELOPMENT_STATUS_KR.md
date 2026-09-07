# EGPU-Future 개발 현황

작성일: 2026-09-07

## 현재 단계

프로젝트는 문서조사 단계에서 **재현 가능한 replay/shadow 검증 도구 단계**로 넘어왔다.

현재 원칙:

```text
관측 가능성
 → deterministic replay 비교
 → output freshness/deadline 검증
 → recovery/hot-fallback 검증
 → live shadow
 → 그 다음에만 자동 최적화/제어 연동
```

차량제어와 GPU PPT 자동 변경은 아직 연결하지 않는다.

---

## 구현 완료

### 1. Chestnut telemetry logger

`tools/chestnut_telemetry_logger.py`

읽기 전용으로 GPU/VRAM 온도, power draw/limit, usage/clock/fan RPM, supply voltage/current/fault, PCIe, Chestnut presence, model alive/valid, 차량속도/정차 상태를 JSONL로 기록한다.

### 2. PPT sweep 분석기

`tools/analyze_ppt_sweep.py`

관측된 PPT별 전력·온도·fan RPM·최저 공급전압·전류·supply fault·PCIe/model 이상을 비교한다. PPT 자동 변경은 하지 않는다.

### 3. eGPU recovery state machine

`egpu_future/recovery_state_machine.py`

상태:

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

추가 반영:

- 사용자 의도적 disable과 장애를 분리
- `official_chestnut_policy()` = 현재 공식 Chestnut 5000 mV powered 기준
- `carrot_usbgpu_policy()` = 현재 ajouatom Carrot USB-GPU 8000 mV minimum-power 기준
- hard thermal: GPU 100 °C / memory 95 °C
- proactive derate 90/85 °C는 EGPU-Future 연구 초기값이며 공식 safety threshold가 아님

### 4. Recovery simulator

`tools/recovery_simulator.py`

telemetry를 상태머신에 재생한다.

```bash
python3 tools/recovery_simulator.py telemetry.jsonl --profile official
python3 tools/recovery_simulator.py telemetry.jsonl --profile carrot
```

프로파일별 전원판정 차이를 같은 로그로 비교할 수 있다.

### 5. Shadow disagreement metric

`egpu_future/shadow_metrics.py`

`modelV2.action`의 `desiredCurvature`, `desiredAcceleration`, `shouldStop` 차이를 계산한다. 점수는 이벤트 선별용 연구값이지 safety score가 아니다.

### 6. Scenario tagger

`egpu_future/scenario_tagger.py`

현재 standstill/creep/hard decel·accel/curve/sharp curve/lead/close lead/closing fast/cruise를 태깅한다. cut-in/lead acquired-lost/merge/construction은 후속 확장한다.

### 7. Route/log action extractor

`tools/extract_model_actions_from_log.py`

openpilot `LogReader`를 사용해 rlog/qlog/route에서 다음을 추출한다.

- frameId / frameIdExtra / frameAge
- logMonoTime
- modelExecutionTime
- big flag
- action 3종
- vEgo/aEgo/standstill
- leadOne context

### 8. Deterministic frame pairing

`egpu_future/frame_pairing.py`  
`tools/pair_shadow_runs.py`

small/big replay를 **frameId 우선**으로 1:1 매칭한다.

기존 nearest-timestamp 방식의 문제였던:

- big sample 재사용
- 서로 다른 replay monotonic time 기준 차이
- ambiguous nearest match

를 방지한다.

Timestamp fallback은 frameId가 없을 때만 명시적으로 켠다.

### 9. Shadow comparator

`tools/compare_shadow_runs.py`

이제 deterministic pairer를 사용하며, significant action disagreement만 scenario tag와 함께 저장한다.

### 10. Output validator

`egpu_future/output_validator.py`  
`tools/validate_paired_shadow.py`

raw tensor 통계 하나가 아니라 다음을 분리 검증한다.

Hard issue:

- frameId mismatch
- stale frame
- non-finite action
- model execution deadline miss

Review event:

- curvature disagreement
- acceleration disagreement
- stop decision mismatch

현재 기본 45 ms execution threshold는 20 Hz/50 ms nominal period에서 시작한 **연구용 값**이며 공식 comma safety threshold가 아니다.

### 11. Latency profiler

`tools/latency_profiler.py`

mean/p50/p95/p99/max/deadline miss rate를 계산한다.

### 12. Same-frame hot fallback budget evaluator

`tools/hot_fallback_budget.py`

Carrot 최신 eGPU 코드에서 확인한 `eGPU failure → 이미 로드된 internal model로 같은 camera frame 재실행` 설계를 실제 latency budget 관점에서 검증한다.

보수적 기본 계산:

```text
big failure detection time
+ handoff overhead
+ small model execution time
≤ research deadline
```

기본 50 ms budget/2 ms overhead는 연구 초기값이며 반드시 실측으로 대체한다.

### 13. Carrot eGPU 분석

`docs/AJOUATOM_CARROT_EGPU_ANALYSIS_KR.md`

분석한 branch:

- `carrot-egpu-yolo`
- `thftgr/carrot-egpu`
- `thftgr/carrot-egpu-tg`

즉시 반영한 설계:

- same-frame hot fallback 개념
- startup/PCIe retry 사고방식
- first-output를 ready milestone으로 보는 방식
- user-disable vs fault 분리
- official/Carrot power profile 분리
- deterministic frame pairing
- action/freshness/deadline validator

전체 Carrot branch를 그대로 merge하지는 않는다.

---

# 자동 테스트

`.github/workflows/unit-tests.yml`

현재 pure-Python 핵심 로직을 GitHub Actions에서 테스트하도록 추가했다.

대상:

- recovery state machine + backend profiles
- deterministic frame pairing
- output validator

openpilot/Chestnut hardware가 필요한 integration test는 별도 환경에서 수행한다.

---

# 현재 확인된 중요한 제약

## Stock official openpilot

공식 stock `modeld`는 control path에서 active big 또는 small 하나를 publish하며 true dual-model shadow를 기본 제공하지 않는다.

## Current Carrot eGPU tip

현재 `carrot-egpu-yolo`는 eGPU primary + warm internal fallback에 가까우며, runtime eGPU exception 발생 시 같은 camera frame을 internal model로 재실행한다.

이는 continuity 측면에서 가치가 있지만, **big 실패 감지시간 + small 재실행시간이 deadline 안에 들어오는지 별도 검증해야 한다.**

---

# 아직 구현하지 않은 핵심

## A. True live dual-model shadow runner

다음 핵심 개발 항목.

목표:

- 동일 frame에 small/big inference
- shadow output은 차량 제어 미사용
- frameId/camera timestamp/inference latency/action 동시 기록
- active control process에 resource interference가 없는지 확인

## B. End-to-end latency instrumentation

필요 timestamp:

```text
camera SOF/EOF
 → frame ready
 → preprocess start/end
 → USB/GPU enqueue
 → GPU complete
 → model output publish
 → controls consume
 → CAN send
```

## C. Sidecar perception evidence

Carrot의 YOLO/RoadSeg/Lane 실험에서 아이디어를 가져오되 처음에는 제어 fusion이 아니라 hard-case mining/evaluator로 사용한다.

## D. GPU PPT 자동 제어

아직 금지.

```text
read-only logging
 → manual PPT sweep
 → stable envelope
 → advisory
 → shadow automatic
 → 충분한 검증 이후에만 제한적 적용 검토
```

---

# Fault-injection test matrix

| ID | fault | 기대 동작 |
|---|---|---|
| F00 | user disable | DISABLED, retry 금지 |
| F01 | eGPU missing | DISCONNECTED, small model |
| F02 | 12 V late | POWER_WAIT 후 초기화 |
| F03 | crank voltage drop | FALLBACK → stable power 후 retry |
| F04 | USB disconnect | FALLBACK |
| F05 | PCIe link loss | FALLBACK |
| F06 | telemetry invalid | FALLBACK |
| F07 | warm GPU | DERATED |
| F08 | GPU/VRAM hard temp | FALLBACK |
| F09 | warmup timeout | FALLBACK → RETRY_WAIT |
| F10 | deadline violation | FALLBACK |
| F11 | power restored | debounce 후 safe retry |
| F12 | eGPU same-frame failure | warm small rerun + deadline 평가 |

---

# 싼타페 TM 실차 단계

대상차량:

**더 뉴 싼타페 TM 2021 / D2.2 / 2WD / 5인승 / 프레스티지 / 조수석 전동·통풍시트**

Chestnut 장착 후:

1. 조수석 발밑 임시 rigid tray
2. 순정 12 V outlet + comma power cable
3. 30/60/120분 read-only telemetry
4. cold/warm start + ISG stop/restart
5. heat-soak
6. manual PPT sweep
7. fan RPM / cabin dBA / latency
8. quiet/efficient point 선정
9. 조수석 하부 최종 bracket 검토

---

# 다음 구현 순서

1. `shadow_modeld` architecture prototype
2. camera/model detailed timestamps
3. sampled dual inference resource budget
4. lead acquired/lost, cut-in, merge tags
5. sidecar YOLO/RoadSeg evidence schema
6. route health report
7. replay fault injection 자동화
8. 이후 advisory PPT controller

원칙은 **관측 → 재현 → shadow → recovery → 자동화** 순이다.
