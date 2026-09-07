# Chestnut GPU / eGPU Dock 호환성 분석

작성일: 2026-09-07

---

## 1. 결론

**RX 9060과 comma Ready-to-Drive 구성만 사용 가능한 것은 아니다.**

comma 공식 상품 페이지는 Chestnut을 두 가지로 판매한다.

1. `ready to drive` — Chestnut + AMD Radeon RX 9060 8GB + 3 m USB3 + 12 V car power cable + mounting hardware
2. `eGPU dock only` — **사용자가 자신의 GPU와 power supply를 연결할 수 있는 구성**

따라서 GPU 자체는 반드시 RX 9060이어야 하는 것은 아니다.

하지만 현재 openpilot Chestnut big-model 구현은 **generic eGPU 표준이 아니라 Chestnut USB firmware + tinygrad의 `USB+AMD:LLVM` backend + AMD SMU telemetry**를 전제로 한다.

따라서 호환성을 세 단계로 구분해야 한다.

| 등급 | 구성 | 판단 |
|---|---|---|
| A | Chestnut + RX 9060 8GB | 공식 Ready-to-Drive, 기준 구성 |
| B | Chestnut + 다른 AMD GPU | 공식적으로 own GPU 사용 가능하지만 각 GPU의 실차 openpilot 성능/전력은 개별 검증 필요 |
| C | 일반 eGPU dock + AMD/NVIDIA GPU | PC에서는 가능할 수 있어도 현재 openpilot Chestnut 경로의 plug-and-play 대체물로 확인되지 않음 |

---

## 2. 왜 Chestnut dock이 단순한 PCIe riser와 다른가

Chestnut은 USB-to-PCIe bridge와 custom open-source firmware를 사용하고, comma four가 이를 특정 USB device로 인식한다.

현재 openpilot `usb.py`에는 Chestnut USB ID가 명시되어 있다.

```python
CHESTNUT_USB_IDS = ((0xADD1, 0x0001), (0x3801, 0x0001))
CHESTNUT_ROM_USB_IDS = ((0x174C, 0x2464), (0x174C, 0x2463))
```

그리고 `deviceState.chestnutPresent`는 이 ID로 결정된다.

즉 generic USB4 eGPU enclosure를 comma four에 꽂는다고 openpilot이 자동으로 Chestnut으로 인식하지는 않는다.

출처:
- https://github.com/commaai/openpilot/blob/master/openpilot/common/hardware/usb.py

---

## 3. 현재 openpilot big-model 경로는 AMD에 강하게 묶여 있음

현재 `openpilot/selfdrive/modeld/SConscript`의 Chestnut compile flags:

```text
DEV=USB+AMD:LLVM
FRAME_DEV=CPU
FLOAT16=1
...
```

즉 big model은 tinygrad의 USB + AMD backend를 명시적으로 사용한다.

또한 `modeld.py` Chestnut telemetry도 다음과 같이 AMD device를 직접 읽는다.

```python
Device["AMD"]
```

여기서 읽는 항목:

- GPU hotspot temperature
- memory temperature
- power draw
- power limit
- GPU activity
- GPU clock
- fan RPM
- PCIe state

따라서 NVIDIA 카드로 바꾸려면 단순히 PCIe에 꽂는 것만으로 끝나지 않는다.

필요 가능성이 있는 작업:

- tinygrad backend 변경
- big-model compile flags 변경
- device discovery 변경
- thermal/power telemetry adapter
- power-limit controller 변경
- watchdog/fault-path 수정
- 성능/latency 재검증

즉 **NVIDIA가 물리적으로 PCIe에서 동작할 수 있는가**와 **현재 openpilot Chestnut release가 이를 지원하는가**는 전혀 다른 문제다.

---

## 4. 다른 AMD GPU는 가능한가

### Fact

comma 공식 상품 페이지는 `eGPU dock only`에 대해 `Use chestnut with your own GPU and power supply`라고 명시한다.

따라서 다른 GPU를 사용하는 것 자체는 제품 설계 목적에 포함된다.

### 하지만 openpilot 실차용은 별도 문제

GPU를 바꾸면 다음이 달라진다.

- VRAM
- memory bandwidth
- FP16/FP8 throughput
- tinygrad kernel 성능
- model compile 시간
- inference latency
- PCIe/USB behavior
- idle/peak power
- fan curve
- card dimensions

따라서 `AMD이면 다 된다`고 단정할 수 없다.

### 권장 후보 선정 기준

우선순위:

1. tinygrad AMD backend에서 안정적으로 인식
2. big model compile 성공
3. 20 Hz model loop deadline에 충분한 margin
4. vehicle power budget 안에 들어옴
5. fan RPM/열이 실내 설치에 적합
6. 카드 크기가 조수석 하부 설치 envelope 안에 들어옴

---

## 5. RX 9060보다 낮은 전력 GPU를 쓰는 이유

자동차에서는 최고 benchmark score보다 **compute/W와 thermal/noise**가 더 중요할 수 있다.

예를 들어 어떤 저전력 AMD 카드가 big model을 충분한 margin으로 20 Hz에 맞춘다면:

- outlet 전류 감소
- DC/DC 열 감소
- GPU fan RPM 감소
- 여름 cabin heat soak margin 증가
- 작은 enclosure 사용 가능
- 장기 신뢰성 증가

따라서 EGPU-Future에서는 RX 9060을 reference baseline으로 두고 다음 metric으로 다른 AMD GPU를 평가한다.

```text
score =
  deadline_margin
  × performance_per_watt
  × thermal_margin
  × acoustic_margin
  × compatibility_reliability
```

가격이나 FLOPS 하나만으로 선택하지 않는다.

---

## 6. 더 강한 GPU가 항상 좋은가

아니다.

더 높은 GPU는 보통:

- 더 큰 TBP
- 더 큰 냉각기
- 더 높은 순간전류
- 더 큰 physical volume
- 더 높은 fan/noise 가능성

을 동반한다.

차량에서는 180 W accessory outlet을 넘어가는 GPU를 사용하면 별도의 dedicated high-power path가 필요해질 가능성이 높다.

또한 big model이 현재 20 Hz에서 충분히 돌아간다면 여분 FLOPS는 주행품질에 직접 기여하지 않을 수 있다.

따라서 먼저 RX 9060을 power-limit sweep해 **실제 최소 안정 전력점**을 찾는 것이 다른 GPU 구매보다 우선이다.

---

## 7. 일반 USB4/Thunderbolt eGPU dock은 가능한가

### PC에서는

Chestnut 자체도 공식적으로 USB4 PC dock으로 사용할 수 있고, 일반 eGPU enclosure도 PC 생태계에서는 흔하다.

### comma four + openpilot에서는

현재 조사한 openpilot master 기준:

- Chestnut-specific USB IDs 확인
- Chestnut firmware 상태 확인
- USB speed 확인
- PCIe LTSSM 확인
- `USB+AMD:LLVM` backend 사용
- Chestnut-specific power telemetry 사용

이 존재한다.

따라서 일반 dock을 꽂는 것만으로는 현재 release의 Chestnut path를 그대로 통과하지 않는다.

### 가능성을 완전히 배제할 수는 없음

openpilot과 tinygrad는 open source이므로:

- generic bridge driver
- device detection abstraction
- generic AMD eGPU backend
- telemetry plugin

을 만들어 다른 dock을 지원하는 연구는 가능하다.

하지만 이는 `비용절감 액세서리 교체` 수준이 아니라 **새 hardware backend 개발**로 보는 것이 정확하다.

---

## 8. 왜 $249 Chestnut dock을 그대로 쓰는 것이 현재는 합리적인가

3rd-party dock으로 절약 가능한 비용보다 다음 engineering cost가 더 클 수 있다.

- firmware compatibility
- ARM/Snapdragon USB behavior
- 5 Gbps link reliability
- reboot/reconnect
- PCIe reset
- power sequencing
- telemetry
- openpilot detection
- vibration/automotive cabling

따라서 EGPU-Future 초기 단계에서는:

```text
Chestnut dock 고정
GPU만 변경 실험
```

이 변수 통제가 더 좋다.

Dock까지 동시에 바꾸면 GPU 성능 문제와 USB/firmware 문제를 구분하기 어렵다.

---

## 9. 권장 실험 순서

### Stage 1

**공식 RX 9060 + Chestnut**

baseline 수집:

- model compile
- p50/p95/p99 inference latency
- power
- temp
- fan RPM
- USB link errors
- reconnect

### Stage 2

**동일 Chestnut dock + 다른 AMD GPU**

목표:

- 성능/W
- 소음
- 열
- 전원

비교

### Stage 3

**RX 9060 power-limit optimization**

132 W 기준에서 점진적으로 PPT를 낮추며 최소 안정전력점 탐색.

### Stage 4

**generic dock 연구**

이 단계에서만 generic USB4/eGPU adapter를 연구한다.

필요 산출물:

- device abstraction
- hotplug state machine
- generic power telemetry
- link/reset recovery
- fault injection test

---

## 10. 권장 Compatibility Matrix

향후 저장소에서 다음 CSV/JSON 형식으로 실제 결과를 누적한다.

| Dock | GPU | Power limit | Big model compile | p99 latency | Temp | Fan RPM | USB reconnect | Verdict |
|---|---|---:|---|---:|---:|---:|---|---|
| Chestnut | RX 9060 8GB | stock | TBD | TBD | TBD | TBD | TBD | baseline |
| Chestnut | RX 9060 8GB | 120 W | TBD | TBD | TBD | TBD | TBD | test |
| Chestnut | RX 9060 8GB | 100 W | TBD | TBD | TBD | TBD | TBD | test |
| Chestnut | other AMD | TBD | TBD | TBD | TBD | TBD | TBD | research |
| generic dock | AMD | TBD | TBD | TBD | TBD | TBD | TBD | unsupported research |

---

## 11. 현재 추천

현재 시점에는 다음이 가장 합리적이다.

**Dock:** comma Chestnut 유지

**GPU:** RX 9060을 baseline으로 시작

**첫 최적화:** GPU 교체가 아니라 RX 9060 PPT reduction

**그 다음:** 동일 Chestnut에서 더 저전력 AMD GPU 비교

**마지막:** generic dock 연구

이 순서가 가장 빠르게 차량용 저소음/저발열 최적점을 찾으면서 software 변수도 통제할 수 있다.

---

## Sources

- comma Chestnut shop: https://comma.ai/shop/chestnut
- Chestnut launch: https://blog.comma.ai/chestnut/
- openpilot USB device detection: https://github.com/commaai/openpilot/blob/master/openpilot/common/hardware/usb.py
- openpilot Chestnut model compile: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/SConscript
- openpilot Chestnut runtime: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/modeld.py
- tinygrad AMD runtime: https://github.com/tinygrad/tinygrad/tree/master/tinygrad/runtime
- community 3rd-party discussion: https://www.reddit.com/r/Comma_ai/comments/1vwmf4p/anyone_likely_to_build_a_3rd_party_chestnut/
