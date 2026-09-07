# EGPU-Future 개발 현황

작성일: 2026-09-07

## 현재 단계

프로젝트는 **replay 기반 deterministic 비교 단계에서 control-isolated live `shadow_modeld` prototype 단계**로 넘어왔다.

현재 원칙:

```text
관측 가능성
 → deterministic replay 비교
 → output freshness/deadline 검증
 → recovery/hot-fallback 검증
 → control-isolated live shadow prototype
 → active-path interference 검증
 → 그 다음에만 자동 최적화/제어 연동 검토
```

차량제어, panda safety, GPU PPT 자동 변경은 아직 연결하지 않는다.

---

# 구현 완료

## 1. Telemetry / power / recovery

- `tools/chestnut_telemetry_logger.py`
- `tools/analyze_ppt_sweep.py`
- `egpu_future/recovery_state_machine.py`
- `tools/recovery_simulator.py`

지원 내용:

- GPU/VRAM 온도, power, fan, PCIe, supply telemetry 기록
- official Chestnut 5000 mV / Carrot USB-GPU 8000 mV 전원 profile 분리
- DISABLED / DISCONNECTED / POWER_WAIT / USB_READY / PCIE_READY / MODEL_WARMUP / ACTIVE / DERATED / FALLBACK / RETRY_WAIT 상태
- 사용자 disable과 fault 분리
- thermal/recovery replay

## 2. Replay small/big 비교

- `tools/extract_model_actions_from_log.py`
- `egpu_future/frame_pairing.py`
- `tools/pair_shadow_runs.py`
- `egpu_future/shadow_metrics.py`
- `tools/compare_shadow_runs.py`
- `egpu_future/output_validator.py`
- `tools/validate_paired_shadow.py`

핵심:

- `modelV2.frameId` 우선 deterministic 1:1 pairing
- timestamp fallback은 명시적 opt-in
- duplicate/ambiguous sample 재사용 방지
- curvature / acceleration / shouldStop disagreement
- frameAge / non-finite / execution deadline hard validation
- live Chestnut 비교를 위해 `--reference-side big` 지원

현재 45 ms execution threshold는 연구 시작값이며 공식 comma safety 기준이 아니다.

## 3. Same-frame hot fallback budget

`tools/hot_fallback_budget.py`

Carrot에서 확인한:

```text
eGPU runtime failure
 → already-warm internal small model
 → same camera frame 재실행
```

구조가 실제 deadline 안에 들어오는지 latency budget으로 평가한다.

## 4. Carrot eGPU branch 분석

`docs/AJOUATOM_CARROT_EGPU_ANALYSIS_KR.md`

분석 branch:

- `carrot-egpu-yolo`
- `thftgr/carrot-egpu`
- `thftgr/carrot-egpu-tg`

반영한 설계:

- same-frame hot fallback 사고방식
- USB startup grace / PCIe retry
- first model output을 startup completion milestone로 보는 방식
- user-disable vs fault 분리
- official / Carrot power profile 분리
- official / Carrot modeld API 차이 인지

외부 branch를 통째로 merge하지 않고 필요한 설계를 재구현한다.

---

# 5. True live `shadow_modeld` prototype — 신규

상세: `docs/SHADOW_MODELD_PROTOTYPE_KR.md`

현재 지원 목표:

```text
active: Chestnut / Carrot USB-GPU big model
shadow: QCOM small model
```

## 5.1 Pure-Python runtime core

`egpu_future/shadow_runtime.py`

구현:

- active/shadow backend admission
- same-backend guard
- duplicate/old frame 거부
- rate limit
- temporal continuity tracker
- settle window
- timing trace
- latest-only backpressure primitive

## 5.2 Exact input metadata tap

`egpu_future/shadow_tap.py`

active `modeld`가 실제 inference에 사용하는 metadata를 non-blocking UNIX datagram으로 sidecar에 전달한다.

snapshot:

- frameId / frameIdExtra
- stateFrameId
- camera SOF / EOF
- active backend
- vEgo
- main / extra transform
- desire pulse
- traffic convention
- action_t
- monotonic timestamp

sender 정책:

```text
retry 없음
block 없음
receiver 없음 → drop
queue/full/error → drop
active model은 계속
```

## 5.3 openpilot bridge

`integrations/openpilot/modeld_shadow_tap_bridge.py`

지원:

- official: `ModelState.chestnut`
- Carrot: `ModelState.usbgpu`

bridge는 실패 결과를 active model logic에 전달하지 않는 fail-open 구조다.

## 5.4 Shadow runtime

`tools/shadow_modeld_prototype.py`

특징:

- `modelV2` publish 안 함
- cereal control service publish 안 함
- 차량 command 생성 안 함
- JSONL only
- manual-start only
- VisionIPC `conflate=True`
- exact frameId camera matching
- active backend가 small이면 shadow small 정지
- default 20 Hz comparison mode
- lower Hz는 interference/load probe 전용
- official/Carrot ModelState signature runtime detection
- official `after_enqueue` timestamp 지원
- Carrot `prepare_only` API에서는 가짜 enqueue timestamp를 만들지 않음
- `stateFrameId`로 실제 openpilot 방식 `frameAge` 계산

## 5.5 Live result normalization / summary

- `egpu_future/shadow_log.py`
- `tools/normalize_shadow_modeld_log.py`
- `tools/summarize_shadow_modeld.py`

요약 metric:

- shadow output count
- skip reason
- comparisonEligible rate
- frame coverage
- timing order
- model-call mean/p50/p95/p99/max
- camera EOF→done mean/p50/p95/p99/max
- research deadline miss rate

---

# 자동 테스트

`.github/workflows/unit-tests.yml`

현재 CI 대상:

- recovery state machine / backend profiles
- deterministic frame pairing
- output validator
- shadow admission / continuity / timing / latest-only queue
- shadow tap encode/decode / missing receiver / drain-to-latest
- live shadow log normalization / frameAge preservation
- official Chestnut / Carrot USB-GPU backend flag detection
- Python compile check: `egpu_future`, `tools`, `integrations`

openpilot/Chestnut/QCOM hardware integration은 GitHub hosted runner에서 검증할 수 없으므로 별도 실기기 단계다.

---

# 현재 확인된 핵심 리스크

## A. QCOM small model 중복 로드

현재 공식 Chestnut `modeld`는 big 활성 상태에서도 fallback용 small model을 내부에 warm 상태로 보유한다.

현재 process-separated shadow prototype은 QCOM small `ModelState`를 추가로 하나 로드한다.

따라서 다음을 실측하기 전에는 상시 실행하지 않는다.

- QCOM memory pressure
- QCOM scheduling contention
- active big latency delta
- fallback small readiness 영향
- camerad/VisionIPC 영향

## B. temporal parity

20 Hz 연속 실행을 요구한다. frame gap 이후 40-frame settle은 연구 heuristic이며 hidden state가 정확히 동일해졌다는 보장이 아니다.

## C. active tap overhead

UNIX socket은 non-blocking이지만 JSON encode는 active process에서 동기 수행한다. bridge에서 encode+send µs를 기록하고 실기기에서 영향도를 측정한다.

## D. Carrot enqueue timestamp

현재 분석한 Carrot `ModelState.run(..., prepare_only)`에는 공식 `after_enqueue` callback이 없다. 따라서 enqueue timestamp는 미확인 상태로 남긴다.

---

# Fault / interference test matrix

| ID | 조건 | 기대 동작 |
|---|---|---|
| F00 | user eGPU disable | DISABLED, retry 금지 |
| F01 | eGPU missing | small active, shadow small 중지 |
| F02 | 12 V late | POWER_WAIT 후 초기화 |
| F03 | power drop | FALLBACK |
| F04 | USB disconnect | FALLBACK |
| F05 | PCIe loss | FALLBACK |
| F06 | telemetry invalid | FALLBACK |
| F07 | warm GPU | DERATED |
| F08 | hard thermal | FALLBACK |
| F09 | warmup timeout | FALLBACK → RETRY_WAIT |
| F10 | deadline violation | FALLBACK |
| F11 | power restored | debounce 후 retry |
| F12 | eGPU same-frame fail | warm small rerun budget 평가 |
| S01 | shadow receiver 없음 | tap drop, active 무영향 |
| S02 | shadow queue/backlog | stale shadow drop, active 무대기 |
| S03 | active big→small fallback | shadow small 즉시 admission 중지 |
| S04 | shadow frame gap | comparison eligibility reset |
| S05 | camera advanced | 해당 shadow frame 폐기 |
| S06 | shadow inference exception | shadow process 오류 기록/종료, active 무영향 |
| S07 | second-small memory pressure | STOP 후보, architecture 재검토 |

---

# 싼타페 TM 실차 적용 전 순서

대상차량:

**더 뉴 싼타페 TM 2021 / D2.2 / 2WD / 5인승 / 프레스티지 / 조수석 전동·통풍시트**

현재 shadow 단계에서는 일반 도로 자동 활성화보다 다음 순서가 먼저다.

1. offroad/replay tap smoke test
2. parked 5 Hz load probe
3. parked/offroad 20 Hz continuity
4. active big baseline latency 기록
5. shadow-on latency delta 기록
6. QCOM memory/load/thermal 확인
7. eGPU fallback 시 shadow stop 확인
8. 결과가 안정적일 때만 제한된 주행 데이터 수집 검토

---

# 다음 구현 순서

1. tap encode/send benchmark 도구
2. active baseline ↔ shadow-on interference report 자동화
3. tinygrad-level enqueue/kernel completion timestamp
4. Carrot `prepare_only` 실제 hardware smoke test
5. lead acquired/lost, cut-in, merge scenario 확장
6. sidecar YOLO/RoadSeg evidence schema
7. route health report
8. replay fault-injection 자동화
9. 이후 advisory PPT controller 검토

현재 성공 기준은 **shadow model이 더 좋다는 것을 증명하는 것이 아니라, active driving path를 방해하지 않고 동일-input 비교 데이터를 얻을 수 있음을 먼저 증명하는 것**이다.
