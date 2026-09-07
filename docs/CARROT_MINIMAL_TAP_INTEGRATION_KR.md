# Carrot eGPU 최소 Shadow Tap 통합 및 단계별 검증 계획

작성일: 2026-09-07  
대상: `ajouatom/openpilot` / `carrot-egpu-yolo`

## 1. 현재 고정 기준선

이 통합안은 다음 Carrot tip을 기준으로 검토했다.

- commit: `2c508b1dde53b9a996546993e1c7b5b74b489541`
- commit message: `Record stationary internal GPU Web publication results`
- `openpilot/selfdrive/modeld/modeld.py` Git blob: `e4de3eb2236f6bb0c54c87666099147311602f4f`

Carrot branch는 매우 빠르게 변경되므로 HEAD 또는 modeld blob이 달라지면 **패치를 강제 적용하지 말고 새 tip을 다시 분석**한다.

---

# 2. 왜 바로 20 Hz second-small을 켜지 않는가

최신 Carrot 실험 문서에는 내부 QCOM GPU에서 YOLO sidecar를 정차 상태로 180초 실행한 결과가 기록되어 있다.

확인된 수치:

- publication: 688 results / 180 s = 약 3.85 Hz
- full live YOLO execution: 119.88 ms p50 / 138.74 ms p95 / 148.59 ms p99 / 184.71 ms max
- active driving execution
  - before: 36.55 ms p50 / 39.26 ms p99 / 40.98 ms max
  - during: 36.62 ms p50 / 43.26 ms p99 / 56.04 ms max
  - after: 35.82 ms p50 / 37.65 ms p99 / 38.89 ms max
- camera EOF → model event
  - before: 80.83 / 94.46 / 104.67 ms
  - during: 83.87 / 108.44 / 120.35 ms
  - after: 84.30 / 95.71 / 99.87 ms

Carrot 문서 자체 결론도 **tail-latency cost가 남아 있고 driving use를 검증한 것이 아니다**라고 한다.

이 실험은 YOLO와 두 번째 small driving model이 동일한 workload라는 뜻이 아니다. 다만 QCOM에 추가 workload를 얹으면 active model tail latency가 악화될 수 있음을 실제 장비에서 보여준다.

원자료 구조화본: `evidence/carrot_qcom_yolo_stationary_20260907.json`

---

# 3. 이번 최소 patch가 하는 일

목표는 **추론을 추가하기 전에 metadata tap 자체의 비용부터 측정**하는 것이다.

Carrot `modeld.py`에 추가되는 것은 세 블록뿐이다.

1. standalone tap module import
2. `Params()` 직후 tap 객체 생성
3. 기존 `model.run()` 직전 best-effort metadata send

전송 조건:

```text
EGPU_FUTURE_SHADOW_TAP=1
AND
prepare_only == False
```

기본 환경에서는 `EGPU_FUTURE_SHADOW_TAP`이 unset/0이므로 tap은 **disabled**다.

전송 payload:

- frameId / frameIdExtra
- road-camera `stateFrameId`
- camera SOF / EOF
- active backend (`usbgpu` → big, otherwise small)
- vEgo
- main / extra transform
- desire pulse
- traffic convention
- action_t
- monotonic timestamp

전송은 AF_UNIX datagram + non-blocking + no retry다.

receiver가 없거나 socket queue가 찼거나 serialization/send가 실패해도 **active `model.run()` 경로는 그대로 진행**한다.

---

# 4. 의도적으로 변경하지 않는 코드

patch verification은 marker 블록을 모두 제거했을 때 원본 `modeld.py`가 byte-for-byte 복원되는지 검사한다.

따라서 다음 기존 landmark는 수정하지 않는다.

```text
model_output = model.run(..., prepare_only)
eGPU exception handling
UsbGpuActive / UsbGpuStartupFailed state
model = small_model
same-frame small fallback model.run(...)
fill_model_msg(...)
pm.send('modelV2', ...)
```

즉 이 단계는 **Carrot의 control/fallback 동작을 바꾸는 patch가 아니다.**

---

# 5. 적용 도구

`tools/apply_carrot_shadow_tap_patch.py`

기본은 dry-run이다.

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 /path/to/EGPU-Future/tools/apply_carrot_shadow_tap_patch.py \
  /path/to/ajouatom-openpilot
```

검사:

- HEAD == pinned commit
- `git hash-object openpilot/selfdrive/modeld/modeld.py` == pinned blob
- target files dirty 여부
- patch anchor 유일성
- marker 제거 후 원본 byte-for-byte 복원
- 기존 eGPU fallback/modelV2 publish landmark 보존

실제 적용은 명시적으로:

```bash
... apply_carrot_shadow_tap_patch.py /path/to/openpilot --apply
```

을 사용한다.

HEAD가 변경되면 기본적으로 거부한다. `--allow-head-mismatch`와 `--allow-modeld-mismatch`는 expert escape hatch이며, 새 source를 재검토하지 않고 사용하는 것을 권장하지 않는다.

---

# 6. Carrot 로그의 `big` 표시 주의

현재 분석한 Carrot `fill_model_msg.py`는 `modelV2.big`을 명시적으로 설정하지 않는다.

따라서 EGPU-Future의 로그 추출기는 다음 옵션을 추가했다.

```bash
python3 tools/extract_model_actions_from_log.py <log> \
  --backend-label big \
  --output active_big.jsonl
```

`--backend-label big`은 **eGPU가 계속 active였음을 별도 telemetry/UI/commissioning 절차로 확인한 구간에만** 사용한다.

runtime fallback이 섞인 일반 주행 전체를 강제로 big으로 라벨링하면 안 된다.

기본값 `auto`는 기존 `modelV2.big`을 그대로 사용한다.

---

# 7. Stage Gate

`egpu_future/stage_gate.py` / `tools/evaluate_shadow_stage_gate.py`

EGPU-Future는 현재 임의의 공식 safety threshold를 만들지 않는다.

실험 책임자가 다음 허용치를 명시해야 한다.

- minimum samples
- maximum p99 increase
- maximum worst-case/max increase
- maximum deadline-miss-rate delta
- maximum frameAge>1 delta
- maximum frame-gap delta

정책이 없으면:

```text
HOLD
```

샘플이 부족해도:

```text
HOLD
```

명시한 한계를 초과하면:

```text
FAIL
```

모든 명시 조건을 만족해야만:

```text
PASS
```

이다.

이 threshold는 실험 정책이며 comma 공식 safety threshold라고 부르지 않는다.

---

# 8. 실제 검증 단계

## T0 — 원본 baseline

patch가 없는 현재 Carrot eGPU 상태에서 active big model 로그를 확보한다.

측정:

- p50/p95/p99/max modelExecutionTime
- deadline miss
- frameAge
- frame gap
- camera EOF → model event가 확보 가능하면 함께 기록

## T1 — patch 적용, tap disabled

환경변수를 설정하지 않는다.

```text
EGPU_FUTURE_SHADOW_TAP unset
```

목적:

- import/object/bool guard 추가만으로 active latency 변화가 없는지 확인

## T2 — tap enabled, receiver 없음

```text
EGPU_FUTURE_SHADOW_TAP=1
```

receiver는 실행하지 않는다.

목적:

- JSON encode + failed non-blocking send 비용 측정
- receiver absence가 modeld를 block하지 않는지 검증

## T3 — tap enabled + receiver, inference 없음

metadata만 수신/drain한다.

목적:

- 실제 socket delivery 및 queue pressure 비용 측정
- frameId/stateFrameId/protocol 정확도 확인

## T4 — 5 Hz shadow load probe

T0~T3에서 active-path interference가 허용범위 이내이고 stage gate가 PASS일 때만 수행한다.

5 Hz 결과는 **driving-model 품질 비교용이 아니다.** temporal hidden state가 active 20 Hz sequence와 달라지기 때문이다.

## T5 — 20 Hz continuous shadow

T4까지 통과한 뒤에만 검토한다.

20 Hz에서는 별도 software rate-limit으로 50 ms를 강제하지 않고 upstream frame cadence를 그대로 받는다. 이는 49.x/50.x ms jitter 때문에 정상 frame이 불필요하게 drop되는 것을 피하기 위함이다.

---

# 9. 현재 STOP 조건

아래가 발생하면 second-small inference 단계로 진행하지 않는다.

- active big p95/p99 또는 max tail이 정책 한계 초과
- new deadline miss
- frameAge 증가
- frame gap 증가
- modeld/selfdrived communication issue
- QCOM thermal/memory pressure
- eGPU failure 시 active warm small fallback readiness 악화

특히 공식/Carrot 구조는 active big 사용 중에도 fallback용 internal small model을 이미 보유한다. 별도 shadow process의 **second small instance**는 QCOM memory와 scheduling을 추가로 사용하므로 실제 하드웨어 검증 전 자동실행 대상이 아니다.

---

# 10. 다음 개발 후보

Tap-only commissioning을 통과한 뒤에는 두 경로를 비교한다.

### A. process-separated second small

장점:
- control isolation이 가장 명확

단점:
- small model 메모리/queue 중복
- QCOM scheduling contention 가능

### B. existing warm fallback small을 활용하는 cooperative sampling

장점:
- 두 번째 model instance를 줄일 가능성

단점:
- active modeld 안에서 sequential work가 늘어나므로 latency isolation이 약함
- eGPU failure와 같은 frame에서 fallback 우선순위를 절대 침해하면 안 됨

현재는 어느 쪽도 자동 채택하지 않는다. **실측 interference가 architecture 선택의 입력**이다.
