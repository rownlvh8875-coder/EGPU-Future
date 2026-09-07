# 차량용 eGPU 전원·발열·소음·신뢰성 통합 설계

작성일: 2026-09-07  
대상: comma four + Chestnut + AMD Radeon RX 9060 8GB 및 향후 외장 GPU 구성

> 이 문서는 `확인된 사실(Fact)`과 `EGPU-Future 설계 제안(Recommendation)`을 구분한다. 전기 배선·퓨즈·차량 저전압 계통 작업은 차량별 회로와 허용 전류가 다르므로 실제 차량 매뉴얼 및 자동차 전장 기준을 확인해야 한다. 고전압 traction battery에는 접근하지 않는다.

---

# 1. 결론

Chestnut의 가장 큰 실차 리스크는 GPU 연산 성능 자체보다 다음 5가지다.

1. **12 V 전원 용량과 ignition/remote-start sequencing**
2. **차량 전원 transient / cold crank / voltage drop**
3. **132 W급 열을 작은 실내 공간에서 지속적으로 배출하는 문제**
4. **GPU fan 및 구조 전달 소음**
5. **USB/PCIe/eGPU가 실패했을 때 안전하게 small model로 복귀하고 다시 회복하는 문제**

따라서 장기적으로 가장 좋은 구조는 다음이다.

```text
Vehicle 12 V / LV bus
        │
        ├─ fuse near source
        │
        ├─ reverse-polarity / load-dump / transient protection
        │
        ├─ wide-input automotive DC/DC or qualified power stage
        │
        ├─ ignition/ACC-controlled enable + low-voltage cutoff
        │
        └─ voltage/current telemetry
                  │
                  ▼
            Chestnut + GPU
                  │
          USB3/PCIe to comma four
                  │
                  ▼
     Power/Thermal/Link Health Manager
                  │
         ┌────────┴────────┐
         ▼                 ▼
    Big model ACTIVE   Small model FALLBACK
```

**Ready-to-Drive stock wiring은 빠른 도입에 적합하고, 장기 연구차량에서는 dedicated automotive-grade power path와 software recovery state machine이 더 적합하다.**

---

# 2. 현재 Chestnut 하드웨어에서 확인된 사실

## 2.1 공식 Ready-to-Drive 구성

comma.ai의 현재 Chestnut 상품 페이지 기준 Ready-to-Drive kit에는 다음이 포함된다.

- Chestnut
- AMD Radeon RX 9060 8GB
- 3 m USB3 cable
- 12 V car power cable
- mounting strips

공식 설치 안내는 GPU를 다음 위치에 설치하도록 제안한다.

- passenger footwell
- passenger seat 아래

그리고 **airflow 공간을 남기라고 명시**한다.

Chestnut launch blog는 차량 cigarette lighter에 전원을 연결하는 방식을 설명한다.

## 2.2 GPU의 정격 전력

AMD 공식 RX 9060 사양:

- Typical Board Power: **132 W**
- GDDR6: **8 GB**
- desktop PSU recommendation: 450 W

450 W PSU 권장값은 차량에서 GPU가 450 W를 사용한다는 의미가 아니다. GPU 자체 Typical Board Power가 132 W라는 점이 전원 계산에서 중요한 숫자다.

---

# 3. 132 W GPU가 차량 12 V 계통에서 의미하는 것

## 3.1 단순 전류 계산

GPU만 132 W를 사용한다고 가정하면:

```text
Ideal @ 12 V
I = P / V
  = 132 / 12
  = 11.0 A
```

DC/DC 포함 효율을 임의로 90%로 가정한 설계 계산:

```text
@ 12 V, 90% efficiency
I ≈ 132 / (12 × 0.90)
  ≈ 12.2 A

@ 14 V, 90% efficiency
I ≈ 132 / (14 × 0.90)
  ≈ 10.5 A
```

**주의:** 90%는 계산용 가정이며 Chestnut 공식 효율 수치가 아니다.

또한 실제 시스템에는 GPU 이외의 power stage/dock/손실이 존재하고 순간 부하 및 설계 margin이 필요하다.

## 3.2 EGPU-Future의 연구차량용 권장 설계 목표

### Recommendation

RX 9060 기반 연구차량에서 장기적으로 별도 전원 회로를 만든다면 **약 180 W급 이상의 continuous system budget**을 초기 설계 목표로 잡고 실제 측정으로 수정하는 것을 권장한다.

이는 comma.ai 공식 요구사항이 아니라 EGPU-Future의 engineering margin이다.

180 W를 12 V에서 90% 효율로 공급한다고 가정하면:

```text
I ≈ 180 / (12 × 0.90)
  ≈ 16.7 A
```

따라서 차량의 accessory socket이 해당 부하를 지속 공급할 수 있는지 **차량별 fuse/rating/owner manual로 반드시 확인**해야 한다.

### 절대 하면 안 되는 것

- 기존 cigarette lighter fuse가 부족하다고 더 큰 fuse만 꽂는 것
- OEM wire ampacity를 확인하지 않고 fuse를 상향하는 것
- traction battery에서 임의로 고전압을 인출하는 것

퓨즈는 GPU를 보호하기 위한 것이 아니라 **배선을 과전류/화재에서 보호하도록** 선정되어야 한다.

---

# 4. 실제로 이미 나타난 전원 sequencing 문제

## Fact — openpilot issue #38685

2026-08-22 공개된 openpilot issue에서는 Hyundai Sonata remote start 시 cigarette lighter가 켜지지 않아 GPU가 무전원 상태가 되고 big model load가 timeout되는 사례가 보고되었다.

이 사례는 중요한 시스템 설계 문제를 보여준다.

```text
vehicle ignition state ≠ accessory socket powered state
```

즉 openpilot이 "차량이 켜졌다"고 판단한 시점과 GPU power rail이 실제로 준비되는 시점이 반드시 같지는 않다.

현재 Chestnut status 코드에도 engine-crank voltage drop 가능성을 고려한 power-lost 경고 문구가 존재한다.

## 해결 방향

### Recommendation

Big-model startup을 단순한 boot-time one-shot으로 두지 않고 다음 조건을 확인해야 한다.

1. Chestnut USB detected
2. supply voltage stable
3. supply fault 없음
4. PCIe link stable
5. GPU telemetry valid
6. 일정 debounce 시간 통과
7. 그 후 model warm-up

전원이 늦게 들어오면 **전체 ignition cycle을 강제하지 않고 안전한 조건에서 eGPU를 재탐색·재초기화**할 수 있어야 한다.

---

# 5. 자동차의 12 V는 "깨끗한 12 V 전원공급기"가 아니다

## Fact

Texas Instruments의 automotive power reference 자료는 자동차 배터리 입력에서 다음을 별도 설계 대상으로 취급한다.

- load dump
- negative transients
- inrush
- cold crank / voltage dip
- reverse battery
- jump start
- overvoltage
- conducted/radiated EMI

TI는 ISO 7637-2 및 ISO 16750-2 조건을 고려한 battery-front-end reference design을 공개하고 있다.

따라서 desktop GPU를 차량에 넣을 때 단순 buck converter 하나만 보는 것은 부족하다.

## 권장 전원 Front-end

```text
12 V/LV source
   │
 [source fuse]
   │
 [reverse polarity protection]
   │
 [TVS / transient protection]
   │
 [inrush / eFuse / current limit]
   │
 [wide-Vin automotive DC/DC]
   │
 [output filtering]
   │
 Chestnut/GPU
```

실제 회로 부품 선정은 필요한 출력 전력과 차량에 맞춰 별도 설계해야 한다. TI의 10~30 W reference design을 180 W 시스템에 그대로 복사할 수는 없지만, **입력 보호 topology와 검증 항목**은 유효한 참고가 된다.

---

# 6. 권장 전원 구성 3안

## A안 — comma Ready-to-Drive 그대로

### 장점

- 가장 간단
- 공식 kit 기준
- 설치/탈거 쉬움
- 검증 시작에 적합

### 단점

- 차량 accessory socket rating 편차
- remote start/ACC sequencing 편차
- start-stop/cold crank 영향 가능
- socket/contact resistance의 차량별 편차

### 추천 용도

**초기 기능 검증 / 데이터 수집**

---

## B안 — Dedicated fused automotive LV feed — 권장

```text
Vehicle LV battery/bus
        │
   fuse near source
        │
 automotive input protection
        │
 high-power wide-input DC/DC
        │
 ignition/ACC enable
        │
 low-voltage cutoff
        │
 Chestnut/GPU
```

### 장점

- accessory socket 한계와 분리
- 전압 drop과 transient를 설계 단계에서 관리
- 전류 측정 및 fault logging 쉬움
- high-power GPU 확장에 적합

### 조건

- wire gauge와 fuse는 실제 cable length, insulation, ambient, routing, connector rating으로 산정
- source-side fuse를 전원원 가까이에 배치
- vehicle ground strategy 검토
- ACC/ignition은 큰 전류를 직접 흘리는 선이 아니라 power-stage enable/relay control용으로 사용
- parked 상태에서 starter battery를 방전시키지 않도록 low-voltage shutdown 필요

### 추천 용도

**장기 연구차량 / 매일 사용하는 차량 / 향후 160 W+ GPU 실험**

---

## C안 — DC→AC inverter + desktop PSU

기술적으로 가능하지만 기본안으로 권장하지 않는다.

```text
12 V DC → inverter AC → ATX PSU DC → GPU
```

변환 단계가 추가되어:

- conversion loss 증가
- 열 증가
- fan/noise 증가 가능
- 부품 수 증가
- shutdown/wake sequencing 복잡

따라서 bench test나 적절한 high-power DC solution이 없는 특수 상황을 제외하면 B안이 더 합리적이다.

---

# 7. EV / Hybrid에서 주의할 점

EV나 hybrid에서도 accessory electronics는 일반적으로 차량 low-voltage system을 통해 전원을 받지만 그 저전압 bus의 에너지는 onboard DC/DC 및 vehicle power-management에 의존한다.

따라서:

- OEM low-voltage auxiliary load allowance 확인
- sleep/wake strategy 확인
- parked 상태에서 차량을 깨우는 부하가 되지 않는지 확인
- 12 V/low-voltage battery SOC 영향 확인
- traction battery 직접 개조 금지

이 프로젝트의 eGPU는 **OEM high-voltage system에 직접 연결하는 방향으로 설계하지 않는다.**

---

# 8. 발열: 132 W는 실내에서 어느 정도인가

전기적으로 소비한 전력의 대부분은 결국 열이 된다.

RX 9060의 132 W TBP를 단순 열부하로 환산하면:

```text
132 W ≈ 450 BTU/h
```

180 W system budget이면:

```text
180 W ≈ 614 BTU/h
```

이는 자동차 HVAC 전체 용량과 비교하면 압도적이지 않지만, **GPU 주변의 수십 리터 이하 작은 정체 공기 공간**에는 큰 국부 열원이다.

문제는 차량 전체 평균 온도가 아니라 GPU inlet temperature와 hot-air recirculation이다.

---

# 9. 설치 위치별 열·소음 평가

## Passenger footwell

### 장점

- comma 공식 설치 위치
- cabin HVAC 공기를 활용하기 쉬움
- 접근성과 점검성 우수

### 위험

- 탑승자 발과 간섭
- 물/우산/먼지 노출
- 급정거·사고 시 단단히 고정되지 않은 GPU가 위험물체가 될 수 있음

### 개선

- passenger foot 공간과 완전히 분리된 bracket
- 전원/USB strain relief
- GPU intake를 cabin의 차가운 공기로 향하게 배치
- exhaust가 다시 intake로 돌아오지 않게 방향 분리

---

## Passenger seat 아래

### 장점

- 눈에 잘 보이지 않음
- 공식 허용 위치
- 일부 차량은 rear/under-seat HVAC airflow 활용 가능

### 위험

- seat rail 이동
- seat harness / airbag / occupancy wiring
- 카펫이 GPU intake를 막을 가능성
- 좁은 공간에서 뜨거운 exhaust recirculation

### 개선

- seat의 full travel을 실제로 시험
- rail, SRS, occupancy sensor wiring과 물리적으로 분리
- 바닥에서 GPU intake를 띄움
- intake와 exhaust 사이에 air path 확보

---

## Glovebox / sealed trim / spare-wheel well

기본적으로 권장하지 않는다.

밀폐 공간에 넣으면 팬 소음은 줄어들 수 있지만 열이 빠져나가지 못한다.

이 위치를 사용하려면 enclosure 자체보다 **덕트형 강제환기** 설계가 우선이다.

---

# 10. 팬 소음 대책

현재 comma Ready-to-Drive RX 9060의 정확한 board vendor 및 검증된 dBA acoustic 자료는 공식 페이지에서 확인되지 않았다. 따라서 "몇 dBA"라고 수치를 임의로 제시하지 않는다.

소음을 줄이는 우선순위는 다음이다.

## 1순위 — 발생 열을 줄인다

- model이 필요로 하는 최소 compute만 사용
- 가능한 경우 GPU power cap / clock policy 연구
- 불필요한 idle full-power 방지
- parked/offroad 시 GPU sleep/off

현재 openpilot master에서는 `powerLimitW`를 읽는 telemetry는 확인되지만, 조사한 코드에서는 PPT power limit을 능동적으로 설정하는 경로를 확인하지 못했다. 따라서 power cap은 별도 구현 및 AMD/tinygrad 검증이 필요하다.

## 2순위 — GPU inlet 온도를 낮춘다

fan RPM은 같은 workload에서도 inlet air가 뜨거우면 올라간다.

가장 실용적인 저소음 방법은:

```text
cool cabin air → GPU intake → GPU heatsink → exhaust away
```

이다.

GPU exhaust가 좁은 seat 아래에서 다시 intake로 돌아오는 recirculation을 막는 것이 중요하다.

## 3순위 — 큰 저속 fan을 보조로 사용

추가 fan이 필요하면 작은 고RPM blower보다 가능한 범위에서 큰 저RPM fan이 동일 airflow를 더 조용하게 만들 수 있다.

단, fan을 추가하기 전에 GPU 자체 온도/RPM 로그를 보고 실제 병목이 airflow인지 확인한다.

## 4순위 — 구조 전달 소음 차단

- bracket에 vibration-isolation element 사용
- thin plastic trim에 GPU fan 진동이 직접 전달되지 않게 함
- cable이 trim을 때리는 rattle 방지

## 5순위 — acoustic enclosure는 마지막

흡음재로 GPU를 둘러싸는 방식은 thermal runaway를 만들 수 있다.

필요하다면:

- ducted cool-air inlet
- ducted hot-air exhaust
- 충분한 cross-sectional area
- service access

가 확보된 enclosure만 검토한다.

---

# 11. 현재 openpilot Chestnut telemetry는 생각보다 잘 준비되어 있다

현재 `ChestnutState` schema에는 다음이 존재한다.

- `tempC`
- `memoryTempC`
- `powerDrawW`
- `powerLimitW`
- `gpuUsagePercent`
- `gpuClockMhz`
- `fanSpeedRpm`
- `pcieLtssm`
- `supplyVoltage`
- `supplyCurrent`
- `supplyFault`

즉 별도 외부 센서부터 붙이는 것보다 **기존 telemetry를 route log와 자동 분석에 활용하는 것**이 먼저다.

---

# 12. 현재 코드에 이미 있는 thermal/power 보호

`openpilot/system/hardware/chestnut/status.py` 현재 master 기준:

```text
GPU_TEMP_LIMIT    = 100 °C
MEMORY_TEMP_LIMIT = 95 °C
TEMP_HYSTERESIS   = 5 °C
```

또한:

- supply voltage
- supply fault
- PCIe link
- USB detection/speed
- power lost/restored

상태를 추적하고 alert를 생성한다.

### 중요

따라서 EGPU-Future가 "열센서부터 새로 만든다"는 방향은 중복이다.

필요한 것은 **이 telemetry를 proactive compute policy와 hot-recovery에 연결하는 것**이다.

---

# 13. 현재 big-model fallback의 장점과 부족한 부분

현재 `modeld.py`는 Chestnut big model 로딩을 시도하고, runtime exception이 발생하면 small model로 fallback하는 코드가 존재한다.

이는 중요한 안전 장점이다.

그러나 현재 loop에서 big model failure 후:

```text
ChestnutActive = False
model = small_model
```

로 전환되고, 같은 주행 cycle에서 big model을 자동으로 재초기화하는 hot-recovery state machine은 확인되지 않는다.

또한 current status alert 자체도 power 복구 후 ignition cycle을 안내한다.

### Recommendation

다음 state machine을 별도 구현/검증할 가치가 크다.

```text
DISCONNECTED
     ↓
POWER_WAIT
     ↓ stable voltage
USB_READY
     ↓
PCIE_READY
     ↓
MODEL_WARMUP
     ↓
ACTIVE
  │   │
  │   ├─ thermal/power/latency degradation → DERATED
  │   └─ hard fault → FALLBACK
  │
  └─────────────────────────────────────┐
                                        ▼
                                   SMALL_MODEL
                                        │
                                  RETRY_WAIT
                                        │
                   safe retry condition │
                                        ▼
                                  MODEL_WARMUP
```

### 초기 구현 원칙

운전 중 무조건 hot reload를 시도하지 않는다.

1차 버전에서는:

- vehicle standstill
- openpilot disengaged
- voltage stable
- thermal condition recovered

같은 보수적 조건에서 재초기화를 시작하는 편이 안전하다.

---

# 14. Thermal De-rate 정책 제안

현재 공식 hard overheat 기준을 임의 변경하는 대신, EGPU-Future는 **더 이른 soft policy**를 실험 데이터로 결정한다.

예시 개념:

```text
NORMAL
  ↓ sustained temperature / fan RPM rise
QUIET or THERMAL-DERATE
  - lower workload where technically possible
  - model rate/context/resolution policy experiment
  ↓ recovery
NORMAL

THERMAL-DERATE
  ↓ continued rise / deadline misses / fault
SMALL-MODEL FALLBACK
```

구체적인 soft threshold는 실차 측정 전 고정하지 않는다.

기록해야 할 관계:

- ambient/cabin temp
- GPU hotspot
- memory temp
- fan RPM
- power draw
- GPU clock
- inference latency
- frame drops
- model quality

이를 통해 "10 W 줄였을 때 몇 °C/몇 RPM/몇 ms가 바뀌는지"를 실제 데이터로 최적화해야 한다.

---

# 15. 더 저전력 GPU라는 선택지

AMD 현재 desktop spec에는 RX 9050이 92 W TBP로 기재되어 있어 RX 9060 132 W보다 낮다.

tinygrad의 AMD runtime은 RDNA3/RDNA4를 지원한다고 문서화돼 있다.

그러나 이것만으로 **RX 9050이 Chestnut openpilot big model의 요구 latency를 만족하고 공식적으로 호환된다고 확정할 수는 없다.**

따라서 저전력 GPU는 다음 순서로 평가한다.

1. enumerate/boot 가능 여부
2. model compile/load
3. full route inference latency
4. frame deadline
5. model output consistency
6. power draw
7. thermal/fan RPM

합격하면 "compute per watt"가 더 좋은 차량용 선택지가 될 수 있다.

### 판단

차량에서는 무조건 가장 빠른 GPU보다:

> required model deadline을 만족하는 가장 낮은 power GPU

가 더 좋은 제품일 가능성이 높다.

---

# 16. USB/PCIe와 EMI/GPS

## 확인된 사실

- Chestnut은 USB-to-PCIe 구조를 사용한다.
- tinygrad에는 USB AMD path에서 큰 JIT object load가 comma four에서 매우 느렸던 이슈가 실제로 존재했다.
- StarPilot 커뮤니티에서는 high-speed USB와 GPS reception 간섭 가능성을 우려해 vehicle GPS를 활용하는 interpreter를 만든 사례가 있다.

GPS 부분은 **커뮤니티 보고이지 Chestnut 전체의 공통 결함으로 검증된 것은 아니다.**

## Recommendation

- 가능한 한 양질의 shielded USB cable 사용
- GNSS antenna/coax와 USB3 cable을 장거리 평행 배선하지 않기
- DC/DC switching node와 GNSS/CAN harness 분리
- connector strain relief
- 설치 전/후 GNSS signal quality 비교
- ferrite/common-mode 대책은 USB signal integrity를 확인하면서 적용
- power converter 자체도 CISPR25 관점에서 EMI 검토

---

# 17. 진동·충격·물리적 고정

Desktop GPU는 본질적으로 자동차용 ruggedized ECU와 다르다.

연구차량에서 점검할 것:

- PCIe card와 Chestnut standoff 고정 상태
- 8-pin power connector strain
- USB connector strain
- 차량 진동 후 접촉불량
- seat 움직임과 cable pinch
- 발/우산/물/먼지 노출
- 급정거 시 assembly 이동 가능성

### Recommendation

장기 사용에는 단순 접착 strip 외에:

- rigid retention
- vibration isolation
- cable strain relief
- ventilation opening

을 함께 설계한 vehicle-specific bracket이 바람직하다.

단, seat rail과 SRS/airbag wiring을 침범해서는 안 된다.

---

# 18. 실제 검증 Test Matrix

## Power

- normal ignition
- remote start
- engine crank
- repeated start/stop
- idle → driving
- alternator charging transition
- accessory socket reconnect
- deliberate Chestnut power removal/recovery
- parked overnight battery drain

## Thermal

- HVAC on/off
- footwell installation
- under-seat installation
- summer hot-soak 후 시작
- 30/60/120 min continuous inference
- repeated stop-and-go

## Acoustic

- GPU idle
- small model
- big model steady state
- hot-soak big model
- HVAC low/medium/high
- driver ear position dBA 기록
- vibration/rattle subjective log

## Compute

- model load time
- inference average/p95/p99
- frame drop
- USB errors
- PCIe state
- fallback time
- recovery time

## Safety

- eGPU unplug while disengaged
- eGPU unplug while shadow mode
- supply brownout simulation on bench
- model NaN/error injection
- inference timeout injection
- thermal fault injection

실차 actuator control을 허용하기 전에 위 fault injection은 replay/simulator/shadow mode에서 먼저 수행한다.

---

# 19. 권장 로그 포맷

각 route에 다음을 동기화해서 저장한다.

```text
timestamp
vehicle_speed
engaged
scenario
small_model_latency_ms
big_model_latency_ms
small_big_disagreement
gpu_temp_c
gpu_memory_temp_c
gpu_power_w
gpu_limit_w
gpu_usage_pct
gpu_clock_mhz
gpu_fan_rpm
supply_voltage_mv
supply_current_ma
supply_fault
pcie_state
usb_link_errors
fallback_state
```

이 데이터가 모이면 "발열을 낮추기 위해 model을 얼마나 줄여야 하는가"를 감으로 결정하지 않고 최적화할 수 있다.

---

# 20. 차량용 eGPU의 추천 최종 형태

## V1 — 지금

```text
comma four
   │ USB3
Chestnut + RX9060
   │
OEM 12 V accessory source
```

용도: 기능 확인, big-model 효과 측정

## V2 — EGPU-Future 연구차량 권장형

```text
        vehicle LV bus
             │
      protected power unit
             │
      Chestnut + efficient GPU
             │
        ducted airflow
             │
    voltage/current/temp/fan logs
             │
     comma four Guardian
             │
 small/big shadow + safe fallback
```

## V3 — 장기 제품 형태

Desktop GPU card가 그대로 노출된 형태보다 다음이 더 이상적이다.

- lower-power GPU/accelerator
- custom automotive enclosure
- automotive DC/DC integrated
- controlled airflow
- fan/noise optimized
- lockable connectors
- dedicated health MCU
- side/rear sensor interface option

즉 Chestnut은 최종 제품의 완성형이라기보다 **openpilot이 cellphone-class compute에서 automotive high-compute architecture로 넘어가는 매우 중요한 실험 플랫폼**으로 보는 것이 타당하다.

---

# 21. 최종 설계 판단

eGPU 도입의 성공 여부는 TFLOPS가 아니라 다음 식에 가깝다.

```text
Real-world value
  = Model capability
  × Sensor coverage
  × Deadline reliability
  × Power stability
  × Thermal stability
  × Vehicle control authority
  × Safe fallback quality
```

하나라도 0에 가까우면 GPU가 아무리 빨라도 실차 자율주행 성능은 안정적으로 올라가지 않는다.

EGPU-Future는 따라서 **GPU benchmark 프로젝트가 아니라 vehicle-integrated autonomy compute project**로 설계해야 한다.

---

# 22. 주요 출처

## Chestnut / openpilot

- Chestnut launch: https://blog.comma.ai/chestnut/
- Chestnut product/setup: https://comma.ai/shop/chestnut
- Chestnut model power/thermal telemetry schema: https://github.com/commaai/openpilot/blob/master/openpilot/cereal/log.capnp
- Chestnut status/power/thermal logic: https://github.com/commaai/openpilot/blob/master/openpilot/system/hardware/chestnut/status.py
- Current modeld fallback: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/modeld.py
- Remote-start power issue #38685: https://github.com/commaai/openpilot/issues/38685

## GPU

- AMD Radeon RX 9060: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
- AMD graphics specifications incl. RX 9050: https://www.amd.com/en/products/specifications/graphics.html

## Automotive power

- TI automotive transient overview: https://www.ti.com/document-viewer/lit/html/SSZT243/GUID-6B969C6E-13D9-447A-B49D-35978B0D5882
- TI TIDA-01167 battery input protection: https://www.ti.com/tool/TIDA-01167
- TI TIDA-01179 wide-Vin/cold-crank reference: https://www.ti.com/tool/TIDA-01179
- TI TIDA-00699 transient/cold-crank/EMI reference: https://www.ti.com/tool/TIDA-00699

## USB/tinygrad/community evidence

- tinygrad AMD USB JIT loading issue #14851: https://github.com/tinygrad/tinygrad/issues/14851
- tinygrad runtime support: https://github.com/tinygrad/tinygrad/blob/master/docs/runtime.md
- StarPilot/Comma community GPS discussion (community evidence, not universal defect): https://www.reddit.com/r/Comma_ai/comments/1w6l7at/nobody_told_our_comma_3_it_was_obsolete/
- Community custom fused wiring example (anecdotal): https://www.reddit.com/r/Comma_ai/comments/1vuz7u2/got_my_chestnut_going_to_set_it_up_with_custom/

---

Last reviewed: 2026-09-07
