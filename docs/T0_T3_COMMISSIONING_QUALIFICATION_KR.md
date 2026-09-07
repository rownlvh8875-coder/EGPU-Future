# T0~T3 Commissioning Qualification

작성일: 2026-09-07

## 목적

Carrot eGPU에 shadow inference를 추가하기 전에 **metadata tap 자체가 active driving model을 방해하지 않는지** 단계별로 검증한다.

단계:

```text
T0 original baseline
 → T1 patch installed, tap disabled
 → T2 tap enabled, receiver absent
 → T3 tap enabled + receiver only, no inference
 → explicit stage gate
 → T4 5 Hz shadow inference
 → T5 20 Hz continuous shadow
```

T0~T3에서는 second-small inference를 실행하지 않는다.

---

# 1. 권장 실행: one-command runner

`tools/commission_t0_t3.py`는 T0~T3를 한 번의 commissioning 흐름으로 수행한다.

기본 실행은 **preflight only**이며 파일을 바꾸지 않는다.

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 /path/to/EGPU-Future/tools/commission_t0_t3.py \
  /path/to/ajouatom-openpilot
```

실제 실행은 ignition ON 상태에서 차량을 **P단 정차**, selfdrive 비활성으로 유지한 뒤 명시적으로 `--run`을 붙인다.

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 /path/to/EGPU-Future/tools/commission_t0_t3.py \
  /path/to/ajouatom-openpilot \
  --run
```

기본 stage duration은 60초다. 실험 정책이 준비되어 있으면:

```bash
... commission_t0_t3.py /path/to/openpilot \
  --run \
  --limits /path/to/commissioning_limits.json
```

정책 파일이 없으면 최종 qualification은 의도적으로 `HOLD`다.

## runner가 자동 수행하는 일

```text
preflight
 → T0 active-model baseline
 → tap patch 적용
 → modeld restart
 → T1 patch installed / tap OFF
 → control-file 생성
 → T2 tap ON / receiver 없음
 → T3 receiver 시작 / inference 없음
 → qualification report
 → control-file 삭제
 → 원본 modeld.py 복원
 → integration runtime 삭제
 → modeld restart
 → git blob/cleanliness 재검증
```

기본값은 시험 종료 후 **원본 복원**이다. `--keep-patch`는 연구자가 의도적으로 남길 때만 사용한다.

---

# 2. 안전 guard

runner는 stage 전체에서 다음을 반복 확인한다.

- `abs(vEgo) <= 0.10 m/s`
- `carState.standstill == true`
- `selfdriveState.active == false`
- gear 정보가 확인 가능하면 `P/park`
- `UsbGpuActive == true`
- modeld가 manager에서 실행 중

하나라도 깨지면 시험은 `ABORTED` 처리하고, 이미 patch를 적용했다면 best-effort rollback을 수행한다.

이 도구는 **주행 중 사용을 위한 자동화가 아니다.** 정차 commissioning에서만 사용한다.

---

# 3. dynamic tap control

Carrot tap runtime은 이제 두 방식으로 enable할 수 있다.

1. process 시작 시 `EGPU_FUTURE_SHADOW_TAP=1`
2. 기본 control file 생성:

```text
/tmp/egpu_future_shadow_tap.enable
```

runner는 두 번째 방식을 사용한다. tap runtime은 control file을 저주기로 polling하므로 T1→T2→T3 전환마다 modeld를 재시작하지 않는다.

patch된 `modeld.py`는 `prepare_only == false`일 때만 `shadow_tap.send()`를 호출한다. sender 내부에서 disabled 상태면 즉시 return하고, enabled 상태에서 receiver가 없거나 queue가 가득 찬 경우에도 retry/wait하지 않는다.

T1은 이 disabled-path 함수 호출 자체의 비용까지 포함해서 측정한다.

---

# 4. source integrity / rollback

runner는 적용 전 다음을 검사한다.

- target `modeld.py` git blob이 리뷰된 값과 일치
- `modeld.py` / tap runtime target이 dirty하지 않음
- 기존 EGPU-Future marker가 없음
- runtime target 파일이 기존에 존재하지 않음
- patch marker 제거 시 원본 `modeld.py` byte-for-byte 복원 가능

Carrot branch HEAD는 문서-only commit으로 자주 움직이므로 runner에서는 **`modeld.py` blob을 hard boundary**로 사용하고, HEAD는 manifest에 기록한다. `modeld.py` blob이 달라지면 실행을 거부한다.

시험 전 원본 `modeld.py`는 output directory의 `backup/modeld.py.original`에 저장된다.

---

# 5. 출력 구조

기본적으로 `/data`가 있으면:

```text
/data/egpu_future/commissioning/<UTC timestamp>/
```

에 저장한다. 그렇지 않으면 현재 디렉터리의 `commissioning_runs/`를 사용한다.

주요 산출물:

```text
manifest.json
T0.jsonl
T1.jsonl
T2.jsonl
T3.jsonl
T3_tap.jsonl
T3_tap_summary.json
commissioning_qualification.json
commissioning_qualification.md
backup/modeld.py.original
```

`manifest.json`에는:

- Carrot HEAD
- reviewed HEAD
- modeld blob
- patch/runtime SHA256
- modeld restart old/new PID
- stage별 sample/continuity
- rollback 결과
- qualification 상태

가 기록된다.

---

# 6. 수동 분석 경로

기존 수동 방식도 유지한다.

Carrot는 `modelV2.big`을 명시하지 않으므로 eGPU active가 독립적으로 확인된 commissioning 구간은 로그 추출 시 다음처럼 라벨링할 수 있다.

```bash
python3 tools/extract_model_actions_from_log.py <log> \
  --backend-label big \
  --output t0_active.jsonl
```

fallback이 섞인 일반 route 전체에 `--backend-label big`을 사용하지 않는다.

one-command runner는 live `UsbGpuActive` Param을 주기적으로 확인해서 각 row의 `big` 필드를 설정한다. eGPU가 fallback하면 stage를 계속 big으로 오라벨링하지 않고 시험 자체를 중단한다.

---

# 7. T3 tap receiver

T3에서는 inference 없이 receiver만 실행한다.

```bash
python3 tools/shadow_tap_receiver_probe.py \
  --duration 120 \
  --output /tmp/t3_tap.jsonl \
  --summary-output /tmp/t3_tap_summary.json
```

summary에는 다음이 기록된다.

- packets received
- records saved
- superseded packets
- decode errors
- frame gap
- duplicate/old transitions
- sender-created timestamp → receiver timestamp transport latency p50/p95/p99/max

`supersededPackets`는 latest-only 정책 때문에 반드시 0이어야 하는 값은 아니다. 반면 decode error는 protocol 문제로 취급한다.

---

# 8. Stage Gate policy

프로젝트는 임의의 공식 safety threshold를 만들지 않는다.

실험 책임자가 다음 값을 JSON으로 명시한다.

```json
{
  "minSamplesEach": 100,
  "maxP99IncreaseMs": 0.0,
  "maxMaxIncreaseMs": 0.0,
  "maxDeadlineMissRateDelta": 0.0,
  "maxFrameAgeGt1Delta": 0,
  "maxFrameGapCountDelta": 0
}
```

위 숫자는 **형식 예시일 뿐 권장값이 아니다.** 실제 값은 baseline과 제어 요구조건을 보고 별도로 결정한다.

정책이 없으면 `HOLD`, 샘플 부족도 `HOLD`, 명시 limit 초과는 `FAIL`, 모든 조건 충족만 `PASS`다.

---

# 9. 자동 qualification report

수동 산출물에서도 다음 도구를 사용할 수 있다.

```bash
python3 tools/build_commissioning_report.py \
  --t0 t0_active.jsonl \
  --t1 t1_active.jsonl \
  --t2 t2_active.jsonl \
  --t3 t3_active.jsonl \
  --t3-tap-summary /tmp/t3_tap_summary.json \
  --limits commissioning_limits.json \
  --json-output commissioning_qualification.json \
  --md-output commissioning_qualification.md
```

출력 Markdown에는 phase별:

- PASS / HOLD / FAIL
- sample 수
- active model p99/max
- gate reason
- T3 tap receiver 상태

가 한 장으로 정리된다.

---

# 10. T3 PASS 후

T3가 PASS일 때만 T4 5 Hz shadow inference를 검토한다.

T4부터는 QCOM/tinygrad hardware profile을 함께 사용한다.

```bash
PROFILE=1 python3 tools/shadow_modeld_prototype.py --max-hz 5 ...
```

그리고:

```bash
python3 tools/correlate_shadow_tinygrad_profile.py shadow.jsonl profile.pkl
```

로 host model-call과 QCOM hardware kernel timeline을 분리한다.

---

# 11. 현재 안전 경계

T0~T3 qualification이 PASS해도 다음을 의미하지 않는다.

- 5 Hz shadow가 안전함
- 20 Hz shadow가 안전함
- active big + second-small 동시 실행이 안전함
- public-road 자동 활성화가 가능함

각 단계는 다음 단계에 들어갈 **실험 진입조건**일 뿐이다.
