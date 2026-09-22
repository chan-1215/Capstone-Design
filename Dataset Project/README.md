# Dataset Project

실제 로봇 없이 자율주행 로직을 개발하고 검증하기 위한 독립 작업 공간입니다.

## 작업 원칙

- 기존 `Lee` 폴더의 카메라 코드는 수정하지 않습니다.
- 실제 로봇 배선과 방향이 설정된 `Lee/motor_module.py`는 실제 관찰값 없이 수정하지 않습니다.
- 가상 카메라와 가상 모터는 이 폴더에 별도 모듈로 구현합니다.
- 자율주행 판단 코드는 실제 환경과 시뮬레이션 환경에서 공통으로 사용할 수 있게 구성합니다.

## 현재 구성

```text
Dataset Project/
├── controllers/   # 차선 추종 및 주행 판단
├── protos/        # 사진을 참고한 4륜 RC카 모델
├── simulation/    # 가상 카메라·모터 연결
├── tests/         # 주행 판단 및 안전 동작 테스트
├── worlds/        # Webots 트랙
└── README.md
```

현재 첫 단계는 카메라 영상 처리와 GPIO 모터 제어를 건드리지 않고,
그 사이의 **주행 판단 계층**을 독립적으로 만드는 것입니다.

## 실행 모드

- `simulation`: 가상 모터를 사용해 명령과 속도를 기록합니다.
- `hardware`: 추후 실제 로봇에서 기존 `Lee/motor_module.py`를 그대로 연결합니다.

Python과 Webots 설치 후 가상 카메라가 생성한 프레임을 OpenCV 차선 인식에
전달하고, 그 결과를 현재 주행 판단 계층에 연결할 예정입니다.

## Webots 첫 실행

Webots에서 다음 월드 파일을 엽니다.

```text
worlds/lane_track.wbt
```

현재 조작키는 다음과 같습니다. Webots의 3D 화면을 한 번 클릭한 후 사용합니다.

시뮬레이션을 재생하면 두 화면이 동시에 표시됩니다.

- Webots 메인 창: 전체 트랙과 RC카를 내려다보는 고정 3인칭 조감도
- `RC Car Front Camera`: RC카 전면 카메라의 1인칭 화면

| 키 | 동작 |
|---|---|
| `W` 또는 `↑` | 전진 |
| `S` 또는 `↓` | 후진 |
| `A` 또는 `←` | 왼쪽 곡선 주행 |
| `D` 또는 `→` | 오른쪽 곡선 주행 |
| `Q` | 제자리 좌회전 |
| `E` | 제자리 우회전 |
| 키를 놓음 | 정지 |
| `M` | 자동주행/수동주행 전환 |
| `R` | 데이터 기록 켜기/끄기 |
| `V` | 교사 경로주행/OpenCV 단독주행 전환 |

시뮬레이션은 기본적으로 `AUTO-EXPERT` 모드와 데이터 기록이 켜진 상태로 시작합니다.
교사 모드는 Webots의 정확한 차량 위치와 타원형 트랙 중앙선을 사용해 계속 순환하고,
OpenCV 인식 결과를 동시에 데이터에 기록합니다. `V`를 누르면 기존 OpenCV 결과만으로
주행하는 `AUTO-VISION` 모드와 비교할 수 있습니다.

`V` 키는 `EXPERT → VISION → LEARNED` 순서로 제어 방식을 전환합니다.

## 학습 모델 테스트 트랙

```text
worlds/test_track_clockwise.wbt
```

이 트랙은 학습용 트랙보다 직선이 길고 곡선이 급하며, 노란색 차선과 다른 조명을
사용합니다. 차량은 시계 방향으로 출발하고 `steering_v1.npz` 학습 모델로 주행합니다.

첫 평가 결과(`run_20260831_013025`):

- 67.36초 연속 주행
- 평균 중앙 이탈 0.0185 m
- 최대 중앙 이탈 0.0726 m
- 가운데 차선 경계 초과 0회
- 전체 도로 이탈 0회

### 점선 직사각형 테스트 트랙

```text
worlds/test_track_rectangle.wbt
```

- 전체 윤곽은 직사각형이며 차량 주행을 위해 모서리만 라운드 처리
- 3개 차로와 4개의 점선 경계
- 위쪽 직선에서 시계 방향 출발
- 기본 제어 방식은 `LEARNED`

`steering_v1` 첫 평가(`run_20260831_013642`)에서는 점선과 직사각형 모서리에
일반화하지 못했습니다. 평균 중앙 이탈은 0.6346 m였고, 820개 샘플 중 708개가
가운데 차선을 벗어났습니다. 이 실행은 `dataset_v2` 교정 대상 실패 사례입니다.
가상 카메라의 원본 이미지와 차선 인식 결과, 좌우 PWM, 차량 위치와 방향은
다음 경로에 실행별로 저장됩니다.

```text
dataset/runs/run_YYYYMMDD_HHMMSS/
├── images/
├── driving.csv
└── run_metadata.json
```

## 첫 RC카 모델의 임시 치수

실제 로봇 측정 전까지 아래 값을 사용합니다.

| 항목 | 임시 값 |
|---|---:|
| 차체 길이 | 0.48 m |
| 차체 폭 | 0.32 m |
| 차체 높이 | 0.20 m |
| 바퀴 반지름 | 0.065 m |
| 전체 질량 | 약 3.82 kg |
| 카메라 | 320×240, 수평 화각 60° |

`protos/BlueRCCar.proto`에는 참조 이미지의 파란 차체, 전면 카메라,
표시창, 이중 초음파 센서 외형을 단순 형상으로 반영했습니다.

## GPIO와 가상 바퀴 매핑

| 실제 모터 | 기존 GPIO | 가상 바퀴 |
|---|---|---|
| motor1 | 22, 27 | 앞 왼쪽 |
| motor2 | 24, 23 | 뒤 왼쪽 |
| motor3 | 21, 16 | 뒤 오른쪽 |
| motor4 | 19, 26 | 앞 오른쪽 |

`controllers/rc_car_controller/rc_car_controller.py`의 가상 GPIO 브리지는
각 핀의 정방향·역방향 PWM 상태를 Webots 바퀴 회전 속도로 변환합니다.

## 현재 3차선 타원형 트랙

- 형태: 양쪽 반원 곡선과 위아래 직선으로 구성된 스타디움형 타원
- 직선 구간 반길이: 약 1.8 m
- 차선 경계 곡률 반지름: 1.0 / 1.6 / 2.2 / 2.8 m
- 차로 수: 3개
- 각 차로 폭: 약 0.6 m
- 차량 시작점: 아래쪽 직선의 가운데 차로, 오른쪽 방향
- 기본 PWM: 0.65
- Webots 바퀴 최대 각속도: 16 rad/s

## 보존 대상 GPIO 설정

실제 로봇에서는 기존 `Lee/motor_module.py`의 설정을 그대로 사용합니다.

```python
motor1 = Motor(22, 27)
motor2 = Motor(24, 23)
motor3 = Motor(21, 16)
motor4 = Motor(19, 26)
```

2026-09-01 실제 모터 단품 테스트에서 좌우 위치를 다시 확인했습니다.
2026-09-02 실제 모터 단품 테스트에서 오른쪽 전후 위치를 다시 확인해
`motor3 = 뒤 오른쪽`, `motor4 = 앞 오른쪽`으로 갱신했습니다.
핀 번호와 모터 번호는 그대로 두고, 좌우 그룹은 `motor1/2 = left_wheels`,
`motor3/4 = right_wheels`로 사용합니다.
# Three-lane curvature dataset collection

The dashed rectangular track has three collection worlds. Each starts the car
on a different lane and records an expert label for that lane.

| World | Lane | Corner radius | Curvature | Expert base PWM |
| --- | --- | ---: | ---: | ---: |
| `collect_rectangle_lane_1.wbt` | inside (1) | 0.8 m | 1.250 1/m | 0.34 |
| `collect_rectangle_lane_2.wbt` | middle (2) | 1.4 m | 0.714 1/m | 0.42 |
| `collect_rectangle_lane_3.wbt` | outside (3) | 2.0 m | 0.500 1/m | 0.48 |

Open one world at a time in Webots. Recording starts automatically and writes
camera images plus GPIO-equivalent left/right PWM labels under `dataset/runs`.
The CSV also identifies `target_lane`, `corner_radius_m`, and
`corner_curvature_1pm`, so the three runs can be balanced during training.
