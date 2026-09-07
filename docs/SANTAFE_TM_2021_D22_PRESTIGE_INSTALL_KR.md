# 더 뉴 싼타페 TM 2021 D2.2 디젤 프레스티지 + comma four + Chestnut/eGPU 설치안

작성일: 2026-09-07
대상차량: **더 뉴 싼타페(TM) 2021년형 / Smartstream D2.2 디젤 / 프레스티지**

> 이 문서는 사용 차량이 확정된 뒤 작성한 전용 설치 기준이다. 5/7인승, 2WD/HTRAC, 세부 선택옵션은 아직 확정되지 않았으므로 시트 하부 브래킷의 최종 치수와 전원 배선 사양은 실차 확인 후 확정한다.

---

## 1. 차량 기준

현대자동차 2021 Santa Fe 공식 자료 기준 Smartstream D2.2는 2,151 cc, 194 PS / 3,800 rpm, 45.0 kgf·m / 1,750~2,750 rpm, 8단 DCT 조합이다.

현대 인증중고차에도 `2021 싼타페(TM) 디젤 2.2 2WD 5인승 프레스티지`가 확인되어 해당 연식/파워트레인/트림 조합이 실제 판매된 구성임을 확인했다.

Sources:
- https://www.hyundai.com/kr/ko/brand/brandstory/model/santafe-history/2021-santafe
- https://certified.hyundai.com/

---

## 2. 이 차량에서의 설치 우선순위

### 1순위 — 조수석 하부 독립 브래킷

상시 설치 최종 목표 위치.

이유:

- windshield의 comma four에서 3 m USB3 cable로 접근하기 현실적
- 승객 시야/수납공간 침범이 작음
- cabin HVAC 환경을 활용 가능
- fan noise가 조수석 발밑 노출 설치보다 줄어듦
- 점검/탈거도 cargo area보다 쉬움

단, **시트 바닥에 GPU를 직접 놓으면 안 된다.**

확인사항:

- 조수석 시트 full forward/backward travel
- 시트 높이 조절 전 구간
- 시트 하부 OEM harness / connector / seat motor
- SRS 및 occupancy 관련 하네스
- 통풍시트 관련 blower/intake가 실제 옵션으로 존재하는지
- 2열 승객 발공간
- 순정 HVAC air path

권장 구조:

```text
Passenger seat
│
├── OEM seat rail / wiring / connectors   [NO TOUCH]
│
└── independent rigid GPU tray
      ├── floor/carpet에서 이격
      ├── front 또는 cabin side = cool-air intake
      ├── rear/center side = hot-air exhaust
      ├── rubber vibration isolator
      └── positive mechanical retention
```

브래킷은 기존 시트/SRS 고정 볼트를 임의로 공유하지 않고 별도 고정점을 우선 검토한다. 충돌 안전과 시트 구조에 영향을 주는 가공은 피한다.

---

### 2순위 — 조수석 발밑 측면/상단

초기 시험용 1순위.

처음 2~4주 동안은 이 위치가 유리하다.

- GPU/Chestnut LED와 cable 즉시 점검
- 12 V plug 발열 확인
- 팬 RPM/소음 직접 확인
- HVAC 냉풍 효과 확인
- USB disconnect 여부 확인

장기 설치 시에는 물/우산/발 간섭 및 충돌시 이탈 위험 때문에 rigid protective tray가 필요하다.

---

### 3순위 — 화물칸

소음에는 가장 유리할 수 있으나 기본안으로는 보류한다.

이유:

- comma 기본 USB3 cable 3 m
- comma four부터 rear cargo까지 실제 routing은 3 m를 넘을 가능성이 높음
- current openpilot Chestnut code는 USB speed < 5000 Mbps를 slow USB로 경고함
- extension/active cable 추가 시 EMI, link error, reconnect failure가 새 변수로 들어감

cargo installation은 `USB signal integrity project`로 별도 검증 후 선택한다.

---

## 3. 전원 — 이 차량에서의 실제 권장안

현대차 power-outlet 매뉴얼 계열은 **12 V / 180 W 이하** 전기기기를 사용하도록 규정한다.

Chestnut Ready-to-Drive의 RX 9060은 AMD 기준 Typical Board Power가 **132 W**다.

단순 차이:

```text
Vehicle outlet limit: 180 W
RX 9060 TBP:         132 W
Nominal difference:   48 W
```

하지만 48 W가 그대로 여유전력은 아니다.

추가 요소:

- Chestnut board 소비전력
- DC/DC conversion loss
- cable/contact resistance
- 순간 power excursion
- plug/socket temperature rise

### Phase 1 권장

순정 회로를 건드리지 않고 먼저 다음 구성으로 실차 데이터를 모은다.

```text
2021 Santa Fe TM 12 V outlet
        ↓
comma supplied car power cable
        ↓
Chestnut + RX 9060
```

조건:

- 해당 outlet에 splitter 사용하지 않음
- 냉장고/청소기/inverter 등 다른 고부하 병렬 사용 금지
- socket plug 완전 삽입
- 최초 30분/1시간/장거리 주행 후 plug 및 socket 주변 발열 확인
- `supplyVoltage / supplyCurrent / supplyFault / powerDrawW` 기록

### Phase 2 조건부 전용 전원

다음 중 하나라도 반복되면 전용 전원 회로를 검토한다.

- engine start/ISG restart에서 Chestnut power lost
- big model load timeout
- supplyFault
- socket/plug 과열
- 장거리 주행에서 voltage drop
- 최대부하에서 불안정한 PCIe/USB link

권장 architecture:

```text
Vehicle low-voltage source
  → source-side fuse
  → reverse-polarity/transient protection
  → automotive power stage
  → ACC/ignition controlled enable
  → low-voltage cutoff
  → Chestnut + GPU
```

**OEM outlet fuse를 더 큰 값으로 교체해서 해결하지 않는다.** fuse는 wire 보호 기준으로 선정되어야 한다.

---

## 4. 디젤/ISG 차량에서 특히 볼 항목

2021 D2.2에는 ISG 운용 가능성이 있으므로 다음 시험을 별도 수행한다.

1. cold start
2. warm restart
3. ISG stop
4. ISG restart
5. ACC → engine ON
6. engine OFF 후 outlet power 유지시간
7. remote start 사용 시 outlet 상태(해당 기능 사용 차량일 경우)

각 이벤트 전후로 기록:

- supplyVoltage
- supplyCurrent
- supplyFault
- Chestnut USB present
- PCIe LTSSM
- ChestnutActive
- big-model load/recovery duration

현대 Sonata에서 remote start 시 accessory outlet이 켜지지 않아 eGPU model load가 timeout된 openpilot issue #38685가 존재하므로, 싼타페에서도 동일하다고 가정하지 말고 **실차 power sequencing을 실제 측정**한다.

Source:
- https://github.com/commaai/openpilot/issues/38685

---

## 5. 발열 — TM 실내에서의 권장 airflow

RX 9060 132 W급 부하는 좁은 시트 하부 공간에서는 의미 있는 열원이다.

### 권장 airflow

```text
Front/cabin cool air
       ↓
 [ GPU intake ]
 [   GPU      ] ───→ rear/center-side exhaust
       ↑
    floor gap
```

핵심은 `hot exhaust → GPU intake` 재순환을 막는 것이다.

초기 설계 기준:

- intake 주변 자유공간 30~50 mm부터 시작하여 실측
- GPU를 carpet에 바로 붙이지 않음
- 완전 밀폐 방음박스 금지
- 필요시 120 mm급 저RPM 보조팬으로 공간 전체 air exchange
- 여름 heat-soak 후 바로 full power를 요구하지 않고 warm-up/de-rate policy 적용

현재 openpilot Chestnut code는 GPU 100°C, memory 95°C 및 5°C hysteresis로 overheat를 판단한다. 차량용 프로젝트에서는 이 hard limit에 닿기 전에 선제적으로 power를 낮추는 정책을 목표로 한다.

---

## 6. 팬소음 — 이 차량에서의 목표

조수석 하부는 cabin과 직접 연결된 공간이므로 thermal management가 곧 noise management다.

권장 우선순위:

1. GPU PPT 최적화
2. hot-air recirculation 차단
3. 큰 저RPM auxiliary fan
4. vibration isolation
5. 마지막에만 부분적인 acoustic treatment

### PPT sweep

```text
132 → 120 → 110 → 100 → 90 W
```

각 step에서:

- p50/p95/p99 inference latency
- frame drop
- GPU hotspot
- memory temperature
- fan RPM
- cabin dBA
- power draw

를 기록한다.

현재 model loop는 20 Hz이므로 nominal period는 50 ms다. 실제 end-to-end deadline margin을 만족하는 가장 낮은 PPT가 이 싼타페용 `quiet/efficient operating point`가 된다.

---

## 7. 최종 권장 패키지

### 초기 검증 패키지

```text
comma four (windshield)
      │
      │ 3 m USB3
      ▼
Chestnut + RX 9060
(passenger footwell, rigid temporary tray)
      │
      ▼
OEM 12 V outlet
```

### 최종 상시 패키지

```text
comma four
   │ routed USB3
   ▼
Passenger-seat-under independent tray
   ├─ front/cabin intake
   ├─ rear/side exhaust
   ├─ rigid retention
   ├─ vibration isolator
   ├─ strain relief
   └─ telemetry logging

Power:
OEM 180 W outlet if validated stable
OR
Dedicated automotive protected feed if tests show need
```

---

## 8. 다음 실차 확인 항목

아직 확정되지 않은 항목은 실제 차량에서 사진/측정 후 결정한다.

- 5인승 / 7인승
- 2WD / HTRAC
- 조수석 전동/통풍시트 실제 구성
- 조수석 하부 모듈/하네스 배치
- 시트 레일 간 폭과 가용 높이
- center console → passenger-seat-under cable route
- 12 V outlet 실제 위치와 plug clearance
- comma four → GPU 실제 USB routing length
- GPU 장착 후 시트 full-travel clearance

**이 항목을 측정하기 전에는 브래킷 치수, fuse ampere, wire gauge를 확정하지 않는다.**

---

## 9. 다음 개발/측정 순서

1. stock Chestnut + RX 9060으로 bench/vehicle telemetry logger 준비
2. 조수석 발밑 임시 장착
3. 정상시동/ISG/원격시동 power-sequence 기록
4. 30/60/120분 thermal soak test
5. PPT sweep와 fan RPM/dBA/latency 측정
6. 조수석 하부 실측
7. 최종 bracket CAD 설계
8. 장기 주행 vibration/USB-link validation
9. 전용 전원 필요 여부 최종 결정

---

## Sources

- Hyundai 2021 Santa Fe: https://www.hyundai.com/kr/ko/brand/brandstory/model/santafe-history/2021-santafe
- Hyundai power outlet guidance: https://ownersmanual.hyundai.com/
- Hyundai certified used vehicle example, 2021 Santa Fe TM D2.2 Prestige: https://certified.hyundai.com/
- comma Chestnut: https://blog.comma.ai/chestnut/
- Chestnut product/setup: https://comma.ai/shop/chestnut
- AMD RX 9060: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
- openpilot Chestnut status: https://github.com/commaai/openpilot/blob/master/openpilot/system/hardware/chestnut/status.py
- openpilot modeld: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/modeld.py
- openpilot issue #38685: https://github.com/commaai/openpilot/issues/38685
- tinygrad AMD power control: https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/support/am/ip.py
