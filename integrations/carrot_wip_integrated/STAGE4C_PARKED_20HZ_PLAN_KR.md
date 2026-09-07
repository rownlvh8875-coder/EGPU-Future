# Stage 4C — Parked 20 Hz Temporal Comparison Plan Gate

작성일: 2026-09-07

## 목적

S4B의 parked 5 Hz load probe가 실제 장비에서 **명시된 interference policy를 통과한 경우에만** 다음 정차 20 Hz 실험계획을 만들 수 있게 한다.

S4C는 현재 **plan-only**다.

```text
S4B 실제 실측
   |
   +-- FAIL/HOLD -> S4C 계획 생성 금지
   |
   +-- PASS
         + source compatibility 재확인
                |
                v
        S4C parked 20 Hz PLAN
```

## 왜 20 Hz인가

5 Hz shadow는 temporal hidden-state sequence가 active 20 Hz 모델과 달라 모델 품질을 공정하게 비교할 수 없다.

S4C에서는 active와 shadow가 동일한 20 Hz camera sequence를 연속 처리하는 조건을 처음 검토한다.

그러나 20 Hz라고 자동으로 비교 가능한 것은 아니다.

최소 다음이 필요하다.

- exact frameId pairing
- consecutive temporal continuity
- frame freshness
- non-finite output 없음
- active-path interference 허용범위 내
- active eGPU fallback 없음

## S4B PASS 요구조건

S4B qualification은 임의 숫자를 내장하지 않는다.

반드시 실험자가 명시한 interference limits와 S4B policy가 있어야 한다.

S4B gate가 확인하는 예:

- active eGPU p99/max latency 증가
- deadline miss delta
- frameAge/frame gap delta
- 충분한 5 Hz shadow run sample
- shadow error/guard stop
- 새 USB link error
- supply fault
- active eGPU fallback
- source restore

기준 미지정 또는 evidence 부족은 `HOLD`다.

## S4C 계획 강제조건

`S4CConfig`는 다음을 강제한다.

```text
hz = exactly 20.0
manual_start = true
manager_autostart = false
stationary_only = true
controls_inactive_required = true
controls_publish = false
```

20 Hz 이외 값은 plan validation error다.

## temporal settle

기본 `settle_frames=40`이다.

S4C 실행을 나중에 구현하더라도 첫 40개의 연속 frameId가 확보되기 전에는 behavioral comparison을 `eligible`로 만들지 않는다.

중간 frame gap이 생기면 continuity를 reset하는 방향을 유지한다.

40은 현재 연구용 초기값이며 안전 임계값이 아니다.

## 금지사항

S4C plan에는 다음을 명시적으로 금지한다.

- public-road 실행
- shadow의 modelV2/controls publish
- manager 자동실행 등록
- YOLO/RoadSeg/다른 QCOM workload 동시실행
- 자동 model hot-swap
- steering/braking authority 변경

## 출력 권한

계획 파일에는 항상:

```text
controlAuthorization = false
publicRoadAuthorization = false
```

가 기록된다.

따라서 S4C 계획 생성 성공은 정차 20 Hz **수동 연구시험의 계획 준비**만 의미한다.

## 도구

```text
tools/build_carrot_wip_s4c_plan.py
```

입력:

```text
s4b_qualification.json
+ current source compatibility 확인
```

예정 사용형태:

```bash
python3 tools/build_carrot_wip_s4c_plan.py \
  s4b_qualification.json \
  --source-compatible \
  --duration 60 \
  --settle-frames 40 \
  --output s4c_plan.json
```

`--source-compatible`는 자동 추정이 아니라, 바로 직전에 별도 source compatibility 검사를 수행했다는 명시적 assertion이다.

## 다음 단계

S4B 실제 장비 결과 없이 S4C runner를 구현하지 않는다.

S4B가 실제 PASS한 뒤:

1. S4C plan 생성
2. 현재 Carrot source 재검토
3. exact 20 Hz shadow runner 구현/검토
4. 정차에서만 실행
5. active interference + temporal continuity 검증
6. 그 후에만 BIG/SMALL behavioral evidence를 비교한다.
