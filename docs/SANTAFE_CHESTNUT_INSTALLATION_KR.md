# 싼타페 + comma four + Chestnut/eGPU 설치 설계

작성일: 2026-09-07

> 현재 사용자의 싼타페 정확 연식/세대는 확인되지 않았다. 따라서 국내 판매 기준으로 신형 MX5와 이전 TM을 모두 고려한 설계 원칙을 정리한다. 실제 배선·퓨즈·브래킷 치수는 연식/트림/하이브리드 여부 확인 후 확정해야 한다.

---

## 1. 결론

싼타페에서는 Chestnut + GPU를 **무조건 조수석 발밑에 던져놓는 방식**보다 다음 우선순위를 권장한다.

1. **조수석 하부 전용 브래킷 + 강제 공기 경로** — 가장 현실적인 상시 설치안
2. **조수석 발밑 측면/상단 브래킷** — 초기 시험용으로 가장 쉬움
3. **2열/센터콘솔 인접부 별도 덕트형 하우징** — 공간이 허용될 때 소음/열 관리에 유리
4. **화물칸** — 냉각과 소음에는 유리하지만 3 m USB3 케이블 길이, 신호품질, 부팅/복구 안정성 때문에 기본안으로는 비추천

가장 중요한 원칙은 다음 네 가지다.

- GPU 흡기와 배기를 분리해 hot-air recirculation을 막을 것
- 시트 레일, SRS/occupancy 배선, 순정 HVAC duct를 건드리지 않을 것
- 12 V 소켓은 초기 검증용으로 사용하고 장기운용은 전용 fused feed를 검토할 것
- GPU 전력 제한(PPT)을 모델 deadline 안에서 낮춰 열과 팬소음을 줄일 것

---

## 2. 싼타페 전원 여유

### MX5 공식 매뉴얼

현대자동차 MX5 2024/2025 사용설명서의 다용도 소켓 항목은 앞좌석 및 화물칸 소켓에 대해 **12 V, 180 W 이하** 전기제품을 사용하도록 명시한다.

출처:
- https://ownersmanual.hyundai.com/full_webhelp/MX5/2024/ko_KR/id7429a7a0837.html
- https://ownersmanual.hyundai.com/manual/%EC%8B%BC%ED%83%80%ED%8E%98?countryCode=A99&langCode=ko_KR&projCode=MX5&year=2025

### TM 공식 매뉴얼

TM 사용설명서도 power outlet을 **180 W 이하**로 규정한다.

출처:
- https://www.hyundai.com/content/dam/hyundai/bh/en/data/marketing/manual/santa-fe/2019/Santa-Fe-TM-Euro-2019.pdf

### RX 9060과 비교

Chestnut Ready-to-Drive의 RX 9060은 AMD 공식 Typical Board Power가 132 W이다.

따라서 단순 수치상으로는 180 W outlet 안에 들어온다.

하지만 132 W는 GPU board power이며 다음이 추가된다.

- DC/DC conversion loss
- Chestnut board 자체 소비전력
- cable/contact loss
- 순간부하

즉 180 W 소켓과 132 W GPU 사이의 약 48 W 차이를 전부 "여유"라고 보면 안 된다.

### 권장 운용

초기 시험:

```text
싼타페 12 V 180 W outlet
  → comma Ready-to-Drive car power cable
  → Chestnut + RX 9060
```

조건:

- 해당 소켓에 splitter를 사용하지 않음
- 냉장고/청소기/인버터 등 다른 고부하 장치 동시 사용 금지
- plug 접촉부 발열 확인
- supplyVoltage/supplyCurrent/supplyFault 로그 기록
- 주행 중 outlet 주변 이상 발열/냄새 발생 시 즉시 중단

장기 설치:

```text
Vehicle LV bus
  → source-side fuse
  → automotive transient/reverse-polarity protection
  → dedicated power stage
  → ACC/ignition enable
  → low-voltage cutoff
  → Chestnut
```

단, 실제 fuse ampere와 wire gauge는 차량 연식/전장도/배선 길이를 확인한 뒤 정해야 하며 OEM fuse만 크게 올리는 방식은 사용하지 않는다.

---

## 3. MX5에서 권장 설치 위치

### A안 — 조수석 아래 전용 브래킷: 장기적으로 1순위

comma도 공식적으로 passenger seat 아래 설치를 허용한다.

장점:

- 시야와 수납공간을 거의 침범하지 않음
- comma four에서 3 m USB3 케이블로 연결하기 쉬움
- 고정 구조를 만들기 쉬움
- 실내 HVAC 환경을 활용 가능

주의점:

MX5 조수석 하부에는 순정 배선과 시트 관련 전장물이 존재할 수 있고, 트림에 따라 전동시트/열선/통풍/occupancy/SRS 계통 배치가 다르다. 바닥 구조 사진에서도 하부에 순정 하네스와 모듈이 존재함을 확인할 수 있으므로 아무 위치에나 나사 체결하면 안 된다.

브래킷 조건:

```text
Seat base
│
├─ OEM rail / SRS / seat wiring   ← 절대 간섭 금지
│
└─ independent GPU tray
      ├─ floor에서 충분히 이격
      ├─ front/cabin side intake
      └─ rear 또는 side exhaust
```

필수 확인:

- 시트 최전방/최후방 full travel
- 시트 최저/최고 위치
- 조수석 탑승자의 발 공간
- 2열 승객 발 공간
- 순정 rear HVAC duct 유무
- 통풍시트 blower/intake와 간섭 여부
- seat harness를 누르거나 cable tie로 묶지 않을 것

**GPU를 카펫 위에 바로 눕히는 방식은 권장하지 않는다.** 흡기면이 막히고 열이 재순환될 가능성이 크다.

---

### B안 — 조수석 발밑: 초기 시험 1순위

comma 공식 launch blog에 제시된 위치다.

장점:

- 장착/분리/관찰이 쉬움
- HVAC 차가운 공기를 직접 받을 수 있음
- 팬상태, cable, LED, 온도를 바로 확인 가능

단점:

- 발에 걸릴 수 있음
- 비/눈/우산/음료 등 수분 위험
- 충돌 시 제대로 고정하지 않으면 위험물체가 됨
- 팬소음이 더 잘 들림

따라서 단순 Velcro만으로 장기 사용하기보다 **발 공간과 분리된 고정 tray + 보호 cage**가 더 적절하다.

추천 형태:

```text
Dashboard lower side
      │
[cool cabin air]
      ↓
   GPU intake
   [ GPU ] → exhaust를 seat/center-console 방향으로 분리
      │
 rigid bracket
```

---

### C안 — 화물칸

싼타페는 화물공간이 넓고 MX5는 공식적으로 cargo-area 12 V outlet도 제공한다.

장점:

- 탑승자 귀에서 멀어 팬소음 감소
- 충분한 하우징/덕트 공간 확보 가능
- 발/음료와 접촉할 가능성 낮음

하지만 기본안으로 권장하지 않는 이유:

- comma kit 기본 USB3 cable은 3 m
- windshield의 comma four부터 cargo area까지 실제 routing 길이가 3 m를 넘을 가능성이 큼
- USB extension은 5 Gbps 링크 margin을 악화할 수 있음
- 현재 openpilot은 Chestnut USB speed가 **5000 Mbps 미만이면 slow USB alert**를 발생시킨다
- 케이블 길이가 늘면 EMI와 reconnect 문제도 늘 수 있음

따라서 cargo 설치는 **active USB solution을 포함한 별도 검증 프로젝트**로 두는 것이 맞다.

---

## 4. 발열 대책 — 싼타페 실내 환경에 맞춘 제안

GPU의 132 W는 결국 대부분 열이 된다.

특히 여름철 주차 후 cabin heat soak 상태에서 바로 Chestnut을 최대부하로 돌리는 것이 최악 조건이다.

### 권장 4단 thermal policy

#### T0 — Cold/Normal

- 정상 PPT
- 기본 fan curve

#### T1 — Warm cabin

- cabin/GPU inlet temperature 상승 시 PPT 10~20 W 감소
- fan RPM이 급증하기 전에 선제 de-rate

#### T2 — Hot

- GPU hotspot / memory / fan RPM / model latency를 함께 보고 추가 PPT 감소
- big-model deadline margin이 부족해지면 small model 준비

#### T3 — Unsafe

- overheat 또는 deadline violation 반복
- big model disable
- small model fallback

현재 openpilot Chestnut 상태 코드는 GPU 100°C, memory 95°C, 5°C hysteresis의 과열 판정을 갖는다. 하지만 이 값에 도달하기 전에 proactive de-rate하는 것이 차량 실내 소음과 장기 신뢰성에는 더 유리하다.

### 물리적 냉각

권장:

- GPU intake 앞 30~50 mm 수준의 자유공간 확보를 초기 기준으로 두고 실제 airflow로 검증
- exhaust와 intake가 서로 마주보지 않도록 배치
- perforated enclosure 사용 시 exhaust 측 개구율을 충분히 확보
- 필요하면 120 mm급 저회전 보조팬을 GPU fan과 멀리 배치하여 낮은 RPM으로 전체 공기 교환

비추천:

- 완전 밀폐 박스
- 방음재로 GPU 전체를 감싸는 것
- 두꺼운 카펫 바로 위 설치
- glovebox 내부 밀폐 설치

---

## 5. 팬소음 해결책

팬소음은 세 가지로 나뉜다.

1. GPU fan의 aerodynamic noise
2. 작은 개구부에서 발생하는 turbulence
3. GPU/bracket 진동이 차체로 전달되는 structure-borne noise

### 우선순위

#### 1. PPT 감소

가장 효과적일 가능성이 높다.

`tinygrad` AMD SMU 구현에는 `set_power_limit(watts)`가 이미 있으므로, RX 9060을 full TBP로만 사용할 필요는 없다.

실험 예:

```text
132 W → 120 → 110 → 100 → 90 W
```

각 단계에서:

- p50/p95/p99 inference time
- dropped frame
- GPU hotspot
- memory temp
- fan RPM
- cabin noise

를 함께 측정한다.

20 Hz model period는 50 ms이므로 실제 end-to-end margin을 해치지 않는 최저 전력점이 싼타페용 sweet spot이 된다.

#### 2. 큰 팬을 저속으로

좁은 GPU fan을 고RPM으로 돌리는 것보다 별도의 큰 fan으로 주변 공기를 천천히 교환하는 편이 소음 대비 airflow가 좋을 수 있다.

#### 3. 진동 절연

- 얇은 고무 isolation mount
- rigid GPU retention + isolator 조합
- GPU가 carpet/seat frame에 직접 닿지 않게 설계

단 너무 부드러운 mount는 충돌/급제동 시 GPU가 움직일 수 있으므로 진동절연과 구조고정을 분리한다.

---

## 6. 소음 목표를 수치로 만들기

주관적인 "조용하다" 대신 다음 test protocol을 권장한다.

```text
vehicle parked / HVAC off
microphone: driver ear position
ambient baseline
↓
GPU idle
↓
big model 10 min
↓
heat-soaked big model 30 min
```

기록:

- fan RPM
- GPU power
- temp
- inference latency
- cabin dBA

그 후 `power limit vs dBA vs latency` Pareto curve를 만든다.

---

## 7. 싼타페에서 특히 확인할 전원 sequence

Hyundai Sonata에서는 remote start 시 cigarette lighter가 powered되지 않아 big model loading이 timeout되는 공개 issue가 있다.

싼타페도 연식/사양별 remote-start 및 outlet power sequence가 동일하다고 단정할 수는 없다.

따라서 다음을 실제 차량에서 계측해야 한다.

- 정상 시동
- 원격 시동
- ISG stop/restart
- ACC→ON
- 시동 직후 crank/voltage dip
- ignition OFF 직후 outlet 유지시간

로그:

- supplyVoltage
- supplyCurrent
- supplyFault
- Chestnut USB present
- PCIe LTSSM
- model loading/active state

---

## 8. 최종 권장 설치안

### Phase 1 — 검증

```text
comma four
  │ 3 m USB3
  ▼
조수석 발밑 Chestnut + RX 9060
  │
싼타페 순정 12 V / 180 W outlet
```

목표:

- 실제 소비전력
- outlet plug 온도
- GPU 온도
- fan RPM
- model latency
- 소음
- remote-start/ISG power sequencing

수집

### Phase 2 — 상시 설치

```text
comma four
  │
  └─ routed USB3
       │
       ▼
조수석 하부 독립 tray
  ├─ intake: cabin/front
  ├─ exhaust: rear/side
  ├─ vibration isolation
  ├─ rigid retention
  └─ temperature/power logging
```

전원은 Phase 1 측정값을 보고 순정 180 W outlet 지속사용 또는 dedicated fused power path 중 선택한다.

### Phase 3 — optimized silent mode

- adaptive GPU PPT
- thermal headroom based de-rate
- optional large low-RPM auxiliary fan
- automatic big→small fallback

---

## 9. 정확한 차량 정보가 확인되면 추가할 항목

사용자의 싼타페 연식/세대/파워트레인 확인 후 다음을 별도 확정한다.

- MX5 vs TM
- gasoline/diesel/hybrid
- 5/6/7 seat
- passenger power seat/relaxation seat 여부
- passenger ventilated seat 여부
- under-seat HVAC duct 위치
- outlet별 fuse 및 동일회로 여부
- 배터리/LV bus 접근 위치
- 실제 bracket envelope
- cable routing length

이 단계에서만 fuse ampere, wire gauge, bracket dimension을 확정한다.

---

## Sources

- comma.ai Chestnut: https://blog.comma.ai/chestnut/
- Chestnut product/setup: https://comma.ai/shop/chestnut
- Hyundai Santa Fe MX5 2024 power outlet: https://ownersmanual.hyundai.com/full_webhelp/MX5/2024/ko_KR/id7429a7a0837.html
- Hyundai Santa Fe MX5 2025 manual: https://ownersmanual.hyundai.com/manual/%EC%8B%BC%ED%83%80%ED%8E%98?countryCode=A99&langCode=ko_KR&projCode=MX5&year=2025
- Hyundai Santa Fe TM manual: https://www.hyundai.com/content/dam/hyundai/bh/en/data/marketing/manual/santa-fe/2019/Santa-Fe-TM-Euro-2019.pdf
- openpilot Chestnut status: https://github.com/commaai/openpilot/blob/master/openpilot/system/hardware/chestnut/status.py
- openpilot issue #38685: https://github.com/commaai/openpilot/issues/38685
- tinygrad AMD power control: https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/support/am/ip.py
