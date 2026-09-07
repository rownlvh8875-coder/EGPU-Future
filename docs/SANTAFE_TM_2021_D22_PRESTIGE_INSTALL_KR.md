# 더 뉴 싼타페 TM 2021 D2.2 디젤 프레스티지 + comma four + Chestnut/eGPU 설치안

작성일: 2026-09-07
대상차량: **더 뉴 싼타페(TM) 2021년식 / Smartstream D2.2 디젤 / 2WD / 5인승 / 프레스티지 / 조수석 전동시트 + 통풍시트**

> 차량 사양은 사용자 실차 기준으로 확정했다. 본 문서는 이 사양을 기준으로 한다. 브래킷의 최종 mm 치수와 전용 전원선 규격은 순정 시트 하부 실측 및 해당 VIN 기준 현대 정비정보 확인 후 확정한다.

---

## 1. 조사 결과 요약

현대 TM 정비자료 계열에는 시트 전장에 대해 `Passenger power seat`, `Seat Heater (Air Ventilation)`, `Air Ventilation Seat`의 component location, schematic, connector/repair procedure가 존재한다.

공개 확인 가능한 TM 정비자료에서 통풍시트 계통은 다음 부품을 별도로 가진다.

- Air ventilation seat blower
- Air ventilation seat control unit (Passenger only)
- Air ventilation seat duct
- Passenger blower power / speed / RPM 관련 신호
- Passenger heater/ventilation 관련 전원 및 ground

따라서 조수석 아래는 단순 빈 공간이 아니며 GPU를 시트 중앙 아래에 임의로 넣는 방식은 피한다.

또한 2021 Santa Fe 계열 fuse 자료에는 `P/SEAT (PASS)` 30 A 회로가 별도로 존재한다. 이 회로는 조수석 전동시트용이며 eGPU 전원 인출점으로 사용하지 않는다.

---

## 2. 조수석 하부 설치 판단

### 원칙

최종 설치 위치는 여전히 조수석 하부가 유력하지만 다음 순정 영역을 모두 피한 별도 tray로 제한한다.

```text
Passenger seat cushion
       │
       ├─ ventilation blower / duct zone       [KEEP CLEAR]
       ├─ power-seat motor/linkage zone        [KEEP CLEAR]
       ├─ seat wiring/connectors                [KEEP CLEAR]
       ├─ SRS / occupant-related wiring         [NO TOUCH]
       │
       └─ remaining verified envelope
              └─ independent Chestnut/GPU tray
```

### 금지

- 통풍시트 blower 흡기 앞을 GPU나 방음재로 막기
- 통풍시트 duct를 GPU 냉각용으로 절단/분기하기
- 시트 모터나 linkage 이동영역에 케이블 배치
- SRS/seat connector에 piggyback 전원 연결
- P/SEAT(PASS) 30 A fuse를 eGPU 전원원으로 전용
- 시트/SRS 구조 볼트에 임의 bracket을 함께 체결

### 실제 브래킷 위치 확정 절차

1. 조수석을 최전방/최후방, 최저/최고로 각각 이동
2. 전동시트 motor/linkage swept volume 표시
3. 통풍시트 blower intake와 duct 위치 표시
4. 순정 harness/connector 위치 표시
5. 바닥/센터콘솔/2열 HVAC duct 위치 표시
6. 남은 공간의 폭×길이×높이를 실측
7. RX 9060 실제 카드 외형과 connector/cable bend radius를 포함해 envelope 비교
8. intake/exhaust가 서로 재순환하지 않는 방향으로 tray 결정

---

## 3. 권장 설치안

### Phase A — 실차 계측 전

초기에는 조수석 발밑의 rigid temporary tray에 stock Chestnut + RX 9060을 설치한다.

```text
comma four (windshield)
      │ 3 m USB3
      ▼
Chestnut + RX 9060
(passenger footwell temporary tray)
      │
      ▼
OEM 12 V outlet
```

이 단계에서 전원/열/팬소음/USB 안정성을 먼저 확인한다.

### Phase B — 조수석 하부 상시 설치

순정 통풍시트 및 전동시트 영역을 실측한 뒤:

```text
Cabin/front cool air
       ↓
 GPU intake
 [ GPU + Chestnut ] ──→ rear/center-side exhaust
       │
 independent rigid tray
       │
 vibration isolator + positive retention
```

GPU는 카펫에 직접 놓지 않고 흡기면과 바닥을 이격한다. 시트 full travel에서 케이블까지 포함해 간섭이 없어야 한다.

---

## 4. 전원

싼타페 TM 계열 power outlet은 매뉴얼 기준 12 V, 180 W 이하 사용 조건이다. RX 9060 TBP는 132 W이므로 초기 stock test는 순정 outlet + comma car-power cable로 수행한다.

하지만 48 W 차이를 전부 margin으로 보지 않는다. Chestnut board, 변환손실, 케이블/접점손실, transient가 존재한다.

### 초기 시험 로그

- supplyVoltage
- supplyCurrent
- supplyFault
- GPU powerDrawW
- PCIe LTSSM
- USB speed/link errors
- plug/socket 온도

### 별도 전원으로 전환하는 조건

- 시동/ISG 재시동에서 power lost 반복
- plug/socket 비정상 온도상승
- supplyFault
- big model load failure
- PCIe/USB instability가 전압강하와 상관됨

전용 회로가 필요해지면 차량 LV source에서 source-side fuse, automotive transient/reverse-polarity protection, ACC-controlled enable, low-voltage cutoff를 거치는 별도 회로를 설계한다. 순정 P/SEAT(PASS) 30 A 회로를 GPU 전원으로 공유하지 않는다.

---

## 5. 발열/소음

조수석 하부는 통풍시트 blower가 이미 존재하므로 GPU 열을 추가했을 때 두 시스템이 서로의 흡기온도를 악화시키지 않도록 해야 한다.

### 권장 thermal policy

- Normal: 기본 PPT
- Warm: GPU PPT 선제 감소
- Hot: 추가 de-rate + small-model standby
- Unsafe/deadline violation: big model disable → small model fallback

현재 openpilot Chestnut hard overheat 판정은 GPU 100°C, memory 95°C, hysteresis 5°C다. 차량 프로젝트에서는 이 hard limit보다 훨씬 앞에서 de-rate하는 것을 목표로 한다.

### PPT sweep

```text
132 → 120 → 110 → 100 → 90 W
```

각 단계에서 p50/p95/p99 inference latency, frame drop, hotspot, memory temp, fan RPM, cabin dBA, supply current를 기록한다. 현재 model loop는 20 Hz(50 ms nominal period)이므로 deadline margin을 만족하는 최저 PPT를 TM용 quiet/efficient point로 선택한다.

필요하면 120 mm급 저RPM 보조팬으로 시트 아래 공간 전체의 공기교환을 돕되 통풍시트 blower intake를 방해하지 않는다.

---

## 6. 차량 배선/도면 조사 상태

확인된 자료 종류:

- Passenger power seat circuit
- Seat ventilation circuit (non-hybrid)
- Air ventilation seat component location
- Air ventilation seat schematic
- Seat heater/ventilation connector signal list
- Instrument-panel fuse distribution
- P/SEAT(PASS) 30 A passenger-seat circuit

현대의 정식 정비정보는 VIN/시장별 세부 사양을 기준으로 확인하는 것이 가장 정확하다. 공개된 해외 2021 Santa Fe 자료는 엔진/트림이 한국형 D2.2와 다를 수 있으므로 connector pin이나 fuse 번호를 그대로 한국형 차량에 적용하지 않는다. 현재 공개 자료는 **물리적 배치와 회로 구조를 이해하는 참고자료**로 사용하고, 실제 배선 변경 전에는 한국형 VIN 기준 현대 정비정보/실차 fuse label을 대조한다.

---

## 7. 다음 실차 작업 때 필요한 사진/치수

최종 CAD 브래킷을 만들기 위해 다음만 실차에서 확보하면 된다.

1. 조수석을 최대로 뒤로 보낸 상태의 시트 아래 전방 사진
2. 최대로 앞으로 보낸 상태에서 2열 쪽에서 본 시트 아래 사진
3. 시트 아래 좌/우 측면 사진
4. 통풍시트 ON 상태에서 blower 위치 확인
5. 바닥에서 가장 낮은 움직이는 시트 부품까지 높이
6. 좌우 시트레일 안쪽 간격
7. 사용 예정 RX 9060 카드의 실제 길이/높이/두께
8. comma four에서 A-pillar/door-sill/center-console 경로로 조수석 하부까지 USB 케이블 실측 길이

이 8개가 확보되면 GPU tray의 실제 envelope와 intake/exhaust 방향을 확정할 수 있다.

---

## Sources

- Hyundai Santa Fe TM seat electrical service information: https://www.hsafe4.com/hyundai_santa_fe_tm_seat_electrical-1237.html
- Hyundai Santa Fe TM seat ventilation schematic: https://www.hsafe4.com/hyundai_santa_fe_seat_heater_air_ventilation_schematic_diagrams-1251.html
- Santa Fe IV facelift wiring index: https://diagnostdata.com/hyundai/santa-fe/iv-facelift-2020-2024/
- Seat ventilation wiring, non-hybrid: https://diagnostdata.com/hyundai/santa-fe/iv-facelift-2020-2024/system/power-seats/seat-ventilation-circuit-except-hybrid/
- 2021 Santa Fe owner/service manual mirror: https://www.carmanualsonline.info/hyundai-santa-fe-2021-owners-manual/5
- comma Chestnut: https://blog.comma.ai/chestnut/
- openpilot Chestnut status/modeld: https://github.com/commaai/openpilot
- AMD RX 9060 specifications: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
