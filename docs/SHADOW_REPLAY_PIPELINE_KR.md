# Small / Big Model Replay·Shadow 검증 절차

작성일: 2026-09-07

목표는 동일 route를 small/big model로 실행한 결과를 **같은 frame 기준으로 재현 가능하게 비교**하는 것이다.

이 파이프라인은 차량제어를 변경하지 않는다.

---

## 1. 왜 timestamp만 쓰지 않는가

서로 별도로 수행한 replay는 process 시작시점과 monotonic clock 기준이 다를 수 있다.

또 nearest timestamp matcher를 단순 구현하면 동일 big sample이 여러 small sample에 재사용될 수도 있다.

따라서 primary key는 `modelV2.frameId`다.

```text
small frameId 1042
        ↕ exact
big   frameId 1042
```

Timestamp는 frameId를 확보할 수 없는 특수 데이터에만 fallback으로 사용한다.

---

## 2. Action 추출

openpilot checkout/environment에서 실행한다.

### Small run

```bash
python3 /path/to/EGPU-Future/tools/extract_model_actions_from_log.py \
  /path/to/small/rlog.zst \
  --output small_actions.jsonl \
  --source-label small
```

### Big run

```bash
python3 /path/to/EGPU-Future/tools/extract_model_actions_from_log.py \
  /path/to/big/rlog.zst \
  --output big_actions.jsonl \
  --source-label big
```

추출 필드:

- `frameId`
- `frameIdExtra`
- `frameAge`
- `logMonoTimeS`
- `modelExecutionTimeS`
- `big`
- `desiredCurvature`
- `desiredAcceleration`
- `shouldStop`
- `speedMps`
- `vehicleAccelMps2`
- lead context

---

## 3. Deterministic pairing

```bash
python3 tools/pair_shadow_runs.py \
  small_actions.jsonl \
  big_actions.jsonl \
  --output paired_shadow.jsonl \
  --summary paired_shadow_summary.json
```

Summary에서 반드시 확인:

- paired sample 수
- small unmatched
- big unmatched
- duplicate frameId
- pair method

### Timestamp fallback

frameId가 없는 데이터에서만:

```bash
python3 tools/pair_shadow_runs.py small.jsonl big.jsonl \
  --timestamp-fallback \
  --max-dt 0.030 \
  --ambiguity-margin 0.005
```

가장 가까운 두 후보가 너무 비슷하면 ambiguous match로 보고 pairing하지 않는다.

---

## 4. Freshness / deadline validation

```bash
python3 tools/validate_paired_shadow.py paired_shadow.jsonl \
  --max-execution-ms 45 \
  --max-frame-age 1
```

Hard issue:

- missing/mismatched frameId
- stale frame
- invalid/non-finite execution/action
- deadline miss

Review issue:

- curvature disagreement
- acceleration disagreement
- shouldStop mismatch

45 ms는 공식 comma safety limit이 아니라 20 Hz nominal model period를 기준으로 한 연구 초기값이다.

---

## 5. Disagreement mining

```bash
python3 tools/compare_shadow_runs.py \
  small_actions.jsonl \
  big_actions.jsonl \
  --events shadow_events.jsonl
```

기본 significant 조건:

- curvature abs + relative difference
- acceleration difference
- stop mismatch

각 event에는 scenario tag가 같이 기록된다.

```bash
python3 tools/summarize_shadow_events.py shadow_events.jsonl
```

---

## 6. Latency 분석

모델 실행시간 자체:

```bash
python3 tools/latency_profiler.py big_actions.jsonl \
  --field modelExecutionTimeS \
  --deadline 0.050
```

평균보다 p95/p99와 miss rate를 우선한다.

---

## 7. Carrot-style same-frame hot fallback budget

Carrot 최신 eGPU 코드는 runtime eGPU exception 시 이미 로드한 internal model로 **같은 카메라 frame을 다시 실행**한다.

그 방법이 실제 20 Hz budget을 만족하는지는 별도 문제다.

```bash
python3 tools/hot_fallback_budget.py paired_shadow.jsonl \
  --budget-ms 50 \
  --handoff-overhead-ms 2 \
  --primary-failure-fraction 1.0
```

보수적인 기본식:

```text
big model이 실패를 알아차릴 때까지 걸린 시간
+ fallback handoff overhead
+ small model 실행시간
= same-frame recovery total
```

결과:

- big p50/p95/p99
- small p50/p95/p99
- fallback total p50/p95/p99/max
- deadline miss rate

실제 exception이 inference 초반에 발생하는 경우 `--primary-failure-fraction`으로 별도 scenario를 시험할 수 있다.

---

## 8. 합격/보류 기준은 데이터로 결정

현재는 고정 합격 기준을 선언하지 않는다.

첫 route dataset에서 다음 분포를 확보한 뒤 기준을 고정한다.

- pairing coverage
- frame-age distribution
- big/small p99 inference
- hot-fallback p99
- disagreement rate
- stop mismatch rate
- scenario별 disagreement
- temperature/PPT별 latency shift

이후 threshold를 `config`로 외부화한다.

---

## 9. 다음 단계: true live shadow_modeld

Replay 파이프라인이 안정된 후 다음 구조를 구현한다.

```text
              camera frame
                   │
             preprocessing
                   │
          ┌────────┴────────┐
          ▼                 ▼
    approved/primary     shadow model
          │                 │
          ▼                 ▼
    normal modelV2      shadow-only bus/log
          │                 │
          ▼                 │
     vehicle control         │
                            ▼
                    disagreement logger
```

필수 조건:

- shadow가 active model scheduling을 방해하지 않음
- frameId exact match
- shadow output은 control bus에 publish하지 않음
- CPU/QCOM/memory/USB thermal interference 측정
- shadow crash가 main modeld에 전파되지 않음

이 조건을 만족하기 전에는 dual live model을 제어경로에 넣지 않는다.
