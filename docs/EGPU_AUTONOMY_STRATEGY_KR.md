# comma 4 + eGPU 이후 자율주행 기술방향 종합분석

작성일: 2026-09-07  
대상: comma four / openpilot / Chestnut-class model / tinygrad eGPU ecosystem

---

## 1. Executive Summary

### 결론

현재 comma 4의 가장 큰 구조적 제약은 **연산량**입니다. comma four는 comma 3X와 같은 Snapdragon 845 계열 compute를 사용하고, comma.ai는 오랫동안 약 10 W급 온디바이스 연산 안에서 driving model을 실행해 왔습니다. Chestnut은 이 한계를 깨기 위한 외장 GPU 구조이며, comma.ai는 첫 Chestnut-class 모델을 약 1B parameter, 기존 on-device model 대비 약 30배 parameter·100배 FLOPs로 설명합니다.

하지만 eGPU를 붙인다고 차량이 곧바로 Tesla FSD와 같은 기능 범위를 갖는 것은 아닙니다. 이유는 자율주행 성능이 다음 다섯 요소의 곱으로 결정되기 때문입니다.

1. 센서가 실제로 무엇을 볼 수 있는가
2. 모델이 그 정보를 얼마나 잘 이해하는가
3. 모델 추론이 충분히 빠르고 안정적인가
4. 차량이 실제로 어느 범위까지 조향·제동·가속 명령을 받아줄 수 있는가
5. 학습·검증·fallback 체계가 얼마나 잘 구축되어 있는가

따라서 eGPU 시대의 올바른 기술 방향은 **"더 큰 모델 하나로 모든 것을 해결"**이 아니라,

> **comma 4를 deterministic guardian으로 두고, eGPU를 high-capability intelligence sidecar로 붙이는 이중 구조**

입니다.

이 구조에서는 eGPU가 고난도 장면 이해와 대형 모델 추론을 담당하되, eGPU가 죽거나 지연되더라도 comma 4의 소형 모델 또는 안전한 disengagement가 남아 있어야 합니다.

---

# 2. 확인된 사실과 해석

## 2.1 comma four의 위치

### Fact

comma.ai의 현재 comma four 제품 페이지는 다음을 명시합니다.

- Processor: Qualcomm Snapdragon 845 MAX
- comma 3X와 동일한 compute, sensor suite, functionality
- 128 GB storage
- dual-cam 360° vision + narrow camera
- USB 3.1 Gen 2 port
- CAN FD 지원

출처: https://comma.ai/shop/comma-four

### Interpretation

comma four는 세대가 바뀌었지만 **연산 아키텍처를 근본적으로 새 세대로 교체한 장비가 아닙니다.**

따라서 comma 4 자체만으로는 모델을 무한정 확장할 수 없고, 모델 크기·입력 해상도·temporal context·multi-camera fusion을 키울수록 빠르게 연산 천장에 도달합니다.

---

# 3. Chestnut/eGPU가 실제로 바꾸는 것

## 3.1 공식 발표

comma.ai는 2026-08-12 Chestnut을 발표했습니다.

### Fact

- comma four의 compute upgrade
- desktop GPU 기반
- 첫 Chestnut-class driving model 약 1B parameter
- 최신 on-device model 대비 약 30x parameter
- 약 100x FLOPs
- Ready-to-Drive kit: AMD Radeon RX 9060 8GB
- comma four + Chestnut을 Tesla HW4와 비슷한 compute라고 설명

출처: https://blog.comma.ai/chestnut/

### 주의

"Tesla HW4와 유사"는 comma.ai 자체 표현이며, 이는 전체 센서 구성·안전 architecture·network bandwidth·software maturity까지 동등하다는 뜻이 아닙니다.

---

# 4. eGPU로 현실적으로 발전 가능한 영역

## 4.1 더 넓은 시야 입력

작은 모델은 제한된 입력 크기 때문에 camera frame 전체 정보를 충분히 쓰기 어렵습니다.

eGPU는 다음을 가능하게 합니다.

- wide camera 정보 확대
- narrow + wide 동시 처리 증가
- peripheral scene 반영
- 급곡선 진입 전 도로 구조 인식
- merge lane, exit lane, construction zone 등 넓은 context 이해

### 기대 효과

- sharp turn cutting 감소
- 공사 cone / temporary lane 이해 향상
- 옆 차로 차량의 cut-in intent 판단 향상
- 교차로 진입 전 scene understanding 개선

단, **GPU가 센서 자체 FOV를 넓혀 주는 것은 아닙니다.** 기존 카메라가 보지 못하는 영역은 여전히 보지 못합니다.

---

## 4.2 더 긴 temporal context

현재 driving model은 실시간 제약 때문에 과거 frame을 무한히 유지할 수 없습니다.

대형 모델에서는 다음이 가능해집니다.

- 수초~수십초 수준 scene memory 확대
- 앞 차량이 방금 brake light를 켰는지 기억
- lane merge가 진행 중인지 추적
- 곡률 변화 패턴 기억
- 교차로 접근 상황 기억
- 이전에 관측된 신호등/차선 구조 유지

### 핵심

자율주행은 단일 frame image recognition이 아니라 **시간에 따른 world state estimation** 문제입니다.

eGPU의 가치는 여기서 크게 나타날 가능성이 높습니다.

---

## 4.3 복잡한 장면의 semantic understanding

큰 모델은 작은 모델보다 다음 상황을 더 세밀하게 구분할 수 있습니다.

- cone이 차선을 막고 있는지 단순히 옆에 있는지
- parked car인지 traffic participant인지
- 전방 차량이 끼어들 준비 중인지
- 도로 가장자리인지 임시 차선인지
- 차선이 실제로 연결되는지 끊기는지
- 공사구간 worker / barrier / temporary marking 관계

Reddit에는 Chestnut-class model이 cone 주변에서 small model과 다른 trajectory를 보였다는 실사용/개발 공유가 있습니다.

참고: https://www.reddit.com/r/Comma_ai/

단, 커뮤니티 사례는 benchmark가 아니므로 일반화해서는 안 됩니다.

---

## 4.4 World Model 확장

openpilot 0.11은 learned simulator / World Model 기반 학습 방향을 크게 강화했습니다.

공식 설명에 따르면:

- World Model이 현재 observation과 action을 받아 future frame/action을 예측
- driving policy를 World Model 안에서 on-policy 방식으로 훈련
- classical simulator가 만들던 artifact를 줄이는 것이 목적

출처:
https://blog.comma.ai/011release/
https://blog.comma.ai/mlsim

### eGPU와의 결합 가능성

향후 eGPU는 단순한 perception model뿐 아니라 다음을 처리할 수 있습니다.

- 실시간 latent world state
- 여러 후보 trajectory rollout
- short-horizon world prediction
- uncertainty estimation
- alternate maneuver scoring

즉,

> "카메라 → 바로 steering"

에서

> "카메라 → world representation → 여러 행동의 미래 결과 추정 → 선택"

쪽으로 발전할 여지가 생깁니다.

---

# 5. eGPU가 해결하지 못하는 문제

## 5.1 차량 actuator 한계

가장 중요한 제한입니다.

GPU가 아무리 좋아도 차량이 허용하는 조향 torque, steering angle rate, brake control, longitudinal authority가 제한되면 그 이상은 할 수 없습니다.

예:

- OEM EPS torque limit
- low-speed steering restriction
- steering angle rate 제한
- 차량별 longitudinal control 지원 여부
- radar/ACC architecture 차이

따라서 **AI capability ≠ vehicle control capability**입니다.

---

## 5.2 센서 한계

현재 comma architecture는 카메라 중심입니다.

모델이 커져도 다음은 그대로입니다.

- 카메라가 가려짐
- 역광
- 폭우/폭설
- 오염
- 렌즈 glare
- physical blind spot

대형 모델이 robustness를 높일 수는 있으나 센서가 없는 정보를 생성할 수는 없습니다.

---

## 5.3 차량별 integration fragmentation

openpilot은 300+ 차량을 지원하지만 차량마다 CAN architecture, EPS, longitudinal control, radar behavior가 다릅니다.

따라서 대형 모델이 동일해도 실제 동작 품질은 차종별로 크게 다를 수 있습니다.

이 문제는 eGPU 성능으로 해결되지 않습니다.

---

# 6. 현재 openpilot 코드/시스템에서 보이는 문제점

아래는 공식 코드·이슈·comma.ai 자체 회고를 기준으로 정리한 것입니다.

---

## 6.1 Train-time / runtime mismatch

comma.ai는 2026년 7월 "Bugs that broke driving" 글에서 여러 번의 runtime/train preprocessing mismatch를 공개했습니다.

대표 사례:

- border padding 차이
- train runtime interpolation 차이
- cv2.BORDER_REPLICATE vs BORDER_CONSTANT
- nearest neighbor vs bilinear

출처: https://blog.comma.ai/driving-bugs/

### 문제의 본질

ML 모델 자체가 좋아도 입력 preprocessing이 training과 runtime에서 다르면 성능이 무너집니다.

### 제안

- preprocessing code single-source화
- training/inference transformation 동일 kernel 공유
- golden image regression test
- pixel-level equivalence CI

---

## 6.2 Delay estimation

현재 modeld 코드에는 actuator delay와 frame delay를 결합해 action timing을 맞추는 로직이 있습니다.

공개 코드에는 delay 관련 TODO가 남아 있고 과거 turn-cutting 관련 이슈도 있었습니다.

### 문제

조향은 모델 정확도보다 **latency compensation**이 더 중요할 수 있습니다.

특히 eGPU가 붙으면 다음 지연이 추가됩니다.

camera capture
→ preprocess
→ USB transfer
→ GPU enqueue
→ inference
→ output transfer
→ modeld
→ planner/control
→ CAN
→ EPS response

### 제안

고정 delay 상수가 아니라 runtime에서 실제 end-to-end latency를 continuously estimate해야 합니다.

---

## 6.3 Camera/frame synchronization

openpilot modeld는 main/extra camera frame timestamp를 맞추고 dropped frame을 추적합니다.

공개 코드에 frame sync error logging과 dropped-frame filtering이 존재합니다.

또한 comma four에서 60 FPS 미만 regression, stale UI frame 등의 이슈가 보고된 적이 있습니다.

참고:
https://github.com/commaai/openpilot/issues/37610
https://github.com/commaai/openpilot/issues/36887

### eGPU에서 더 중요해지는 이유

큰 모델은 frame 하나의 처리 시간이 길어지기 때문에 camera sync와 backpressure가 훨씬 민감해집니다.

---

## 6.4 eGPU 실패 처리

현재 공개 modeld 구조에는 big model inference exception 발생 시 small model로 fallback하는 로직이 있습니다.

이 방향 자체는 매우 중요합니다.

### 개선 필요점

현재와 같은 binary active/off 방식보다 다음이 필요합니다.

- timeout 분리
- GPU hang detection
- USB disconnect detection
- thermal fault
- power brownout
- memory allocation failure
- model compile/load failure

각 fault를 구분하는 explicit state machine이 필요합니다.

---

## 6.5 USB transport / model loading

tinygrad 공개 이슈에는 AMD USB interface에서 큰 JIT artifact load가 매우 느린 문제가 보고됐습니다.

예시 이슈에서는 50 MB JIT pickle load가 workstation에서 약 28초, comma four에서 약 108초까지 걸렸다고 보고했습니다.

출처:
https://github.com/tinygrad/tinygrad/issues/14851

### 의미

주행 중 inference throughput만 빠르다고 충분하지 않습니다.

- boot time
- GPU init
- model load
- reconnect
- failover

이 모두 사용자 체감 reliability에 영향을 줍니다.

---

## 6.6 thermal / power 문제

comma four 자체는 0.11.1에서 thermal policy가 개선됐습니다.

comma.ai 공개 자료에서는 heat-soak 후 CPU/GPU temperature를 계측하고 thermal trip point를 조정했다고 설명합니다.

출처: https://blog.comma.ai/0111release/

Chestnut은 여기에 별도의 desktop-class GPU power/heat를 추가합니다.

커뮤니티에서는 다음 우려가 나타납니다.

- cigarette lighter power capacity
- summer cabin temperature
- under-seat airflow
- vibration
- USB/power cable reliability

이는 아직 community report가 많은 영역이므로 충분한 실차 데이터가 필요합니다.

---

## 6.7 GPS/EMI 가능성

Reddit StarPilot 개발자는 high-speed USB hardware와 GPS reception 간 간섭 우려를 언급하고 일부 차량에서 vehicle GPS 데이터를 대체 입력으로 사용했다고 공유했습니다.

참고:
https://www.reddit.com/r/Comma_ai/comments/1w6l7at/

### 주의

이것은 범용적인 Chestnut 결함으로 확인된 사실은 아닙니다.

하지만 automotive EMC 관점에서는 반드시 검증해야 할 리스크입니다.

---

# 7. comma four의 핵심 한계

## 7.1 Compute ceiling

가장 직접적인 한계입니다.

- Snapdragon 845 MAX
- phone-class compute architecture
- 약 10 W 수준 inference philosophy

작은 모델 최적화에는 매우 효율적이지만 1B+ model이나 고해상도 multi-camera model에는 부족합니다.

---

## 7.2 Memory bandwidth / memory capacity

큰 모델에서는 FLOPs뿐 아니라 memory bandwidth와 tensor movement가 병목이 됩니다.

따라서 eGPU를 붙여도 comma 4 ↔ eGPU transport가 새로운 bottleneck이 될 수 있습니다.

---

## 7.3 USB dependency

Chestnut architecture는 external GPU link에 의존합니다.

이 때문에 internal PCIe-connected automotive SoC보다 다음 위험이 늘어납니다.

- connector fault
- cable fault
- hotplug
- power sequencing
- USB reset
- bandwidth contention

---

## 7.4 Automotive packaging

comma four는 windshield device로 설계됐지만 desktop GPU는 본래 자동차 cabin의 vibration, dust, thermal cycling을 전제로 한 제품이 아닙니다.

따라서 장기적으로는 Chestnut이 과도기 architecture가 될 가능성이 높습니다.

---

# 8. 내가 제안하는 미래 구조

## Guardian + Intelligence Sidecar Architecture

```text
            Cameras / IMU / CAN
                    |
                    v
            +---------------+
            |   comma four  |
            |---------------|
            | Sensor ingest |
            | Calibration   |
            | Vehicle state |
            | Safety checks |
            | Small model   |
            +-------+-------+
                    |
             high-speed link
                    |
                    v
            +---------------+
            |     eGPU      |
            |---------------|
            | Big vision    |
            | World model   |
            | Temporal mem  |
            | Big policy    |
            +-------+-------+
                    |
                    v
            +---------------+
            | Arbitration   |
            | disagreement  |
            | watchdog      |
            +-------+-------+
                    |
                    v
             vehicle control
```

### 핵심 원칙

1. eGPU는 없어도 시스템이 최소 기능으로 살아 있어야 한다.
2. eGPU 결과는 deadline 안에 도착할 때만 사용한다.
3. small model과 big model disagreement를 항상 기록한다.
4. actuator safety constraint는 model 외부에 둔다.
5. eGPU hardware fault가 CAN safety layer까지 전파되면 안 된다.

---

# 9. 가장 먼저 개발해야 할 기능

## 9.1 Dual inference

small model과 big model을 동시에 실행합니다.

저장할 항목:

- predicted path
- acceleration
- lead estimate
- lane change intent
- confidence
- latency
- GPU temperature
- dropped frame
- disengagement

### 목적

큰 모델이 실제로 어디서 더 좋은지 객관적으로 확인합니다.

---

## 9.2 Disagreement detector

예:

```text
small path curvature = A
big path curvature   = B
|A-B| > threshold
=> disagreement event
```

이 이벤트를 자동 저장하면 사람이 수백 시간 영상을 볼 필요가 없습니다.

---

## 9.3 Scenario mining

자동 분류할 scenario:

- standstill
- lead acquired
- lead lost
- cut-in
- cut-out
- merge
- sharp curve
- construction cone
- narrow road
- unprotected turn
- traffic light approach
- stop sign approach
- parked-car avoidance
- sudden brake

---

## 9.4 Latency budget

권장 metric:

| Stage | Metric |
|---|---|
| camera | capture timestamp |
| preprocessing | warp duration |
| USB H2D | transfer time |
| GPU | queue + inference |
| USB D2H | return time |
| modeld | decode time |
| control | command issue |
| actuator | response delay |

최종적으로 **camera photon → actuator response**에 가까운 end-to-end delay를 추적해야 합니다.

---

# 10. eGPU로 가장 유망한 기능 순위

## Tier 1 — 바로 효과가 기대되는 것

1. 큰 driving model
2. wider FOV utilization
3. longer temporal context
4. construction / cone / parked car handling
5. complex cut-in / merge interpretation

## Tier 2 — 중기

1. scene memory
2. short-horizon world prediction
3. multiple trajectory rollout
4. uncertainty model
5. teacher/student distillation

## Tier 3 — 장기

1. route-conditioned driving
2. intersection reasoning
3. richer semantic interaction
4. VLM-assisted offline scenario labeling
5. fleet-learned hard-case retrieval

---

# 11. VLM을 실시간 steering model로 바로 쓰지 않는 이유

대형 VLM은 scene description에는 강하지만 deterministic control loop에는 다음 문제가 있습니다.

- latency
- output variability
- temporal jitter
- difficult certification
- structured trajectory output 부족

따라서 초기에는 VLM을 다음 용도로 쓰는 것이 더 현실적입니다.

- offline labeling
- scenario classification
- failure explanation
- rare-event mining
- driving model teacher

실시간 steering path 자체는 specialized driving policy가 담당하는 편이 좋습니다.

---

# 12. Big model → Small model distillation

Chestnut의 가장 중요한 장기 가치 중 하나입니다.

### 구조

```text
Big model on eGPU
      |
      | teacher output
      v
fleet disagreement dataset
      |
      v
small model retraining
      |
      v
comma four standalone improvement
```

이 구조에서는 eGPU를 가진 차량이 전체 fleet의 teacher 역할을 할 수 있습니다.

즉, Chestnut을 사지 않은 사용자도 장기적으로 이익을 받을 수 있습니다.

---

# 13. Safety 관점

## 반드시 유지할 것

- CAN safety constraint
- actuator limit
- driver monitoring
- watchdog
- model deadline
- disengagement path

## 절대 피해야 할 것

- "큰 모델이니까 safety check 생략"
- eGPU 연결만으로 steering torque limit 완화
- single model confidence만 믿고 redundancy 제거
- USB disconnect를 단순 software error로 취급

---

# 14. 실제 개발 Roadmap

## Phase 0 — Baseline

목표: 현재 comma four/small model 동작을 수치화

- route logging
- latency logging
- scenario extraction
- disengagement tagging

완료 조건:

- 동일 route 재현 가능
- baseline metric 확보

---

## Phase 1 — eGPU Observability

목표: Chestnut link 안정성 측정

- GPU init time
- model load time
- inference FPS
- p50/p95/p99 latency
- USB reconnect
- temperature
- power loss

완료 조건:

- 2시간 이상 연속 test
- no silent failure

---

## Phase 2 — Shadow Big Model

목표: 차량 제어에는 small model을 사용하면서 big model을 동시에 실행

- output logging
- disagreement mining
- scenario scoring

완료 조건:

- 최소 수십~수백 route comparison
- hard case 자동 추출

---

## Phase 3 — Controlled Arbitration

목표: 제한된 조건에서 big model path를 사용

초기 조건 예:

- highway only
- clear weather
- stable GPU
- latency under threshold
- no thermal warning

완료 조건:

- fallback test 통과
- fault injection test 통과

---

## Phase 4 — Expanded Autonomy

- wider scene
- urban
- construction
- intersection approach
- richer long control

단, 이 단계부터는 데이터·학습·안전 검증 비용이 급격히 증가합니다.

---

# 15. 평가 지표

단순 disengagement count만 보면 안 됩니다.

권장 지표:

### Driving quality

- lateral jerk
- longitudinal jerk
- lane center error
- path curvature smoothness
- speed convergence
- lead response delay

### Model quality

- small/big disagreement
- confidence calibration
- scene-conditioned failure rate

### System quality

- dropped frames
- inference deadline miss
- GPU reset count
- USB retry count
- thermal throttle
- model fallback count

### Human interaction

- driver override
- brake override
- steering override
- manual disengagement

---

# 16. 내가 보는 가장 큰 기술적 기회

### 1위: Temporal intelligence

큰 모델의 가장 중요한 발전은 object detection 정확도보다 **"조금 전부터 무엇이 벌어지고 있었는지"를 기억하는 능력**일 가능성이 높습니다.

### 2위: World-model planning

단일 trajectory를 바로 예측하는 대신 여러 행동의 결과를 짧게라도 simulation할 수 있다면 복잡 장면에서 큰 발전이 가능합니다.

### 3위: Fleet teacher

Chestnut vehicle에서 얻은 big-model output을 small-model distillation에 쓰면 전체 ecosystem이 발전할 수 있습니다.

### 4위: automated failure mining

모델을 키우는 것보다 더 중요한 것은 **어디서 틀렸는지 자동으로 찾는 시스템**입니다.

comma.ai의 자체 회고에서도 실제 개선의 상당 부분은 화려한 알고리즘보다 bug discovery/fix에서 왔다고 설명합니다.

출처: https://blog.comma.ai/driving-bugs/

---

# 17. 가장 큰 위험

1. 큰 모델이 좋아졌다는 인상만 있고 정량 metric이 없는 것
2. eGPU latency spike
3. USB/power reliability
4. thermal derating
5. train/runtime mismatch
6. big model regression
7. vehicle-specific actuator limitation 무시
8. fallback path가 실제로 테스트되지 않은 것

---

# 18. 장기적인 미래 모습

내 판단으로 Chestnut은 최종 형태라기보다 **transition architecture**에 가깝습니다.

향후 이상적인 hardware는 다음과 같을 가능성이 높습니다.

- comma four 수준의 센서 front-end
- 자동차용 high-performance AI accelerator
- 더 큰 memory
- high-bandwidth internal interconnect
- automotive thermal design
- power management integration
- redundant compute path

즉 지금은

```text
comma four + USB + desktop GPU
```

이지만 장기적으로는

```text
integrated automotive AI compute
```

쪽으로 가는 것이 더 자연스럽습니다.

Chestnut은 그 전에 **"큰 모델을 실제 fleet에 먼저 배치하여 software/data scaling을 검증하는 실험 플랫폼"** 역할을 할 가능성이 큽니다.

---

# 19. 최종 방향 제안

## 추천 방향

### A. 단기

**성능 향상보다 측정 체계부터 만든다.**

- dual inference
- disagreement logging
- end-to-end latency
- fault logging

### B. 중기

**big model을 teacher + high-capability planner로 쓴다.**

- hard-scene mining
- shadow evaluation
- selected-condition arbitration

### C. 장기

**World Model + temporal memory + multi-trajectory reasoning을 강화한다.**

### D. 계속 유지

**comma four small model을 fallback guardian으로 남긴다.**

---

# 20. 최종 한 문장

> **eGPU 시대의 openpilot 발전 방향은 "더 큰 신경망을 붙이는 것"이 아니라, comma four를 안전한 실시간 제어 플랫폼으로 유지하면서 eGPU를 장면 이해·시간 기억·World Model·고난도 planning을 담당하는 지능 계층으로 분리하고, 두 모델의 차이를 fleet 데이터로 학습시키는 구조로 가는 것이 가장 합리적이다.**

---

# Sources

## Official

- comma.ai — Introducing chestnut  
  https://blog.comma.ai/chestnut/

- comma.ai — openpilot 0.11  
  https://blog.comma.ai/011release/

- comma.ai — openpilot 0.11.1  
  https://blog.comma.ai/0111release/

- comma.ai — Bugs that broke driving  
  https://blog.comma.ai/driving-bugs/

- comma.ai — MLSim / Learning to Drive from a World Model  
  https://blog.comma.ai/mlsim

- comma four specifications  
  https://comma.ai/shop/comma-four

- openpilot repository  
  https://github.com/commaai/openpilot

- openpilot RELEASES.md  
  https://github.com/commaai/openpilot/blob/master/RELEASES.md

- modeld source  
  https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/modeld.py

## tinygrad

- Runtime documentation  
  https://github.com/tinygrad/tinygrad/blob/master/docs/runtime.md

- AMD runtime  
  https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/ops_amd.py

- USB JIT loading performance issue  
  https://github.com/tinygrad/tinygrad/issues/14851

## Community references

Community references are anecdotal and are not treated as controlled benchmarks.

- r/Comma_ai  
  https://www.reddit.com/r/Comma_ai/

- Chestnut introduction discussion  
  https://www.reddit.com/r/Comma_ai/comments/1vmtu41/

- eGPU setup / big model failure discussion  
  https://www.reddit.com/r/Comma_ai/comments/1vwoaze/

- StarPilot Chestnut / GPS discussion  
  https://www.reddit.com/r/Comma_ai/comments/1w6l7at/

---

Status: initial research baseline v1.0
