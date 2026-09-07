# True `shadow_modeld` Prototype

작성일: 2026-09-07

## 목적

이 단계의 목적은 **active driving model과 동일한 입력 프레임을 별도 small model에도 넣어 결과를 기록하되, shadow 결과가 차량제어에 단 한 번도 사용되지 않도록 구조적으로 분리**하는 것이다.

현재 구현은 다음 조합을 우선 대상으로 한다.

```text
active: Chestnut / USB-GPU big model
shadow: comma 내부 QCOM small model
```

첫 prototype에서는 shadow big model을 지원하지 않는다. active big과 별도의 second big process가 같은 Chestnut/USB-GPU 자원을 동시에 잡는 구조는 검증 전에는 허용하지 않는다.

---

# 1. 왜 camera만 두 번 읽으면 안 되는가

현재 openpilot model input에는 camera buffer 외에 다음이 들어간다.

- main / extra camera transform
- desire pulse
- traffic convention
- action timing (`action_t`)
- vehicle speed는 최종 action 계산에도 사용

따라서 별도 process가 camera만 같은 frameId로 읽어서는 **정확한 동일-input A/B**라고 할 수 없다.

그래서 active `modeld`가 자신이 실제 사용하려는 input metadata를 shadow process로 보내는 **shadow input tap**을 추가한다.

```text
camerad
  │
  ├──────────────→ active modeld ─────────→ modelV2 → controls
  │                     │
  │                     │ non-blocking UNIX datagram
  │                     ▼
  └──────────────→ shadow_modeld ─────────→ JSONL only
```

shadow output은 PubMaster로 `modelV2`를 publish하지 않는다.

---

# 2. active path 보호 원칙

## 2.1 Tap은 non-blocking / fail-open

`egpu_future/shadow_tap.py`

`NonBlockingShadowTapSender.send()`는:

- UNIX datagram
- non-blocking socket
- retry 없음
- receiver가 없거나 queue가 차면 즉시 drop
- 오류가 나도 active model 실행은 계속

으로 설계했다.

즉:

```text
shadow가 죽음
shadow socket 없음
shadow queue full
serialization 오류
```

어느 경우에도 active model이 기다리면 안 된다.

## 2.2 modeld bridge

`integrations/openpilot/modeld_shadow_tap_bridge.py`

공식 openpilot의 `ModelState.chestnut`과 Carrot의 `ModelState.usbgpu`를 모두 인식한다.

bridge가 보내는 snapshot:

- frameId / frameIdExtra
- camera SOF / EOF
- active backend (`big` / `small`)
- vEgo
- main / extra 3x3 transform
- desire pulse
- traffic convention
- action_t
- tap monotonic timestamp

## 2.3 same-backend guard

shadow backend는 현재 `small` 고정이다.

active backend가 small로 바뀌면:

```text
active small == shadow small
        ↓
shadow inference 중지
```

한다.

따라서 eGPU fallback 후 QCOM에서 active small과 shadow small을 계속 이중 실행하는 구조를 금지한다.

단, eGPU가 **해당 frame 도중** 실패하여 active가 같은 frame을 small로 hot-fallback하는 경우에는 shadow small이 이미 실행 중일 수 있다. 이 1-frame transient contention은 실측 대상이며 완전 제거하려면 active modeld와 shadow process 사이에 별도 cancellation/coordination protocol이 필요하다.

---

# 3. backpressure 정책

shadow는 active path보다 항상 버려질 수 있는 작업이다.

정책:

```text
active work: 절대 shadow를 기다리지 않음
shadow work: 최신 frame 우선
old shadow frame: 폐기
```

`egpu_future/shadow_runtime.py`의 `LatestOnlySlot`은 이 원칙을 unit-test 가능한 형태로 구현한다.

실제 `shadow_modeld_prototype.py`에서는 VisionIPC client를 `conflate=True`로 사용해 camera backlog가 누적되지 않게 한다.

---

# 4. temporal model에서 5 Hz shadow가 비교용이 아닌 이유

small/big driving model은 hidden state와 frame history를 사용한다.

따라서 active model이 20 Hz인데 shadow를 5 Hz로만 실행하면 단순히 4개 중 1개 frame만 비교하는 것이 아니다.

**shadow model의 temporal state 자체가 다른 sequence를 경험하게 된다.**

그래서:

- `--max-hz 20`: comparison 후보
- `<20 Hz`: load / thermal / interference probe용

으로 구분한다.

`ContinuityTracker`는 frame gap이 생기면 comparison eligibility를 다시 reset하고, 기본 40 consecutive frames 이후에만 `comparisonEligible=true`로 만든다.

40 frames는 공식 comma safety 기준이 아니라 초기 연구 settle window다.

---

# 5. timing instrumentation

현재 JSONL에는 다음 timestamp/derived metric을 기록한다.

```text
camera SOF
camera EOF
  ↓
shadow frame received
  ↓
ModelState.run call start
  ↓
model/device enqueue callback     # 공식 API에서만 현재 직접 관측
  ↓
inference complete
  ↓
record emit
```

Derived:

- capture → receive
- receive → model call
- model call → enqueue
- enqueue → done
- model call total
- capture EOF → done
- done → record

## 중요한 한계

공식 current `ModelState.run()`은 `after_enqueue` callback을 제공하므로 enqueue 위치를 기록할 수 있다.

현재 분석한 Carrot `ModelState.run()`은 마지막 인자가 `prepare_only`이고 같은 callback을 제공하지 않는다. Carrot에서는 **가짜 enqueue timestamp를 만들지 않고 `None`으로 남긴다.**

또한 official callback도 low-level GPU hardware timestamp 그 자체는 아니다. 현재 `outs.numpy()`가 완료 synchronization 경계이므로, 더 정확한 GPU queue/kernel timestamp는 tinygrad profiler/event instrumentation 단계에서 추가한다.

---

# 6. 공식 openpilot / Carrot API compatibility

`tools/shadow_modeld_prototype.py`는 runtime signature를 확인한다.

### 공식 계열

```text
ModelState.run(..., after_enqueue)
ModelState.chestnut
VISION_STREAM_NARROW_ROAD
```

### 현재 분석한 Carrot eGPU 계열

```text
ModelState.run(..., prepare_only)
ModelState.usbgpu
VISION_STREAM_ROAD
```

Carrot의 `get_action_from_model()`은 dynamic lateral smoothing과 `VEgoStopping` 인자를 추가로 사용하므로 sidecar는 signature를 확인하고 동일 upstream helper/Params를 사용한다.

---

# 7. 코드 구성

## Core

- `egpu_future/shadow_runtime.py`
  - backend admission
  - same-backend guard
  - rate limiting
  - continuity / settle window
  - timing trace
  - latest-only slot

- `egpu_future/shadow_tap.py`
  - exact input snapshot schema
  - encode/decode
  - non-blocking sender
  - drain-to-latest receiver

- `egpu_future/shadow_log.py`
  - live shadow JSONL → 기존 flat action schema 변환

## Integration

- `integrations/openpilot/modeld_shadow_tap_bridge.py`

## Runtime

- `tools/shadow_modeld_prototype.py`
- `tools/summarize_shadow_modeld.py`
- `tools/normalize_shadow_modeld_log.py`

---

# 8. active modeld 최소 integration 위치

현재 prototype은 openpilot을 자동 patch하지 않는다.

active `modeld`에서 input dict와 transforms를 모두 만든 직후, 기존 `model.run()` 직전에 bridge를 호출하는 방식이다.

개념 예시:

```python
shadow_tap.send(
  model=model,
  meta_main=meta_main,
  meta_extra=meta_extra,
  v_ego=v_ego,
  transform_main=model_transform_main,
  transform_extra=model_transform_extra,
  inputs=inputs,
)

model_output = model.run(...)
```

bridge send 실패 결과는 active model logic에서 사용하지 않는다.

이 tap 자체의 encode/send overhead도 comma 장비에서 측정해야 하며, active model latency에 유의미한 영향이 확인되면 JSON protocol을 fixed binary/shared-memory 형태로 교체한다.

---

# 9. prototype 실행 순서

## Phase 0 — offroad / replay

우선 차량제어 없는 환경에서:

1. tap encode/decode
2. camera frame matching
3. small model load
4. 20 Hz 연속 처리 가능 여부
5. JSONL 정상 생성
6. active process latency 변화

를 확인한다.

## Phase 1 — parked hardware smoke test

Chestnut + big active 상태에서 차량 정차/안전 상태로 sidecar를 수동 시작한다.

예시:

```bash
PYTHONPATH=/path/to/EGPU-Future:/path/to/openpilot \
python3 /path/to/EGPU-Future/tools/shadow_modeld_prototype.py \
  --max-hz 5 \
  --output /tmp/shadow_probe.jsonl
```

5 Hz는 **부하 확인용**이다.

요약:

```bash
python3 tools/summarize_shadow_modeld.py /tmp/shadow_probe.jsonl
```

## Phase 2 — 20 Hz comparison test

부하 문제가 없을 때만:

```bash
python3 tools/shadow_modeld_prototype.py \
  --max-hz 20 \
  --settle-frames 40 \
  --output /tmp/shadow_20hz.jsonl
```

---

# 10. active big ↔ shadow small 비교 pipeline

### 1. shadow log 정규화

```bash
python3 tools/normalize_shadow_modeld_log.py \
  /tmp/shadow_20hz.jsonl \
  --output shadow_small.jsonl
```

기본값은 `comparisonEligible=true` frame만 남긴다.

### 2. 같은 drive의 active modelV2 추출

```bash
python3 tools/extract_model_actions_from_log.py <rlog/qlog/route> \
  --output active_big.jsonl
```

### 3. frameId pair

```bash
python3 tools/pair_shadow_runs.py \
  shadow_small.jsonl active_big.jsonl \
  --output paired_live_shadow.jsonl
```

### 4. validator

live Chestnut 구조에서는 **big이 active/reference**이고 small이 shadow/candidate이므로:

```bash
python3 tools/validate_paired_shadow.py \
  paired_live_shadow.jsonl \
  --reference-side big
```

---

# 11. 첫 실차에서 보는 KPI

## 반드시 확인

- active `modelV2` p95/p99 latency 변화
- active frame-drop 변화
- shadow model-call p50/p95/p99
- shadow capture-to-done p95/p99
- shadow frame coverage
- comparisonEligible rate
- camera_advanced skip rate
- tap drop rate
- QCOM temperature / load
- Chestnut big latency 변화

## 초기 판정

### GO 후보

- active big p95/p99가 baseline 대비 의미 있게 악화되지 않음
- active deadline miss 증가 없음
- camera/model communication issue 증가 없음
- shadow 20 Hz continuity가 안정적으로 유지

### STOP

- active model latency 악화
- active frame drop 증가
- modeld/controls comm issue
- thermal/power abnormal
- shadow가 active small fallback과 지속적으로 자원 경쟁

구체 숫자는 실측 baseline을 얻기 전에는 확정하지 않는다.

---

# 12. 현재 의도적으로 하지 않는 것

- shadow output을 `modelV2`로 publish
- shadow output을 controls에 전달
- manager 자동 시작
- vehicle command 생성
- panda safety 변경
- GPU PPT 자동 제어
- second big model process
- public-road 자동 활성화

---

# 13. 다음 단계

1. tap encode/send overhead 실측
2. parked 5 Hz load probe
3. parked/offroad 20 Hz continuity
4. active big baseline vs shadow-on latency delta
5. Carrot branch에서 `prepare_only` API 실제 smoke test
6. tinygrad-level enqueue/kernel completion instrumentation
7. stable하면 process isolation/CPU affinity 자동 추천
8. 이후 sidecar perception evidence와 연결

현재 단계의 성공 기준은 **shadow model의 정확도가 아니라 active driving path에 영향을 주지 않으면서 동일-input 데이터를 안정적으로 얻는 것**이다.
