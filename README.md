# EGPU-Future

comma 4 + Chestnut/eGPU 이후의 openpilot 계열 자율주행 발전 방향을 조사·분석하는 저장소입니다.

이 저장소의 목표는 단순히 "GPU를 달아 openpilot을 빠르게 만드는 것"이 아닙니다.

**더 큰 driving/world model을 실차에서 사용할 수 있게 된 이후, 센서·학습·안전·전원·열·통신·fallback까지 포함한 vehicle-integrated autonomy architecture를 설계하는 것**을 목표로 합니다.

---

## 핵심 결론

**eGPU의 가장 큰 가치는 FPS 향상이 아니라, 지금까지 comma 4의 약 10 W급 온디바이스 연산 한계 때문에 사용할 수 없었던 훨씬 큰 driving/world model을 실차에서 실행하고, 그 big model을 전체 openpilot 생태계의 teacher/evaluator로 활용할 수 있다는 점입니다.**

따라서 바람직한 방향은 comma 4를 버리고 eGPU가 모든 것을 담당하게 하는 구조가 아닙니다.

- **comma 4 / Guardian:** 카메라 입력, 차량 인터페이스, 상태 추정, DMS, health/deadline 감시, small-model fallback
- **eGPU / Intelligence:** large driving model, temporal context, scene reasoning, 향후 world model
- **Safety Validator:** big-model output과 실제 vehicle command 사이의 독립 제약 계층
- **Learning Plane:** small/big disagreement, hard-case mining, replay/simulation, teacher→student distillation
- **차량 제어:** 기존 차량별 actuator 한계와 panda/openpilot safety constraint 유지

이 구조를 **Guardian + Intelligence Sidecar**라고 부릅니다.

---

# 왜 지금 eGPU인가

comma.ai는 2026-08-12 Chestnut을 공개하면서 다음을 발표했습니다.

- comma four와 외장 desktop GPU를 연결하는 compute upgrade
- 기존 on-device model 대비 약 30배 parameters, 약 100배 FLOPs
- comma four + Chestnut compute를 Tesla HW4와 유사하다고 설명
- Ready-to-Drive 구성은 AMD Radeon RX 9060 8GB
- GPU를 passenger footwell 또는 passenger seat 아래에 설치하고 vehicle 12 V power를 사용

### 정확성 메모

Chestnut launch blog는 모델을 **"1B parameter"**라고 소개하지만 현재 openpilot 0.11.2 공식 `RELEASES.md`는 **"Big model with 880M parameters"**라고 명시합니다.

따라서 이 저장소에서는 **1B급 모델(공식 release-note 정확값 880M)**로 취급합니다.

또한 comma.ai의 "Tesla HW4와 유사한 compute" 표현은 compute 비교이지 Tesla 차량 전체 센서·전원·제어·안전 architecture와 동등하다는 독립 검증 결과가 아닙니다.

---

# 다른 자율주행 프로젝트에서 얻은 결론

| 프로젝트 | 핵심 접근 | EGPU-Future가 가져올 부분 |
|---|---|---|
| Tesla FSD | fleet data + end-to-end + factory-integrated surround vision | big→small distillation, fleet learning loop |
| Wayve | end-to-end Embodied AI / foundation model | generalizable driving model, large evaluator/world model |
| Waymo | camera+lidar+radar redundancy + HD-map prior + simulation | world-model validation, long-tail scenario simulation |
| Mobileye | True Redundancy + RSS + 단계적 compute/sensor 확대 | independent safety envelope |
| Autoware | modular validation + shadow mode + mixed criticality | eGPU와 safety-critical guardian 분리 |
| Apollo | perception/prediction/planning/control 모듈화 | observability와 fault localization |
| NVIDIA DRIVE | automotive-grade high-compute + multimodal sensors + safety platform | compute보다 system integration이 중요하다는 교훈 |

상세 비교: [자율주행 아키텍처 비교와 EGPU-Future 적용 방향](docs/AUTONOMY_ARCHITECTURE_COMPARISON_KR.md)

---

# Tesla와 openpilot의 가장 중요한 차이

Tesla는 factory-integrated vehicle architecture에서 8개의 외부 카메라와 자체 inference hardware, 차량 전체 control/data pipeline을 통합합니다.

openpilot은 기존 차량의 CAN network와 OEM ADAS가 허용하는 steering/brake/acceleration interface를 활용하는 retrofit 시스템입니다.

또한 comma four 상품 설명의 "360° vision" 표현과 Tesla의 **8 external camera surround sensing**을 같은 것으로 보면 안 됩니다. openpilot이 기록하는 camera stream은 road, wide-road, driver camera로 정의돼 있습니다.

따라서:

> **eGPU는 두뇌를 크게 만들지만, 센서가 보지 못하는 side/rear 정보를 새로 만들지는 않습니다.**

장기적으로 L3+를 목표로 한다면 compute 증설과 별도로 sensor/actuation redundancy roadmap이 필요합니다.

---

# Tesla에서 특히 중요한 힌트: Distillation

Tesla는 2026 Q2 자료에서 AI3용 FSD v14 lite가 **AI4 v14 series의 driving behavior를 AI3 camera/compute configuration으로 distill**한다고 직접 설명했습니다.

이는 EGPU-Future의 가장 중요한 장기 방향과 일치합니다.

```text
Chestnut Big Model
      │
      ├─ hard-case discovery
      ├─ teacher labels / behavior
      ├─ disagreement mining
      ▼
comma-four Small Model
      │
      ▼
전체 일반 openpilot fleet 개선
```

즉 Chestnut 장착 차량의 가치가 장착 차량만의 성능 향상에 그치지 않도록 해야 합니다.

---

# 차량 전원·열·소음 문제

Ready-to-Drive의 RX 9060은 AMD 공식 기준 **132 W Typical Board Power**입니다.

단순 계산상:

- 12 V에서 GPU만 이상적으로 약 **11.0 A**
- 90% conversion efficiency를 가정하면 약 **12.2 A**
- 연구차량용 180 W system budget을 가정하면 12 V / 90%에서 약 **16.7 A**

180 W는 comma 공식 요구사항이 아니라 overhead와 margin을 포함하기 위한 EGPU-Future의 초기 설계 기준입니다.

따라서 장기 연구차량에서는 cigarette lighter만을 전제로 하기보다 다음을 검토합니다.

```text
Vehicle low-voltage bus
   → source-side fuse
   → reverse-polarity / transient protection
   → automotive wide-input DC/DC
   → ignition/ACC controlled enable
   → low-voltage cutoff
   → voltage/current telemetry
   → Chestnut + GPU
```

실제 차량별 outlet fuse/rating과 배선 허용전류는 반드시 별도 확인하며 OEM wiring보다 fuse만 크게 변경하지 않습니다.

상세 설계: [차량용 eGPU 전원·발열·소음·신뢰성 통합 설계](docs/VEHICLE_EGPU_POWER_THERMAL_INTEGRATION_KR.md)

---

# 발열·팬소음은 software로도 줄일 수 있음

추가 소스 분석 결과, `tinygrad` AMD SMU 구현에는 실제 GPU PPT를 바꾸는 `set_power_limit(watts)`가 존재합니다.

현재 openpilot Chestnut code는 power limit을 telemetry로 읽지만 조사한 master code에서는 이 기능을 closed-loop thermal/noise control에 적극 사용하지 않습니다.

따라서 EGPU-Future에서는 다음 실험이 가능합니다.

```text
Default GPU PPT
   ↓ 10 W step sweep
GPU power / temperature / fan RPM 측정
   +
p95/p99 model latency / frame drop 측정
   ↓
20 Hz deadline을 안정적으로 만족하는
가장 낮은 GPU power point 선택
```

현재 model loop는 20 Hz이므로 nominal period는 50 ms입니다. 초기 연구 기준으로 p99 model execution을 40 ms 이하로 두는 등 margin을 적용해 볼 수 있으나, 이는 공식 openpilot 기준이 아니라 실제 end-to-end 측정으로 수정할 연구값입니다.

상세 설계: [Chestnut Adaptive Power / Thermal / Noise Control](docs/CHESTNUT_POWER_THERMAL_CONTROL_DESIGN_KR.md)

---

# 현재 openpilot에 이미 있는 Chestnut health telemetry

현재 master에는 다음이 이미 존재합니다.

- GPU hotspot temperature
- memory temperature
- GPU power draw / power limit
- GPU usage / clock
- fan RPM
- PCIe state
- supply voltage / current / fault

현재 Chestnut status code에는:

- GPU temp limit: **100 °C**
- memory temp limit: **95 °C**
- hysteresis: **5 °C**

도 구현되어 있습니다.

따라서 새 하드웨어 센서를 먼저 만드는 것보다 이 데이터를 **proactive de-rate / health policy / retry / route analytics**에 연결하는 것이 우선입니다.

---

# 전원 문제는 이미 실사용에서 나타나고 있음

openpilot issue #38685에는 Hyundai Sonata remote start 시 cigarette lighter가 powered되지 않아 GPU가 무전원 상태이고 big model load가 timeout되는 사례가 보고돼 있습니다.

현재 openpilot에는 big model exception 발생 시 small model fallback이 이미 구현되어 있지만, 같은 drive cycle에서 eGPU power가 나중에 복원됐을 때 자동으로 big model을 다시 살리는 완전한 hot-recovery state machine은 현재 조사한 코드에서 확인되지 않았습니다.

따라서 우선 구현 후보는:

```text
DISCONNECTED
 → POWER_WAIT
 → USB_READY
 → PCIE_READY
 → MODEL_WARMUP
 → ACTIVE
 → DERATED / FALLBACK
 → RETRY_WAIT
 → safe hot-retry
```

입니다.

---

# 이 저장소에서 우선 검증할 연구 과제

1. **Dual-model shadow runner** — small/big model 동일 route 동시 추론
2. **Disagreement logger** — 두 model 판단이 달라진 hard case 자동 저장
3. **Latency observability** — camera → preprocess → USB → eGPU → action end-to-end latency
4. **Chestnut health recorder** — voltage/current/temp/power/fan/PCIe/USB 연속 기록
5. **Adaptive PPT controller** — model deadline을 만족하는 최소 안정 전력점 탐색
6. **Recovery state machine** — late power, GPU reset, USB reconnect 후 안전한 retry
7. **Scenario evaluator** — 급곡선, cut-in, 정체출발, cone, lane merge, lead lost/acquired
8. **Independent action/trajectory validator** — eGPU output의 vehicle feasibility 검증
9. **Fallback validation** — eGPU fault 시 small model 전환의 연속성과 안정성 검증
10. **Teacher/student pipeline** — big model behavior를 small model 개선에 활용
11. **World-model evaluation** — long-tail 상황을 replay/generative simulation에서 반복 검증

---

# 개발 단계

## Stage A — Supervised L2 Excellence

현재 센서/actuator 범위에서:

- highway/arterial stability
- curve
- cut-in
- lead behavior
- congestion
- construction/cones
- merge

성능과 reliability를 최대화합니다.

## Stage B — Route-aware L2+

- richer route context
- side/rear sensing 또는 OEM sensor access 확대
- stronger independent validator

## Stage C — L3+ 연구

이 단계부터는 eGPU만으로 해결할 수 없습니다.

- sensor redundancy
- actuation diagnostics/redundancy
- minimum-risk maneuver
- functional-safety level validation

이 필요합니다.

---

# 분석 문서

1. [EGPU 이후 자율주행 기술방향 종합분석](docs/EGPU_AUTONOMY_STRATEGY_KR.md)
2. [Tesla·Waymo·Wayve·Mobileye·Autoware 등 자율주행 아키텍처 비교](docs/AUTONOMY_ARCHITECTURE_COMPARISON_KR.md)
3. [차량용 eGPU 전원·발열·팬소음·신뢰성 통합 설계](docs/VEHICLE_EGPU_POWER_THERMAL_INTEGRATION_KR.md)
4. [Chestnut Adaptive Power / Thermal / Noise Control 설계](docs/CHESTNUT_POWER_THERMAL_CONTROL_DESIGN_KR.md)

---

# 원칙

이 저장소의 목표는 차량의 OEM 조향/제동 한계나 openpilot safety constraint를 우회하는 것이 아닙니다.

연산 능력 확대는 actuator 권한 확대를 뜻하지 않습니다.

```text
Autonomy capability
  ≠ GPU FLOPS alone

Real-world capability
  = model intelligence
  × sensor coverage
  × latency reliability
  × power stability
  × thermal stability
  × actuator authority
  × safe fallback
```

---

# 주요 출처

- comma.ai Chestnut: https://blog.comma.ai/chestnut/
- Chestnut product/setup: https://comma.ai/shop/chestnut
- openpilot source: https://github.com/commaai/openpilot
- openpilot releases: https://github.com/commaai/openpilot/blob/master/RELEASES.md
- Tesla Q2 2026 Update: https://ir.tesla.com/_flysystem/s3/sec/000162828026049213/tsla-20260722-gen.pdf
- Tesla FSD evidence dashboard: https://www.tesla.com/fsd-evidence-dashboard
- Waymo 6th-gen Driver: https://waymo.com/blog/2026/02/ro-on-6th-gen-waymo-driver/
- Waymo World Model: https://waymo.com/blog/2026/02/the-waymo-world-model-a-new-frontier-for-autonomous-driving-simulation/
- Wayve technology: https://wayve.ai/technology/
- Mobileye products: https://www.mobileye.com/products/
- Autoware Open AD Kit: https://github.com/autowarefoundation/openadkit
- NVIDIA DRIVE Hyperion: https://www.nvidia.com/en-us/solutions/autonomous-vehicles/drive-hyperion/
- AMD RX 9060: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
- tinygrad AMD runtime: https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/support/am/ip.py
- TI automotive power/transient references: https://www.ti.com/tool/TIDA-01167
- comma.ai Reddit community: https://www.reddit.com/r/Comma_ai/

Last reviewed: 2026-09-07
