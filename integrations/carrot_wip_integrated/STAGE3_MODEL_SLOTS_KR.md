# Stage 3 — QCOM / eGPU Model Slot Metadata

작성일: 2026-09-07

## 목적

sunnypilot의 장점인 **QCOM용 모델과 Chestnut/eGPU용 모델을 서로 다른 slot으로 관리하는 개념**을 가져오되, 현재 Carrot의 big-model 다운로드/compile/startup 경로는 그대로 유지한다.

S3의 목표는 모델을 바꾸는 것이 아니라 **어떤 모델이 어느 하드웨어에서 실행될 수 있는지 명확하고 검증 가능한 metadata로 표현하는 것**이다.

```text
qcom slot
  -> internal fallback/default model metadata

egpu slot
  -> external AMD/USB big-model metadata
```

## S3에서 하지 않는 것

- 주행 중 model hot-swap
- QCOM ↔ eGPU 임의 cross-fallback
- 새로운 modeld selection logic
- model output의 control authorization
- 모델 다운로드/compile 교체
- panda/controls 변경

현재 Carrot modeld의 실제 선택 권한은 그대로 유지한다.

## 기본 정책

```text
normal startup preference:
  eGPU ready + verified eGPU slot exists
      -> metadata 상 preference = egpu

  otherwise
      -> metadata 상 preference = qcom

runtime fallback:
  항상 qcom
```

위 `startup_preference()`는 설명용 pure function이며 실제 modeld를 바꾸지 않는다.

## slot schema

각 slot은 다음을 가진다.

- `slot`: `qcom` / `egpu`
- `model_id`
- `ref`
- `backend`
- `runner`
- `generation`
- `nominal_hz`
- `source`
- `artifact`
- `builtin`
- `control_eligible`

artifact가 있는 외부 모델은:

- filename
- byte size
- SHA256

을 모두 검증한다.

## QCOM slot

현재 Carrot의 internal small/default model은 source/build에 의해 관리되므로 Stage 3에서는 기본적으로:

```text
source = carrot-builtin
backend = qcom
runner = tinygrad
builtin = true
artifact = null 가능
```

으로 표현한다.

즉 sunnypilot의 모델 selector 때문에 현재 검증된 Carrot fallback 모델을 임의 외부 모델로 교체하지 않는다.

## eGPU slot

현재 Carrot `BigModelManifest`를 그대로 adapter한다.

Carrot manifest의:

- `model_id`
- `filename`
- `size`
- `sha256`

를 Stage-3 `egpu` slot으로 변환한다.

```text
backend = amd-usb
runner = tinygrad
source = carrot-big-model-manifest
```

Carrot의 실제 download/resume/hash verify/state.json 흐름은 변경하지 않는다.

## control authorization 분리

Stage 3 registry는 의도적으로:

```json
"controlAuthorization": false
```

로 고정한다.

개별 slot의 `control_eligible=true`도 validation에서 거부한다.

즉 metadata 파일을 편집하는 것만으로 어떤 모델이 차량제어를 담당하게 만들 수 없다.

## cross-slot fallback 금지

Stage 3 registry의 fallback slot은 반드시:

```text
qcom
```

이다.

`fallbackSlot=egpu`는 validation error다.

이것은 다음과 같은 위험을 막는다.

```text
QCOM model 문제
  -> 임의 eGPU model로 fallback

또는

eGPU slot 비어 있음
  -> 다른 eGPU/QCOM external model을 추측해서 사용
```

fallback은 현재 Carrot의 검증된 internal QCOM path만 사용한다.

## artifact verification

`verify_artifact()`는 파일을 다운로드하거나 load하지 않고 다음만 확인한다.

1. file exists
2. exact byte size
3. SHA256

S3는 네트워크를 사용하지 않는다.

## 저장 형식

기본 예정 경로:

```text
/data/egpu_integrated/model_slots.json
```

예시:

```json
{
  "schemaVersion": 1,
  "fallbackSlot": "qcom",
  "slots": {
    "qcom": {
      "slot": "qcom",
      "model_id": "carrot-builtin-small",
      "ref": "carrot-source-default",
      "backend": "qcom",
      "runner": "tinygrad",
      "generation": 0,
      "nominal_hz": 20.0,
      "source": "carrot-builtin",
      "artifact": null,
      "builtin": true,
      "control_eligible": false
    },
    "egpu": {
      "slot": "egpu",
      "model_id": "example-big",
      "ref": "example-big",
      "backend": "amd-usb",
      "runner": "tinygrad",
      "generation": 0,
      "nominal_hz": 20.0,
      "source": "carrot-big-model-manifest",
      "artifact": {
        "file_name": "big_driving_supercombo.onnx",
        "size": 123456789,
        "sha256": "<64 hex>"
      },
      "builtin": false,
      "control_eligible": false
    }
  },
  "policy": {
    "runtimeHotSwap": false,
    "crossSlotFallback": false,
    "controlAuthorization": false
  }
}
```

숫자/모델명은 schema 예시이며 실제 active model을 의미하지 않는다.

## sunnypilot에서 가져온 원칙

- QCOM / Chestnut active slot 분리
- bundle/ref 개념
- artifact hash 검증
- generation/runner/frequency metadata
- invalid bundle을 그대로 신뢰하지 않는 구조

## sunnypilot에서 그대로 가져오지 않는 것

- 현재 Carrot와 다른 전체 model manager
- 수많은 runner를 동시에 지원하는 복잡성
- 자동 migration으로 QCOM slot을 Chestnut slot에 복사하는 동작
- 주행 중 자유로운 모델 교체

## S3 완료 기준

- qcom/egpu slot schema 존재
- Carrot BigModelManifest adapter 존재
- external artifact hash/size validation
- unsafe filename/path traversal 거부
- fallbackSlot=qcom 강제
- control_eligible 거부
- runtime hot-swap 없음
- JSON atomic write/load roundtrip
- unit tests PASS

## S4로 넘어가는 조건

S3 metadata가 완료되어도 바로 Guardian을 control에 연결하지 않는다.

S4 순서:

```text
observer/provenance
+ telemetry
+ model slots
      |
      v
shadow output
      |
      v
freshness/deadline/disagreement validator
      |
      v
research evidence only
```

S4 초기에도 shadow 결과는 controls bus로 보내지 않는다.
