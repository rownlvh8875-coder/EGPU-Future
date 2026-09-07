# 실기기 대기 중 Offline Readiness 및 T4 진입 Gate

작성일: 2026-09-07

## 목적

실제 comma/Carrot 장비가 연결되지 않은 시간에도 다음 세 가지를 검증한다.

1. 빠르게 변하는 Carrot branch에서 **실제로 중요한 코드가 바뀌었는지** 판별
2. T0~T3 qualification 파이프라인의 PASS/HOLD/FAIL 동작을 deterministic synthetic evidence로 회귀검증
3. 실제 T0~T3가 PASS하고 runtime 복원까지 확인되기 전에는 T4 5 Hz shadow inference에 진입하지 못하도록 별도 gate 유지

---

# 1. Source compatibility

도구:

```text
egpu_future/source_compatibility.py
tools/check_carrot_source_compatibility.py
```

Carrot의 branch HEAD는 자주 움직인다. HEAD가 달라졌다는 이유만으로 항상 코드가 달라진 것은 아니며, 반대로 HEAD 이름이 같다는 사실만으로 우리가 의존하는 코드가 안전하다는 것도 보장하지 않는다.

따라서 다음 critical Git blobs를 별도로 고정한다.

- `modeld.py`
- `fill_model_msg.py`
- manager `process.py`
- manager `process_config.py`
- manager `manager.py`
- `launch_chffrplus.sh`
- tinygrad HCQ
- tinygrad QCOM backend

판정:

```text
HEAD reviewed + critical blobs 동일
  -> EXACT_REVIEWED_HEAD

HEAD 변경 + critical blobs 전부 동일
  -> CODE_EQUIVALENT_HEAD_DRIFT

critical blob 하나라도 변경/누락
  -> REVIEW_REQUIRED
```

`CODE_EQUIVALENT_HEAD_DRIFT`는 **critical code 관점에서만 동등**하다는 뜻이다. 새 문서나 비critical 코드까지 자동 검토됐다는 뜻이 아니다.

실기기에서:

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 tools/check_carrot_source_compatibility.py /path/to/openpilot \
  --output source_compatibility.json
```

T4 gate에는 이 JSON을 그대로 사용한다.

---

# 2. Synthetic commissioning regression

도구:

```text
egpu_future/synthetic_commissioning.py
tools/simulate_commissioning_pipeline.py
```

지원 case:

- `pass`
- `fail_latency`
- `fail_transport`
- `fail_gap`
- `hold_no_policy`
- `hold_samples`

예:

```bash
python3 tools/simulate_commissioning_pipeline.py pass --output-dir /tmp/synth_pass
python3 tools/simulate_commissioning_pipeline.py fail_latency --output-dir /tmp/synth_fail_latency
python3 tools/simulate_commissioning_pipeline.py fail_transport --output-dir /tmp/synth_fail_transport
python3 tools/simulate_commissioning_pipeline.py fail_gap --output-dir /tmp/synth_fail_gap
python3 tools/simulate_commissioning_pipeline.py hold_no_policy --output-dir /tmp/synth_hold
```

synthetic limit 숫자는 오직 소프트웨어 테스트용이다. 실차 commissioning limit으로 재사용하지 않는다.

이 harness가 검증하는 것:

- `latency_stats_ms`
- T0 baseline 처리
- T1/T2/T3 delta gate
- frame gap detection
- tap decode error failure
- policy 미지정 HOLD
- sample 부족 HOLD
- qualification JSON/Markdown 생성

검증하지 않는 것:

- comma hardware 성능
- 실제 eGPU 안정성
- 실제 차량 안전성
- 실제 허용 latency threshold

---

# 3. T4 readiness gate

도구:

```text
egpu_future/t4_readiness.py
tools/evaluate_t4_readiness.py
```

첫 T4는 다음 범위만 허용한다.

```text
parked/offroad
selfdrive inactive
manual start
control-isolated shadow
PROFILE=1
<= 5 Hz
```

T4 PASS prerequisite:

1. `commissioning_qualification.json` overall = PASS
2. T0~T3 session manifest status = `COMPLETED_RUNTIME_RESTORED`
3. final reboot evidence 존재
4. source restore failure 없음
5. current Carrot critical code = compatible

하나라도 부족하면 HOLD다.

T0~T3 qualification 자체가 FAIL했거나 source restore가 명시적으로 실패했다면 FAIL이다.

실기기 T0~T3 완료 후:

```bash
python3 tools/check_carrot_source_compatibility.py /path/to/openpilot \
  --output <session>/source_compatibility.json

python3 tools/evaluate_t4_readiness.py \
  --qualification <session>/commissioning_qualification.json \
  --manifest <session>/manifest.json \
  --source-compatibility <session>/source_compatibility.json \
  --max-hz 5 \
  --output <session>/t4_readiness.json
```

`PASS`는 오직 **다음 parked 5 Hz 실험에 들어갈 조건이 충족됐다**는 뜻이다. public-road 사용, 20 Hz shadow, control integration 승인이 아니다.

---

# 4. 최신 Carrot perception 실험 반영

최신 `egpu_yolo_next_steps.md`에서 확인한 실험 신호:

- 한 자전거 scene에서 512×256 입력 confidence가 매우 낮았음
- 동일 weights의 640×384 이상 입력에서 해당 scene confidence가 크게 회복됨
- shared eGPU의 짧은 latency는 5~6 ms 수준이었지만 이후 24.887 ms overrun 관측
- driving-warp input과 full-camera letterbox는 tensor dimension이 같아도 FOV가 동일하지 않음

따라서 T4 이후 perception 실험은:

```text
accuracy candidate: 640x384
performance validation: p95/p99/max + queue/readback/end-to-end age
frequency reduction before resolution reduction
FOV mapping explicit
```

을 우선한다.

관련 evidence:

- `evidence/carrot_yolo_next_steps_20260907.json`
- `docs/CARROT_YOLO_NEXT_STEPS_ANALYSIS_KR.md`

---

# 5. 현재 의미

현재 프로젝트는 실기기 없이 할 수 있는 다음 검증까지 준비됐다.

```text
source drift classification
+ synthetic end-to-end qualification regression
+ T4 entry gate
+ latest Carrot perception evidence integration
```

따라서 실제 장비가 연결되면 새 설계 작업부터 다시 시작할 필요 없이:

```text
source compatibility
-> T0 prepare
-> reboot
-> T1/T2/T3 resume
-> final reboot/finalize
-> source compatibility 재확인
-> T4 readiness
```

순서로 바로 측정 단계에 들어갈 수 있다.
