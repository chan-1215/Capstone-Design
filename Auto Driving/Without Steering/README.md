# 조향장치 없는 주행

[프로젝트](../../README.md) · [서보 조향 주행](../With%20Steering/README.md)

좌우 DC 모터의 출력 차이로 방향을 바꾸는 이전 차량의 코드입니다.
서보 조향 차량과 모터 구성·배선·제어값이 다릅니다.

| 폴더 | 내용 |
| --- | --- |
| `controller/` | 기존 Driving test의 OpenCV·P제어·학습 모델 주행과 Flask |
| `legacy_rover/` | Lee의 초기 통합 화면·카메라·필터·모터·차선 모듈 |
| `simulation/` | Webots 데이터 생성·학습·평가와 Pi 어댑터 |
| `experiments/` | 카메라·키보드·라인 센서·모터 실험 |

`controller/road_drive_web.py`는 OpenCV 화면,
`controller/road_drive_dataset_web.py`는 학습 모델 주행·수동 제어 화면입니다.
당시 옵션은 [controller/HISTORY.md](controller/HISTORY.md)에 있습니다.
그 문서의 `Driving test`는 현재 `Auto Driving/Without Steering/controller`입니다.

모터 없이 인식을 확인하는 예시입니다.

```bash
cd "Auto Driving/Without Steering/controller"
python3 road_drive_web.py --camera rpicam --dry-run
```

시뮬레이션 검사는 별도로 실행합니다.

```bash
cd "Auto Driving/Without Steering/simulation"
python3 -B -m unittest discover -s tests -v
```

`legacy_rover`의 모델·배선은 해당 차량의 당시 구성입니다.
제스처는 [Gesture](../../Gesture/README.md)에 통합했고,
시뮬레이션의 기존 데이터와 모델은 그대로 옮겨 보존했습니다.
