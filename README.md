# 보행자와 소통하는 자율주행 시스템

Raspberry Pi 모형 차량의 차선 추종과 손동작 인식을 다룬 캡스톤 팀 프로젝트입니다.
주행은 조향장치 유무에 따라 구분하고, 제스처 인식은 별도 모듈로 관리합니다.

![모형 트랙과 서보 조향 차량](docs/images/robot-track.jpg)

## 프로젝트 구성

| 영역 | 주요 내용 | 코드와 개발 기록 |
| --- | --- | --- |
| 조향장치 없는 주행 | 좌우 DC 모터의 속도 차이로 회전, OpenCV 차선 추종과 학습 모델 실험 | [살펴보기](docs/driving-without-servo.md) |
| 조향장치 있는 주행 | 앞바퀴 서보 조향과 후륜 구동, 경로 추종과 Flask 수동·자율 제어 | [살펴보기](docs/driving-with-servo.md) |
| 제스처 인식 | MediaPipe 손 관절 추출, NumPy 특징 처리, KNN GO·STOP 분류 | [살펴보기](docs/gesture-recognition.md) |

## 사용 기술

- 영상과 인식: **Python · OpenCV · NumPy · MediaPipe · KNN**
- 차량 제어: **Raspberry Pi · GPIO Zero · lgpio · P제어**
- 웹 인터페이스: **Flask · HTML/CSS · JavaScript**
- 별도 실험: **Webots 데이터 생성·모델 학습 · YOLO 객체 검출 · CNN 분류 비교**

## 개발 과정

DC 모터 속도 차이를 이용한 주행 실험에서 시작해 서보 조향 구조로 확장했습니다.
차선 검출, 모터 출력 보정, 커브 경로 추종을 실험하고, 손동작 인식 모듈을 별도로 정리했습니다.
이 저장소에는 각 시기의 코드와 설정·검증 기록을 함께 보관합니다.

[발표 및 시연 자료](https://pedestrian-gesture-deck.pages.dev/showcase) · [전체 폴더 안내](docs/repository-map.md)

## 코드 버전

현재 공개된 서보 주행 기준본은 [`Auto Driving 20261018`](Auto%20Driving%2020261018/README.md)입니다.
이 기준본은 제스처 코드·모델을 보관하지만 Flask와의 연결은 포함하지 않습니다.
이후 개발한 제스처·GIF 통합 및 주행 보완 내용은 공개 기준본과 구분해 관리합니다.
각 버전의 실행 방법과 검증 범위는 해당 폴더의 README와 HANDOFF에서 확인할 수 있습니다.
