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

## 2. 받는 파이에서 해야 할 일

### 2-1. 파일 배치
`gesture_recognition_module.py`, `hand_utils.py`, `cnn_compare_module.py`(선택)는 **같은 폴더**에 두어야
합니다. `import hand_utils`처럼 평범한 모듈 import 방식이라, 패키지 경로가 아니라 같은 디렉터리에 있어야
정상적으로 불러와집니다.

`gesture_knn_model.npz`는 기본적으로 `/home/pi/gesture_knn_model.npz` 경로를 찾습니다
(`gesture_recognition_module.py`의 `GestureRecognizer.__init__` 기본값, `model_path="/home/pi/gesture_knn_model.npz"`).
다른 경로에 두실 경우, `GestureRecognizer(model_path="원하는 경로")`로 직접 지정해 주시면 됩니다.

### 2-2. 설치해야 하는 패키지
```
pip install mediapipe opencv-python numpy
```
`cnn_compare_module.py`를 같이 쓰실 경우에만 추가로:
```
pip install torch
```

### 2-3. 주행 코드에 연결하는 방법
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

## 3. 원본 출처
이 파일들은 메인 코드가 있는 파이(`~/ai_rover/gesture/`)에서 2026-10-13에 내려받았습니다. 메인 파이 쪽의
최신 수정 사항이 있다면 이 폴더의 내용이 오래된 상태일 수 있으니, 통합 전에 최신 버전인지 한 번 더
확인하시는 것을 권장합니다.
