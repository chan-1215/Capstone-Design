# 소스 통합과 이전 경로

[프로젝트 처음으로](../README.md)

2026년 11월 3일 소스를 세 영역으로 통합했습니다. 원래 개발 PC 폴더는 보존하고,
GitHub의 실제 코드 구조를 아래처럼 변경했습니다.

| 이전 위치 | 현재 위치 |
| --- | --- |
| `Lee/gesture`, `Gesture PC`, `gesture` | [Gesture](../Gesture/README.md) |
| `Auto Driving 20261018/gesture_reference` | `Gesture`의 공통 모듈·모델 |
| `Auto Driving 20261018` 및 PC 후속 변경 | [With Steering](../Auto%20Driving/With%20Steering/README.md) |
| `Auto Driving`, `Auto Driving@` | `With Steering/experiments/paper_track` 한 벌 |
| `Track Vision` | 후속 `With Steering`으로 대체, 과거 내용은 Git 이력 |
| `Driving test` | `Without Steering/controller` |
| `Lee`의 비제스처 모듈 | `Without Steering/legacy_rover` |
| `Dataset Project` | `Without Steering/simulation` |
| `image capture`, `image capture1`, `keyboard`, `모터제어`, `vision_11`, `linetracer` | `Without Steering/experiments` |
| 루트의 `lego.py`, `yolo_lcd__picam.py` | `Without Steering/experiments` |

## 중복 처리

- 제스처 인식 모듈·손 좌표 보조 함수·KNN 모델은 공통 한 벌만 유지합니다.
  개행만 다른 복사본도 통합했으며 모델 내용과 분류 계산은 변경하지 않았습니다.
- Flask의 `gesture_adapter.py`와 이전 트랙의 같은 이름 파일은 공유 모듈 연결용 파일입니다.
  인식 알고리즘과 모델을 복사해 둔 파일이 아닙니다.
- 이전 서보 주행은 `Auto Driving`을 바탕으로 팀원의 `Auto Driving@` 변경을 반영했습니다.
  중복된 도구·테스트·자료를 한 벌로 만들고 팀원 출처는 `history/TEAM_MOTOR_*`에 보존했습니다.
- 동일한 카메라·키보드 단품 실험은 SHA256이 같을 때만 하나로 줄였습니다.
- 서로 다른 트랙의 제어기, 시뮬레이션과 실차 코드는 별도 구현으로 유지합니다.

기존 공개 상태는 [정리 전 커밋 d0b0e91](https://github.com/chan-1215/Capstone-Design/tree/d0b0e911daa404e70202c62789a86ade9a3090c0)에서 확인할 수 있습니다.
이전 `Track Vision`의 공개 보관본은 그 커밋의 `Auto Driving 20261018`에 있습니다.
복사한 후속 PC 소스의 원래 경로·SHA256은 [출처 목록](consolidation-sources.json)에 기록했습니다.
기존 Git 추적 데이터 이미지와 모델은 삭제하지 않고 시뮬레이션 아래로 옮겼습니다.

## 검증 범위

PC에서 공유 제스처·서보 제어·이전 트랙·시뮬레이션 테스트와 웹 입력 테스트를 실행합니다.
Python 테스트 468개와 Node UI 테스트 묶음 7개가 통과했습니다.
이전 데이터 9,002개 파일은 원본과 SHA256을 비교해 보존을 확인했습니다.
검사 결과는 [consolidation-check.json](consolidation-check.json)에 있습니다.
이 작업은 파일·경로 통합이며 새로운 주행 성능이나 인식 정확도를 입증하는 시험은 아닙니다.
Pi의 설치·실행 경로는 자동 변경하지 않았습니다.
