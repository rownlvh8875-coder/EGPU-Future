# Chestnut Adaptive Power / Thermal / Noise Control 설계안

작성일: 2026-09-07

이 문서는 차량 eGPU에서 **전력·발열·팬소음과 inference deadline을 동시에 최적화**하기 위한 구체적인 software control 방향을 정리한다.

---

# 1. 핵심 발견

현재 openpilot과 tinygrad 소스코드를 함께 보면 필요한 primitive가 이미 상당 부분 존재한다.

## openpilot이 현재 읽을 수 있는 값

`ChestnutState`:

- GPU hotspot temperature
- memory temperature
- GPU power draw
- current power limit
- GPU utilization
- GPU clock
- fan RPM
- PCIe link state
- supply voltage/current/fault

## tinygrad가 현재 제공하는 기능

AMD SMU implementation에는 다음 method가 존재한다.

```python
def set_power_limit(self, watts: float):
    ...
    PPSMC_MSG_SetPptLimit
```

즉 Chestnut/tinygrad stack에는 **GPU PPT를 software에서 변경할 수 있는 기반**이 이미 존재한다.

현재 조사한 openpilot master의 Chestnut code는 이 method를 적극적인 thermal/noise controller로 사용하지 않고 telemetry를 읽는 쪽에 집중돼 있다.

---

# 2. 이것이 중요한 이유

팬소음 문제를 hardware fan 추가로만 해결하면 다음 악순환이 생길 수 있다.

```text
high GPU power
 → high heat
 → high GPU fan RPM
 → noise
 → auxiliary fan 추가
 → system power 증가
 → additional noise/heat
```

더 좋은 순서는:

```text
required model latency 확인
 → 필요한 최소 GPU power 탐색
 → 발생 열 자체 감소
 → fan RPM 감소
 → 필요할 때만 airflow 보조
```

이다.

---

# 3. 현재 timing budget

openpilot current constants 기준:

```text
MODEL_RUN_FREQ = 20 Hz
MODEL_CONTEXT_FREQ = 5 Hz
```

따라서 model output loop의 nominal period는:

```text
1 / 20 = 50 ms
```

### 주의

50 ms 전체를 GPU inference에 사용할 수 있다는 뜻은 아니다.

실제 path에는:

```text
camera capture
→ copy/preprocess
→ USB transport
→ GPU inference
→ output copy
→ parsing
→ control
```

가 포함된다.

따라서 EGPU-Future의 power optimization은 **GPU 평균 FPS가 아니라 p95/p99 end-to-end latency와 frame drop**을 기준으로 해야 한다.

---

# 4. Power-limit Sweep Test

## 목적

RX 9060의 default PPT가 실제 openpilot big-model inference에 필요한 최소 power인지 확인한다.

## 방법

차량 actuator와 연결하지 않은 bench/replay/shadow 환경에서:

1. current/default `powerLimitW` 기록
2. big model warm-up
3. 일정 workload로 inference 실행
4. power limit을 단계적으로 낮춤
5. 각 단계마다 아래를 기록

```text
PPT setting
actual powerDrawW
GPU hotspot
memory temperature
fan RPM
GPU clock
average inference latency
p95 latency
p99 latency
frame drop rate
model output numerical validity
```

### 권장 sweep

고정 숫자를 production setting으로 가정하지 않는다.

예:

```text
default PPT
→ default - 10 W
→ default - 20 W
→ ...
```

각 GPU firmware가 허용하는 범위 안에서만 진행한다.

## 초기 engineering pass criterion

20 Hz loop가 50 ms이므로 초기 연구용 목표로:

- p99 model execution이 nominal cycle의 80% 미만
- 즉 약 **40 ms 이하**를 우선 목표
- frame drop 증가 없음
- numerical error 없음

을 사용할 수 있다.

**40 ms는 openpilot 공식 기준이 아니라 EGPU-Future의 초기 margin이며, 실제 end-to-end 측정 결과로 수정해야 한다.**

---

# 5. 추천 Operating Modes

## FULL

- GPU default PPT
- 최대 model capability
- benchmark/reference mode

## BALANCED

- 자동 sweep에서 확인된 lowest stable PPT보다 일정 margin을 둔 값
- 기본 daily-driving 후보

## QUIET

- cabin noise를 우선
- deadline margin이 충분한 경우 추가 PPT 감소
- fan RPM과 p99 latency를 동시에 감시

## THERMAL-DERATE

- 장시간 고온일 때 workload/PPT 축소
- quality보다 stable operation 우선

## FALLBACK

- thermal/power/link/deadline fault
- small model 사용

---

# 6. Temperature 정책

현재 openpilot Chestnut status hard threshold:

```text
GPU_TEMP_LIMIT = 100 °C
MEMORY_TEMP_LIMIT = 95 °C
TEMP_HYSTERESIS = 5 °C
```

이 값은 현재 openpilot source의 값이다.

EGPU-Future는 공식 hard alert threshold를 바로 변경하는 대신 더 이른 **soft control threshold**를 별도 사용한다.

## 초기 연구용 예시

```text
GPU soft warning     = hard limit - 15 °C ≈ 85 °C
GPU derate           = hard limit - 10 °C ≈ 90 °C

Memory soft warning  = hard limit - 15 °C ≈ 80 °C
Memory derate        = hard limit - 10 °C ≈ 85 °C
```

이 값은 production requirement가 아니다. hot-soak 실차 데이터와 board별 특성에 따라 다시 정해야 한다.

목적은 100/95 °C에 도달한 뒤 대응하는 것이 아니라 **도달하기 전에 compute와 airflow를 조절**하는 것이다.

---

# 7. 추천 Adaptive Controller

```text
                 ┌──────────┐
                 │  NORMAL  │
                 └────┬─────┘
                      │ sustained heat/noise
                      ▼
                 ┌──────────┐
                 │  DERATE  │
                 └────┬─────┘
                      │
          recovered   │   latency/fault/continued heat
        ┌─────────────┘              │
        ▼                            ▼
     NORMAL                     FALLBACK
                                   │
                            small model active
                                   │
                            safe retry condition
                                   ▼
                               RECOVERY
```

## Inputs

- `tempC`
- `memoryTempC`
- `powerDrawW`
- `powerLimitW`
- `fanSpeedRpm`
- `gpuUsagePercent`
- `gpuClockMhz`
- `supplyVoltage`
- `supplyCurrent`
- `supplyFault`
- `pcieLtssm`
- inference p95/p99
- frame drop

## Outputs

- target PPT
- big/small model state
- retry permission
- thermal/fault log

---

# 8. Controller가 해야 하지 말아야 할 것

1. 매 frame마다 PPT를 빠르게 변경하지 않는다.
2. 1~2°C 온도 변화만으로 mode를 반복 전환하지 않는다.
3. fan RPM만 보고 power를 낮추지 않는다.
4. latency가 이미 부족한 상태에서 quiet mode를 강제하지 않는다.
5. power fault 후 바로 반복 GPU reset을 하지 않는다.

필요 요소:

- moving average
- hysteresis
- minimum dwell time
- retry backoff
- fault counter

---

# 9. 팬소음 최적화 알고리즘

팬소음에 대한 정확한 dBA spec이 없는 상황에서는 `fanSpeedRpm`을 직접 feedback으로 사용할 수 있다.

예:

```text
if temperature margin 충분
and p99 latency margin 충분
and fan RPM이 일정 시간 높은 상태:
    PPT를 작은 step으로 낮춤

if p99 latency가 threshold 근처:
    PPT를 복구
```

단, GPU fan controller 자체의 hysteresis 때문에 즉시 RPM이 변하지 않을 수 있으므로 수십 초~수분 단위의 thermal response를 평가해야 한다.

---

# 10. Airflow와 Software를 함께 최적화

가장 좋은 quiet mode는 power cap만도, fan만도 아니다.

```text
lower PPT
 + cooler intake air
 + exhaust recirculation 방지
 = lower heatsink temperature
 = lower GPU fan RPM
```

따라서 power sweep은 반드시 설치 위치별로 반복한다.

- passenger footwell
- passenger seat 아래
- HVAC floor airflow on/off

동일 PPT에서도 installation에 따라 fan RPM이 크게 달라질 수 있다.

---

# 11. 저전력 GPU 후보 평가 방식

AMD desktop specification에는 RX 9050이 92 W TBP로 표기돼 있다.

그러나 openpilot Chestnut의 실전 후보가 되려면 다음을 통과해야 한다.

```text
Compatibility Gate
  ↓
Model Load Gate
  ↓
20 Hz Deadline Gate
  ↓
Thermal Gate
  ↓
Noise Gate
  ↓
Driving-quality Gate
```

따라서 "132 W RX 9060보다 92 W RX 9050이 차량용으로 무조건 낫다"고 현재 결론낼 수 없다.

반대로 model deadline을 만족한다면 **낮은 TBP 자체가 차량에서는 매우 큰 장점**이 된다.

---

# 12. 구현 위치 제안

EGPU-Future prototype에서는 upstream openpilot을 바로 수정하기 전에 독립 instrumentation으로 시작한다.

예시 repository layout:

```text
tools/
  chestnut_telemetry_logger.py
  chestnut_power_sweep.py
  chestnut_latency_report.py

analysis/
  power_latency_curve.py
  thermal_fan_curve.py

config/
  chestnut_power_policy.yaml

docs/
  test_results/
```

검증 후 upstream/fork integration 후보:

```text
openpilot/system/hardware/chestnut/
  power_policy.py
  recovery.py
```

단, safety-critical driving loop에 넣기 전 replay/shadow test를 먼저 통과해야 한다.

---

# 13. 최종 목표

최적화 목표는 최대 GPU clock이 아니다.

```text
minimize:
  power + heat + acoustic cost

subject to:
  model quality maintained
  p99 deadline maintained
  frame drop maintained
  fallback reliability maintained
```

즉 차량용 compute의 최적점은:

> **모델 요구조건을 만족하는 가장 낮은 안정 전력점**

이다.

---

# 주요 소스

- openpilot Chestnut telemetry schema: https://github.com/commaai/openpilot/blob/master/openpilot/cereal/log.capnp
- openpilot Chestnut status: https://github.com/commaai/openpilot/blob/master/openpilot/system/hardware/chestnut/status.py
- openpilot model timing constants: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/constants.py
- openpilot modeld: https://github.com/commaai/openpilot/blob/master/openpilot/selfdrive/modeld/modeld.py
- tinygrad AMD SMU `set_power_limit`: https://github.com/tinygrad/tinygrad/blob/master/tinygrad/runtime/support/am/ip.py
- AMD RX 9060 specification: https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060.html
- AMD GPU specification table: https://www.amd.com/en/products/specifications/graphics.html

Last reviewed: 2026-09-07
