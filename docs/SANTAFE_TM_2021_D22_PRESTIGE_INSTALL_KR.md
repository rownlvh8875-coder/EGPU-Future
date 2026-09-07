# 더 뉴 싼타페 TM 2021 D2.2 2WD 5인승 프레스티지 + comma four + Chestnut/eGPU 설치 설계

작성일: 2026-09-07  
대상차량: **더 뉴 싼타페(TM) 2021년식 / Smartstream D2.2 디젤 / 2WD / 5인승 / 프레스티지 / 조수석 전동시트 + 통풍시트**

> 차량 사양은 사용자 실차 기준으로 확정한다. 공개 TM 정비자료와 2021 Santa Fe 회로자료를 교차검토하되, 한국형 D2.2 VIN별 connector pin/fuse 번호가 공개자료로 확정되지 않은 항목은 추정하지 않는다. 최종 브래킷 mm 치수와 전용 전원선 규격은 실차 실측 후 확정한다.

---

## 1. 이번 조사에서 추가로 확인한 사실

TM 정비자료의 `Air Ventilation Seat` 절차에는 통풍시트가 단순 시트 내부 기능이 아니라 다음의 별도 하드웨어를 가진다고 명시돼 있다.

- cushion blower
- air duct
- air ventilation unit
- passenger blower power
- passenger blower speed
- passenger blower RPM input
- passenger blower ground

정비 절차상 cushion blower, duct, ventilation unit을 탈거하려면 front seat assembly를 먼저 탈거하도록 되어 있다. 따라서 조수석 하부는 GPU용 빈 공간이 아니라 **통풍시트 시스템의 서비스/흡기/배선 공간**이기도 하다.

또한 facelift 2020-2024 non-hybrid seat-ventilation 회로 인덱스에는 `Passenger Air Ventilation Seat Cushion Blower Motor`, `Front Air Ventilation Control Module`, `ICU Junction Block`, `S/HEATER DRV/PASS Fuse` 등이 하나의 회로 계통으로 나타난다. 이 회로는 eGPU 전원 인출 후보가 아니라 보호해야 할 OEM 회로다.

2021 Santa Fe 전원분배 자료에서는 엔진룸 B+3 50 A가 ICU Junction Block을 통해 P/SEAT(DRV), P/SEAT(PASS) 등으로 분배되는 구조가 확인된다. 이것 역시 eGPU를 P/SEAT 회로에 병렬 연결해야 한다는 의미가 아니라, **시트 전원계통과 eGPU 고부하 계통을 분리해야 한다는 근거**로 사용한다.

---

## 2. 조수석 하부 공간을 4개 Zone으로 정의

실차 CAD가 확보되기 전에는 임의 치수를 만들지 않고 아래와 같이 functional zone으로 관리한다.

```text
TOP VIEW — Passenger seat underfloor conceptual map

          VEHICLE FRONT
               ↑

  [A] seat motor / linkage swept zone       KEEP CLEAR
  [B] ventilation blower + duct zone        KEEP CLEAR
  [C] OEM harness / SRS / connectors        NO TOUCH
  [D] verified residual envelope            GPU CANDIDATE ONLY

 ┌─────────────────────────────────────┐
 │ AAAAAA        BBBBBBB        AAAAAA │
 │ AAAAAA        BBBBBBB        AAAAAA │
 │                                     │
 │ CCCCCCCCC OEM HARNESS CCCCCCCCCCCCC │
 │                                     │
 │      DDDDDDDDDDDDDDDDDDDDD          │
 │      D  GPU/TRAY 후보영역 D          │
 │      DDDDDDDDDDDDDDDDDDDDD          │
 └─────────────────────────────────────┘

               ↓
           VEHICLE REAR
```

이 그림은 실제 부품 좌표가 아니라 **설계 규칙**이다. 실제 A/B/C의 위치와 크기는 실차 사진/측정으로 대체한다.

### 절대 금지영역

- 시트 motor/linkage의 full-travel swept volume
- cushion blower 흡기면
- ventilation duct
- yellow SRS connector 및 SRS harness
- occupant/seat-related connector와 OEM harness service loop
- 시트 레일 및 seat anchorage 구조
- 순정 floor/HVAC duct의 토출구

---

## 3. 가장 유력한 상시 패키징 구조

현 단계에서는 **조수석 하부의 남는 바닥 envelope에 낮은 독립 tray를 두는 구조**를 1순위로 유지한다.

중요한 변경점은 GPU를 시트 중앙에 먼저 놓고 주변 부품을 피하는 것이 아니라, **OEM 금지영역을 먼저 subtract한 뒤 남은 공간에 GPU를 맞추는 방식**이다.

```text
SIDE VIEW

Passenger seat cushion
────────────────────────────
 motor/linkage     ventilation hardware
     X X X             X X X

        minimum moving-part clearance
────────────────────────────  ← keep-out boundary

       [ Chestnut / GPU ]
       [ independent tray ]
       ↑                  → hot exhaust
   floor clearance
────────────────────────────
 carpet / floor
```

브래킷은 다음 조건을 만족해야 한다.

1. 시트 최전/최후/최저/최고 위치에서 moving part와 무접촉
2. 통풍시트 ON/OFF와 관계없이 blower intake를 막지 않음
3. OEM connector를 정비할 수 있는 service clearance 유지
4. USB/전원 케이블 bend radius 및 strain relief 확보
5. 급제동/충돌 시 GPU가 이탈하지 않는 positive retention
6. 진동절연재는 사용하되 구조 고정을 약화시키지 않음
7. GPU 흡기와 배기가 서로 재순환하지 않음

---

## 4. USB 케이블 권장 경로

comma four는 전면유리에 있으므로 3 m USB3 cable을 최대한 짧고 보호된 경로로 내려보낸다.

### 1차 후보

```text
comma four
  ↓
headliner edge
  ↓
passenger A-pillar trim edge
  ↓
dash lower / glovebox-side trim
  ↓
center-console RH side 또는 carpet edge
  ↓
passenger-seat-under GPU
```

### 주의

- A-pillar curtain-airbag deployment path를 가로질러 케이블을 묶지 않는다.
- airbag harness에 cable tie로 함께 고정하지 않는다.
- seat rail 위/아래를 횡단하지 않는다.
- 시트 이동부 근처에는 service loop를 두되 pinch point를 만들지 않는다.
- USB connector 양단에 strain relief를 둔다.

### 왜 화물칸을 기본안으로 두지 않는가

현재 openpilot Chestnut status는 USB speed가 5000 Mbps 미만이면 slow-USB alert를 낸다. 기본 3 m보다 긴 extension은 link margin과 EMI/reconnect risk를 늘리므로, 화물칸 설치는 active USB/repeater를 포함한 별도 signal-integrity 시험 이후 판단한다.

---

## 5. 전원 경로

### Phase 1 — 순정 12 V outlet

초기 실차 시험은 차량 순정 12 V outlet과 comma supplied power cable을 사용한다.

RX 9060 TBP 132 W는 180 W급 outlet 조건과 단순 수치상 양립하지만, Chestnut 자체소비·변환손실·접촉저항·순간부하가 추가되므로 margin은 실제 계측한다.

기록:

- Chestnut supplyVoltage
- supplyCurrent
- supplyFault
- GPU powerDrawW
- plug/socket temperature
- PCIe LTSSM
- USB link error/speed
- model load/recovery time

### Phase 2 — 전용 protected feed가 필요한 경우

다음이 반복될 때만 전용 전원을 설계한다.

- cold start/ISG restart에서 power loss
- plug/socket 과열
- voltage sag와 PCIe/USB fault의 상관
- big-model load/recovery failure
- 장거리 high-load에서 공급 불안정

권장 topology:

```text
Vehicle LV source
   ↓
source-side fuse
   ↓
reverse-polarity / transient / inrush protection
   ↓
automotive-rated power stage
   ↓
ACC/ignition-controlled enable
   ↓
low-voltage cutoff
   ↓
Chestnut + GPU
```

### 사용하지 않을 회로

- P/SEAT(PASS)
- S/HEATER DRV/PASS
- SRS/occupant-related circuit
- seat ventilation circuit

시트 계통은 기능·안전·진단을 위해 OEM 상태로 유지한다.

---

## 6. 통풍시트와 GPU 냉각의 상호간섭 방지

통풍시트 blower가 존재하므로 GPU 냉각은 독립 air path로 설계한다.

### 목표 airflow

```text
front/cabin relatively cool air
          ↓
      GPU intake
     [ GPU ] ─────────→ rear/center-side exhaust
          │
      raised tray

Seat ventilation blower/duct = separate OEM airflow
```

### 하지 않을 것

- 통풍시트 duct 절단/분기
- 통풍 blower를 GPU 냉각팬으로 겸용
- GPU hot exhaust를 blower intake 쪽으로 배출
- 방음재로 seat-under cavity를 밀폐

### 여름 heat-soak 정책

차량이 햇볕에 장시간 주차된 뒤 cabin이 고온이면 big model을 즉시 full PPT로 돌리지 않는 정책을 연구한다.

예:

```text
BOOT
 ↓
GPU/VRAM/inlet 상태 확인
 ↓
WARM-UP / reduced PPT
 ↓
온도와 model latency 안정
 ↓
NORMAL PPT
```

현재 openpilot hard overheat는 GPU 100°C, memory 95°C, hysteresis 5°C다. EGPU-Future의 목표는 이 hard limit 전에 proactive de-rate하는 것이다.

---

## 7. 싼타페 TM용 PPT/소음 시험

```text
132 W → 120 → 110 → 100 → 90 W
```

각 단계에서 최소 다음을 동시 기록한다.

| 항목 | 목적 |
|---|---|
| p50/p95/p99 inference latency | 20 Hz deadline margin |
| frame drop | compute/transport overload 확인 |
| GPU hotspot | silicon thermal margin |
| memory temperature | VRAM thermal margin |
| fan RPM | noise proxy |
| cabin dBA | 실제 체감소음 |
| supply current/voltage | vehicle electrical load |
| USB/PCIe errors | undervolt/thermal correlation |

최종 목표는 최고 성능점이 아니라 **주행 deadline을 안정적으로 만족하는 최저전력/최저소음 operating point**다.

---

## 8. 실차 측정 시트 — CAD 브래킷 제작에 필요한 값

다음 값만 확보하면 bracket envelope를 수치화할 수 있다.

### 시트/바닥

- L1: 좌우 seat rail 안쪽 거리
- L2: 좌우 seat rail 바깥 거리
- H1: carpet → 가장 낮은 고정 부품
- H2: carpet → 가장 낮은 moving part (seat 최저 상태)
- X1: front rail 기준 ventilation blower 시작 위치
- X2: front rail 기준 blower/duct 종료 위치
- X3: front rail 기준 주요 OEM connector 위치
- W1/H3: 남는 연속 rectangular envelope

### 시트 이동

- full forward 상태 사진/치수
- full rear 상태 사진/치수
- seat lowest/highest 상태 사진/치수
- 각 상태에서 motor/linkage 최저점

### GPU

- 실제 카드 length
- height
- thickness
- power connector 돌출 포함 높이
- USB/PCIe/power cable 최소 bend 공간

### 케이블

- comma four → A-pillar 하단
- A-pillar → dash lower
- dash lower → seat-under
- 총 실제 routing length

이 값이 확보되기 전에는 브래킷 mm 도면을 확정하지 않는다.

---

## 9. 실차 사진 촬영 위치

브래킷 설계를 위해 다음 6장 정도면 충분하다.

1. 조수석 full rear — 앞쪽 발밑에서 시트 하부 전체
2. 조수석 full forward — 2열에서 시트 하부 전체
3. 조수석 하부 좌측
4. 조수석 하부 우측
5. 통풍시트 작동 상태에서 blower/흡기 확인 가능한 근접사진
6. 센터콘솔 RH 하단부터 조수석 레일까지 케이블 경로

사진에는 줄자 또는 자를 같이 두면 CAD 스케일 추정이 훨씬 정확해진다.

---

## 10. 현재 결론

### 확정

- 차량: 2021 더 뉴 싼타페 TM D2.2 2WD 5인승 프레스티지
- 조수석: 전동 + 통풍
- 통풍시트는 독립 blower/duct/control 계통을 가짐
- seat power/ventilation/SRS 회로에서 eGPU 전원을 빼지 않음
- 초기 설치: passenger footwell temporary rigid tray
- 상시 목표: passenger-seat-under residual envelope
- USB: 전면유리 → passenger A-pillar/dash lower → 조수석 하부의 보호경로 우선
- cooling: seat ventilation과 완전히 독립
- power: stock outlet로 먼저 계측 후 필요할 때만 dedicated feed

### 아직 실측 필요

- 정확한 seat-under free envelope
- blower/duct의 한국형 실차 좌표
- harness/connector 좌표
- 실제 USB routing length
- 실제 RX 9060 card 외형

따라서 다음 실제 행동은 **차량을 뜯는 것이 아니라 위 6장의 사진과 L/H/X 치수를 확보하는 것**이다. 그 데이터가 들어오면 실제 브래킷 형상과 GPU 방향을 확정할 수 있다.

---

## Sources

- Hyundai Santa Fe TM Seat Electrical / Air Ventilation Seat: https://www.hsafe4.com/hyundai_santa_fe_tm_seat_electrical-1237.html
- Hyundai Santa Fe TM Seat Heater/Air Ventilation schematic: https://www.hsafe4.com/hyundai_santa_fe_seat_heater_air_ventilation_schematic_diagrams-1251.html
- Hyundai Santa Fe TM Floor Console service information: https://www.hsafe4.com/hyundai_santa_fe_tm_floor_console-1034.html
- Santa Fe IV facelift non-hybrid seat ventilation wiring index: https://diagnostdata.com/hyundai/santa-fe/iv-facelift-2020-2024/system/power-seats/seat-ventilation-circuit-except-hybrid/
- 2021 Santa Fe power/fuse manual mirror: https://www.carmanualsonline.info/hyundai-santa-fe-2021-owners-manual/
- comma.ai Chestnut: https://blog.comma.ai/chestnut/
- openpilot Chestnut status/modeld: https://github.com/commaai/openpilot
- AMD RX 9060 specifications: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
