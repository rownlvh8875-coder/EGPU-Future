# Carrot-WIP Integrated eGPU Branch Architecture

작성일: 2026-09-07

## 목표

한국에서 실제 사용성이 높은 `ajouatom/openpilot:carrot-wip`를 주행 UX/차량지원 기준선으로 유지하면서 다음 세 계열의 장점을 기능 단위로 통합한다.

- **Carrot-WIP**: 한국차 운용성, eGPU startup/retry, same-frame hot fallback, 실차 디버깅
- **comma.ai openpilot**: Chestnut/AMD telemetry, upstream model/safety 구조, hardware health 기준
- **sunnypilot**: QCOM/eGPU 별도 model slot, bundle/hash 검증, 모델 세대/runner 관리

핵심 원칙은 **기능을 한 번에 합치지 않고 안전 경계별로 순차 적용**하는 것이다.

## 절대 보존 경계

초기 단계에서 다음은 carrot-wip 원본을 그대로 보존한다.

1. panda safety
2. 차량별 actuator limits
3. controls / car interface
4. DesireHelper 및 당근 주행 UX
5. eGPU primary driving model 경로
6. 이미 구현된 internal QCOM warm fallback
7. eGPU 장애 시 같은 camera frame을 QCOM small model로 재실행하는 fallback

즉 첫 통합은 **더 강한 제어권을 만드는 작업이 아니다.**

## 최종 목표 구조

```text
road/wide camera
      |
      +------------------------------+
      |                              |
      v                              v
 Carrot primary modeld          optional observers
 eGPU BIG when healthy          / shadow / perception
 QCOM SMALL fallback                 |
      |                              |
      v                              v
 model output ----------------> Guardian evidence
      |                              |
      +------------+-----------------+
                   |
             Output Validator
                   |
            existing controls
                   |
           panda / OEM limits
                   |
               vehicle
```

장기적으로 OEM radar/BSM/CAN은 BIG model을 직접 대체하지 않고 Guardian의 독립 증거로 먼저 사용한다.

## 단계

### S0 — Baseline freeze ✅

현재 기준선:

- `ajouatom/openpilot:carrot-wip`
- commit `b2a2db5590f28af420ed01e75c145ddb8ddd90d6`

key blob을 `baseline_20260907.json`에 고정했다.

### S1 — Observer / provenance layer ✅

차량제어와 무관한 observer를 modeld에 삽입해 다음만 기록한다.

- frameId / stateFrameId / frameAge
- 이번 프레임에서 처음 시도한 backend (`egpu`/`qcom`)
- 실제 결과를 만든 backend
- model execution time
- fallback count / last fallback frame / reason
- rolling p95 / max model latency

observer의 반환값은 modeld control flow에서 절대 사용하지 않는다. observer 예외도 내부에서 삼킨다.

기본 비활성화이며 다음 중 하나로만 활성화한다.

- `EGPU_INTEGRATED_OBSERVER=1`
- `/data/egpu_integrated/observer_enabled` marker file

Stage-1 patch는 marker 제거 시 reviewed `carrot-wip/modeld.py`가 byte-for-byte 복원되도록 검증된다.

### S2 — comma-style eGPU hardware telemetry parity ✅ 코드 구현 / 실기기 검증 대기

Carrot의 USB/power readiness는 유지하면서 comma `ChestnutState`에서 유효한 항목을 read-only로 이식한다.

구현 항목:

- GPU hotspot temp
- memory temp
- socket power
- PPT/power limit **조회만**
- GPU utilization
- GPU clock
- fan RPM
- supply voltage/current/fault
- PCIe link state
- USB speed/link error/firmware status

중요한 차이:

- hardware read는 modeld 20 Hz loop에서 수행하지 않는다.
- 기본 OFF인 daemon telemetry thread가 nominal 2초 간격으로만 읽는다.
- telemetry는 AMD device를 먼저 열지 않는다. modeld가 이미 열어둔 `Device["AMD"]`만 사용한다.
- USB supply/PCIe read는 Carrot의 `usbgpu_bus_lock`을 사용한다.
- telemetry 결과는 `/data/egpu_integrated/hardware.json`에만 기록한다.
- PPT/fan/PCIe/USB write는 없다.

상세: `STAGE2_TELEMETRY_KR.md`

실기기에서는 telemetry OFF/ON active latency 간섭 측정을 통과해야 S2 실사용을 승인한다.

### S3 — sunnypilot-inspired model slots

현재 Carrot big model manifest/download 흐름을 버리지 않는다.

그 위에 두 slot을 명시한다.

- `qcom` slot
- `egpu` slot

각 slot은 최소 다음 metadata를 갖는다.

- model id/ref
- artifact filename
- size
- SHA256
- generation
- nominal frequency
- runner/backend
- compatibility constraints

중요: 빈 slot은 자동으로 다른 slot의 임의 모델로 cross-fallback하지 않는다. fallback은 검증된 QCOM default/small 경로만 사용한다.

초기 S3에서는 metadata/validation만 구현하고 주행 중 자동 hot-swap은 만들지 않는다.

### S4 — Guardian + shadow validation

EGPU-Future에서 개발한 다음 기능을 통합한다.

- deterministic frame pairing
- output freshness/deadline validator
- big/small disagreement mining
- temporal lead/stop scenario tags
- route health report
- T0~T4 commissioning gate

shadow output은 control bus로 publish하지 않는다.

### S5 — bounded perception sidecars

Carrot YOLO2의 설계를 따른다.

- driving inference 우선
- optional inference는 admission gate 통과 시만 실행
- 후처리는 bounded CPU worker로 격리
- queue가 밀리면 오래된 결과 drop, latest-only
- YOLO/RoadSeg/traffic-light 등을 동시에 켜지 않고 한 workload씩 검증

### S6 — OEM sensor Guardian

현대/기아에서 실제 사용 가능한 radar/BSM/CAN 신호를 독립 evidence로 사용한다.

우선순위:

1. front radar
2. BSM/corner radar availability 확인
3. wheel speed/yaw/steering/brake state
4. timestamp alignment
5. big-model output과 독립 cross-check

센서 신호는 초기에 직접 steering/braking command를 만들지 않는다.

### S7 — 향후 손발 확장 대비 Actuation Adapter

미래에 comma.ai나 제3자가 더 강한 actuator interface 하드웨어를 제공할 가능성을 고려해 software boundary만 준비한다.

```text
Driving Intelligence
  -> Validator
  -> Vehicle Actuation Adapter
  -> panda safety / hardware safety
  -> actuator interface
```

현재 브랜치에서는 새로운 steering/braking authority를 추가하지 않는다.

## 단계별 완료 조건

### S1 완료 조건

- patch 제거 시 carrot-wip `modeld.py` byte-for-byte 복원
- observer disabled일 때 기존 동작과 동일
- observer failure가 modeld failure로 전파되지 않음
- fallback control flow 변경 없음
- pure-Python unit tests 통과

### S2 코드 완료 조건

- telemetry default OFF
- telemetry가 AMD device를 먼저 열지 않음
- hardware read가 modeld 20 Hz loop 밖에서 실행
- SMU/USB/PCIe read-only
- Stage-2 제거 시 exact Stage-1 restore
- pure-Python unit tests 통과

### S2 실기기 완료 조건

- telemetry OFF baseline 확보
- telemetry ON active big p95/p99/max 비교
- frame age/gap 증가 여부 확인
- USB link error 증가 없음
- sample duration tail 확인
- 이상 시 telemetry를 기본 OFF로 유지하고 구조 재검토

이후에만 S3 model slot을 실제 openpilot fork에 적용한다.
