# 서보 조향 주행

[프로젝트](../../README.md) · [제스처](../../Gesture/README.md) · [DC 모터 주행](../Without%20Steering/README.md)

앞바퀴 서보와 후륜 DC 모터 두 채널을 사용하는 차량입니다.
`Auto Driving 20261018` 이후 PC 작업의 차선 인식, 수동·자율 제어,
제스처·GIF 표시와 횡단보도 연동을 모았습니다.

| 파일 | 역할 |
| --- | --- |
| `track_web.py` | Flask 진입점·카메라와 기능 연결 |
| `camera_source.py`, `track_vision.py`, `lane_path.py` | 영상 입력·차선 검출·경로 구성 |
| `manual_drive.py`, `autonomous.py` | 수동 입력·GPIO·경로 추종 |
| `gesture_adapter.py` | 공통 `Gesture/worker.py` 연결 |
| `crosswalk.py`, `interaction.py` | 횡단보도 관측과 선택적인 제스처 대기 |
| `media_capture.py`, `static/`, `templates/` | 촬영·녹화·웹 화면·GIF |
| `compare_vision.py`, `hough_vision.py`, `replay_path.py` | 오프라인 분석 |
| `experiments/paper_track/` | 이전 트랙 코드와 팀원 모터 보정본을 합친 한 벌 |
| `experiments/hardware/`, `history/` | 단품 실험·이전 시험·출처 기록 |

## 환경과 실행

Pi의 저장소 루트에서 Python 3.11 환경을 만듭니다.

```bash
cd "Auto Driving/With Steering"
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-gesture-pi311.txt
./.venv/bin/python -B track_web.py --gesture --fps 30 --preview-fps 30 --analysis-max-side 544 --port 5001
```

위 명령은 영상·인식 확인용입니다. OS의 `rpicam-vid` 또는 호환 Picamera2가 필요합니다.
배선을 확인한 차량에서 전체 제어 패널을 켜는 명령입니다.

```bash
./.venv/bin/python -B track_web.py \
  --manual --motor-wiring-confirmed --autonomous --gesture --lap-mode \
  --initial-speed 0.28 --pilot-speed 0.27 \
  --fps 30 --preview-fps 30 --analysis-max-side 544 --port 5001
```

접속은 `http://<파이 IP>:5001`입니다. 서버 시작은 주행을 시작하지 않습니다.
제스처 표시와 횡단보도 제스처 제어 활성화는 별도 설정입니다.
입력·전송 30FPS 설정은 도로 처리 30FPS를 보장하지 않습니다.

## 검증

```bash
./.venv/bin/python -B -m unittest discover -p 'test_*.py'
node test_pilot_ui.cjs
```

사진·영상·로그·가상환경은 Git에서 제외합니다. 이전 기록은
[history/HANDOFF_before_consolidation.md](history/HANDOFF_before_consolidation.md)에 있습니다.
그 안의 예전 경로와 실행 중 상태는 당시 기록입니다.
이번 정리는 PC에서 검사했으며 새 경로를 Pi에 배포하거나 실제 주행하지 않았습니다.
