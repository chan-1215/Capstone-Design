# Auto Driving@

2026-10-14 후륜 구동 모터 보정 작업의 최종 코드 보관본입니다.
기존 `Auto Driving/`은 보존하고 별도 폴더로 추가했습니다.
변경 상세는 [CHANGES_20261014.md](CHANGES_20261014.md),
이어받을 내용은 [HANDOFF.md](HANDOFF.md)를 읽어주세요.

## 출처

실행 파일은 Pi의 아래 파일을 직접 받아 저장했습니다.

```text
/home/pi/steering_robot_presentation_20261014/road_drive_web.py
```

다른 실행 보조 코드와 기존 테스트 자료는 저장소의 `Auto Driving/` 사본입니다.
Pi 전체 폴더, 설치 환경 또는 모든 배포 파일을 백업한 것은 아닙니다.

## 최종 구동 구성

- 앞바퀴: 서보 조향. 앞바퀴 하나만 독립 정지시키는 기능은 없습니다.
- 후륜: DC 모터 두 개로 추진합니다.
- 현재 코드 정의: 모터 1 = 왼쪽 후륜, 모터 2 = 오른쪽 후륜.
- BCM GPIO: 모터 1 `(20, 21)`, 모터 2 `(23, 24)`, 서보 `18`.
- 전진 극성: 모터 1 `forward()`, 모터 2 `backward()`.
- 좌우 번호는 사용자의 마지막 정정을 반영한 설정입니다. 독립 단품 물리 검증은 미완료입니다.

| 전진 입력 | 모터 1 / 왼쪽 | 모터 2 / 오른쪽 |
| --- | --- | --- |
| W | 기존 보정 PWM × 1.10 | 기존 보정 PWM |
| W+A | 정지 | 기존 보정 PWM × 1.60 |
| W+D | 기존 보정 PWM × 1.35 | 정지 |

후진에는 추가 증속·직진 보정을 적용하지 않습니다.
A/D만 누르면 전진 입력이 없어 두 구동 모터는 정지하고 서보만 조향합니다.
자동 제어는 같은 전진 모터 함수를 쓰지만 자동 서보 방향은 기존대로입니다.
수동 A/D 부호 보정이 자동 조향에 적용된 것은 아닙니다.

## 실행

알려진 배선과 카메라 환경이 준비된 Pi에서 사용할 명령입니다.

```bash
cd '/home/pi/Capstone-Design/Auto Driving@'
python road_drive_web.py --gesture --motor1-scale 1.08 --motor2-scale 0.89
```

이번 작업에서 사용한 기존 Pi 가상환경·배포 경로의 실행 명령:

```bash
/home/pi/steering_robot_drive_eval_20261012/.venv/bin/python \
  /home/pi/steering_robot_presentation_20261014/road_drive_web.py \
  --gesture --motor1-scale 1.08 --motor2-scale 0.89
```

웹 주소는 `http://<pi-ip>:5001/`입니다. 같은 CSI 카메라를 사용하는 서버는 한 번만 실행합니다.
서버 시작만으로 모터가 구동되지는 않습니다. GitHub 보관 작업에서 서버를 재시작하지 않았습니다.
`--gesture`는 표시용이며 모터 시작·정지를 제어하지 않습니다.
선택적 제스처 기능에는 외부 `/home/pi/gesture_knn_model.npz`와 MediaPipe 등이 필요합니다.
이 폴더에 모델을 새로 포함하지 않았습니다.

## PWM 계산 예시

속도 `0.22`, 보정값 `1.08 / 0.89` 기준입니다.

| 상황 | 모터 1 | 모터 2 |
| --- | --- | --- |
| 직진 | `forward(0.26136)` | `backward(0.19580)` |
| 왼쪽 커브 | `stop()` | `backward(0.31328)` |
| 오른쪽 커브 | `forward(0.32076)` | `stop()` |
| 후진 | `backward(0.23760)` | `forward(0.19580)` |

이는 실제 RPM이나 회전 반경이 아니라 PWM 명령입니다.
`/status`의 `drive.motor1_pwm_command`, `drive.motor2_pwm_command`도 명령값입니다.
모터 2는 차량 전진에 `backward()`를 쓰므로 전진 명령 상태가 음수로 표시됩니다.

## PC 검증

```bash
python -m pip install -r requirements-pc.txt
python -B verify_pc.py
```

Python 3.12 환경에서 **103개 테스트 통과**를 확인했습니다.
Windows 한글 경로의 이미지 읽기는 검증 프로세스에서만 우회합니다.
카메라 코드나 실제 Pi 런타임에 우회 코드를 넣은 것이 아닙니다.
실제 GPIO 대신 모의 객체를 사용하므로 이 테스트는 물리 주행 성공을 인증하지 않습니다.

## 남은 확인

- 마지막 수정 이후 왼쪽 후륜 정지와 직진 쏠림 개선 결과는 아직 받지 못했습니다.
- Pi 최종본의 `MAX_CORNER_SECONDS = 0`을 그대로 보존했습니다. 자동 코너 허용 시간이 0초인 설정입니다.
- 수동과 자동 서보 방향 차이, 실제 모터 좌우 번호, 반복 주행 및 연속 완주는 별도 확인이 필요합니다.
- 원본 영상·학습 세션·가상환경·Pi 배포 백업·비밀번호는 포함하지 않았습니다.
