# T0~T3 Commissioning Qualification

작성일: 2026-09-07

## 목적

Carrot eGPU에 shadow inference를 추가하기 전에 **metadata tap 자체가 active driving model을 방해하지 않는지** 단계별로 검증한다.

```text
T0 original baseline
 → patch source 준비
 → full device reboot
 → T1 patch loaded, tap disabled
 → T2 tap enabled, receiver absent
 → T3 tap enabled + receiver only, no inference
 → explicit stage gate
 → source restore
 → final reboot 권장
 → T4 5 Hz shadow inference
```

T0~T3에서는 second-small inference를 실행하지 않는다.

---

# 1. 왜 T0와 T1 사이에 재부팅이 필요한가

Carrot manager는 Python process를 `prepare()` 단계에서 미리 import하고, 이후 `modeld` child를 fork한다.

따라서 `modeld.py` 파일을 수정한 뒤 **modeld child PID만 재시작하면 새 source가 import된다고 보장할 수 없다.**

또 현재 `launch_chffrplus.sh`는 `./manager.py` 종료 뒤 자동으로 manager를 다시 실행하지 않고 sleep loop로 들어간다.

그래서 EGPU-Future는 다음 방식을 사용하지 않는다.

```text
patch file
 → kill modeld only
 → patched modeld라고 가정   # 금지
```

정확한 실험 경계는:

```text
T0
 → patch source 작성
 → full device reboot
 → 새 manager가 patched modeld를 import
 → T1
```

이다.

---

# 2. reboot-aware runner

`tools/commission_t0_t3.py`는 세 단계 명령으로 동작한다.

## 2.1 preflight

파일을 수정하지 않는다.

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 /path/to/EGPU-Future/tools/commission_t0_t3.py \
  preflight /path/to/ajouatom-openpilot
```

## 2.2 prepare — T0 + patch source 준비

ignition ON / 차량 P단 정차 / selfdrive 비활성 상태에서 실행한다.

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 /path/to/EGPU-Future/tools/commission_t0_t3.py \
  prepare /path/to/ajouatom-openpilot
```

수행 내용:

```text
stationary/eGPU preflight
 → T0 live modelV2 측정
 → 원본 modeld.py backup
 → reviewed tap patch 작성
 → syntax/control-path 검증
 → manifest 저장
 → AWAITING_REBOOT_FOR_T1
```

이 단계는 **재부팅을 자동 실행하지 않는다.**

prepare 출력에 session directory가 표시된다.

## 2.3 full device reboot

사용자가 기기를 정상적으로 재부팅한다.

runner는 `/proc/sys/kernel/random/boot_id`를 저장하므로 `resume`에서 실제 reboot 여부를 검사한다.

## 2.4 resume — T1/T2/T3 + report + source restore

재부팅 후 동일한 안전조건에서:

```bash
PYTHONPATH=/path/to/EGPU-Future \
python3 /path/to/EGPU-Future/tools/commission_t0_t3.py \
  resume /data/egpu_future/commissioning/<session>
```

자동 수행:

```text
boot_id 변화 확인
 → patched source/runtime 확인
 → stationary/eGPU preflight
 → T1 tap disabled
 → control-file ON
 → T2 receiver absent
 → T3 receiver only / no inference
 → qualification report
 → control-file OFF
 → 원본 modeld.py 복원
 → tap runtime source 삭제
 → SOURCE_RESTORED_FINAL_REBOOT_RECOMMENDED
```

T1→T2→T3 사이에는 modeld를 재시작하지 않는다.

## 2.5 final reboot + finalize

`resume` 뒤 source file은 원본으로 복원되지만 **현재 실행 중인 manager/modeld 메모리에는 patched module이 남아 있을 수 있다.** tap은 disabled 상태지만 byte-for-byte runtime 복원을 확인하려면 한 번 더 정상 재부팅한다.

그 다음:

```bash
python3 tools/commission_t0_t3.py \
  finalize /data/egpu_future/commissioning/<session>
```

`finalize`는:

- boot_id가 다시 바뀌었는지
- `modeld.py`가 original blob인지
- tap runtime 파일이 제거됐는지
- modeld/eGPU가 정상인지

확인하고 `COMPLETED_RUNTIME_RESTORED`로 종료한다.

---

# 3. 안전 guard

prepare/resume/finalize에서 다음을 확인한다.

- `abs(vEgo) <= 0.10 m/s`
- `carState.standstill == true`
- `selfdriveState.active == false`
- gear 정보가 확인 가능하면 `P/park`
- `UsbGpuActive == true`
- `modeld`가 manager에서 실행 중

stage 도중 조건이 깨지면 시험을 중단한다.

이 runner는 **주행 중 자동사용을 위한 도구가 아니다.** 정차 commissioning 전용이다.

---

# 4. dynamic tap control

patched tap runtime은 두 방식으로 enable할 수 있다.

1. `EGPU_FUTURE_SHADOW_TAP=1`
2. control file:

```text
/tmp/egpu_future_shadow_tap.enable
```

commissioning runner는 두 번째 방식을 사용한다.

sender는 control file을 저주기로 polling한다. 따라서 재부팅으로 patched modeld가 한 번 로드된 후에는:

```text
T1 file 없음
T2 file 있음 + receiver 없음
T3 file 있음 + receiver 있음
```

으로 같은 modeld instance에서 단계 전환이 가능하다.

`prepare_only` frame은 tap하지 않는다.

receiver가 없거나 queue/send가 실패해도 retry/wait하지 않는다.

---

# 5. source integrity

fresh T0에서는 다음을 요구한다.

- target `modeld.py`가 reviewed git blob과 일치
- `modeld.py` / tap target이 clean
- 기존 EGPU-Future marker 없음
- tap runtime target 없음

Carrot HEAD는 문서-only commit으로 자주 움직이므로 runner는 **`modeld.py` blob을 hard boundary**로 사용하고 HEAD는 manifest에 증거로 기록한다.

`modeld.py` blob이 바뀌면 실행을 거부하고 새 source를 다시 검토한다.

patch는 marker를 제거했을 때 original `modeld.py`가 byte-for-byte 복원되는지 검증한다.

---

# 6. 출력

기본 경로:

```text
/data/egpu_future/commissioning/<UTC timestamp>/
```

`/data`가 없으면 현재 디렉터리의 `commissioning_runs/`를 사용한다.

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

manifest에는:

- prepare/resume/final boot_id
- Carrot HEAD
- reviewed modeld blob
- patch/runtime SHA256
- stage sample/continuity
- source restore 상태
- qualification 결과

가 저장된다.

---

# 7. Carrot `modelV2.big` 주의

현재 Carrot `fill_model_msg.py`는 `modelV2.big`을 명시적으로 설정하지 않는다.

runner는 일반 로그처럼 default field를 믿지 않고 `UsbGpuActive` Param을 주기적으로 확인해 live row의 `big`을 기록한다.

`UsbGpuActive`가 false로 바뀌면 해당 구간을 big으로 오라벨링하지 않고 stage 자체를 중단한다.

수동 로그 추출에서는 eGPU active가 독립 확인된 구간에 한해:

```bash
python3 tools/extract_model_actions_from_log.py <log> \
  --backend-label big \
  --output active_big.jsonl
```

을 사용할 수 있다.

---

# 8. Stage Gate

프로젝트는 공식 safety threshold를 임의로 만들지 않는다.

실험 책임자가 다음 policy를 명시할 수 있다.

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

위 숫자는 형식 예시일 뿐 권장값이 아니다.

- policy 없음 → `HOLD`
- sample 부족 → `HOLD`
- limit 초과 → `FAIL`
- 모든 명시 조건 충족 → `PASS`

이다.

---

# 9. T3 receiver evidence

T3 receiver summary에는:

- packets received
- records saved
- superseded packets
- decode errors
- frame gap
- duplicate/old transitions
- sender-created → receiver latency p50/p95/p99/max

가 기록된다.

T3에서는 **model inference를 추가하지 않는다.**

---

# 10. T3 PASS 후

T3가 PASS일 때만 T4 5 Hz second-small shadow를 검토한다.

T4부터는:

```bash
PROFILE=1 python3 tools/shadow_modeld_prototype.py --max-hz 5 ...
```

와 QCOM tinygrad hardware profile을 함께 사용한다.

```bash
python3 tools/correlate_shadow_tinygrad_profile.py \
  shadow.jsonl profile.pkl
```

T0~T3 PASS는 **T4/T5 안전성 증명**이 아니라 다음 실험에 들어갈 진입조건이다.
