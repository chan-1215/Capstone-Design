# Raspberry Pi 5 적용 절차

이 프로젝트의 실제 로봇 배선 기준은 `Lee/motor_module.py`입니다. GPIO 핀,
모터 번호와 전진/후진 극성은 실제 테스트 관찰값 없이 바꾸지 않습니다.

2026-09-02 실제 모터 단품 테스트로 확인된 매핑:

| 모터 | GPIO | 위치 |
|---|---|---|
| `motor1` | `22, 27` | 왼쪽 앞 |
| `motor2` | `24, 23` | 왼쪽 뒤 |
| `motor3` | `21, 16` | 오른쪽 뒤 |
| `motor4` | `19, 26` | 오른쪽 앞 |

주행 코드에서는 `motor1/2`를 `left_wheels`, `motor3/4`를 `right_wheels`로 사용합니다.

## 모터 배선 보정 테스트

로봇을 새로 연결해서 배선 기준을 다시 잡을 때는 바퀴를 띄운 상태에서 대화형 콘솔을 사용합니다.

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/test_motors_console.py --speed 0.30 --duration 1.0
```

콘솔 안에서 자주 쓰는 명령:

```text
map          현재 코드 기준 motor1~4 라벨과 GPIO 표시
sequence     motor1~4를 forward/backward 순서로 하나씩 테스트
1f / 1b      motor1 forward/backward
2f / 2b      motor2 forward/backward
3f / 3b      motor3 forward/backward
4f / 4b      motor4 forward/backward
all f        현재 설정 기준 전체 전진
arc-left     현재 설정 기준 좌회전 곡선
arc-right    현재 설정 기준 우회전 곡선
stop         전체 정지
q            종료
```

관찰값은 `motor1 forward = 실제 어느 바퀴가 어느 방향으로 도는지` 형식으로 기록한다.
그 결과를 기준으로만 `Lee/motor_module.py`의 핀/좌우/전후 매핑을 수정한다.

## Pi에 가져갈 파일

- `Lee/`
- `Dataset Project/controllers/`
- `Dataset Project/hardware/run_learned_pi.py`
- `Dataset Project/hardware/test_motors_console.py`
- `Dataset Project/models/steering_v2.npz`
- `Dataset Project/models/driveability_v1.npz`

`dataset/runs/`와 `dataset_v2/`는 Pi 주행 런타임에는 필요 없습니다. 학습과
재학습용 원본이므로 PC나 외장 저장소에 보관합니다.

## USB 이더넷으로 Pi에 전송

현재 Pi가 USB 네트워크로 `192.168.137.8`에 잡혀 있으면, Windows PC에서 아래
스크립트로 필요한 파일을 보낼 수 있습니다.

```powershell
cd "C:\Users\a\Capstone-Design"
powershell -ExecutionPolicy Bypass -File "Dataset Project\hardware\sync_pi_usb.ps1" -PiHost 192.168.137.8 -PiUser pi
```

compact dataset까지 Pi에 같이 보관하려면 `-IncludeDatasetV2`를 추가합니다.

```powershell
powershell -ExecutionPolicy Bypass -File "Dataset Project\hardware\sync_pi_usb.ps1" -PiHost 192.168.137.8 -PiUser pi -IncludeDatasetV2
```

원본 `dataset/runs/`는 훨씬 크므로 Pi에는 기본 전송하지 않습니다. 꼭 필요할 때만
`-IncludeRawRuns`를 추가합니다.

## 설치

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy python3-gpiozero rpicam-apps
```

카메라는 기존 `Lee/camera_module.py`처럼 `rpicam-vid` MJPEG 스트림을 사용합니다.

## 첫 실행

바퀴를 바닥에서 띄운 상태로 먼저 확인합니다.

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/run_learned_pi.py --duration 10
```

화면 확인이 필요하면:

```bash
python3 -B hardware/run_learned_pi.py --preview
```

종료는 `Ctrl+C`입니다. `q` 키는 preview 창이 떠 있을 때만 동작합니다.

## 데이터셋 사용 방식

- 긍정형 데이터: 차선이 보이고 expert PWM 라벨이 있는 정상 주행 프레임입니다.
  `steering_v2.npz`가 좌우 PWM을 학습할 때 사용합니다.
- 복구형 데이터: learned 주행 중 흔들리거나 이탈 직전인 프레임에 expert 기준 PWM을
  붙인 데이터입니다. 정상 주행으로 돌아가는 조향을 학습시킵니다.
- 부정형 데이터: 차선이 없거나 경로에서 많이 벗어난 프레임입니다.
  PWM 라벨로 섞지 않고 `driveability_v1.npz` 안전 판단 모델에 사용합니다.

실제 Pi에서는 `driveability_v1.npz`가 위험 장면을 감지하면 `safety_stop`으로
모터를 멈춥니다. 차선이 일부라도 보이는 낮은 확신 구간은 바로 멈추지 않고
`vision_trim`으로 보정하면서 계속 주행합니다.

## 현재 검증 상태

- 일반 검은 도로/흰 차선 Webots 테스트: 통과
- 반전 흰 도로/검은 차선 Webots 테스트: 통과
- 단위 테스트: `python -B -m unittest discover -s tests -v`

실제 로봇 첫 주행 전에는 반드시 낮은 속도, 짧은 시간, 넓은 공간에서 테스트합니다.
