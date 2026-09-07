# Temporal Scenario Tagging

작성일: 2026-09-07

## 목적

기존 `scenario_tagger.py`는 한 프레임의 상태만 보고 `standstill`, `curve`, `close_lead`, `closing_fast` 등을 붙인다.

그러나 실제 hard-case는 **상태 변화**에서 많이 발생한다.

예:

- lead가 새로 생김
- lead가 사라짐
- lead가 갑자기 가까워짐
- closing speed가 임계영역으로 진입
- 정차 진입/출발
- small/big stop 판단 차이가 새로 발생

이를 위해 `egpu_future/temporal_scenarios.py`를 추가했다.

## 태그

- `lead_acquired`
- `lead_lost`
- `close_lead_acquisition`
- `close_lead_entry`
- `rapid_range_closure`
- `closing_fast_onset`
- `standstill_entry`
- `standstill_exit`
- `small_stop_onset`
- `big_stop_onset`
- `stop_disagreement_onset`
- `stop_disagreement_resolved`
- `cut_in_candidate_heuristic`

## cut-in 주의

`cut_in_candidate_heuristic`은 ground truth가 아니다.

현재 heuristic:

```text
previous leadPresent == false
current leadPresent == true
current leadDistance < 30 m
current leadRelativeSpeed < -1 m/s
```

이 조건은 다음도 포함할 수 있다.

- 곡선/가림 뒤에서 lead가 다시 보인 경우
- radar/vision association이 새로 잡힌 경우
- 앞차가 detector threshold를 넘은 경우
- 실제 차선 cut-in
- merge 차량

따라서 해당 태그는 **자동 제어 입력이 아니라 review queue 생성용**으로만 사용한다.

향후 실제 cut-in validation에는 최소한:

- 원본 영상
- ego lane/path geometry
- visual track continuity
- raw radar lateral/longitudinal motion
- timestamp alignment
- independently reviewed event label

이 필요하다.

## 중요한 구현 원칙

Temporal tracker는 significant disagreement 프레임에서만 갱신하지 않는다.

small/big pair가 정상적으로 매칭된 **모든 프레임**에서 상태를 갱신한 뒤, disagreement가 significant일 때만 현재 temporal tags를 event에 기록한다.

그렇지 않으면 sparse event 사이의 중간 프레임을 보지 못해 가짜 `lead_acquired`/`lead_lost`가 만들어질 수 있다.

## 출력

`tools/compare_shadow_runs.py`의 event에는 이제:

```json
{
  "tags": ["close_lead", "lead_acquired"],
  "temporalTags": ["lead_acquired"]
}
```

형태로 저장된다.

기존 `summarize_shadow_events.py`는 `tags`를 집계하므로 temporal tag도 자동으로 전체 집계에 포함된다.

## 다음 확장

실제 Carrot/openpilot 로그에서 raw radar/lane context를 확보하면 다음을 별도 schema로 추가한다.

- visual track ID
- radar track ID
- lateral offset / lateral velocity
- lane boundary crossing
- existing Carrot `leadCutInRisk` 비교값
- independently reviewed cut-in label

그 전까지 `cut_in_candidate_heuristic`을 `cut_in`으로 이름을 바꾸지 않는다.
