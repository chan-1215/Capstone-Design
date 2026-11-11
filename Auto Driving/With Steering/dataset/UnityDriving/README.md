# 조향장치 차량 · Unity 주행 데이터셋

[조향장치 주행](../../README.md)

사진과 CAD 치수를 참고한 Unity 트랙·로봇에서 만든 **합성 주행 데이터셋**입니다.
실물 로봇 데이터와 이전 Webots 데이터셋과 구분합니다.

| 구성 | 내용 |
| --- | --- |
| `Dataset/` | 최초 Unity 교사 주행 489장, 조향·위치·방향·에피소드 기록 |
| `AlignedDatasetFrontCamera/` | 현재 카메라로 다시 렌더링한 2,377장과 `labels.csv` |
| `Assets/`, `Packages/`, `ProjectSettings/` | Unity 2022.3.62f3 실행 프로젝트·로봇·트랙 |
| `Assets/Resources/VisionPolicy.json` | 카메라 영상으로 조향·속도를 예측하는 학습 모델 |
| `Tools/` | 데이터 분리·검사·MLP 학습·OpenCV 차선 표시 코드 |
| `Diagnostics/` | 학습·폐루프 시험 결과와 실제 시뮬레이터 캡처 |
| `manifest.json` | 이미지 수·라벨 연결·모델 SHA-256·실험 조건 |

## 생성·학습 방식

기존 Unity 교사 주행의 위치·방향을 재사용하고, 새 카메라 시야로 영상을 다시 생성했습니다.
좌우 ±25mm·방향 ±6° 변형 장면은 해당 위치에서 교사 조향 정답을 다시 계산했습니다.
교사는 가상 경로 좌표를 아는 pure pursuit 제어기입니다.
학습은 원본 시드·차선 그룹으로 나눠 **2,102장 + 좌우 반전 = 4,204개 예시**, 검증은 275장입니다.
같은 원본의 변형 장면은 같은 분할에 포함합니다.

NumPy MLP(288→64→32→2)가 영상의 검정·흰색·노랑 분포를 읽어 조향각·목표 속도를 예측합니다.
실행 중 조향은 저장 경로 재생이나 교사 좌표 보정 없이 카메라 입력으로 결정합니다.
OpenCV는 GaussianBlur·HSV·윤곽 검출로 경계·점선·추적 경로를 **표시**하며, 현재 조향 제어기는 아닙니다.

## 현재 카메라·검증

- 광학 중심: 지면 높이 15.5cm, 차체 중앙보다 앞쪽 2cm, 아래로 30°, 수직 화각 48°.
- 지지대를 렌즈 뒤로 옮겨 중앙 시야 확보. 모델과 카메라 조건이 다르면 출발하지 않음.
- 1차선 출발 2바퀴 80.62초 / 2차선 출발 2바퀴 92.23초, 교사 조향 전환 0회.
- 검증 영상 평균 조향 오차 약 0.98°. Python·Unity의 동일 이미지 특징 차이 0.
- 같은 가상 트랙의 두 출발 조건에서 확인한 결과이며 실물·새 트랙 성능은 미검증.
- 트랙 일부 치수는 사진 기반 추정, 차량은 타이어 미끄러짐 없는 운동학 모델.
- 횡단보도 줄무늬는 트랙에 있으나 이 실험은 제스처·보행자 정차 제어를 포함하지 않음.

## Unity 실행 중 캡처

아래는 2026-11-11 Unity를 다시 실행해 **학습 모델이 주행하는 동안** 렌더링한 실제 장면입니다.
주행 상태의 Unity 가상 카메라 출력을 이미지로 저장했습니다.
시뮬레이션 시간·차량 위치는 각 이미지 폴더의 `capture.json`에 기록합니다.
이번 실행도 1차선 출발에서 두 바퀴를 완료했으며 [실행 결과](Diagnostics/runtime_20261111/run_result.json)에 모델 해시와 함께 보관했습니다.
재촬영은 Unity Editor가 해당 프로젝트를 열고 있지 않을 때 `-batchmode -projectPath <UnityDriving 경로> -executeMethod RuntimeCapture.Run -simSmoke -policyTest -policyLane 0 -simSeconds 150` 인수로 실행합니다.

| 주행 장면 A · 시뮬레이션 약 6초 | 주행 장면 B · 약 26초 |
| --- | --- |
| ![학습 모델 주행 6초의 로봇](Diagnostics/runtime_20261111/frame_01/unity_robot.png) | ![학습 모델 주행 26초의 로봇](Diagnostics/runtime_20261111/frame_03/unity_robot.png) |

![실행 중 전체 트랙과 차량 위치](Diagnostics/runtime_20261111/frame_03/unity_overview.png)

| 모델에 입력되는 실제 RGB | 같은 실행의 OpenCV 인식 표시 |
| --- | --- |
| ![차량 카메라 RGB 입력](Diagnostics/runtime_20261111/frame_03/unity_policy_input.png) | ![노란 경계·하늘색 흰 점선·초록 연결선 표시](Diagnostics/runtime_20261111/frame_03/opencv_tracking.png) |

노랑은 경계, 하늘색은 점선 후보, 초록은 검출한 점선 연결입니다.
OpenCV는 비동기로 갱신하므로 오른쪽 화면은 왼쪽과 정확히 동일 시점의 프레임은 아닐 수 있습니다.
점선이 부족한 장면은 경로 미확인으로 표시하며, 이 선은 주행 모델의 조향 정답이 아닙니다.

## Webots 사륜 구동과 Unity 조향 데이터셋 비교

두 실험 모두 가상 카메라 영상과 교사 정답으로 **모방학습용 데이터셋**을 만들었습니다.
Webots는 사륜만, Unity는 조향만 가능한 것이 아닙니다. 아래는 **우리 코드와 데이터 생성 방식**의 비교입니다.

| 항목 | Webots · 이전 사륜 구동 실험 | Unity · 현재 앞바퀴 조향 실험 |
| --- | --- | --- |
| 차량 구성 | 회전 모터 4개, 좌우 출력 차이로 회전 | 앞바퀴 조향·후륜 구동을 운동학 자전거 모델로 계산 |
| 교사·정답 | 가상 위치·경로 기반 좌우 PWM 2개 | 가상 위치·경로 기반 바퀴 조향각·목표 속도 |
| 보관 데이터 | 17개 run에서 선별한 9,000장, 차선별 3,000장 | 최초 489장 → 현재 시야·위치·방향 변형 2,377장 |
| 입력·학습 | 회색조 32×18 픽셀, 릿지 회귀 | RGB 색 분포 12×8×3, MLP |
| 전처리·증강 | 회색조·극성 정규화, 좌우/노면 반전 | 카메라 재렌더링·위치/방향 변형, 색 분포 정규화·좌우 반전 |
| 데이터 생성의 장점 | 모터·카메라 API와 물리 노드로 구동과 수집을 연결. 마찰·접촉·질량 조건을 넣은 주행 실험으로 확장하기 좋음 | CAD 바퀴·차체 크기·카메라 시야를 현재 로봇에 맞춰 조절. 같은 기록 자세를 새 카메라 위치에서 재렌더링하고 새 조향 정답을 붙일 수 있음 |
| 데이터 생성의 단점 | 좌우 PWM 정답을 조향 차량에 바로 쓸 수 없음. 질량·마찰·모터 설정을 실물과 맞추지 않으면 움직임도 달라짐 | 현재 운동학 구현에는 타이어 미끄러짐·모터 토크·하중·배터리 편차가 없음. 카메라 시야가 좋아 보여도 실제 차량 동작을 검증한 것은 아님 |
| 영상 조건의 한계 | 노면 반전 증강이 실제 빛 반사·구김을 대신하지 못함 | 현재 단순 재질·조명 변형이 실제 반사·노출·블러를 충분히 재현하지 못함 |
| 평가에서 주의할 점 | 기존 차선별 무작위 분할은 같은 run의 인접 프레임이 양쪽에 들어갈 수 있음. 최종 주행은 영상 보정을 결합한 구성 | 시드·차선별 분할로 같은 원본 변형을 묶었지만 원본 시나리오는 3개뿐. 새 트랙·실물 평가는 별도 필요 |

**지금 목적에는 Unity를 사용합니다.** 조향장치가 있는 현재 로봇의 시야와 조향 정답을 맞추고 데이터 생성 과정을 확인하기 위한 선택입니다.
좌우 모터 출력·접촉을 포함한 이전 차량 실험은 Webots 기록이 참고 자료입니다.
실제 속도·조향·마찰을 보정하지 않은 상태에서 어느 쪽이 실물 성능이 더 좋다고 결론 내릴 수는 없습니다.
수집 FPS·생성 속도를 같은 PC·해상도·장면으로 비교한 벤치마크도 아직 없습니다.
두 데이터셋은 출력의 의미와 차량 크기가 다르므로 그대로 합쳐 한 모델에 넣지 않습니다.

근거: [Webots 데이터·학습·평가 기록](../../../../docs/webots-training.md),
[Webots 4개 모터·Physics 정의](../../../Without%20Steering/simulation/protos/BlueRCCar.proto),
[Unity 차량 이동 모델](Assets/Scripts/RobotVehicle.cs), [재렌더링 코드](Assets/Scripts/DrivingLabData.cs).
엔진 기능 참고: [Webots Physics](https://cyberbotics.com/doc/reference/physics),
[Unity Render Texture](https://docs.unity3d.com/2022.3/Documentation/Manual/class-RenderTexture.html).

## 실행

1. 이 `UnityDriving` 폴더를 Unity Hub에서 **2022.3.62f3 프로젝트**로 엽니다.
2. PC Python에 `python -m pip install -r requirements.txt`를 실행합니다.
3. `Assets/Scenes/DrivingLab.unity`를 열고 Play. 씬이 없으면 `Capstone → Build or reset driving lab`.
4. P: 모델 주행 / C: OpenCV 카메라 창 / H: 상태창 / Space·Esc: 정지.
   W/S·A/D: 수동, T: 데이터 수집용 교사, R: 기록.

OpenCV 실행 Python은 `Assets/Settings/DrivingConfig.asset`의 `openCvPython`에 설정합니다.
기본값 `python`이 안 잡히면 설치된 Python 실행 파일의 절대 경로를 입력합니다.

재학습은 이 폴더에서 실행합니다.

```powershell
python Tools/train_vision_policy.py --data AlignedDatasetFrontCamera --epochs 400
```

원본 교사 수집 때 카메라는 앞쪽 65mm였으며 현재 +20mm 영상과 혼동하면 안 됩니다.
이전 뒤쪽 카메라의 중간 렌더링·캐시·Unity Library는 제외하고 현재 데이터와 원본 기록을 보관했습니다.
Unity·Python 코드는 PC 시뮬레이션 전용이며 Raspberry Pi GPIO를 제어하지 않습니다.
