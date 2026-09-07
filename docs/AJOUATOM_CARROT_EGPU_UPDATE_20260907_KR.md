# ajouatom/Carrot eGPU 최신 업데이트 — 2026-09-07 18시 기준

이 문서는 `docs/AJOUATOM_CARROT_EGPU_ANALYSIS_KR.md` 이후 빠르게 진행된 `carrot-egpu-yolo` 변경을 보충한다.

## 최신 확인 tip

- branch: `carrot-egpu-yolo`
- tip: `2c508b1dde53b9a996546993e1c7b5b74b489541`
- timestamp: 2026-09-07 09:00:46 UTC / 18:00:46 KST
- message: `Record stationary internal GPU Web publication results`

이 tip의 `modeld.py`는 이전에 분석한 핵심 eGPU 구조를 유지한다.

- eGPU startup grace
- PCIe readiness retry
- eGPU model-loader timeout
- active eGPU + warm internal small fallback
- runtime eGPU failure 시 같은 camera frame을 internal small model로 재실행
- `prepare_only` dropped-frame handling

따라서 EGPU-Future의 recovery/hot-fallback 설계와 기본 방향은 바뀌지 않는다.

---

# 새로 중요해진 사실: QCOM sidecar interference가 실측됨

최신 commit은 `docs/egpu_yolo_experiment.md`에 internal-QCOM YOLO의 실제 stationary publication trial 결과를 추가했다.

### 180초 trial

- 688 publications
- 3.85 Hz
- skipped frames: 0
- one car detection per publication

### YOLO full live execution

- p50: 119.88 ms
- p95: 138.74 ms
- p99: 148.59 ms
- max: 184.71 ms

### active driving execution

| 구간 | p50 | p99 | max |
|---|---:|---:|---:|
| before | 36.55 ms | 39.26 ms | 40.98 ms |
| during | 36.62 ms | 43.26 ms | 56.04 ms |
| after | 35.82 ms | 37.65 ms | 38.89 ms |

### camera EOF → model event

| 구간 | p50 | p99 | max |
|---|---:|---:|---:|
| before | 80.83 ms | 94.46 ms | 104.67 ms |
| during | 83.87 ms | 108.44 ms | 120.35 ms |
| after | 84.30 ms | 95.71 ms | 99.87 ms |

Carrot 원문 결론은 이 결과가 **remaining tail-latency cost**를 보여주며 **driving use를 validate하지 않는다**는 것이다.

EGPU-Future도 이 결론을 그대로 존중한다.

---

# EGPU-Future 해석

이 실험으로 다음을 확정할 수는 없다.

- YOLO 3.85 Hz interference == second driving small 20 Hz interference
- 56.04 ms maximum 하나만으로 실제 control safety failure가 발생한다
- QCOM sidecar는 절대 주행 중 사용할 수 없다

하지만 다음 결론은 충분히 정당하다.

> **QCOM에 추가 sidecar workload를 얹으면 active driving model의 tail latency가 변할 수 있으므로, second-small live shadow는 tap-only commissioning과 interference stage gate를 먼저 통과해야 한다.**

그래서 이전 계획의 `5 Hz → 20 Hz shadow` 앞에 다음을 추가한다.

```text
T0 original baseline
 → T1 patch installed, tap disabled
 → T2 tap enabled, receiver absent
 → T3 tap enabled + receiver only, no inference
 → explicit interference gate
 → T4 5 Hz shadow load probe
 → explicit interference gate
 → T5 20 Hz continuous shadow
```

---

# Carrot modelV2.big 주의

현재 tip의 `fill_model_msg.py`는 `modelV2.big`을 명시적으로 설정하지 않는다.

따라서 Carrot eGPU commissioning 로그를 EGPU-Future에서 분석할 때 message default를 그대로 믿으면 active big 로그를 small로 오인할 수 있다.

이를 위해 `extract_model_actions_from_log.py`에:

```text
--backend-label auto|big|small
```

을 추가했다.

`big` 강제 라벨은 **eGPU active 상태가 독립적으로 확인된 실험 interval**에만 사용한다. fallback이 섞인 일반 route 전체를 강제 라벨하면 안 된다.

---

# 최소 통합 patch

최신 tip에 대한 실제 integration은 `docs/CARROT_MINIMAL_TAP_INTEGRATION_KR.md`를 따른다.

핵심 원칙:

- patch 기본 disabled
- control/fallback code 수정 없음
- `prepare_only` frame은 tap하지 않음
- non-blocking AF_UNIX metadata only
- patch marker 제거 시 original modeld byte-for-byte 복원 검증
- HEAD/modeld blob mismatch 시 기본 거부

이 접근은 Carrot 개발속도가 빠른 상황에서 stale patch가 silently 적용되는 것을 막기 위한 것이다.
