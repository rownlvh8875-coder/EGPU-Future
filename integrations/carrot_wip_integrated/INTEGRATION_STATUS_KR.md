# Carrot-WIP Integrated eGPU — 현재 진행상태

기준일: 2026-09-07

## 기준선

- base: `ajouatom/openpilot:carrot-wip`
- reviewed head: `6f4c00e625dc3d41d3776427a272a5c3fed75e6c`
- previous reviewed head: `b2a2db5590f28af420ed01e75c145ddb8ddd90d6`
- reviewed `modeld.py` blob: `e4de3eb2236f6bb0c54c87666099147311602f4f`
- integration development branch: `rownlvh8875-coder/EGPU-Future:carrot-wip-integrated-v0`

`6f4c00e6`는 이전 기준선의 바로 다음 commit이며 Hyundai PV5/navigation speed 관련 파일만 바뀌었다. eGPU/modeld critical blob은 변경되지 않아 동일한 integration boundary로 검토했다.

## 단계 상태

| 단계 | 상태 | 핵심 |
|---|---|---|
| S0 Baseline freeze | 완료 | Carrot/comma/sunnypilot/Carrot-experimental 기준 commit 및 critical blob 고정 |
| S1 Observer/provenance | 완료 + CI PASS | active/attempted backend, frame age, latency, same-frame fallback 기록 |
| S2 Hardware telemetry | 코드 완료 + CI PASS / 실기기 대기 | AMD SMU, power, USB, PCIe read-only background telemetry |
| S3 Model slots | 코드 완료 + CI PASS | qcom/egpu slot metadata, hash/size/generation/runner validation |
| S4A Guardian contract | 코드 완료 + CI PASS | active-vs-shadow evidence 평가, control authorization 강제 false |
| S4B Live shadow load probe | 코드 완료 / 최신 CI 검증 중 | P단·정차·controls inactive 전용, QCOM <=5 Hz 간섭시험 |
| S4C 20 Hz parked comparison | 대기 | temporal continuity가 유지되는 품질비교 단계 |
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

`/data/egpu_integrated/state.json`에 frame/backend/latency/fallback provenance를 기록한다. 기본 OFF, fail-open이다.

## S2 결과

`/data/egpu_integrated/hardware.json`에 GPU temperature/power/PPT readback/utilization/clock/fan, supply V/I/fault, PCIe/USB 상태를 저주기 background thread로 기록한다. modeld 20 Hz loop에서 hardware read를 하지 않으며 hardware write도 없다.

## S3 결과

`qcom`/`egpu` 두 model slot metadata를 분리했다.

```text
fallbackSlot = qcom only
runtimeHotSwap = false
crossSlotFallback = false
controlAuthorization = false
```

Carrot BigModelManifest의 model ID/file/size/SHA256을 eGPU slot metadata로 adapter할 수 있지만 실제 Carrot 다운로드/compile/startup logic은 아직 그대로다.

## S4A 결과

Guardian은 same frame, freshness, nonfinite, optional latency policy, curvature/accel/stop disagreement, supply fault, hardware evidence age를 확인한다.

그러나 결과는 항상:

```text
controlAuthorization = false
shadowPublishToControls = false
```

이다.

## S4B 결과

### Tap v2

기존 exact-input metadata에 다음을 추가했다.

```text
standstill
vEgo
gear
latActive
longActive
```

sender와 receiver 모두 다음을 요구한다.

```text
P
standstill
abs(vEgo) < 0.01 m/s
latActive = false
longActive = false
```

AF_UNIX nonblocking/latest-only이며 send 결과는 active modeld가 사용하지 않는다.

### Probe

`tools/carrot_wip_s4b_shadow_probe.py`는:

- manual start only
- manager autostart 없음
- QCOM shadow only
- <=5 Hz
- 최대 300초
- PROFILE=1 default
- no PubMaster
- no modelV2/controls publish
- active eGPU가 아니면 skip

으로 제한한다.

S4B output은 강제로:

```text
shadowOnly = true
controlEligible = false
qualityComparisonEligible = false
```

이다.

### 왜 품질비교를 금지하는가

5 Hz shadow는 20 Hz active model과 temporal hidden-state history가 다르다. 따라서 S4B는 **두 번째 QCOM workload가 active eGPU latency/resource를 방해하는지**만 본다.

BIG/SMALL 행동 품질 비교는 이후 S4C parked 20 Hz continuity 단계에서만 허용한다.

## S4B 실기기 실행 순서

```text
1. T0~T3 / T4 readiness PASS
2. source compatibility 재확인
3. S1 + S2 + S4B tap 적용
4. full reboot
5. active eGPU baseline
6. receiver-only 확인
7. QCOM shadow <=5 Hz load probe
8. active during/after latency 비교
9. QCOM tinygrad profile correlation
10. tap/patch restore
11. final reboot/source verification
```

중지조건:

- 차량 이동/P 해제
- lat/long control active
- eGPU fallback
- active model latency tail anomaly
- frame gap 증가
- USB link errors
- thermal/power fault
- shadow exception

S4B 성공은 20 Hz/public-road/control integration 승인이 아니다.

## 현재 가장 큰 외부 제약

사용자 GitHub 계정에는 아직 writable openpilot fork가 없다.

따라서 현재 branch는 실제 openpilot tree를 대체하는 저장소가 아니라, `carrot-wip`에 순차 적용할 **reviewed integration patchset**이다.

writable fork가 준비되면 S1→S2→S4B patch와 S3/S4A runtime metadata 계층을 실제 fork에 옮긴다.
