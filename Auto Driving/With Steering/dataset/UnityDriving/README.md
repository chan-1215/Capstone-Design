# Unity로 조향 주행 데이터를 만들고 모델을 학습한 과정

[조향장치 주행](../../README.md)

사진과 CAD 치수를 참고한 Unity 트랙·로봇에서 만든 **합성 주행 데이터셋**입니다.
실물 로봇 데이터와 이전 Webots 데이터셋과 구분합니다.

[실행 화면](#가상-환경과-주행-화면) · [라인 트래킹](#카메라에서-라인을-어떻게-잡나요) · [학습 방식](#생성학습-방식) · [실행 방법](#실행)

## 가상 환경과 주행 화면

![Unity 전체 트랙과 학습 모델로 이동 중인 차량](Diagnostics/runtime_20261111/frame_03/unity_overview.png)

사진의 트랙 형태와 CAD 치수를 참고해 구성한 두 차선 도로입니다.
로봇은 직사각형 프레임·바퀴 네 개·카메라로 단순화하고 앞바퀴 조향과 후륜 구동을 계산합니다.

| 커브를 이동하는 로봇 | 차량 카메라의 실행 중 라인 트래킹 |
| --- | --- |
| ![Unity 모델 주행 약 6초의 로봇](Diagnostics/runtime_20261111/frame_01/unity_robot.png) | ![노란 경계와 흰 점선을 검출하고 커브 경로를 연결한 실행 화면](Diagnostics/runtime_20261111/frame_01/opencv_tracking.png) |

두 이미지는 **2026-11-11 학습 모델 주행 실행의 약 6초 장면**입니다.
Unity 카메라 출력과 실행 중 OpenCV 표시를 저장했습니다. OpenCV는 비동기 갱신이므로 정확히 같은 프레임을 뜻하지는 않습니다.
노란색은 경계 윤곽, 하늘색은 흰 점선 후보, 초록색은 선택한 점선들의 연결 경로입니다.
이 실행은 1차선 출발에서 두 바퀴를 완료했으며 [결과·모델 해시](Diagnostics/runtime_20261111/run_result.json)와
[캡처 시각·차량 위치](Diagnostics/runtime_20261111/frame_01/capture.json)를 함께 보관했습니다.

## 카메라에서 라인을 어떻게 잡나요?

다음은 실행 약 26초에 저장한 **동일 RGB 프레임을 OpenCV로 다시 처리한 설명용 결과**입니다.
원본과 처리 결과를 같은 시야로 비교할 수 있습니다.

| ① 실제 모델 입력 RGB | ② OpenCV 점선·경계·추적 경로 |
| --- | --- |
| ![모델이 보는 원본 카메라 영상](Diagnostics/runtime_20261111/frame_03/unity_policy_input.png) | ![같은 RGB에서 검출한 경계와 점선 연결](Diagnostics/vision_stages_20261111/tracking.png) |

| ③ 노란 경계 마스크 | ④ 흰색 후보 마스크 |
| --- | --- |
| ![HSV로 노란 경계를 분리하고 닫힘 연산을 적용한 마스크](Diagnostics/vision_stages_20261111/yellow_mask.png) | ![윤곽 검사 전 흰색 표시 후보를 분리한 마스크](Diagnostics/vision_stages_20261111/white_mask.png) |

1. **노이즈 완화:** GaussianBlur(5×5)로 잔무늬를 부드럽게 만듭니다.
2. **색 분리:** HSV에서 노랑·흰색을 마스크로 추출하고 관심 영역을 제한합니다. 마스크의 흰 픽셀이 검출 후보입니다.
3. **점선 후보 선별:** 윤곽의 면적·폭·높이와 주변 검은 노면을 검사합니다. 위 흰색 마스크에는 아직 노면 밖의 흰 바탕이 포함되므로 마스크 자체를 확정 차선으로 보지 않습니다.
4. **경로 표시:** 가까운 점선부터 연결하고 노란 경계를 가로지르는 연결을 제외합니다.

코드는 [`opencv_lane_view.py`](Tools/opencv_lane_view.py), 설명용 이미지 재생성 도구는
[`export_unity_vision_stages.py`](../../../../docs/export_unity_vision_stages.py)입니다.
**OpenCV 추적선은 인식 확인용이며, 현재 차량의 조향·속도는 원본 RGB를 읽는 학습 MLP가 결정합니다.**

<details>
<summary>점선이 부족한 장면에서는 어떻게 보이나요?</summary>

![점선 하나만 검출돼 연결 경로를 확정하지 못한 실행 화면](Diagnostics/runtime_20261111/frame_02/opencv_tracking.png)

약 16초 장면에서는 흰 점선 후보가 1개여서 초록 연결 경로를 확정하지 못했습니다.
이는 OpenCV 표시의 경로 미확인 상태이며, 학습 모델의 경로 상실 판정이나 정지 여부와는 구분합니다.
[해당 검출 기록](Diagnostics/runtime_20261111/frame_02/opencv_tracking.json)

</details>

## 어떤 데이터를 보관했나요?

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

## 주행 사진과 시뮬레이터 비교

실행 사진과 Webots·Unity의 장단점 비교는 [Auto Driving README](../../../README.md#가상-주행-데이터셋)에서 바로 볼 수 있습니다.
이 페이지에서는 Unity의 실행·인식 화면부터 데이터 구성과 학습·실행 방법까지 확인할 수 있습니다.

## 실행

1. 이 `UnityDriving` 폴더를 Unity Hub에서 **2022.3.62f3 프로젝트**로 엽니다.
2. PC Python에 `python -m pip install -r requirements.txt`를 실행합니다.
3. `Assets/Scenes/DrivingLab.unity`를 열고 Play. 씬이 없으면 `Capstone → Build or reset driving lab`.
4. P: 모델 주행 / C: OpenCV 카메라 창 / H: 상태창 / Space·Esc: 정지.
   W/S·A/D: 수동, T: 데이터 수집용 교사, R: 기록.

OpenCV 실행 Python은 `Assets/Settings/DrivingConfig.asset`의 `openCvPython`에 설정합니다.
기본값 `python`이 안 잡히면 설치된 Python 실행 파일의 절대 경로를 입력합니다.

재촬영은 Unity Editor가 해당 프로젝트를 열고 있지 않을 때 `-batchmode -projectPath <UnityDriving 경로> -executeMethod RuntimeCapture.Run -simSmoke -policyTest -policyLane 0 -simSeconds 150` 인수로 실행합니다.

재학습은 이 폴더에서 실행합니다.

```powershell
python Tools/train_vision_policy.py --data AlignedDatasetFrontCamera --epochs 400
```

원본 교사 수집 때 카메라는 앞쪽 65mm였으며 현재 +20mm 영상과 혼동하면 안 됩니다.
이전 뒤쪽 카메라의 중간 렌더링·캐시·Unity Library는 제외하고 현재 데이터와 원본 기록을 보관했습니다.
Unity·Python 코드는 PC 시뮬레이션 전용이며 Raspberry Pi GPIO를 제어하지 않습니다.
