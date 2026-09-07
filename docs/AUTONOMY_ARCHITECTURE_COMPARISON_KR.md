# 자율주행 아키텍처 비교와 EGPU-Future 적용 방향

작성일: 2026-09-07  
범위: Tesla FSD (Supervised), openpilot/Chestnut, Waymo, Wayve, Mobileye, Autoware/Open AD Kit, Apollo, NVIDIA DRIVE

> 이 문서는 각 회사·프로젝트의 공개 자료와 공개 소스코드를 기준으로 비교한다. 회사가 스스로 제시한 성능·안전성 표현은 독립 검증 결과와 구분한다.

---

## 1. 결론부터

EGPU-Future가 따라가야 할 방향은 특정 회사 하나의 복제품이 아니다.

가장 현실적인 조합은 다음이다.

- **Tesla / Wayve에서 가져올 것:** 대규모 데이터 기반 end-to-end 학습, temporal model, 큰 teacher model → 작은 student model distillation
- **Waymo에서 가져올 것:** world model·simulation을 이용한 long-tail 재현과 반복 검증, 센서 중복성에 대한 사고방식
- **Mobileye에서 가져올 것:** 학습 모델과 별개인 독립적인 safety envelope 및 redundancy
- **Autoware에서 가져올 것:** mixed-criticality, trajectory validator, shadow mode, fault containment
- **openpilot에서 유지할 것:** 저비용 retrofit, open-source, 다양한 OEM 지원, 학습형 driving model, 기존 panda/safety 제약

이를 EGPU-Future에서는 다음 구조로 정의한다.

```text
             ┌───────────────────────────────────────┐
             │        eGPU Intelligence Plane        │
             │ Big Driving / World / Temporal Model  │
             └──────────────────┬────────────────────┘
                                │ candidate action / trajectory
                                ▼
┌───────────────────────────────────────────────────────────────┐
│              comma four Guardian Plane                       │
│ sensor ingest / state / DMS / deadline / health / fallback   │
│          + independent Safety Envelope / Validator            │
└──────────────────────────────┬────────────────────────────────┘
                               │ bounded command
                               ▼
                     OEM vehicle interface
                steering / brake / accelerator
```

핵심 원칙은 **"큰 모델은 더 똑똑하게, 작은 독립 계층은 더 보수적으로"**이다.

---

# 2. Tesla는 자율주행을 어떻게 접근하는가

## 2.1 현재 접근

### Fact

Tesla의 현재 FSD는 **FSD (Supervised)**이며, Tesla의 2026 Q2 자료에도 "active driver supervision required; does not make the vehicle autonomous"라고 명시되어 있다.

Tesla가 공개한 핵심 구성은 다음과 같다.

- 8개의 고해상도 외부 카메라
- 차량 전체를 둘러보는 360° 시야 구성
- Tesla 자체 inference computer/custom silicon
- IMU, GPS, cabin camera/driver monitoring 입력
- 대규모 실차 fleet 데이터
- end-to-end foundation model 중심의 FSD v14 계열

2026 Q2 Tesla 자료에서 특히 중요한 점은 **AI3용 FSD v14 lite가 AI4의 v14 driving behavior를 AI3의 camera/compute configuration으로 distill한다**고 Tesla가 직접 명시했다는 것이다.

즉 Tesla 역시 "가장 큰 모델을 모든 구형 차량에 그대로 탑재"하는 방식만을 쓰지 않는다.

```text
large / newer-compute model
          │
          │ behavior distillation
          ▼
smaller / constrained-compute deployment model
```

이 구조는 Chestnut의 big model을 comma four용 small model 개선에 활용한다는 EGPU-Future의 teacher/student 전략과 매우 유사하다.

### Tesla의 강점

1. **차량과 AI의 수직 통합**
   - 센서 배치, 컴퓨터, 차량 제어, OTA, 데이터 수집을 동일 회사가 설계한다.

2. **주변 시야**
   - 여러 외부 카메라가 차량 주위를 본다.
   - 단순히 전방 경로 추종만 개선하는 것보다 lane change, turn, merge, parking 등에 필요한 정보량이 많다.

3. **fleet-scale 데이터 루프**
   - 실제 차량에서 데이터를 수집하고 다시 학습·배포하는 폐루프가 강하다.

4. **compute 세대 간 distillation**
   - 최신 하드웨어의 behavior를 제한된 구형 hardware configuration으로 내리는 경로가 실제 제품에 사용되고 있다.

## 2.2 Tesla 방식의 한계와 주의점

- FSD (Supervised)는 현재 운전자 감시가 필요한 시스템이다.
- Tesla가 발표하는 안전·성능 수치는 Tesla 자체 자료인 경우가 많으므로 외부 독립 검증과 구분해야 한다.
- Tesla처럼 공장 단계에서 센서와 actuator를 통합하는 회사의 구조를 retrofit openpilot에 그대로 복사할 수 없다.

---

# 3. openpilot과 Tesla의 본질적 차이

| 항목 | Tesla FSD (Supervised) | openpilot + comma four | EGPU-Future에서의 의미 |
|---|---|---|---|
| 제품 형태 | 차량에 factory-integrated | 기존 차량 retrofit | OEM별 actuator 한계를 항상 고려 |
| 외부 비전 | 8개 외부 카메라 | openpilot 로그 기준 road + wide-road, 별도 driver camera | eGPU만 늘려도 side/rear 정보는 새로 생기지 않음 |
| compute | 차량 전용 Tesla AI computer | Snapdragon 845 MAX급 C4 + 선택적 desktop eGPU | Chestnut은 compute 격차를 크게 줄이나 전체 시스템 동등성은 아님 |
| 제어 인터페이스 | Tesla native vehicle architecture | OEM ADAS가 제공하는 CAN 제어 명령 활용 | 조향 torque/rate, longitudinal authority가 차량별로 다름 |
| ML 방향 | end-to-end foundation model | learned driving model, MLSim, big external model | 방향은 점점 가까워지고 있음 |
| 소프트웨어 | proprietary | open source | 실험·검증·fork 개발에는 openpilot이 유리 |
| 데이터 | 대규모 Tesla fleet | comma fleet | 규모 차이는 있지만 양쪽 모두 fleet learning |
| 안전 운영 | FSD Supervised + Tesla DMS/vehicle stack | panda safety + DMS + vehicle-specific limits | eGPU는 safety layer를 제거하면 안 됨 |

## 중요한 오해: comma four의 "360° vision"과 Tesla surround vision은 같은 뜻이 아니다

comma four 상품 설명에는 360° vision이라는 표현이 존재하지만, openpilot의 실제 기록 스트림은 다음과 같이 정의된다.

- `fcamera.hevc`: road camera
- `ecamera.hevc`: wide road camera
- `dcamera.hevc`: driver camera

따라서 Tesla의 **8 external cameras around the vehicle**와 동일한 주변 외부 센싱 구조로 해석하면 안 된다.

### 판단

**eGPU는 "두뇌"를 키운다. 센서가 보지 못하는 방향을 만들어 주지는 않는다.**

향후 목표가 supervised L2 성능 향상이라면 현재 forward camera 계열을 최대 활용하는 것이 우선이다. 반면 point-to-point city driving이나 eyes-off/L3+를 장기 목표로 삼는다면 side/rear sensing 및 독립 redundancy까지 별도 hardware roadmap으로 다뤄야 한다.

---

# 4. Waymo: 큰 모델보다 "시스템 전체의 중복성 + simulation"

## Fact

Waymo의 6세대 Driver는 camera, lidar, radar를 함께 사용한다. 공개 자료에서는 13 cameras, 4 lidar, 6 radar 및 external audio receiver를 제시했고, 2026년에는 이 6세대 시스템으로 fully autonomous operation을 시작했다고 발표했다.

Waymo는 2026년 8월 자사의 200M+ fully autonomous miles 경험을 정리하면서 multimodal sensing의 상호보완성과 HD map의 prior 역할을 강조했다.

또한 2026년 Waymo World Model을 공개하며 simulation을 자사의 안전 AI 개발의 핵심 축 중 하나로 명시했다.

## EGPU-Future가 배울 점

### 1. World model은 "차 안에서 더 큰 모델을 돌리는 용도"만이 아니다

가장 큰 가치 중 하나는 실차에서 위험하게 재현하기 힘든 상황을 무한 반복하는 것이다.

예:

- 반대편 차량의 비정상 침범
- 갑작스러운 cut-in
- 공사 cone 재배치
- 부분 차선 폐쇄
- 급정거 lead
- 비·눈·역광
- 센서 일부 degradation

EGPU-Future에서도 실제 주행 모델과 별도로 **scenario generation / replay / closed-loop evaluation world model** 트랙을 두는 편이 좋다.

### 2. 센서 redundancy는 model parameter 수와 다른 문제다

카메라가 가려진 상태에서 모델을 10배 크게 해도 가려진 정보를 복원할 수 있다는 보장은 없다.

따라서 장기적으로 L3+를 목표로 한다면 compute upgrade와 sensor/safety redundancy roadmap을 분리해야 한다.

---

# 5. Wayve: end-to-end generalization의 극단

## Fact

Wayve는 AV2.0을 기존의 modular `sense → plan → act` 구조를 raw sensor input에서 driving output으로 직접 연결하는 end-to-end neural network 방식으로 설명한다.

또한 GAIA-3라는 **15B parameter generative world model**을 실제 차량 제어 자체가 아니라 autonomous driving AI의 evaluation/validation을 위해 사용한다.

## EGPU-Future가 배울 점

- 큰 모델을 반드시 실시간 actuator loop에 전부 넣을 필요는 없다.
- 일부 가장 큰 모델은 **teacher / evaluator / world simulator**가 되는 편이 비용 대비 효과가 클 수 있다.
- 장기적으로 `Driving Model`과 `Evaluation World Model`을 별도 프로젝트로 운영할 필요가 있다.

---

# 6. Mobileye: Intelligence와 Safety를 독립시키는 사고방식

## Fact

Mobileye의 제품 구성은 단계가 올라갈수록 compute와 sensor redundancy를 추가하는 방식이다.

- SuperVision: 360° cameras, EyeQ 계열, REM, RSS, eyes-on/hands-off
- Chauffeur: 추가 EyeQ compute + surround imaging radar + front lidar, eyes-off/hands-off 목표
- Mobileye Drive: no-driver 용도

Mobileye는 Chauffeur에서 camera perception과 radar/lidar perception을 독립적인 sensing subsystem으로 구성하는 **True Redundancy**를 강조한다.

또한 RSS(Responsibility-Sensitive Safety)는 안전한 거리를 포함한 driving safety 원칙을 수학적·검증 가능한 형태로 분리하려는 접근이다.

## EGPU-Future가 배울 점

Big driving model이 "가도 된다"고 판단하더라도 최종 actuator command 전에는 별도의 제한 계층이 있어야 한다.

예시:

```text
Big model proposed trajectory
        │
        ▼
Independent Validator
  - steering feasibility
  - max lateral accel
  - max jerk / accel
  - lead collision envelope
  - vehicle actuator limits
  - stale/deadline check
        │
   valid│        invalid
        ▼           ▼
    controller   reject/fallback
```

이것을 Mobileye RSS의 복제라고 부를 수는 없다. 그러나 **"AI policy의 성능과 safety envelope의 검증을 분리한다"**는 구조적 철학은 EGPU-Future에 매우 적합하다.

---

# 7. Autoware / Open AD Kit: EGPU-Future와 가장 직접적으로 닮은 안전 구조

## Fact

Autoware 1.8.0에는 trajectory validator와 shadow mode가 포함되어 있다. 후보 trajectory를 여러 safety/traffic-rule filter로 평가하고 부적합한 trajectory를 제거하는 구조다.

Open AD Kit은 mixed-criticality deployment를 명시적으로 지원한다.

- safety-critical 기능은 certified / real-time 환경
- monitoring·development·비핵심 workload는 일반 compute

2026년 Open AD Kit 관련 개발에서는 main Linux compute와 safety processor를 분리하고 fault 발생 시 Minimum Risk Maneuver 계층으로 연결하는 방향도 공개돼 있다.

## EGPU-Future 적용

이 개념을 그대로 참고하면 다음과 같다.

| Autoware 계층 개념 | EGPU-Future 대응 |
|---|---|
| Linux high-compute planning/perception | eGPU big model |
| safety-critical processor | comma four + panda safety/guardian |
| trajectory validator | independent action/trajectory validator |
| shadow mode | small/big dual model comparison |
| MRM | small model fallback 또는 safe disengagement |

**현재 조사한 여러 프로젝트 중 EGPU-Future의 hardware reality에 가장 적합한 안전 구조는 이 mixed-criticality 방식이다.**

---

# 8. Apollo: 모듈식 architecture가 아직 가치 있는 이유

Apollo는 전통적인 다음 분리를 명확하게 보여준다.

```text
Perception
   ↓
Prediction
   ↓
Routing / Planning
   ↓
Control
   ↓
CANBus
```

end-to-end 모델은 모듈 간 hand-crafted interface를 줄이는 장점이 있지만, 장애 분석이 어려워진다.

EGPU-Future는 driving policy 자체는 end-to-end로 가더라도 **관측·진단·safety interface는 모듈형**으로 유지하는 것이 좋다.

즉:

> end-to-end intelligence + modular observability

이 조합이 필요하다.

---

# 9. NVIDIA DRIVE가 보여주는 또 다른 교훈

NVIDIA DRIVE Hyperion 10은 두 개의 DRIVE AGX Thor와 14 cameras, 9 radars, 1 lidar, 12 ultrasonics 등을 하나의 자동차용 reference platform으로 통합하고 ASIL-D capable 구성을 내세운다.

이 비교의 목적은 Chestnut과 TOPS 숫자를 단순 비교하는 데 있지 않다.

중요한 차이는 다음이다.

- NVIDIA DRIVE는 처음부터 automotive power/thermal/network/sensor integration을 전제로 설계
- desktop RX 9060 + Chestnut은 매우 저렴하고 유연하지만 자동차용 subsystem 설계는 사용자가 추가로 해결해야 함

따라서 "GPU 연산량이 Tesla/고급 AV와 비슷하다"와 "자동차 시스템 전체가 같은 수준이다"는 완전히 다른 주장이다.

---

# 10. EGPU-Future가 채택해야 할 V2 architecture

## 10.1 4개 Plane으로 분리

### Plane A — Sensor/Data Plane

- comma road camera
- comma wide road camera
- driver monitoring
- carState/CAN
- radar if supported/available
- GPS/IMU
- 장기적으로 optional side/rear sensors

### Plane B — Intelligence Plane (eGPU)

- large driving model
- temporal context
- scene semantics
- possible world model
- uncertainty / disagreement output

### Plane C — Guardian/Safety Plane (comma four)

- eGPU health
- deadline monitoring
- power/thermal monitoring
- action freshness
- vehicle actuator envelope
- small model fallback
- DMS

### Plane D — Learning/Evaluation Plane

- route mining
- hard-case extraction
- small-vs-big disagreement
- closed-loop replay
- world-model scenario generation
- teacher/student distillation

---

# 11. 가장 중요한 개발 우선순위

## Priority 0 — ODD부터 고정

목표를 섞지 않는다.

### Stage A: Supervised L2 Excellence

목표:

- 고속도로
- 일반도로 curve
- cut-in
- 정체 출발
- lead handling
- 공사구간 인지
- 운전자 상시 감독

현재 센서·차량 제어 한계 내에서 가장 빨리 현실화 가능하다.

### Stage B: Route-aware L2+

추가 필요:

- richer route/context
- lane-change/merge reasoning
- side/rear sensing 또는 OEM sensor access 확대
- 더 강한 safety validator

### Stage C: Eyes-off / L3+

이 단계부터는 단순 eGPU upgrade 프로젝트가 아니다.

필요 요소:

- sensor redundancy
- actuation redundancy/diagnostics
- minimal-risk strategy
- functional safety engineering
- 훨씬 큰 validation scope

EGPU-Future의 당장 목표는 **Stage A를 매우 강하게 만드는 것**으로 잡는 것이 타당하다.

---

# 12. 우리가 실제로 가져와야 하는 기능

## 단기

1. `dual_model_runner`
2. `model_disagreement_logger`
3. `end_to_end_latency_profiler`
4. `chestnut_health_monitor`
5. `scenario_miner`
6. `fallback/recovery state machine`

## 중기

7. `trajectory/action validator`
8. uncertainty / confidence proxy
9. big-model teacher dataset generation
10. small-model distillation evaluator
11. replay + closed-loop simulation

## 장기

12. generative world model evaluation
13. optional side/rear sensor gateway
14. independent secondary perception for selected safety-critical situations
15. route-aware urban driving policy

---

# 13. 무엇을 하지 말아야 하는가

1. **GPU 성능 증가 = 자율주행 레벨 상승**으로 간주하지 않는다.
2. OEM steering torque/rate 제한을 safety 검증 없이 우회하지 않는다.
3. big model output을 검증 없이 CAN actuator로 직결하지 않는다.
4. Tesla HW4와 연산량 숫자만 비교해 시스템 동등성을 주장하지 않는다.
5. 카메라가 보지 못하는 side/rear scene을 model parameter로 해결하려 하지 않는다.
6. 큰 모델만 개발하고 simulation/replay/telemetry를 후순위로 미루지 않는다.

---

# 14. 최종 판단

Tesla가 EGPU-Future에 주는 가장 큰 힌트는 "카메라만 사용한다"가 아니다.

**가장 중요한 힌트는 `fleet data → large model → distillation → lower-compute fleet → more data`라는 학습 폐루프다.**

Waymo가 주는 힌트는 **실차 성능 못지않게 simulation과 redundancy가 중요하다**는 점이다.

Mobileye와 Autoware가 주는 힌트는 **AI의 지능과 safety-critical execution을 분리하라**는 것이다.

따라서 EGPU-Future의 장기 구조는 다음 한 줄로 요약된다.

> **Tesla/Wayve식 학습형 지능 + Waymo식 simulation + Mobileye/Autoware식 독립 안전 계층 + openpilot의 retrofit/open-source 장점을 결합한다.**

---

# 15. 주요 출처

## comma / openpilot

- Chestnut launch: https://blog.comma.ai/chestnut/
- Chestnut product/setup: https://comma.ai/shop/chestnut
- openpilot: https://comma.ai/openpilot
- comma four: https://blog.comma.ai/comma-four/
- openpilot release notes: https://github.com/commaai/openpilot/blob/master/RELEASES.md
- openpilot logging/cameras: https://github.com/commaai/openpilot/blob/master/docs/concepts/logs.md
- current modeld: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/modeld.py

## Tesla

- Tesla FSD evidence dashboard: https://www.tesla.com/fsd-evidence-dashboard
- Tesla Q2 2026 Update / SEC exhibit: https://ir.tesla.com/_flysystem/s3/sec/000162828026049213/tsla-20260722-gen.pdf

## Waymo

- 6th generation Driver: https://waymo.com/blog/2026/02/ro-on-6th-gen-waymo-driver/
- Waymo Driver sensing: https://waymo.com/waymo-driver/
- 10 AI lessons / 200M+ autonomous miles: https://waymo.com/blog/2026/08/10ailessons/
- Waymo World Model: https://waymo.com/blog/2026/02/the-waymo-world-model-a-new-frontier-for-autonomous-driving-simulation/

## Wayve

- Wayve technology / AV2.0: https://wayve.ai/technology/
- GAIA-3: https://wayve.ai/press/wayve-launches-gaia3/

## Mobileye

- Product spectrum: https://www.mobileye.com/products/
- RSS: https://www.mobileye.com/blog/responsibility-sensitive-safety-unwritten-rules-of-the-road/
- 2025 Form 10-K: https://www.sec.gov/Archives/edgar/data/1910139/000110465926014300/mbly-20251227x10k.htm

## Autoware / Open AD Kit

- Open AD Kit: https://github.com/autowarefoundation/openadkit
- Autoware 1.8.0 release: https://github.com/orgs/autowarefoundation/discussions/7095
- Trajectory Validator: https://autowarefoundation.github.io/autoware_universe/latest/planning/autoware_trajectory_validator/

## Apollo

- Apollo repository: https://github.com/ApolloAuto/apollo
- Apollo software architecture: https://github.com/ApolloAuto/apollo/blob/master/docs/14_Others/Apollo_5.5_Software_Architecture.md

## NVIDIA

- DRIVE Hyperion: https://www.nvidia.com/en-us/solutions/autonomous-vehicles/drive-hyperion/

---

Last reviewed: 2026-09-07
