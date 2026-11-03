# 저장소 폴더 안내

[프로젝트 처음으로](../README.md)

코드는 원래 경로를 유지하고, 주행 구조와 제스처 작업을 아래처럼 구분합니다.
분류 문서는 실행 코드의 설치·인계 문서를 대체하지 않습니다.

## 주요 개발 영역

| 영역 | 폴더 | 문서 |
| --- | --- | --- |
| 조향장치 없는 주행 | `Driving test`, `Lee` | [주행 구조와 진입점](driving-without-servo.md) |
| 조향장치 있는 주행 | `Auto Driving 20261018`, `Auto Driving`, `Auto Driving@` | [버전별 차이와 코드 구조](driving-with-servo.md) |
| 제스처 인식 | `Lee/gesture`, `gesture`, `Auto Driving 20261018/gesture_reference` | [인식 과정과 모델](gesture-recognition.md) |

`Lee`는 초기 통합 코드이며 하위 `gesture`에 별도 인식 모듈을 포함합니다.
이 때문에 폴더 하나가 한 기능에만 대응하는 구조는 아닙니다.

## 실험과 보조 자료

| 위치 | 내용 |
| --- | --- |
| [`Dataset Project`](../Dataset%20Project/README.md) | Webots 시뮬레이션, 데이터 생성·학습·평가, Pi 실행 실험 |
| [`image capture`](../image%20capture/), [`image capture1`](../image%20capture1/) | 카메라 입력·촬영 실험 |
| [`keyboard`](../keyboard/) | 키보드 조작 실험 |
| [`linetracer`](../linetracer/) | 라인 센서 기반 주행 실험 |
| [`모터제어`](../모터제어/) | DC 모터 개별 제어 실험 |
| [`vision_11`](../vision_11/) | 별도 비전 파이프라인 실험 |
| [`lego.py`](../lego.py) | 색상 영역 검출·LCD 표시 실험 |
| [`yolo_lcd__picam.py`](../yolo_lcd__picam.py) | YOLO·카메라·LCD 연결 실험 |

## 공개 코드와 후속 작업

이 안내의 서보 주행 기준은 GitHub에 공개된 2026년 10월 18일 보관본입니다.
발표 영상이나 PC에서 실행한 후속 버전이 항상 이 코드와 같은 것은 아닙니다.
후속 제스처·GIF 통합과 주행 개선은 해당 소스와 테스트를 검토해 별도 변경으로 반영해야 합니다.

원본 데이터, 가상환경, 비밀번호와 OS 이미지는 저장소에 포함할 대상이 아닙니다.
팀원의 `Auto Driving@`와 각 버전의 HANDOFF·출처 기록은 그대로 보존합니다.
