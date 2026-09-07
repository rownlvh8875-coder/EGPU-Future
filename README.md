# EGPU-Future

comma 4 + Chestnut/eGPU 이후의 openpilot 계열 자율주행 발전 방향을 조사·분석하는 저장소입니다.

## 핵심 결론

**eGPU의 가장 큰 가치는 FPS 향상이 아니라, 지금까지 comma 4의 약 10 W급 온디바이스 연산 한계 때문에 사용할 수 없었던 더 큰 driving/world model을 실차에서 실시간 실행할 수 있게 만드는 데 있습니다.**

따라서 바람직한 방향은 comma 4를 버리고 eGPU가 모든 것을 담당하게 하는 구조가 아니라 다음과 같은 역할 분리입니다.

- **comma 4:** 카메라 입력, 차량 인터페이스, 상태 추정, 안전 감시, 소형 모델 fallback
- **eGPU:** 대형 vision/world/driving model 추론, 더 넓은 FOV·긴 temporal context·고난도 scene reasoning
- **차량 제어:** 기존 차량별 actuator 한계와 safety constraint를 그대로 유지
- **실패 시:** eGPU 장애가 즉시 전체 시스템 장애로 번지지 않도록 comma 4의 small model 또는 안전한 disengagement로 복귀

이 구조를 이 저장소에서는 **Guardian + Intelligence Sidecar** 구조라고 부릅니다.

## 왜 지금 eGPU인가

comma.ai는 2026-08-12 Chestnut을 공개하면서 다음을 발표했습니다.

- comma four와 외장 GPU를 연결하는 compute upgrade
- 첫 Chestnut-class 모델은 약 1B parameter 급
- 기존 on-device 모델 대비 약 30배 parameter, 약 100배 FLOPs
- comma four + Chestnut의 compute를 Tesla HW4와 유사한 수준이라고 설명
- Ready-to-Drive 구성은 AMD Radeon RX 9060 8GB 사용

단, 위 Tesla HW4 비교는 comma.ai 자체 설명이며 독립적인 동등성 검증 결과로 보아서는 안 됩니다.

## 분석 문서

- [EGPU 이후 자율주행 기술방향 종합분석](docs/EGPU_AUTONOMY_STRATEGY_KR.md)

## 이 저장소에서 우선 검증할 연구 과제

1. **Dual-model shadow runner** — small model과 big model의 동일 route 동시 추론 및 disagreement 기록
2. **Latency observability** — camera capture → preprocess → USB → eGPU inference → action까지 end-to-end latency 계측
3. **Big-model watchdog** — timeout, GPU reset, USB reconnect, power instability에 대한 상태기계 구현
4. **Scenario evaluator** — 급곡선, cut-in, 정체 출발, 공사 cone, lane merge, lead lost/acquired 등을 자동 분류
5. **Fallback validation** — eGPU 중단 시 small model 복귀가 실제로 연속적이고 안전한지 replay/sim에서 확인
6. **Teacher/student pipeline** — big model 결과를 small model 개선·distillation용 평가 데이터로 활용

## 원칙

이 저장소의 목표는 차량의 OEM 조향/제동 한계나 openpilot safety constraint를 우회하는 것이 아닙니다. 연산 능력 확대가 차량 actuator 권한 확대를 뜻하지 않으며, 실제 차량 적용은 항상 차량별 제어 한계·센서 가시성·전원·열·통신 안정성을 별도 검증해야 합니다.

## 주요 출처

- comma.ai, Introducing chestnut: https://blog.comma.ai/chestnut/
- comma.ai, openpilot 0.11: https://blog.comma.ai/011release/
- comma.ai, Bugs that broke driving: https://blog.comma.ai/driving-bugs/
- comma.ai, openpilot source: https://github.com/commaai/openpilot
- openpilot RELEASES.md: https://github.com/commaai/openpilot/blob/master/RELEASES.md
- tinygrad runtime documentation: https://github.com/tinygrad/tinygrad/blob/master/docs/runtime.md
- comma.ai Reddit community: https://www.reddit.com/r/Comma_ai/

Last reviewed: 2026-09-07
