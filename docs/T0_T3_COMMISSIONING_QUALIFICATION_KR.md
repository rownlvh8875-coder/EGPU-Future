# T0~T3 Commissioning Qualification

작성일: 2026-09-07

## 목적

Carrot eGPU에 shadow inference를 추가하기 전에 **metadata tap 자체가 active driving model을 방해하지 않는지** 단계별로 검증한다.

단계:

```text
T0 original baseline
 → T1 patch installed, tap disabled
 → T2 tap enabled, receiver absent
 → T3 tap enabled + receiver only, no inference
 → explicit stage gate
 → T4 5 Hz shadow inference
 → T5 20 Hz continuous shadow
```

T0~T3에서는 second-small inference를 실행하지 않는다.

---

## 1. 준비

각 phase에서 active model `modelV2` action log를 추출한다.

현재 Carrot는 `modelV2.big`을 명시하지 않으므로 eGPU active가 독립적으로 확인된 commissioning 구간은 다음처럼 라벨링한다.

```bash
python3 tools/extract_model_actions_from_log.py <log> \
  --backend-label big \
  --output t0_active.jsonl
```

fallback이 섞인 일반 route 전체에 `--backend-label big`을 사용하지 않는다.

---

## 2. T3 tap receiver

T3에서는 inference 없이 receiver만 실행한다.

```bash
python3 tools/shadow_tap_receiver_probe.py \
  --duration 120 \
  --output /tmp/t3_tap.jsonl \
  --summary-output /tmp/t3_tap_summary.json
```

summary에는 다음이 기록된다.

- packets received
- records saved
- superseded packets
- decode errors
- frame gap
- duplicate/old transitions
- sender-created timestamp → receiver timestamp transport latency p50/p95/p99/max

`supersededPackets`는 latest-only 정책 때문에 반드시 0이어야 하는 값은 아니다. 반면 decode error는 protocol 문제로 취급한다.

---

## 3. Stage Gate policy

프로젝트는 임의의 공식 safety threshold를 만들지 않는다.

실험 책임자가 다음 값을 JSON으로 명시한다.

```json
{
  "minSamplesEach": 100,
  "maxP99IncreaseMs": 0.0,
  "maxMaxIncreaseMs": 0.0,
  "maxDeadlineMissRateDelta": 0.0,
  "maxFrameAgeGt1Delta": 0,
  "maxFrameGapCountDelta": 0
}
```

위 숫자는 **형식 예시일 뿐 권장값이 아니다.** 실제 값은 baseline과 제어 요구조건을 보고 별도로 결정한다.

정책이 없으면 `HOLD`, 샘플 부족도 `HOLD`, 명시 limit 초과는 `FAIL`, 모든 조건 충족만 `PASS`다.

---

## 4. 자동 qualification report

```bash
python3 tools/build_commissioning_report.py \
  --t0 t0_active.jsonl \
  --t1 t1_active.jsonl \
  --t2 t2_active.jsonl \
  --t3 t3_active.jsonl \
  --t3-tap-summary /tmp/t3_tap_summary.json \
  --limits commissioning_limits.json \
  --json-output commissioning_qualification.json \
  --md-output commissioning_qualification.md
```

출력 Markdown에는 phase별:

- PASS / HOLD / FAIL
- sample 수
- active model p99/max
- gate reason
- T3 tap receiver 상태

가 한 장으로 정리된다.

---

## 5. T3 PASS 후

T3가 PASS일 때만 T4 5 Hz shadow inference를 검토한다.

T4부터는 QCOM/tinygrad hardware profile을 함께 사용한다.

```bash
PROFILE=1 python3 tools/shadow_modeld_prototype.py --max-hz 5 ...
```

그리고:

```bash
python3 tools/correlate_shadow_tinygrad_profile.py shadow.jsonl profile.pkl
```

로 host model-call과 QCOM hardware kernel timeline을 분리한다.

---

## 6. 현재 안전 경계

T0~T3 qualification이 PASS해도 다음을 의미하지 않는다.

- 5 Hz shadow가 안전함
- 20 Hz shadow가 안전함
- active big + second-small 동시 실행이 안전함
- public-road 자동 활성화가 가능함

각 단계는 다음 단계에 들어갈 **실험 진입조건**일 뿐이다.
