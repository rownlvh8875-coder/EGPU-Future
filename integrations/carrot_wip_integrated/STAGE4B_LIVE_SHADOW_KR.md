# Stage 4B — Parked 5 Hz Live Shadow Load Probe

작성일: 2026-09-07

## 목적

S4A Guardian 계약 다음 단계로 실제 Carrot active eGPU modeld와 별도 QCOM small-model process를 동시에 실행할 수 있는 골격을 만든다.

그러나 **첫 S4B는 모델 품질 비교가 아니다.**

```text
목적 = second QCOM inference가 active eGPU path에 주는 간섭 측정

아님 = BIG vs SMALL 누가 더 잘 운전하는지 판단
```

## 왜 5 Hz 결과로 품질 비교를 하지 않는가

Driving model은 hidden state / temporal context를 가진다.

active model이 20 Hz로 다음 sequence를 처리할 때:

```text
F0 F1 F2 F3 F4 F5 ...
```

5 Hz shadow는 대략:

```text
F0          F4          F8 ...
```

만 처리하게 된다.

따라서 shadow hidden state가 active 20 Hz 모델과 다른 history를 가지며 action 차이를 모델 자체의 우열로 해석할 수 없다.

그래서 S4B output은 항상:

```text
qualityComparisonEligible = false
controlEligible = false
shadowOnly = true
```

이다.

## Tap protocol v2

기존 metadata 외에 다음 stationary/control evidence를 추가한다.

- `v_ego`
- `standstill`
- `gear`
- `lat_active`
- `long_active`

packet을 보내는 조건:

```text
standstill == true
abs(vEgo) < 0.01 m/s
gear == park
latActive == false
longActive == false
```

sender와 receiver 모두 같은 guard를 적용한다.

한 조건이라도 깨지면 shadow work를 생성하지 않는다.

## active-path 보호

### modeld sender

`IntegratedShadowTap.send()`는:

- AF_UNIX datagram
- nonblocking
- retry 없음
- receiver 없음 -> drop
- packet encode 오류 -> drop

이다.

send 결과는 modeld control flow에서 사용하지 않는다.

### receiver

receiver는 queue를 쌓지 않고 현재 socket에 온 packet 중 가장 최신 것만 남긴다.

```text
old pending packet
  -> superseded
  -> newest only
```

Carrot YOLO2의 bounded/latest-only 철학과 동일한 방향이다.

## modeld patch layering

```text
reviewed carrot-wip
  -> S1 observer
  -> S2 telemetry
  -> S4B parked shadow tap
```

S4B는 다음 세 marker만 추가한다.

1. import
2. tap construction
3. model.run 직전 best-effort metadata send

S4B marker 제거 후 S2 source가 byte-for-byte 복원되어야 한다.
S2/S1까지 제거하면 reviewed Carrot modeld 원본으로 복원되어야 한다.

## Shadow probe

도구:

```text
tools/carrot_wip_s4b_shadow_probe.py
```

강제 조건:

- manual start only
- manager autostart 금지
- max 5 Hz
- max 300 s
- QCOM shadow only
- active backend가 eGPU가 아니면 skip
- no PubMaster
- no `modelV2`
- no controls publish
- PROFILE=1 default
- lower-priority nice increment default +10

출력 예:

```json
{
  "type": "load_probe",
  "stage": "S4B-load-probe",
  "frameId": 1234,
  "activeBackend": "egpu",
  "shadowBackend": "qcom",
  "modelCallMs": 34.2,
  "cameraEofToDoneMs": 51.8,
  "shadowOnly": true,
  "controlEligible": false,
  "qualityComparisonEligible": false
}
```

숫자는 schema 예시다.

## S4B admission

`runtime/s4b_commissioning.py`는 다음을 모두 요구한다.

- T4 readiness evidence = PASS
- current source = reviewed compatible
- P
- standstill
- vEgo < 0.01 m/s
- lat/long controls inactive
- maxHz <= 5
- manual start
- no manager autostart
- controls publish disabled

S4B admission PASS도 차량제어 승인이 아니다.

```text
controlAuthorization = false
```

## 실기기 시험 순서

```text
A. active eGPU baseline, shadow OFF
B. S4B tap ON, receiver only
C. S4B QCOM shadow 5 Hz + PROFILE=1
D. shadow stop
E. active eGPU post baseline
F. active OFF/ON interference 비교
G. QCOM tinygrad kernel profile correlation
H. tap source restore + reboot
```

중간 중지조건:

- 차량 이동
- P 해제
- latActive/longActive true
- eGPU fallback
- active model latency tail anomaly
- frame gap 증가
- USB link error 증가
- thermal/power fault
- shadow exception

## S4B 성공 후에도 바로 20 Hz로 가지 않는다

S4B가 정상이어도 의미는:

```text
"parked 5 Hz second-QCOM load가 관측상 감당 가능했다"
```

뿐이다.

다음 단계 S4C에서 정차 20 Hz continuous shadow가 active path를 방해하지 않는지 별도로 검증한 뒤에야 temporal comparison eligibility를 검토한다.

public-road shadow는 그보다 훨씬 뒤 단계다.
