# Stage 4A — Observe-only Guardian Contract

작성일: 2026-09-07

## 목적

S1 observer, S2 hardware telemetry, S3 model-slot metadata를 바탕으로 active driving model과 shadow model의 결과를 **동일 프레임 기준으로 평가**한다.

하지만 S4A의 Guardian은 아직 차량제어를 할 수 없다.

```text
active model output
shadow model output
hardware telemetry
        |
        v
Guardian assessment
        |
        +-- HOLD / REVIEW / OBSERVE
        |
        +-- research evidence

항상:
controlAuthorization = false
shadowPublishToControls = false
```

## active / shadow 정의

초기 통합에서는:

```text
active
= 현재 Carrot modeld가 실제 modelV2를 만드는 모델
  eGPU big 또는 fallback QCOM small

shadow
= 동일 camera frame을 별도 research path에서 계산한 비교 모델
```

shadow가 실제 controls message를 publish하면 안 된다.

## hard issue

다음은 evidence 자체를 신뢰하기 어려운 상태라 `HOLD`다.

- `frame_mismatch`
- `active_frame_stale`
- `shadow_frame_stale`
- `active_nonfinite`
- `shadow_nonfinite`
- 명시한 execution policy 초과
- `egpu_supply_fault`
- hardware evidence timestamp가 명시 policy보다 오래됨

`HOLD`는 차량제어 명령이 아니다.
단지 해당 shadow evidence를 다음 단계 판단에 사용하지 않는다는 뜻이다.

## review issue

다음은 사람/리플레이 검토 대상으로 분류한다.

- curvature disagreement
- acceleration disagreement
- stop-decision mismatch
- active/shadow가 같은 backend인 비교
- hardware telemetry missing/invalid

현재 기본 disagreement threshold:

```text
curvature abs = 0.003
curvature rel = 0.25
acceleration abs = 0.50 m/s²
```

이 숫자는 **연구용 event-mining threshold**이며 safety limit이 아니다.

## latency threshold

S4A는 기본적으로 execution-time hard limit을 임의로 만들지 않는다.

`max_execution_ms=None`이 기본이다.

실기기 T0~T4에서 baseline을 확보한 뒤 실험 policy를 명시한 경우에만 execution-time hold 조건을 활성화한다.

## hardware telemetry 처리

S2의 `hardware.json`에서:

- supply fault는 명확한 hard issue로 취급 가능
- telemetry 자체가 invalid/missing인 것은 기본적으로 review issue
- timestamp가 있고 너무 오래된 경우만 policy에 따라 hard issue

GPU 온도 자체에 대해서는 S4A에서 임의의 새로운 안전 cutoff를 만들지 않는다.
공식/Carrot 기준과 실제 commissioning을 거쳐 별도 thermal policy 단계에서 다룬다.

## 출력 예시

```json
{
  "stage": "S4A-observe-only",
  "activeBackend": "egpu",
  "shadowBackend": "qcom",
  "frameId": 12345,
  "hardIssues": [],
  "reviewIssues": ["acceleration_disagreement"],
  "evidenceEligible": true,
  "analysisStatus": "REVIEW",
  "controlAuthorization": false,
  "shadowPublishToControls": false
}
```

## 중요한 안전 경계

`GuardianAssessment`에는 steering/acceleration command field가 없다.

또한:

```text
controlAuthorization = false
shadowPublishToControls = false
```

는 결과 생성 시 고정된다.

따라서 S4A 코드를 controls에 연결하려면 별도의 명시적 설계/코드변경이 필요하다.
그 작업은 이 단계에 포함하지 않는다.

## S4A 완료 기준

- same-frame check
- frame-age/freshness check
- NaN/Inf check
- optional execution policy
- curvature/acceleration/stop disagreement
- supply-fault evidence
- stale hardware evidence check
- no control command fields
- control authorization hard false
- unit tests PASS

## 다음 단계 S4B

실제 live shadow process와 연결한다.

순서:

```text
Carrot active modeld
  -> metadata tap

shadow process
  -> same camera frame
  -> bounded rate first
  -> JSON/shadow-only output

Guardian
  -> active/shadow pair
  -> evidence
```

첫 live integration은 정차/offroad 5 Hz부터 시작하고, T4 commissioning gate를 통과하기 전에는 20 Hz continuous shadow로 올리지 않는다.
