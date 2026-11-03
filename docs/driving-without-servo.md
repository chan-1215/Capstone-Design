# 조향장치 없는 주행

[프로젝트 처음으로](../README.md) · [서보 조향 주행](driving-with-servo.md) · [제스처 인식](gesture-recognition.md)

## 구동 방식

별도 조향 서보 없이 좌우 DC 모터 출력의 차이로 회전하는 방식입니다.
좌우 속도를 조절하는 커브 주행과 서로 반대 방향으로 구동하는 회전 기능을 실험했습니다.
이 단계의 모터 배선과 보정값은 후속 서보 조향 차량과 다릅니다.

## 코드 안내

| 위치 | 역할 |
| --- | --- |
| [`Driving test`](../Driving%20test/README.md) | OpenCV와 P제어 기반 주행 및 학습 모델 주행 실험 |
| [`road_drive_p_control.py`](../Driving%20test/road_drive_p_control.py) | 차선 검출, 중심 오차 계산, 좌우 출력 계산 |
| [`road_drive_dataset_web.py`](../Driving%20test/road_drive_dataset_web.py) | 학습 모델 주행과 수동조작을 제공하는 Flask 화면 |
| [`motor_module.py`](../Driving%20test/motor_module.py) | 해당 차량의 모터 정의와 이동 함수 |
| [`Lee`](../Lee/) | 카메라·차선 추종·필터·모터 제어 모듈과 초기 통합 화면 |
| [`Dataset Project`](../Dataset%20Project/README.md) | Webots 데이터 생성, 학습, 평가 및 Pi 실행 실험 |

## 인식과 제어

OpenCV 방식은 카메라 영상에서 차선 후보를 검출하고, 화면 중앙과 목표 위치의 차이로 좌우 모터 출력을 보정합니다.
학습 모델 방식은 저장된 `.npz` 모델을 읽어 판단합니다. 주행할 때 원본 학습 이미지 전체를 읽는 구조는 아닙니다.
두 방식은 별도 실험이며, 모든 주행 코드가 학습 모델을 사용하는 것은 아닙니다.

```text
카메라 -> 차선 검출 또는 학습 모델 판단 -> 좌우 출력 계산 -> DC 모터
```

## 개발 기록과 실행

직선 출력 보정, 차선 중심 보정, 커브 진입과 경로 상실 조건을 다룬 실험이 포함되어 있습니다.
실행 옵션과 차량별 배선은 [Driving test README](../Driving%20test/README.md),
시뮬레이션과 실차 시험의 구분은 [데이터 프로젝트 인계 문서](../Dataset%20Project/HANDOFF.md)를 참고합니다.
실험별 결과를 이 단계 전체의 완주 성능으로 합산하지 않습니다.

[모든 버전의 위치](repository-map.md)
