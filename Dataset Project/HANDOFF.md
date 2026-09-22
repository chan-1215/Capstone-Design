# 새 PC 작업 인계 문서

마지막 갱신: 2026-09-02 20:45 KST

## 가장 먼저 지킬 것

1. 이 문서를 끝까지 읽고 시작한다.
2. `Lee/motor_module.py`의 GPIO 핀, 모터 순서, 전진/후진 극성은 변경하지 않는다.
3. 기존 `Lee/camera_module.py`, `Lee/gesture_recognition_module.py` 등 사람 제스처/카메라 코드는 자율주행 데이터 작업 중 수정하지 않는다.
4. Webots/시뮬레이션 쪽 어댑터와 실제 하드웨어 코드는 분리한다.
5. `Dataset Project/dataset/runs/`와 `Dataset Project/dataset_v2/`는 Git 추적 대상이 아니다. 삭제하지 말고 보존한다.

## 프로젝트 목적

Webots 가상 RC카와 전방 카메라로 차선 중앙 주행 데이터를 만들고, 최종적으로 같은 주행 판단과 좌우 PWM을 Raspberry Pi 5 실제 RC카에 적용한다.

## 새 PC 세팅 상태

이 PC 기준으로 확인/설치 완료:

- Git `2.53.0.windows.2`
- GitHub CLI `2.96.0`
- Python `3.9.13`
- NumPy `2.0.2`
- OpenCV `5.0.0`
- pytest `8.4.2`
- Webots `R2025a`

`Dataset Project/controllers/rc_car_controller/runtime.ini`는 현재 Python 3.9 경로:

```text
C:\Users\a\AppData\Local\Programs\Python\Python39\python.exe
```

## Raspberry Pi USB 연결 상태

2026-09-01 17:52 KST 기준:

- Pi USB 이더넷 IP: `192.168.137.8`
- Windows 쪽 USB 네트워크 IP: `192.168.137.1`
- SSH 포트 22: reachable
- Pi 사용자명: `pi`
- 전송 위치: `~/Capstone-Design`
- 전송 방식: `hardware/sync_pi_usb.ps1 -PiHost 192.168.137.8 -PiUser pi -IncludeDatasetV2`
- 전송 완료: runtime 코드, `models/`, `dataset_v2/`
- Pi 확인 결과:
  - `Dataset Project/models/*.npz`: 3개
  - `Dataset Project/dataset_v2/images`: 9,000개
  - `Dataset Project/dataset_v2/manifest.csv`: 9,001줄
  - Pi Python에서 `cv2`, `numpy` import 성공
  - `models/steering_v2.npz` 로드 성공
  - 첫 dataset 이미지 OpenCV 로드 shape: `(240, 320, 3)`

비밀번호는 문서나 스크립트에 저장하지 않는다.

## Raspberry Pi 연결 USB 백업 상태

2026-09-02 12:05 KST 기준, Pi에 연결된 SanDisk 64GB USB 저장장치에 Pi 내부 작업 폴더를 백업했다.

- USB 장치: `/dev/sda1`
- 마운트 위치: `/mnt/sandisk64`
- 백업 위치: `/mnt/sandisk64/Capstone-Design-Pi-Backup-20260901_185455`
- 백업 원본: `/home/pi/Capstone-Design`
- 원본 크기/파일 수: `87M`, `9,043` files
- 백업 크기/파일 수: `88M`, `9,043` files
- `rsync -ani` dry-run 결과: 추가 복사 필요 파일 없음

이 백업은 Pi에 올라간 runtime 코드, 모델, `dataset_v2` 기준이다. Windows PC에만 남아 있는 raw run 데이터 `Dataset Project/dataset/runs/`는 Pi 내부 저장소에 없으면 이 USB 백업에도 포함되지 않는다.

## Raspberry Pi 첫 실행 결과

2026-09-01 18:01 KST, 바퀴를 띄운 상태에서 10초 실행 완료:

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/run_learned_pi.py --duration 10
```

결과:

- `rpicam camera started`
- `steering_v2.npz` 로드 성공
- `driveability_v1.npz` 로드 성공
- 로그 9회 출력, 모두 `learned_model`
- lane status: 모두 `both_lanes`
- driveability score: 모두 `1.000`
- safety state: 모두 `driveable`
- PWM 범위:
  - left: `0.269` ~ `0.288`
  - right: `0.352` ~ `0.371`
- 종료 시 `Motors cleaned up`, `rpicam camera stopped`
- 실행 후 `run_learned`, `rpicam`, `gesture` 관련 잔여 프로세스 없음

처음 실행 시 `GPIO busy`로 실패했다. 원인은 기존
`gesture/project4_iot_center_filltering.py` 프로세스와 그 자식 `rpicam-vid`가
GPIO/카메라를 잡고 있었기 때문이다. 해당 프로세스를 정상 종료한 뒤 재실행하니 성공했다.

## Raspberry Pi 모터 단품 테스트 결과

2026-09-01 18:06 KST, 바퀴를 띄운 상태에서 1~4번 모터를 순차 테스트했다.

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/test_motors_once.py --speed 0.35 --duration 0.5 --pause 0.4
```

처음 스크립트의 위치명은 좌우가 반대로 표기되어 있었다. 2026-09-01 18:15 KST에
사용자가 실제 관찰값으로 `motor1/2 = 좌측`, `motor3/4 = 우측`이라고 확인했다.
2026-09-02 20:45 KST에 사용자가 다시 실제 관찰값으로 `motor3 = 오른쪽 뒤`,
`motor4 = 오른쪽 앞`이라고 확인했다. 핀 번호와 motor 번호는 유지하고, 오른쪽
전후 그룹과 문서 표기만 아래처럼 수정했다.

현재 기준 순서:

- `motor1 left_front`: forward 0.5s, backward 0.5s
- `motor2 left_rear`: forward 0.5s, backward 0.5s
- `motor3 right_rear`: forward 0.5s, backward 0.5s
- `motor4 right_front`: forward 0.5s, backward 0.5s

결과:

- 모든 단계 로그 출력 완료
- 종료 시 `Motors cleaned up`
- 실행 후 `test_motors`, `run_learned`, `rpicam`, `gesture` 관련 잔여 프로세스 없음

2026-09-02 15:38 KST에 새 로봇 배선 확인용 대화형 모터 테스트 콘솔을 추가했다.

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/test_motors_console.py --speed 0.30 --duration 1.0
```

주요 콘솔 명령은 `sequence`, `1f`, `1b`, `2f`, `2b`, `3f`, `3b`, `4f`, `4b`,
`all f`, `arc-left`, `arc-right`, `stop`, `q`이다. 실제 관찰값을 기준으로만
`Lee/motor_module.py`의 핀/좌우/전후 매핑을 다시 수정한다.

## Raspberry Pi 모델 주행 테스트 결과

2026-09-01 18:28 KST, 실제 Pi에서 dataset_v2로 학습한 모델을 5초 실행했다.
데이터셋 파일을 실시간으로 읽은 것이 아니라, `steering_v2.npz`와
`driveability_v1.npz`를 사용한 주행 테스트다.

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/run_learned_pi.py --duration 5
```

결과:

- `rpicam camera started`
- `steering_v2.npz` 로드 성공
- `driveability_v1.npz` 로드 성공
- 로그 4회 출력, 모두 `learned_model`
- lane status: 모두 `both_lanes`
- safety state: `driveable` 2회, `uncertain` 2회
- safety_stop 없음
- lane error: `17`, `5`, `1`, `-1`
- driveability score: `0.729`, `0.151`, `0.214`, `1.000`
- PWM 범위:
  - left: `0.347` ~ `0.417`
  - right: `0.278` ~ `0.318`
- 종료 시 `Motors cleaned up`, `rpicam camera stopped`
- 실행 후 `run_learned`, `rpicam`, `gesture` 관련 잔여 프로세스 없음

사용자 관찰:

- 차량은 정상적으로 앞으로 이동했다.
- 5초 제한 때문에 우회전 라인 부근에서 정확히 멈췄다.
- 이 관찰 기준으로 전체 forward/backward 극성은 정상이다.
- 다음 확인은 `--duration 10` 또는 `--duration 15`로 우회전 구간 진입/통과 여부를 보는 것이다.

2026-09-01 18:39 KST, 트랙 위 실제 카메라 기반 주행을 10초 실행했다.

```bash
cd ~/Capstone-Design/Dataset\ Project
python3 -B hardware/run_learned_pi.py --duration 10
```

결과:

- `rpicam camera started`
- `steering_v2.npz` 로드 성공
- `driveability_v1.npz` 로드 성공
- 로그 9회 출력, 모두 `learned_model`
- lane status: `left_only` 2회, `both_lanes` 7회
- safety state: `driveable` 6회, `uncertain` 3회
- safety_stop 없음
- lane error 범위: `-50` ~ `57`
- driveability score 범위: `0.000` ~ `1.000`
- PWM 범위:
  - left: `0.102` ~ `0.604`
  - right: `0.238` ~ `0.645`
- 종료 시 `Motors cleaned up`, `rpicam camera stopped`
- 실행 후 `run_learned`, `rpicam`, `gesture` 관련 잔여 프로세스 없음

실제 궤적 관찰 결과를 사용자에게 받아서, 우회전/좌회전 조향 방향 또는 속도 제한을
다음 단계에서 보정한다.

## 절대 변경 금지 배선

`Lee/motor_module.py` 기준:

```python
motor1 = Motor(22, 27)  # 왼쪽 앞
motor2 = Motor(24, 23)  # 왼쪽 뒤
motor3 = Motor(21, 16)  # 오른쪽 뒤
motor4 = Motor(19, 26)  # 오른쪽 앞
```

`front_wheels = Robot(motor1, motor4)`, `rear_wheels = Robot(motor2, motor3)`,
`left_wheels = Robot(motor1, motor2)`, `right_wheels = Robot(motor3, motor4)`이다.
Webots 쪽 `VirtualGPIOBridge`와 `BlueRCCar.proto`도 이 번호 체계에 맞춰져 있다.

## 주요 파일

- Webots RC카: `Dataset Project/protos/BlueRCCar.proto`
- 메인 Webots 컨트롤러: `Dataset Project/controllers/rc_car_controller/rc_car_controller.py`
- 데이터 기록기: `Dataset Project/controllers/rc_car_controller/dataset_recorder.py`
- Expert 경로 추종: `Dataset Project/controllers/oval_track_expert.py`
- Lee tracker adapter: `Dataset Project/controllers/lee_lane_adapter.py`
- 공용 전처리: `Dataset Project/controllers/vision_preprocessing.py`
- learned PWM 안정화: `Dataset Project/controllers/learned_control.py`
- learned steering 런타임: `Dataset Project/controllers/learned_steering.py`
- driveability 안전 모델 런타임: `Dataset Project/controllers/driveability.py`
- compact dataset 빌더: `Dataset Project/training/build_dataset_v2.py`
- steering v2 학습: `Dataset Project/training/train_steering_v2.py`
- 부정형 안전 모델 학습: `Dataset Project/training/train_driveability.py`
- Webots run 평가: `Dataset Project/training/evaluate_drive_run.py`
- Pi 실행 스크립트: `Dataset Project/hardware/run_learned_pi.py`
- Pi 모터 단품 테스트 스크립트: `Dataset Project/hardware/test_motors_once.py`
- Pi 모터 반복 보정 콘솔: `Dataset Project/hardware/test_motors_console.py`
- USB 이더넷 Pi 전송 스크립트: `Dataset Project/hardware/sync_pi_usb.ps1`
- Pi 배포 문서: `Dataset Project/RASPBERRY_PI_DEPLOY.md`

## Webots 월드

- `worlds/lane_track.wbt`: 기존 3차선 타원형 트랙
- `worlds/test_track_clockwise.wbt`: 시계 방향 일반화 테스트
- `worlds/test_track_rectangle.wbt`: 검은 도로/흰 점선 직사각형 테스트
- `worlds/test_track_rectangle_inverted.wbt`: 흰 도로/검은 점선 반전 테스트
- `worlds/collect_rectangle_lane_1.wbt`: 1차선 수집, corner radius 0.8m
- `worlds/collect_rectangle_lane_2.wbt`: 2차선 수집, corner radius 1.4m
- `worlds/collect_rectangle_lane_3.wbt`: 3차선 수집, corner radius 2.0m

조작키:

- `M`: 자동/수동
- `V`: `EXPERT -> VISION -> LEARNED`
- `R`: 기록 켜기/끄기
- `W/A/S/D`: 수동 주행
- `Q/E`: 제자리 회전

## 현재 데이터 상태

원본 run 데이터는 `Dataset Project/dataset/runs/`에 보존되어 있다.

추가 수집 완료:

- 1차선: `run_20260901_113405`, 17,007 rows/images
- 2차선: `run_20260901_122200`, 3,198 rows/images
- 3차선: `run_20260901_131627`, 3,087 rows/images

최종 compact dataset:

- 위치: `Dataset Project/dataset_v2/`
- 총 샘플: 9,000
- 차선별: 1차선 3,000 / 2차선 3,000 / 3차선 3,000
- 라벨 구성: `expert_command` 8,500 / `expert_reference` 500
- 용량: 약 54.83MB

`expert_reference`는 learned 주행 중 흔들림/복구 구간 프레임에 대해, 같은 순간 시뮬레이터 expert가 냈어야 할 좌우 PWM을 붙인 복구 학습 라벨이다.

## 긍정형/복구형/부정형 데이터 정책

- 긍정형 데이터: 정상 주행 이미지 + expert PWM. `steering_v2` 학습에 사용한다.
- 복구형 데이터: learned 주행 중 흔들리거나 이탈 직전인 프레임 + expert PWM. `steering_v2`에 일부 섞어 복구 조향을 학습시킨다.
- 부정형 데이터: 차선 없음, 오프로드, 큰 경로 이탈 프레임. PWM 회귀 라벨로 넣지 않는다. `driveability_v1` 안전 판단 모델 학습에만 사용한다.

부정형 데이터를 실패 PWM과 함께 steering 모델에 직접 넣으면 잘못된 행동을 학습할 수 있으니 금지한다.

## 현재 모델 상태

### `models/steering_v2.npz`

마지막 학습: 2026-09-01 17:13:27 KST

- source: `dataset_v2/manifest.csv`
- source rows: 9,000
- train rows: 7,200
- validation rows: 1,800
- augmentation 포함 학습 샘플: 28,800
- feature mode: `grayscale`
- input polarity: `auto_dark_road`
- polarity augmentation: true
- PWM output range: 약 0.0800 ~ 0.7197
- steering range: 약 -0.6197 ~ 0.6197
- steering MAE: `0.0439986661`
- lane1 steering MAE: `0.0540992245`
- lane2 steering MAE: `0.0464338735`
- lane3 steering MAE: `0.0314628966`

이 마지막 17:13 모델은 최종 Webots closed-loop 재평가까지 완료했다. 일반 색상과 반전 색상 모두 pass였다.

### `models/driveability_v1.npz`

마지막 학습: 2026-09-01 16:57:55 KST

- positive candidates: 9,000
- negative candidates: 3,604
- selected per class: 2,500 / 2,500
- feature mode: `lane_edges`
- threshold: `0.45`
- validation accuracy: `0.9595`
- drivable recall: `0.9960`
- negative recall: `0.9227`

## 최근 Webots 평가 결과

평가 스크립트:

```powershell
python -B training\evaluate_drive_run.py run_이름
```

저장된 최종 비교 리포트:

```text
Dataset Project/reports/closed_loop_final_color_polarity_eval.json
```

마지막 저장: 2026-09-01T17:27:00

일반 검은 도로/흰 차선:

- run: `run_20260901_172142`
- world: `test_track_rectangle.wbt`
- duration: 127.52s
- usable duration: 127.52s
- pass: true
- mean abs CTE: 0.04073m
- max abs CTE: 0.09819m
- safety stop: 0

반전 흰 도로/검은 차선:

- run: `run_20260901_172316`
- world: `test_track_rectangle_inverted.wbt`
- duration: 124.48s
- usable duration: 124.48s
- pass: true
- mean abs CTE: 0.04790m
- max abs CTE: 0.10827m
- safety stop: 0

이전 반전 평가(`run_20260901_170811`)에서는 mean abs CTE가 0.47648m였지만, 최종 `steering_v2.npz`와 tracker fallback 적용 후 0.04790m까지 개선됐다.

## 오늘 변경된 핵심 내용

1. `build_dataset_v2.py` 추가/확장
   - 고품질 expert 데이터만 균형 추출
   - learned run의 `expert_left_pwm`, `expert_right_pwm`를 복구 라벨로 사용
   - `safety_stop` 프레임은 steering 학습에서 제외
2. `train_steering_v2.py` 추가/확장
   - 차선별 균형 학습
   - 좌우 flip augmentation
   - 흰 도로/검은 차선 polarity augmentation
   - 출력 PWM/steering clip 메타데이터 저장
3. `learned_steering.py`
   - 모델 메타데이터 기반 전처리/출력 제한 적용
4. `vision_preprocessing.py`
   - 밝은 도로/어두운 차선을 자동으로 어두운 도로/밝은 차선 입력처럼 정규화
   - 부분 반전 augmentation 지원
5. `Lee/lane_tracking_module.py`
   - 기존 코드에 최소 변경으로 반전 차선 인식 지원
   - Hough 실패 시 pixel 기반 fallback 추가
   - blank frame 오탐 방지 contrast check 추가
6. `driveability_v1`
   - 부정형 데이터 기반 안전 판단 모델 추가
   - learned mode에서 위험 시 `safety_stop`
   - 단, 일부 차선이 보이면 즉시 정지하지 않고 `uncertain`으로 두어 계속 주행
7. `learned_control.py`
   - learned PWM에 OpenCV lane error 기반 `vision_trim` 보정 추가
8. `test_track_rectangle_inverted.wbt`
   - 흰 도로/검은 차선 Webots 테스트 월드 추가
9. `hardware/run_learned_pi.py`
   - Raspberry Pi 5 실제 RC카용 learned 실행 스크립트 추가
   - 기존 Lee camera/motor module을 import만 하고 배선은 수정하지 않음
10. `hardware/sync_pi_usb.ps1`
   - USB 이더넷으로 잡힌 Pi(`192.168.137.8`)에 코드/모델을 전송
   - `-IncludeDatasetV2` 옵션으로 compact dataset까지 함께 전송
   - 비밀번호는 파일에 저장하지 않고 SSH/SCP 프롬프트에서만 입력
11. 실제 모터 좌우 매핑 보정
   - 사용자 관찰값 기준 `motor1/2 = 좌측`, `motor3/4 = 우측`
   - `Lee/motor_module.py`의 GPIO 핀 번호와 motor1~4 번호는 유지
   - `left_wheels/right_wheels` 그룹, `test_motors_once.py` 표기, Webots 브리지/proto 문서만 수정
   - Pi에 동기화 후 `Lee/motor_module.py` 확인 및 `python3 -m py_compile` 통과
12. 실제 모터 오른쪽 전후 매핑 보정
   - 사용자 관찰값 기준 `motor3 = 오른쪽 뒤`, `motor4 = 오른쪽 앞`
   - `front_wheels = Robot(motor1, motor4)`, `rear_wheels = Robot(motor2, motor3)`로 수정
   - 좌우 그룹은 계속 `motor1/2 = left_wheels`, `motor3/4 = right_wheels`

## 검증 명령과 마지막 결과

단위 테스트:

```powershell
cd "C:\Users\a\Capstone-Design\Dataset Project"
python -B -m unittest discover -s tests -v
```

마지막 결과:

- 22 tests
- OK

dataset_v2 dry-run:

```powershell
python -B training\build_dataset_v2.py --dry-run
```

마지막 확인:

- candidate counts: lane1 30,998 / lane2 5,254 / lane3 3,188
- selected counts: 3,000 / 3,000 / 3,000
- selected recovery counts: lane2 500

최종 모델 학습:

```powershell
python -B training\train_steering_v2.py
```

마지막 완료:

- created_at: 2026-09-01T17:13:27
- model: `models/steering_v2.npz`

부정형 안전 모델 학습:

```powershell
python -B training\train_driveability.py
```

마지막 완료:

- model: `models/driveability_v1.npz`
- accuracy: 0.9595

## 바로 다음 작업

1. 최종 상태 보존

```powershell
cd "C:\Users\a\Capstone-Design\Dataset Project"
python -B -m unittest discover -s tests -v
python -B training\evaluate_drive_run.py run_20260901_172142 run_20260901_172316
```

2. 반전/조명 조건을 더 늘리고 싶으면 새 run을 수집한다.

```powershell
& "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe" --mode=fast --batch --stdout --stderr --heartbeat=1000 "C:\Users\a\Capstone-Design\Dataset Project\worlds\test_track_rectangle_inverted.wbt"
```

3. 새 run을 반영하려면 아래 순서로 반복한다.

```powershell
python -B training\build_dataset_v2.py --overwrite
python -B training\train_steering_v2.py
python -B training\train_driveability.py
```

4. Pi 적용 전 최종 기준
   - 일반/반전 Webots 모두 pass
   - safety_stop이 정상 주행을 과도하게 막지 않을 것
   - 반전 평균 CTE는 현재 0.04790m로 0.2m 기준 통과
   - 실제 Pi 첫 주행은 `RASPBERRY_PI_DEPLOY.md` 절차대로 바퀴를 띄우고 10초부터 시작
   - USB 이더넷 전송은 `hardware/sync_pi_usb.ps1 -PiHost 192.168.137.8 -PiUser pi` 사용

## 주의점

- Webots run은 기록이 기본 ON이다. 단순 화면 확인이면 `R`로 꺼야 한다.
- Webots를 강제 종료해도 CSV는 매 샘플 flush되어 대부분 보존된다.
- 같은 트랙 반복 프레임만 나눈 validation 수치는 실제 일반화 성능으로 보지 않는다.
- raw dataset을 지우지 않는다. Pi에는 raw dataset이 아니라 `models/`와 runtime 코드만 가져간다.
- `reports/`, `dataset/runs/`, `dataset_v2/`, `webots_smoke_*.log`는 `.gitignore`에 추가되어 있다.
