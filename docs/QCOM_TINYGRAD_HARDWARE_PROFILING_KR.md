# QCOM tinygrad Hardware Profiling

작성일: 2026-09-07

## 목적

`shadow_modeld`가 QCOM에 추가되었을 때 단순한 Python wall-clock latency만 보지 않고 다음 구간을 분리한다.

```text
host model-call start
  ↓
첫 QCOM kernel hardware start
  ↓
QCOM kernel sequence
  ↓
마지막 QCOM kernel hardware end
  ↓
host model-call return
```

이 단계는 차량제어를 바꾸지 않는다. QCOM/tinygrad 자체도 패치하지 않는다.

---

## 1. 왜 tinygrad 기존 PROFILE을 사용하나

현재 Carrot의 tinygrad HCQ는 이미 hardware timestamp를 지원한다.

`HCQProgram.__call__()`은 `PROFILE=1`일 때 kernel 실행 앞뒤에 device timestamp signal을 삽입하고, 동기화 시 `ProfileRangeEvent`로 수집한다.

또 profile 종료 시 `ProfileDeviceEvent.tdiff`를 저장한다. tinygrad viz도 다음 방식으로 device timestamp를 CPU/host timeline에 맞춘다.

```text
host_aligned_timestamp = device_timestamp + ProfileDeviceEvent.tdiff
```

따라서 QCOM driver에 별도 timestamp patch를 넣기보다 이 공식 tinygrad profiling 경로를 사용한다.

---

## 2. 측정값의 의미

`ProfileRangeEvent`가 주는 것은 **QCOM hardware command timeline상의 kernel start/end**다.

EGPU-Future는 shadow JSONL의 host model-call 구간과 결합하여 프레임마다 다음을 계산한다.

- `modelCallMs`
- `firstKernelDelayMs`
  - host model-call 시작 → 첫 hardware kernel 시작
- `enqueueToFirstKernelMs`
  - upstream enqueue callback이 있는 경우만
- `kernelEnvelopeMs`
  - 첫 kernel 시작 → 마지막 kernel 종료
- `kernelBusyMs`
  - 겹치는 kernel interval을 union 처리한 실제 busy 시간
- `afterLastKernelMs`
  - 마지막 kernel 종료 → host model-call return
- `kernelCount`

Carrot의 현재 `ModelState.run(..., prepare_only)`에는 official openpilot의 `after_enqueue` callback이 없으므로 `enqueueToFirstKernelMs`는 없는 것이 정상이다. 가짜 timestamp를 만들지 않는다.

---

## 3. PROFILE=1 실행

이 기능은 **offroad / parked commissioning**에서 먼저 사용한다.

예:

```bash
PROFILE=1 \
PYTHONPATH=/path/to/EGPU-Future:/path/to/openpilot \
python3 /path/to/EGPU-Future/tools/shadow_modeld_prototype.py \
  --max-hz 5 \
  --output /tmp/shadow_5hz_profile.jsonl
```

프로세스 종료 시 tinygrad가 `profile.pkl`을 저장한다.

`profile.pkl`은 Python pickle이므로 **신뢰할 수 있는 로컬 tinygrad 출력만 사용한다.** 외부에서 받은 pickle을 열지 않는다.

---

## 4. 전체 QCOM kernel profile 요약

```bash
python3 tools/analyze_tinygrad_profile.py \
  /path/to/profile.pkl \
  --device-prefix QCOM \
  --output qcom_profile_summary.json
```

출력:

- kernel sample 수
- device clock offset
- profile span
- union busy time/ratio
- kernel duration p50/p95/p99/max
- total GPU time 기준 상위 kernel

---

## 5. shadow frame과 kernel timeline 상관분석

```bash
python3 tools/correlate_shadow_tinygrad_profile.py \
  /tmp/shadow_5hz_profile.jsonl \
  /path/to/profile.pkl \
  --device-prefix QCOM \
  --frames-output shadow_kernel_frames.jsonl \
  --summary-output shadow_kernel_summary.json
```

기존 shadow JSONL에도 `cameraTimestampEofNs`, `capture_to_done_ms`, `model_call_total_ms`가 있으므로 runtime patch 없이 host model-call 구간을 복원할 수 있다.

프레임별 hardware profile coverage가 낮으면 해당 분석은 신뢰하지 않는다.

---

## 6. 해석

예를 들어 `modelCallMs`가 증가했을 때:

### firstKernelDelay 증가

```text
host scheduling / QCOM queue wait / preprocessing / submission overhead 후보
```

### kernelEnvelope 또는 kernelBusy 증가

```text
실제 QCOM compute workload / clock / contention 영향 후보
```

### afterLastKernel 증가

```text
GPU completion 이후 output copy/parse/synchronization/host scheduling 후보
```

이 분해를 통해 단순히 `QCOM이 느리다`가 아니라 어느 구간이 병목인지 좁힌다.

---

## 7. 주의

- `PROFILE=1` 자체도 profiling overhead를 만들 수 있다.
- 따라서 PROFILE OFF baseline과 PROFILE ON 결과를 같은 것으로 취급하지 않는다.
- 처음에는 parked/offroad에서만 사용한다.
- tinygrad hardware profile PASS가 차량제어 safety PASS를 의미하지 않는다.
- T0~T3 tap-only gate를 먼저 통과한 뒤 T4/T5 shadow inference 분석에 사용한다.

---

## 8. 다음 연구

1. 5 Hz QCOM small shadow의 frame별 hardware profile
2. 20 Hz 이전에 QCOM memory/thermal/scheduling 확인
3. active big latency와 QCOM kernel busy window의 상관계수 분석
4. 필요 시 process CPU affinity/niceness 조정
5. second-small process가 구조적으로 불리하면 active modeld 내부 warm-small shadow reuse 방식 재검토
