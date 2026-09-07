# Carrot eGPU YOLO 다음 단계 분석 — 2026-09-07

이 문서는 `ajouatom/openpilot`의 `carrot-egpu-yolo` 최신 실험 메모 중 EGPU-Future에 직접 영향을 주는 부분만 분리해 해석한다.

## 1. 자전거 miss는 단순 threshold 문제가 아니다

현재 한 saved road frame에서 512×256 입력의 자전거 후보는 약 38×22 px이고, matching NV12 preprocessing에서 bicycle confidence가 0.0276으로 0.35 display threshold보다 크게 낮았다. 동일 YOLOv8n weights를 더 큰 입력으로 테스트하면 그 한 장면에서 640×384 0.5764, 896×512 0.8532, 1344×768 0.8927까지 올라갔다.

이 결과는 **고해상도가 일반적으로 더 정확하다는 차량 전체 benchmark가 아니다.** 한 장면의 증거다. 그러나 작은 lateral hazard를 볼 때 512×256만 고집하면 물체가 너무 작아져 feature가 사라질 수 있다는 설계 신호로는 충분하다.

따라서 EGPU-Future는 perception sidecar에서 다음을 구분한다.

```text
Driving model input resolution / FOV
!=
Sidecar detector input resolution / FOV
```

동일 tensor 크기만으로 동일 시야나 동일 정보량으로 취급하지 않는다.

## 2. 다음 해상도 후보

현재 다음 실험 후보는 640×384다.

이유:

- 512×256 대비 해당 scene의 bicycle confidence가 크게 회복됨
- 896×512 이상보다 compute 증가가 상대적으로 작음
- 이미 workstation static ONNX 후보가 만들어져 있음

하지만 차량에서 compile/timing된 상태가 아니므로 **아직 vehicle-qualified artifact가 아니다.**

## 3. shared eGPU latency에서 얻은 교훈

과거 shared-eGPU 경로에서 짧은 trial은 약 5.27 ms median / 5.73 ms max였지만 이후 24.887 ms overrun이 관측됐다.

따라서 앞으로는 평균/median 하나로 eGPU sidecar를 평가하지 않는다.

반드시 다음을 분리한다.

- GPU kernel
- queue wait
- USB readback
- host scheduling
- NMS/postprocess
- camera EOF → publication 전체 age
- p95/p99/max tail

이 원칙은 EGPU-Future의 QCOM/tinygrad profiling 방식과 동일하다.

## 4. 주파수와 해상도 순서

Carrot 메모의 방향처럼 성능 압력이 생기면 우선순위는:

```text
frequency 감소
→ queue/admission 개선
→ bounded work 검토
→ 그 다음에만 resolution 조정
```

으로 둔다.

작은 물체 miss 때문에 이미 512×256이 accuracy bottleneck 가능성을 보였기 때문에, 단순히 해상도를 더 낮춰 latency를 맞추는 방식은 기본 전략으로 사용하지 않는다.

## 5. T4 이후 EGPU-Future 반영

T0~T3가 실제 실기기에서 PASS하기 전에는 아래를 실행하지 않는다.

T4 이후에는 다음 matrix를 사용한다.

| 축 | 후보 |
|---|---|
| 실행 위치 | QCOM / eGPU |
| 입력 | 512×256 / 640×384 |
| 빈도 | 2 Hz / 5 Hz / 이후 검증된 상향 |
| 목적 | load probe / perception accuracy / tail latency |
| 출력 소비자 | JSON/Web/shadow evidence only |

control consumer는 추가하지 않는다.

## 6. 추후 perception 연구 순서

1. 차량/자전거/보행자 detector 품질과 latency 분리 측정
2. 동일 frame의 resolution/FOV mapping 검증
3. visual track ID 유지
4. raw radar object 사용 가능성 확인
5. camera/radar timestamp alignment
6. association uncertainty와 unmatched visual object 기록
7. cut-in warning-time 평가
8. traffic-light state / stop-line은 별도 전용 perception으로 분리

YOLO COCO traffic-light class는 신호 상태(red/green/arrow)나 stop-line을 제공하지 않으므로 제동 로직 근거로 직접 사용하지 않는다.

## 결론

최신 Carrot 실험에서 EGPU-Future에 가장 중요한 교훈은 두 가지다.

1. **작은 hazard의 accuracy는 input resolution/FOV에 크게 민감할 수 있다.**
2. **eGPU 성능은 짧은 median보다 sustained p99/max와 queue/readback/end-to-end age가 중요하다.**

따라서 T4 이후 sidecar는 `640×384 accuracy candidate + tail-latency decomposition`을 우선 검토한다.
