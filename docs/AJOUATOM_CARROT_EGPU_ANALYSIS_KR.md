# ajouatom/openpilot Carrot eGPU 브랜치 분석

작성일: 2026-09-07  
분석 대상: `https://github.com/ajouatom/openpilot`

> 이 문서는 공개 GitHub 코드 기준의 기술 분석이다. Carrot eGPU 코드는 매우 활발하게 변경 중이므로 특정 시점의 동작을 다른 시점에도 그대로 일반화하면 안 된다.

---

## 1. 발견된 eGPU 브랜치

GitHub branch 검색으로 다음 3개를 확인했다.

- `carrot-egpu-yolo`
- `thftgr/carrot-egpu`
- `thftgr/carrot-egpu-tg`

2026-09-07 확인 시점의 tip:

- `carrot-egpu-yolo`: `9ba9adcf3412c5c25fc5e25a0d53d0ad0a20354e`
  - 2026-09-07
  - `Allow explicitly parked maintenance with cameras and controls stopped`
- `thftgr/carrot-egpu`: `0bde5f6fbc1bf377c949aa04aa6384d4aadc5b6b`
  - 2026-08-30
  - `egpu: raise bounded copy staging to 256 KiB`
- `thftgr/carrot-egpu-tg`: `0f3b1d65f1a2ce457b388aa7a04fd1a80d0c569a`
  - 2026-08-31
  - `egpu: preserve probe Python import paths`

`thftgr/carrot-egpu`와 `thftgr/carrot-egpu-tg`는 단순한 앞뒤 버전이 아니라 GitHub compare 기준 **diverged** 상태다. 따라서 이름만 보고 `-tg`가 항상 상위/최신이라고 보면 안 된다.

---

## 2. 현재 carrot-egpu-yolo의 핵심 구조

### 2.1 eGPU가 primary, 내부 모델은 hot fallback

현재 `modeld.py`는 eGPU가 준비되면 eGPU model을 primary로 사용한다.

동시에 internal/QCOM model을 미리 로드해 둬서 runtime eGPU exception이 발생하면:

1. `UsbGpuActive = False`
2. eGPU startup failure 상태 기록
3. `model = small_model`
4. **같은 camera frame을 이미 로드된 internal model로 다시 실행**
5. `modelV2` publication 공백을 최소화

한다.

이 설계는 단순한 다음-cycle fallback보다 낫다. 모델 출력이 한 주기 통째로 비면 downstream에서 communication fault처럼 보일 수 있기 때문이다.

### EGPU-Future 적용

**채택한다.**

우리의 `RecoveryStateMachine`에서 FALLBACK을 단순 상태표시로 끝내지 않고, 향후 live integration 시 다음 원칙을 적용한다.

```text
Big model execution failure
        ↓
failed output 폐기
        ↓
already-warm small model
same input frame 재실행 가능 여부 확인
        ↓
model output continuity 유지
```

단, small-model same-frame rerun이 전체 deadline 안에 들어오는지는 별도 측정해야 한다.

---

## 3. 부팅/늦은 연결 처리

현재 Carrot `modeld`에는 다음이 구현되어 있다.

- eGPU가 과거에 hardware-seen 상태이고 model artifact도 있는데 현재 USB enumeration이 늦으면 startup grace period 부여
- grace 동안 SuperSpeed USB enumeration 대기
- PCIe link가 아직 준비되지 않았으면 제한 횟수 재시도
- device cache refresh 후 재초기화
- model loader thread timeout 처리
- 첫 model output이 실제 publish되기 전까지 Loading 상태 유지

특히 마지막 항목은 중요하다.

```text
PKL load 완료 ≠ 실제 주행용 modelV2 준비 완료
```

첫 inference에서 queue/kernel 초기화 지연이 발생할 수 있으므로 `model loaded`가 아니라 **첫 정상 output publication**을 ready 기준으로 삼는 것이 더 정확하다.

### EGPU-Future 적용

다음 milestone으로 반영한다.

- `MODEL_WARMUP` → `ACTIVE` 전환 조건에 first-output/deadline validation 추가
- boot grace와 late-attach를 fault가 아니라 별도 startup condition으로 처리
- model loader thread가 영구 hang하지 않도록 timeout/watchdog

---

## 4. power threshold 차이

### comma 공식 Chestnut

현재 공식 openpilot Chestnut status 코드는 powered 판단 기준으로 **5,000 mV**를 사용한다.

### Carrot USB-GPU

현재 `openpilot/system/hardware/usbgpu.py`는:

```text
USBGPU_MIN_POWER_MV = 8000
```

을 사용한다.

또한 다음을 별도로 검사한다.

- USB device 1개인지
- USB speed >= 5000 Mbps
- firmware version match
- supply fault
- minimum voltage
- PCIe/GPU tinygrad probe

### 해석

5 V와 8 V 중 어느 하나가 모든 차량/GPU 조합에 보편적으로 맞는 값이라는 근거는 없다.

따라서 EGPU-Future는 hard-coded global threshold를 사용하지 않고:

- `official_chestnut_policy()` → 5000 mV
- `carrot_usbgpu_policy()` → 8000 mV

로 profile을 분리했다.

실차에서는 threshold 자체보다 **voltage sag와 fault/PCIe/model failure 사이의 상관관계**를 기록해 최종 기준을 정한다.

---

## 5. 사용자 의도적 비활성화와 장애의 구분

Carrot commit history에서는 eGPU 사용자가 의도적으로 기능을 끈 상태와 GPU 오류를 구분해, 오류일 때는 retry하되 사용자 disable 상태에서는 계속 재시도하지 않도록 개선해 왔다.

이 설계는 중요하다.

기존의 단순 상태기계에서:

```text
eGPU not active = retry 대상
```

으로 처리하면 사용자가 실험을 끈 상태에서도 계속 USB/GPU init을 수행할 수 있다.

### EGPU-Future 적용

`EgpuState.DISABLED`와 `Health.user_enabled`를 추가했다.

```text
user_enabled = False
   → DISABLED
   → hardware/model retry 금지

user_enabled = True
   → DISCONNECTED
   → 정상 discovery sequence 재개
```

---

## 6. Carrot의 역사적 dual-model 접근에서 얻는 교훈

`carrot-egpu-yolo`의 commit history에는 eGPU 결과를 차량 주행모델 출력에 연결하면서 **QCOM on-device model과 eGPU model을 함께 유지하고 eGPU 실패 시 QCOM으로 복귀**하는 실험이 존재한다.

이후 코드가 여러 차례 refactor되었고, 현재 tip은 매 프레임 두 출력을 동시에 publish하는 구조라기보다 `eGPU primary + internal hot fallback`에 가깝다.

### EGPU-Future 판단

두 아이디어를 분리해서 가져간다.

#### 실험/평가 단계

**dual-model shadow inference**가 가치 있다.

- same frame
- same preprocessing
- small/big output 모두 기록
- control에는 small 또는 현재 승인된 primary 하나만 사용
- disagreement mining

#### 실제 안정화 단계

**hot fallback**이 더 중요하다.

매 프레임 이중 inference는:

- QCOM load
- memory bandwidth
- thermal load
- frame scheduling

을 추가로 압박할 수 있기 때문이다.

따라서 최종 구조 후보는:

```text
Research mode:
  small + big dual shadow

Production-like experiment:
  big primary
  + warm small fallback
  + sampled/triggered shadow validation
```

이다.

---

## 7. raw tensor difference만으로는 부족하다

Carrot의 과거 eGPU integration history에서는 모델 raw output 차이를 통계값으로 비교해 eGPU output 사용 여부를 판단하는 실험이 있었다.

이 아이디어 자체는 corruption 검출에 유용하지만, **raw tensor 전체의 단일 통계값만으로 실제 driving safety를 판단하면 부족하다.**

예를 들어 동일한 표준편차라도:

- trajectory curvature의 핵심 구간이 다른 경우
- stop decision 하나만 반대인 경우
- acceleration이 크게 다른 경우
- frame이 한 프레임 stale한 경우

의 의미는 전혀 다르다.

### EGPU-Future 적용

`output_validator.py`를 추가해 다음을 별도로 본다.

Hard reject for shadow pairing:

- frameId mismatch
- stale frame
- non-finite output
- model execution deadline miss

Review event:

- desiredCurvature disagreement
- desiredAcceleration disagreement
- shouldStop mismatch

즉:

```text
Tensor integrity
   +
Frame freshness
   +
Deadline
   +
Action-space disagreement
   +
Scenario context
```

를 함께 본다.

---

## 8. YOLO / RoadSeg / Lane / PointTracker 실험의 의미

Carrot eGPU history에는 단순히 큰 driving model만이 아니라 다음을 eGPU로 시험한 흔적이 있다.

- YOLO vehicle/object detection
- traffic-light related detection/UI
- road segmentation
- lane output
- point tracking

이 방향은 EGPU-Future에 매우 유용하다.

### 하지만 역할을 다르게 본다

초기에는 이러한 sidecar perception을 steering/brake command에 직접 fusion하지 않는다.

대신:

1. difficult-scene 자동 태깅
2. big/small disagreement 원인 설명
3. cone/construction/cut-in/vehicle hard-case mining
4. offline evaluator
5. 독립 evidence channel

로 사용한다.

예:

```text
Driving model says: path clear
YOLO/RoadSeg sidecar says: unusual obstacle/temporary lane
        ↓
즉시 제어 override X
        ↓
HIGH-VALUE DISAGREEMENT EVENT로 저장
        ↓
replay / human review / training set 후보
```

향후 독립 safety validator로 발전시키려면 false-positive/false-negative와 timing을 별도 검증해야 한다.

---

## 9. Carrot에서 확인되는 현재 위험요소

### 9.1 빠른 코드 churn

2026-09 초 commit history에는 짧은 기간에 다음 영역이 반복 수정됐다.

- USB GPU boot detection
- late reconnect
- PCIe readiness
- loader thread
- device/tensor cache reset
- eGPU status/UI
- YOLO preprocessing/inference
- fallback

이는 두 가지 의미가 있다.

긍정적:
- 실제 문제를 빠르게 발견하고 해결하는 활발한 실험장이다.

주의:
- 현재 branch를 automotive-stable baseline으로 간주하면 안 된다.

### 9.2 branch 간 divergence

`thftgr/carrot-egpu`와 `thftgr/carrot-egpu-tg`는 서로 diverged되어 있고, eGPU 외의 Carrot 주행/레이더/서버 변화도 많이 섞여 있다.

따라서 전체 branch merge보다 **기능 단위 cherry-pick/재구현**이 적절하다.

### 9.3 eGPU failure와 주행모델 변경을 동시에 다루는 위험

GPU transport, model architecture, Carrot control customization이 한 branch에서 같이 움직이면 regression 원인 분리가 어렵다.

EGPU-Future는 이를 분리한다.

```text
Transport/health
Model execution
Shadow validation
Vehicle control
```

각 layer를 따로 시험한다.

---

## 10. comma 공식 vs Carrot vs EGPU-Future

| 항목 | comma 공식 Chestnut | Carrot eGPU | EGPU-Future 방향 |
|---|---|---|---|
| GPU path | USB+AMD/tinygrad | USB+AMD 중심 | 동일 baseline부터 시작 |
| big model | 공식 880M model | 공식/실험 model + sidecars | big model + evaluator |
| fallback | small model fallback | hot internal fallback 강화 | same-frame fallback 검증 |
| late boot | 공식 상태/장애 처리 | grace/retry 적극 실험 | explicit startup state |
| reconnect | 제한적/보수적 | 적극 실험 | safe retry state machine |
| power threshold | 5000 mV | 8000 mV | backend profile |
| user disable | 일반 active state | 의도적 disable/error 구분 | `DISABLED` 상태 |
| YOLO/Seg sidecar | 핵심 공식 경로 아님 | 활발한 실험 | evaluation/mining부터 |
| raw-output 비교 | 핵심 경로 아님 | 역사적 실험 존재 | action/freshness/deadline 검증 |
| control integration | 공식 modeld | 실험적 Carrot integration | shadow → validator → staged integration |

---

## 11. 채택 우선순위

### 즉시 채택

1. same-frame hot fallback 개념
2. startup grace / PCIe retry
3. first-output-ready semantics
4. user-disable vs error 분리
5. power-profile 분리
6. eGPU status observability
7. deterministic `frameId` pairing

### shadow 연구로 채택

8. dual-model execution
9. YOLO/RoadSeg sidecar evidence
10. action-space disagreement mining

### 당장 채택하지 않음

- Carrot 전체 eGPU branch 통합
- raw tensor single-statistic만으로 control 승인
- generic reconnect 후 즉시 차량제어 재진입
- 검증되지 않은 sidecar perception의 steering/brake 직접 override

---

## 12. 다음 구현

1. route/qlog/rlog → modelV2 action extractor
2. frameId deterministic pairer
3. output freshness/deadline/action validator
4. Carrot-style first-output startup milestone
5. same-frame hot-fallback simulator
6. live shadow_modeld prototype
7. sidecar perception event schema
8. replay fault-injection

---

## 주요 소스

- ajouatom/openpilot: https://github.com/ajouatom/openpilot
- carrot-egpu-yolo: https://github.com/ajouatom/openpilot/tree/carrot-egpu-yolo
- thftgr/carrot-egpu: https://github.com/ajouatom/openpilot/tree/thftgr/carrot-egpu
- thftgr/carrot-egpu-tg: https://github.com/ajouatom/openpilot/tree/thftgr/carrot-egpu-tg
- current Carrot USB-GPU helper: https://github.com/ajouatom/openpilot/blob/carrot-egpu-yolo/openpilot/system/hardware/usbgpu.py
- current Carrot modeld: https://github.com/ajouatom/openpilot/blob/carrot-egpu-yolo/openpilot/selfdrive/modeld/modeld.py
- comma official openpilot: https://github.com/commaai/openpilot

Last reviewed: 2026-09-07
