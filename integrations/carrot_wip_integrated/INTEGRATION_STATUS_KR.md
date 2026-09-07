# Carrot-WIP Integrated eGPU — 현재 진행상태

기준일: 2026-09-07

## 기준선

- base: `ajouatom/openpilot:carrot-wip`
- reviewed head: `b2a2db5590f28af420ed01e75c145ddb8ddd90d6`
- reviewed `modeld.py` blob: `e4de3eb2236f6bb0c54c87666099147311602f4f`
- integration development branch: `rownlvh8875-coder/EGPU-Future:carrot-wip-integrated-v0`

## 단계 상태

| 단계 | 상태 | 핵심 |
|---|---|---|
| S0 Baseline freeze | 완료 | Carrot/comma/sunnypilot/Carrot-experimental 기준 commit 및 critical blob 고정 |
| S1 Observer/provenance | 완료 + CI PASS | active/attempted backend, frame age, latency, same-frame fallback 기록 |
| S2 Hardware telemetry | 코드 완료 + CI PASS / 실기기 대기 | AMD SMU, power, USB, PCIe read-only background telemetry |
| S3 Model slots | 코드 완료 + CI PASS | qcom/egpu slot metadata, hash/size/generation/runner validation |
| S4A Guardian contract | 코드 완료 + CI PASS | active-vs-shadow evidence 평가, control authorization 강제 false |
| S4B Live shadow integration | 다음 | parked/offroad bounded live shadow 연결 |
| S5 Perception sidecars | 대기 | Carrot YOLO2 방식 bounded/latest-only workload |
| S6 OEM sensor Guardian | 대기 | radar/BSM/CAN 독립 evidence fusion |
| S7 Actuation adapter boundary | 대기 | 미래 actuator hardware 대비 software boundary |

## 현재 보존되는 Carrot 동작

다음은 아직 변경하지 않는다.

- `modelV2` 실제 publish 경로
- Carrot eGPU primary model 선택
- eGPU startup grace / PCIe retry
- warm QCOM small fallback
- eGPU runtime failure 시 **same camera frame QCOM 재실행**
- DesireHelper 및 Carrot 주행 UX
- controls / car interface
- panda safety
- 차량별 actuator limits

## S1 결과

출력:

```text
/data/egpu_integrated/state.json
```

기록:

- frameId / stateFrameId / frameAge
- attempted backend
- actual backend
- execution latency
- rolling p95/max
- fallback count/reason

기본 OFF, fail-open.

## S2 결과

출력 예정:

```text
/data/egpu_integrated/hardware.json
```

기록:

- hotspot/memory temperature
- GPU power/PPT readback
- utilization/clock/fan
- supply V/I/fault
- PCIe LTSSM
- USB speed/link errors/firmware status

2초 nominal background thread이며 modeld 20 Hz loop에서 hardware read를 수행하지 않는다.

## S3 결과

예정 registry:

```text
/data/egpu_integrated/model_slots.json
```

정책:

```text
qcom slot = trusted fallback/default

egpu slot = Carrot verified big-model manifest adapter

fallbackSlot = qcom only
runtimeHotSwap = false
crossSlotFallback = false
controlAuthorization = false
```

## S4A 결과

Guardian은 다음을 확인한다.

- same frame
- frame freshness
- NaN/Inf
- optional latency policy
- curvature disagreement
- acceleration disagreement
- stop mismatch
- supply fault
- hardware evidence freshness

그러나 결과는 항상:

```text
controlAuthorization = false
shadowPublishToControls = false
```

이다.

## 다음 S4B 순서

실기기 없이 가능한 코드는 먼저 만들되 실행 순서는 다음을 유지한다.

```text
1. reviewed metadata tap
2. active baseline
3. parked/offroad shadow <=5 Hz
4. active latency interference 비교
5. Guardian evidence 생성
6. QCOM/tinygrad profile correlation
7. source restore
8. final reboot/verification
```

S4B에서 성공하더라도 20 Hz/public-road/control integration 승인을 의미하지 않는다.

## 현재 가장 큰 외부 제약

사용자 GitHub 계정에는 아직 writable openpilot fork가 없다.

따라서 현재 branch는 실제 openpilot tree를 대체하는 저장소가 아니라, `carrot-wip`에 순차 적용할 **reviewed integration patchset**이다.

writable fork가 준비되면 이 branch의 S1→S2→S3→S4 순서를 그대로 실제 openpilot fork에 옮긴다.
