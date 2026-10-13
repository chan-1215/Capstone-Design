# 제스처 인식 모듈 — 다른 파이(주행 코드)에 통합하기 위한 설명서

이 폴더(`Lee/gesture/`)는 AI-Rover 메인 코드가 있는 파이에서 제스처 인식과 관련된 파일만 모아 올린 것입니다.
주행 코드만 있는 다른 파이에 이 파일들을 받아서 제스처 인식 기능을 통합하려는 목적입니다.

## 1. 포함된 파일

| 파일 | 용도 | 필수 여부 |
|---|---|---|
| `gesture_recognition_module.py` | MediaPipe + KNN으로 손 모양(주먹="stop", 손바닥="go")을 인식하는 핵심 모듈 | 필수 |
| `hand_utils.py` | `gesture_recognition_module.py`가 내부에서 쓰는 손 좌표 정규화/판정 함수 모음 | 필수 (같은 폴더에 있어야 함) |
| `gesture_knn_model.npz` | KNN 분류기가 참조하는 학습된 손동작 특징 데이터 | 필수 |
| `cnn_compare_module.py` | KNN 결과를 CNN으로 한 번 더 비교해서 로그만 남기는 "그림자 모드" 보조 기능 | 선택 (기본적으로 꺼져 있음) |
| `gesture_seq_skeleton_cnn_model.pt` | `cnn_compare_module.py`가 쓰는 CNN 가중치 파일 | 선택 (`cnn_compare_module.py`를 쓸 때만 필요) |

이 버전은 OpenCV(cv2) 호출이 전부 살아있는 **정상 동작 버전**입니다. 원래 메인 파이에서는 카메라/모터
자원 충돌을 피하려고 이 모듈의 OpenCV 호출을 잠시 주석 처리해 뒀었는데, 이 폴더에 올린 파일은 그 주석을
해제한 원본이므로 그대로 쓰시면 됩니다.

## 2. 파일별 역할과 기능

### gesture_recognition_module.py
제스처 인식의 핵심 모듈입니다. `GestureRecognizer` 클래스 하나로 구성되어 있습니다.

- `__init__`: `gesture_knn_model.npz`를 불러오고, 최근 30프레임을 쌓아두는 버퍼와 MediaPipe의 손 검출기
  (`mp.solutions.hands.Hands`)를 초기화합니다.
- `load_model`: `.npz` 파일에서 학습된 특징 벡터(`features`)와 정답 라벨(`labels`)을 읽어옵니다.
- `raw_hand_points`: MediaPipe가 내놓은 손 랜드마크 21개(x, y, z)를 numpy 배열로 변환합니다.
- `normalize_hand`: `hand_utils.normalize_hand_frame`을 호출해서 손목 기준으로 좌표를 정규화합니다.
- `make_feature`: 버퍼에 쌓인 30프레임을 하나의 특징 벡터로 이어 붙입니다. 손이 인식되지 않은 프레임은
  0으로 채웁니다.
- `predict_knn`: 지금 들어온 특징 벡터와 `.npz`에 저장된 학습 데이터 사이의 거리를 계산해서, 가장 가까운
  k개(기본 3개)의 라벨 중 다수결로 예측합니다. 거리가 `threshold`(기본 30.0)보다 멀면 `"unknown"`으로
  처리합니다.
- `smooth_prediction`: 최근 5번의 예측 중 다수결로 최종 라벨을 정해서, 한두 프레임의 오판정으로 라벨이
  순간적으로 튀는 것을 막습니다.
- `update_display_label`: `"stop"`/`"go"`로 판정되면 그 라벨을 `hold_seconds`(기본 1초) 동안 유지해서,
  화면에 라벨이 깜빡이는 현상을 줄입니다.
- `process(frame)`: 가장 바깥에서 호출하는 진입점입니다. 프레임을 MediaPipe에 넘겨 손을 검출하고, 특징을
  뽑아 KNN으로 예측한 뒤, `hand_utils.is_open_hand`/`is_palm_allowed`로 "stop" 판정을 한 번 더 검증하고,
  디버그용 프레임(손 랜드마크와 라벨 텍스트가 그려진 이미지)과 함께 결과를 dict로 반환합니다.
- `get_raw_sequence`: `cnn_compare_module.py`의 CNN이 쓸 수 있도록, 정규화하지 않은 원본 좌표 시퀀스를
  제공합니다.
- `close`: MediaPipe 핸들을 정리합니다. 프로그램 종료 시 호출해야 합니다.

### hand_utils.py
`gesture_recognition_module.py`가 쓰는 손 좌표 계산용 보조 함수 모음입니다. 클래스 없이 함수만 있습니다.

- `normalize_hand_frame`: 손목(0번 관절)을 원점으로 옮기고, 손목에서 중지 MCP 관절(9번)까지의 거리로
  나눠서 크기를 정규화합니다. 카메라와 손 사이의 거리나 손의 크기가 달라도 같은 모양이면 같은 특징 벡터가
  나오게 하기 위한 처리입니다.
- `normalize_hand_sequence`: 위 정규화를 프레임 시퀀스 전체에 적용합니다.
- `is_open_hand`: 손가락 네 개(검지~소지)의 끝 관절이 중간 관절보다 손목에서 더 멀리 떨어져 있는지로
  손이 펴져 있는지 판정합니다. KNN이 `"stop"`(손바닥)으로 예측했을 때, 실제로 손이 펴져 있는지 한 번 더
  확인하는 안전장치로 쓰입니다.
- `palm_score`: 손목과 검지·소지 MCP 관절로 벡터의 외적을 구해서, 손바닥이 카메라를 향하는지 손등이
  향하는지를 양수/음수 값으로 나타냅니다.
- `is_palm_allowed`: `palm_sign` 설정(`"off"`/`"positive"`/`"negative"`)에 따라 특정 방향으로 향한
  손바닥만 `"stop"`으로 인정하도록 걸러줍니다. 기본값(`"off"`)은 방향을 가리지 않습니다.

### cnn_compare_module.py (선택 기능)
실제 주행에는 관여하지 않고, KNN의 판정이 맞는지 CNN으로 한 번 더 검증해서 로그만 남기는 "그림자 모드"
비교 도구입니다.

- `SeqCNN`: 10프레임의 손 스켈레톤 이미지를 입력으로 받는 3개 합성곱 층짜리 분류기(`"stop"`/`"go"`/
  `"unknown"` 3종 분류)입니다.
- `draw_skeleton_frame`: MediaPipe 손 좌표 21개를 64x64 크기의 흑백 스켈레톤 그림으로 그려서 CNN에 넣을
  수 있는 이미지로 바꿔줍니다.
- `CNNComparator.__init__`: `gesture_seq_skeleton_cnn_model.pt`(학습된 가중치)를 불러옵니다.
- `CNNComparator.predict`: `GestureRecognizer.get_raw_sequence()`가 내놓은 30프레임 중 10프레임을
  골라 스켈레톤 이미지로 만든 뒤 CNN으로 추론해서 라벨과 확신도를 반환합니다.
- `CNNComparator.log_comparison`: KNN이 내놓은 라벨과 CNN이 내놓은 라벨이 일치하는지를 CSV 파일에
  주기적으로(기본 1초 간격) 기록합니다. 이 기록은 CNN이 KNN을 대체할 만큼 믿을 수 있는지 나중에
  판단하기 위한 데이터일 뿐, 그 자체로 로봇을 제어하지는 않습니다.

## 3. 받는 파이에서 해야 할 일

### 3-1. 파일 배치
`gesture_recognition_module.py`, `hand_utils.py`, `cnn_compare_module.py`(선택)는 **같은 폴더**에 두어야
합니다. `import hand_utils`처럼 평범한 모듈 import 방식이라, 패키지 경로가 아니라 같은 디렉터리에 있어야
정상적으로 불러와집니다.

`gesture_knn_model.npz`는 기본적으로 `/home/pi/gesture_knn_model.npz` 경로를 찾습니다
(`gesture_recognition_module.py`의 `GestureRecognizer.__init__` 기본값, `model_path="/home/pi/gesture_knn_model.npz"`).
다른 경로에 두실 경우, `GestureRecognizer(model_path="원하는 경로")`로 직접 지정해 주시면 됩니다.

### 3-2. 설치해야 하는 패키지
```
pip install mediapipe opencv-python numpy
```
`cnn_compare_module.py`를 같이 쓰실 경우에만 추가로:
```
pip install torch
```

### 3-3. 주행 코드에 연결하는 방법
메인 루프 쪽에서 아래처럼 사용하시면 됩니다. (원래 메인 파이의 `project4_iot_center_filltering.py`에서
쓰던 방식과 동일합니다.)

```python
from gesture_recognition_module import GestureRecognizer

gesture_recognizer = GestureRecognizer(
    model_path="/home/pi/gesture_knn_model.npz",
)

# 매 프레임마다
result = gesture_recognizer.process(frame)   # frame: BGR numpy 배열 (cv2로 읽은 그대로)
label = result["label"]                       # "stop" / "go" / "unknown"
debug_frame = result["debug_frame"]           # 손 랜드마크가 그려진 디버그용 프레임
```

`label`이 `"stop"`이면 정지, `"go"`이면 주행 시작 같은 식으로 받는 파이의 주행 로직에 연결하시면 됩니다.
종료 시에는 `gesture_recognizer.close()`를 호출해서 MediaPipe 핸들을 정리해 주셔야 합니다.

`cnn_compare_module.py`는 KNN 판정 결과를 검증용으로 로그에만 남기는 선택 기능이라, 당장 주행에 꼭
필요하지는 않습니다. 쓰시려면 아래처럼 생성합니다.

```python
from cnn_compare_module import CNNComparator

cnn_comparator = CNNComparator(
    model_path="gesture_seq_skeleton_cnn_model.pt",
    log_path="cnn_compare_log.csv",
)
```

## 4. 원본 출처
이 파일들은 메인 코드가 있는 파이(`~/ai_rover/gesture/`)에서 2026-10-13에 내려받았습니다. 메인 파이 쪽의
최신 수정 사항이 있다면 이 폴더의 내용이 오래된 상태일 수 있으니, 통합 전에 최신 버전인지 한 번 더
확인하시는 것을 권장합니다.
