# Handoff: New Track / Python 3.11 / 2026-10-18

## Latest: Owner Requested Flask Shutdown And File Path

Sent SIGTERM to verified PID1985 running
/home/pi/Capstone-Design/Auto Driving 20261018/track_web.py. Confirmed process
exit, port5001 closed and no rpicam-vid/libcamera-vid process. Pi stays ON.
No diagnostic deployment, movement command or restart. Keep Flask OFF until
requested; diagnostic changes described below remain PC-only.

## Latest: Manual Disconnect Investigation, Diagnostic Deployment Pending

Owner reports video continues while manual control stops, then confirmed a
manual power-cycle. PID5309 disappeared due to that reboot, not evidence of a
Flask crash. Previous-boot journal is not persistent. Restarted full runtime
PID1985/5001 from outputs/manual_direct_20261021_205242/argv.json and restored
that folder's after.json autonomous settings. Server log currently is
outputs/manual_direct_20261021_205242/restart_after_reboot.log.

Measured stationary with preview:30 PC /status requests31..129ms, median74ms;
20 Pi-local /status requests14..68ms, median36ms. Temperature59.8C, throttled0x0,
Wi-Fi signal-43dBm,2.4GHz, link rate72.2Mbps, power saving ON. No network setting
changed. During owner's real manual driving,25 samples46..388ms, road20.8..30.6FPS,
camera fresh and command sequence advancing, outputs.31/.31. No450ms failure
observed. Subsequent12 pings2..111ms, mean21ms, no loss. These are small samples,
not proof of the original fault. Client450ms timeout, server700ms lease, blur,
visibility/tab changes all can stop control independently of video.

New PC-only diagnostics:manual_drive.py logs actual stop reason/input age/last
sequence/previous outputs AFTER hardware stop; track_web.py logs a whitelisted
browser stop source after handling it. static/manual.js adds stop-source labels
and a Korean450ms timeout message. No threshold/speed/control semantics changed.
New tests in test_manual_drive.py/test_manual_ui.cjs. PC332 Python and all seven
Node suites passed. Logging patch NOT UPLOADED: deployment guard saw armed=true
and aborted before any backup/shutdown/write. Owner was driving; no agent
arm/input/start commands. Asked owner to stop and confirm before deployment.
Remote hashes before diagnostic edits begin with0c0d943e745c(manual_drive),
f2bb0e836004(track_web),5096ff951b33(manual.js),bc12331efaa3(test_manual_drive),
99fd6a4f3900(test_manual_ui). Direct-control/angle feature is already deployed;
only the later diagnostic patch is pending. Do not claim root cause fixed.

## Latest 2026-10-21 20:55: Direct Manual Input Deployed

User requested Flask ON, then removal of the manual enable/disable switch.
Connected to .60; initial45.5C/throttled0x0, no old server. Started PID1885 with
manual/auto/gesture, input/preview30, analysis544, manual.28/pilot.27, lap mode.
User operated the old UI during development; by deployment it was disarmed,
outputs0, PWMoff. Agent sent no real arm/input/start/reference command.

UI now has no manual-enabled checkbox. A fresh W/S/A/D or primary pointer press
in the visible manual panel acquires the existing guarded ownership, then sends
the currently held keys. Loading the page, timers and sliders do not acquire it.
Releasing keys removes the corresponding motor/steering command; idle owned
heartbeats retain the lease at zero output. Stop, blur, hidden page and control
tab switch disarm and clear input. Global stop also cancels local pending input.
Generation checks reject late replies; releasing while arm is pending cancels
without sending input. New activation is blocked until pending arm/stop/input
requests settle. Key repeat cannot resume after stop or a failed request.
Form editing and the hidden manual panel cannot start motion. Unconfirmed motor
locks and ownership conflict checks remain. Manual A/D angle sliders from the
earlier PC-only entry are deployed too, with unchanged hardware105/85 bounds.

Changed/deployed seven files:manual_drive.py,track_web.py,static/manual.js,
templates/manual_controls.html,test_manual_drive.py,test_control_display.py,
test_manual_ui.cjs. Remote diffs were limited to these intended changes; files
backed up under outputs/manual_direct_20261021_205242/ before SIGTERM PID1885.
Hashes match PC. PC/Pi331 Python tests and seven PC Node suites pass. Fake-GPIO
headless Edge verifies direct keyboard/pointer input, independent30/25 angles,
release/stop, hidden-panel lockout and desktop/mobile layout. Local fixture is
stopped; images under PC outputs/manual_steering_check/direct_*.png.

Restarted PID5309/5001 using saved argv; preserved the immediate pre-restart
autonomous settings and manual speed. These settings had boundary_guidance=false,
crosswalk_gesture=false,max_left105/max_right85; older crosswalk snapshots are
historical, not current active options. No automatic reference calibration.
HTTP page/JPEG OK, gesture initialized, camera online, motors0/PWMoff/disarmed,
motor_write_count0 at validation. Startup sample camera30.1/road20.8FPS is not
a sustained benchmark. before.json/after.json/argv.json/restart.log and stationary
preview are in the remote backup folder. No live keyboard/movement test was run.
The older manual runaway/stop fault is still unproven and unresolved.

## Latest 2026-10-21: Manual Steering Settings, PC Only

Owner requested independent manual steering adjustment and asked whether the
number of Flask status fields slows recognition. Pi SSH timed out; owner then
confirmed Pi is OFF. No further connection, deployment or hardware action.
Earlier explicit Flask start used PID1887/camera1892; both were stopped on the
owner's shutdown request and port5001 was closed. This supersedes older running
PID entries below. Last temperature before power-off was48.3C, throttled=0x0;
it is not a current temperature reading.

Local changes awaiting deployment:
- manual_drive.py: separate positive left/right manual magnitudes, default105/85.
  Strict finite numeric bounds use the unchanged physical command limits.
  Only a successfully accepted, current owner input updates the stored values;
  stale, duplicate, foreign, expired or disarmed requests cannot replace them.
- track_web.py: forward optional left_angle/right_angle through /manual/input.
- templates/manual_controls.html: collapsed `수동 조향 설정`, separate A/D sliders.
- static/manual.js: labels/tooltips and heartbeat fields, sliders locked while
  any driving key/pointer is held. Slider input alone never arms or moves.
- test_manual_drive.py and new test_manual_ui.cjs: backend/API/browser regression.

A/D commands use the selected signed magnitude; release returns command0 as
before. These are servo command units, not measured wheel angles. Motor speed,
trim, autonomous limits and all stop/ownership/lease guards remain unchanged.
Unarmed edits live only in the browser until an accepted input. Accepted settings
live in server memory; restart restores defaults. No disk persistence was added.

PC verification:331 Python tests and all seven Node suites pass. Headless Edge
with Playwright tested fake-GPIO Flask on loopback at1365x1000 and390x844:
slider-only writes0, A=-30/D=25, release0, stop/disarm, movement slider lock,
unchanged auto105/85, no JS errors or horizontal overflow. Browser and temporary
fixture server were stopped. Evidence:outputs/manual_steering_check/.
This is NOT proof of physical steering or resolution of the earlier runaway/
unresponsive-stop report. Fresh supervised readiness is still required.

Performance findings, not a tuning change:
- /status refreshes about every700ms after completion; it does not rerun vision.
- Preview selects one image stream; switching tabs does not display all streams.
- Collapsing status sections does not stop segmentation/path/crosswalk work.
- Gesture inference already pauses during movement, except zero-output crossing
  waits; do not claim it always runs concurrently during driving.
- PC offline benchmark,20 measured raw-image runs at analysis544, median road
  processing25.671ms, JPEG82 encoding1.297ms, status JSON serialization0.031ms.
  JSON was6734bytes. It excludes Flask route/DOM/network/camera/gesture costs.
  Report:outputs/manual_steering_check/performance.json. This is not Pi FPS or
  proof of the current Pi bottleneck. No FPS/resolution/gesture/poll tuning.

Next: upon explicit reconnection, compare remote files before deploying the six
source/test files above; preserve changes made by others and existing runtime
settings. Pi tests and stationary timing measurements are still pending.

## 최신 2026-10-21 01:53: 횡단보도 묶음과 조향 점선 분리

사용자가 커브 후 횡단보도 앞에서 멈췄다고 보고했다. 실패
run_20261020T163547_639248Z.jsonl과 PNG에서 실제 정지 원인은 path_lost /
inconsistent_dash_chain이다. 횡단보도 검출0, crossing latch=false였으므로
정상 횡단보도 정차가 아니었다. 원본에는 레고와 횡단보도5줄이 보인다.
ROI 상단에서 일부 잘린 줄무늬가 서로 다른 기울기/낮은 직사각형 채움률을
갖는데, 기존 평행 막대 검출 조건이 이를 놓쳤다. 그중 흰 조각이 먼 차선
점선으로 잘못 연결돼 경로가 옆 차선 쪽으로 튀었다.

crosswalk.py:
- 원래 평행 막대 검출은 유지하고 원근 가로 행 묶음 검사를 추가.
- 최소4개 서로 다른 연결영역, 비슷한 폭/간격, 영상폭35% 이상,
  기준점 포함, 연속8개 표본 행 및 영상높이3.5% 이상 지지 필요.
- 넓은 한 반사영역/두 점선 차선/짧은 띠/옆 차선 묶음은 새 방법으로 승인 안 함.
- 검출된 실제 줄무늬 다각형 안의 후보만 차선 점선에서 제외. 노면/흰 원본
  지원 마스크는 보존. track_web은 이 분리를 경로 계산 전에 수행한다.
- opt-in crosswalk_gesture=true이면 서로 다른 신선 프레임3개 이상·0.12초
  이상의 확인 후 stop 조건 생성. 이전 영상높이70% 근접 조건까지 전진하지
  않는다. OFF일 때는 기존 근거리 조건 유지. 정차 거리의 물리 보정은 아니다.
- replay_path.py도 동일 분리 과정을 적용하고 crosswalk.py 해시/결과 기록.

PC/Pi324 테스트 통과. 추가6개는 원근/ROI 잘림5줄, 신선 프레임/중복/지연,
조기 정지 opt-in,2차선/반사/불규칙/연결 띠 음성 사례, 조향 후보 분리와
노면 지원 보존, 미확인/신뢰 불가 관측의 후보 미변경이다.
이전 직선/코너 사진8장은 검출0 및 경로 유효/목표점 변화 없음(기존 무효1장
포함). 현재 JPEG/실패 PNG는 모두 횡단보도5줄, 오연결 후보1/2개 제외 후
유효한 실제 근거리 점선 경로를 만든다. 주행 성공이나 완주 증거가 아니다.
증거: PC outputs/crosswalk_stop_20261021_013646/의 원본/로그/regression.json/
live_after.json/jpg. 파이 백업 outputs/crosswalk_fix_20261021/.

사용자가 레고 감지 생략을 허용했다. 촬영 범위는 횡단보도->정지->실제 손
제스처로 정리하며, 레고는 장면 소품이다. 구현하지 않은 레고 인식을 인식
완료로 표시하지 않는다. 기존 GO gate(새5결과/0.5초)와 STOP/unknown 대기는
변경하지 않았다. 앞서 요청한 GO3초, STOP 해제5초, 사람없음3초 출발은 아직
구현하지 않았고, 손 미검출을 사람 없음으로 치환하지 않는다.

PID15240 정상 종료 후5개 코드/테스트 파일 해시 확인·Pi 테스트,
PID31297/5001 재시작. --gesture 포함, 수동0.28/자율0.27, Kp35/heading1,
좌100/우80, 완주/연속/복구/경계추가조향/횡단보도 ON 등 직전 사용자 설정
모두 보존. 모터0/0, PWMoff, armed=false, motor_write_count=0.
재시작 후 중앙 기준 없음. 새 직선 보정/감독 준비 없이 주행하지 않는다.
정지 실측12회 모두 검출5/안정/정지조건/경로 유효, 제스처 초기화됨.
도로13.8~14.8FPS: 30FPS 입력과 별개이며 고정30 처리 주장 금지.
실제 제스처 출발/브레이크/타이밍/정지 먹통 문제는 이번에 시험하지 않았다.

## 최신 2026-10-21 01:16: 열린 경계의 노면 분리 복원

사용자는 라인 미검출 개선과 카메라 각도/인식 방식 원인 구분을 요청했다.
원본에 흰 점선과 양쪽 노란 선이 보이지만, 노란 barrier가 열려 검은 도로와
바깥 흰 바닥이 동일 연결영역으로 분류됐다. 현재 JPEG의 그 영역은 어두운
비율63.67%로 기존70% 기준 미달; 영역 전체가 버려져 노면3.19%/점선0개였다.
카메라 각도 변화는 이 취약성을 드러내는 조건이며, 사진에 필요한 선은 보인다.
새 Canny/Hough 비교 방식을 라이브에 적용해서 생긴 문제가 아니다.
run_20261020T160101_037664Z.jsonl은 경로 점선6개 뒤 후보0/path_lost로 정지.
제스처는 주행 중 OFF였고, 보정 기준도 존재했다. 모터 고장/과열 증거가 아니다.

track_vision.py의 기존 영역 판정은 보존하고, 탈락 영역만 보완했다:
- 실제 어두운 연결부가 영상4% 이상·높이25% 이상이어야 한다.
- 24개 표본 행 중 양쪽 실제 노란 픽셀 지지가6행 이상이고 높이20% 이상 필요.
- 관측된 어두운 픽셀만 복원하며, 원래70% 미달 연결영역 전체를 채우지 않는다.
- 점선은 흐린 회색 테두리까지 포함한 작은 밝은 섬으로 검사한다. 둘레85%
  이상이 복원된 어두운 노면, 흰색 픽셀25% 이상, 기존 면적/종횡비/채움 조건을
  만족해야 한다. 바깥 흰 바닥에 연결된 큰 영역/큰 반사 패치/경계 없는 어두운
  물체를 같은 방식으로 복원하지 않는다. ROI/노란 barrier는 유지한다.
- 현재 프레임만 사용하며 이전 경로나 조향을 재생하지 않는다.
모터·조향·안전 정지·제스처 모델·해상도/FPS 설정 변경 없음.

PC/Pi318 테스트 통과. 새7개 테스트는 열린 경계, 양쪽 지지 없음/짧음,
큰 반사/바깥 흰 물체, 바깥에 열린 흰 영역, ROI, 하단 잘린 점선, 흐린 테두리.
이전 직선/코너/반사 사진8장은 노면 마스크 자체와 경로 유효 여부/방향 불변.
현재 JPEG는 점선0->5 및 유효 좌회전, 실패 진단 PNG는 전체 점선후보1->7,
실제 경로는 유효한 앞쪽 점선4개를 선택. 정지 사진 재생은 주행 성공이 아니다.
PC outputs/open_road_check_20261021_011213/에 baseline/comparison.json/마스크/
오버레이/live_after.json 보관. 고정 비교 기준은 실제 재보정이 아니다.

파이 원본 백업: outputs/open_road_fix_20261021_011550/.
수동/자율 비활성 확인 후 PID8767 정상 종료, 코드/테스트 해시 확인 및 배포,
파이 테스트 통과 후 PID15240/5001 재시작. 수동0.28, 자율0.27, 사용자 변경
max_left100/max_right80, boundary_guidance=true 및 완주/연속/복구 ON 보존.
제스처/GIF 유지, crosswalk_gesture=false. 중앙 기준 없음, 모터0/0, PWMoff,
armed=false, motor_write_count=0. 주행이나 자동 중앙 보정을 하지 않았다.
적용 후 정지 상태12회 관측 모두 경로 유효/좌회전, 점선4~5개, 노면46.9%.
카메라29.9~30.0FPS, 제스처 동시 도로 처리18.6~20.3FPS(중앙값19.55).
검출/경로 복원이 계산량을 늘리므로 고정30FPS 달성을 주장하지 말 것.
카메라 각도 변경/재시작 뒤 실제 직선 위치에서 새 기준 설정 필요.
이전 수동 정지 먹통 원인은 미해결. 이번 시각 처리 수정과 별개다.

## 최신 2026-10-21 00:49: 재부팅 후 수동주행·제스처 함께 실행

사용자가 Flask 재실행, 수동주행, 제스처 포함을 요청했다. 처음 .60의 SSH와
5001은 시간 초과였고, 재연결 후 재부팅 및 기존 Flask/카메라 프로세스 없음을
확인했다. PC/Pi의 웹·카메라·수동·자율·제스처 어댑터 코드 해시 일치 확인.
코드 변경 없이 Python3.11로 PID1867/5001 실행:
--manual --motor-wiring-confirmed --autonomous --lap-mode --pilot-speed 0.27
--gesture --fps 30 --preview-fps 30 --analysis-max-side 544.
수동 출력0.30, 자율0.27 및 이전 완주/연속/복구 설정 보존.
중앙 기준 없음, armed=false/active=false, 모터0/0, PWMoff 및 쓰기 횟수0.
카메라 온라인, 제스처 initialized=true/error=null, 실제 추론 증가 확인.
두 GIF HTTP200 확인. 손 미검출이므로 GO/STOP 실물 시연 확인은 아니다.
기존 제스처 모드는 수동제어 활성화 중 OFF, 해제 후 preview로 돌아간다.
횡단보도 제스처 모터 제어는 OFF. 정지 먹통 원인은 여전히 미해결.
로그: outputs/manual_gesture_restart_20261021_004935.log (파이).
이번에는 파일 변경 없이 실행 확인만 했으므로 테스트 재실행/주행은 하지 않음.

## 최신 2026-10-21: 제스처 OFF 및 30FPS 목표 프로파일

사용자가 제스처를 빼고 카메라·영상·도로 인식을30FPS로 요청했다.
코드/GIF는 삭제하지 않고 --gesture 없이 실행했다. 수동/자율 탭은 유지.
제스처만 끈640 분석은22~23FPS, 분석544 적용 후26~27FPS, 카메라 JPEG
디코드를 수신 스레드에서 처리하도록 바꾼 뒤 정지 상태28~30FPS 수준이다.
960x720 원본은 유지하고 도로 분석만544x408로 낮췄다.

track_web.py: 전송 간격을 JPEG 인코딩 시작 기준으로 계산한다. 인코딩 후
33ms를 추가로 쉬던 구조를 수정했다. 느린 전송의 밀린 프레임을 몰아 보내지 않는다.
camera_source.py: rpicam 수신 스레드에서 디코드/치수 검증 후 최신1장만 게시.
원래 수신시각을 유지하며, EOF/잘못된JPEG/정지 시 이전 영상을 재생하지 않는다.
도로 처리와 JPEG 디코드가 서로 다른 스레드에서 겹쳐 실행될 수 있다.
주행 판단/출력/정지/프레임 신선도 한도는 변경하지 않았다.
PC/Pi311 테스트 통과: 압축시간 포함 전송주기·느린 전송 버스트 방지,
디코드 실패·정지 중 디코드·수신시각 보존·최신 프레임 처리 등 포함.

480x360은 과거 직선 사진1장에서 추가 경로 실패가 있어 채택하지 않았다.
비교8장(직선/우회전/반사실패)의544 결과는640과 유효7/무효1 및 방향이 일치.
고정된 비교 reference는 실제 새 보정이 아니며, 주행/정확도 보장은 아니다.
이번에는 Canny/Hough를 통합하거나 HSV 임계값을 변경하지 않았다.

실제 PC MJPEG 수신12초 검증:
- 카메라 수신30.0~30.1FPS.
- 도로 인식27.5~29.1FPS, 평균28.62FPS.
- 처리 영상322장 수신,26.75FPS, 전송 오류 없음.
- processing_ms 중앙값34.9ms. 브라우저 표시 FPS를 측정한 것은 아님.
모두 고정30FPS에 도달했다고 설명하지 말 것. 카운터/타이머를 바꿔 인식률을
부풀린 것이 아니라 실제 처리 프레임과 수신 프레임을 따로 측정했다.
PC outputs/road_30fps_stream_check_20261021.json 및 road_30fps_live_20261021.jpg.

현재 PID43588/5001, Python3.11, --fps30 --preview-fps30 --analysis-max-side544,
--manual --motor-wiring-confirmed --autonomous, 제스처 OFF.
사용자가 작업 전 바꾼 speed0.27, turn_recovery=true를 보존했다.
lap_mode/continuous=true, Kp35/heading1/curve_scale0.85,
boundary_guidance/crosswalk_gesture=false. 이번에 주행 명령 없음.
재시작 후 reference 없음, armed=false/active=false/모터0/0/PWMoff 확인.
파일 백업(파이):
outputs/road_30fps_deploy_20261020_235920/ (웹 코드/테스트),
outputs/pipeline_decode_deploy_20261021_000337/ (카메라 코드/테스트).
제스처 복원은 사용자가 요청할 때만. 이전 수동 정지 먹통 원인은 미해결.

## 최신 23:29 KST: 완주 모드 시험과 반사 시작점 오검출 보완

사용자가 직선 중앙 배치·물리 전원 차단 준비를 확인하여 PC 감독 2초 시험을
1회 실행했다. 실제 로그는 약0.68초에 path_lost로 중단(PC 관측 약0.94초).
사용자는 거의 움직이지 않았고 네 바퀴가 검은 노면 안이라고 확인했다.
좌우 출력 명령은0.30, 조향은 거의0이었다. 주행 성공이나 커브 시험은 아님.
run_20261020T142142_031179Z.jsonl 및 실패 원본
photo_20261020T142142_716649Z_raw.png가 파이 captures/에 저장됐다.
PC 사본: outputs/lap_trial_20261020_232142/.

실패 PNG로 dash_association_failed를 정확히 재현: 반사 조각(151,374.5)을
경로 시작점으로 선택하고 실제 세로 점선 연결을 놓쳤다. lane_path.py의
기존 작은 근거리 반사 필터에 제한된 예외를 추가했다. 완주 모드와 보정된
reference가 있을 때만 적용하며, 약한 가로 조각이 기준에서 벗어나 있고
앞쪽에 정렬된 점선3개 이상, 현재 연결된 노란 경계8개 이상, 근거리 노면
90% 이상이 함께 확인될 때 그 조각을 제외한다. 굵은 실제 표시·곡선·
경계 없음·잘못된 방향·분리된 경계·기준 없음 음성 테스트를 유지했다.
정지·소유권·프레임 신선도·출력·조향 한도는 변경하지 않았다.
동일 PNG는 수정 후 실제 점선3개와 경계로 직선 경로가 유효해졌다.
PC/Pi 각각308 테스트 통과. 이는 단일 실패 유형 재현 검증이지 완주 증거가 아니다.

이전 코너의 insufficient_dash_span은 새 수정이 아니라 기존 완주 모드가
꺼져 있던 문제였다. 같은 JPEG3장은 기본 모드 실패/완주 모드 유효였다.
이번 시험부터 lap_mode=true, continuous=true; Kp35, heading1, speed0.30,
curve_scale0.85 유지. turn_recovery/boundary_guidance/crosswalk_gesture는 OFF.
boundary_guidance OFF여도 기본 경로 검증은 노란 경계를 사용한다.
완주 모드는 원격 PC의 별도2초 감독 제한을 없애지 않았다.

백업: 파이 outputs/reflection_fix_deploy_20261020_232827/.
lane_path.py 및 test_curve_path.py만 배포 후 기존 인자로 Flask 재시작.
PID37736/5001, 수동·자율·제스처·GIF 유지, 모터0/0·armed=false·PWMoff 확인.
API로 시험 설정만 복원했으며 중앙 기준은 초기화된 상태다. 재주행하지 않음.
다음 시험은 다시 직선 중앙 배치 확인 및 중앙 기준 설정이 필요하다.
이전 수동 정지 먹통 원인은 여전히 미해결; 이번 인식 수정으로 해결됐다고
설명하지 말 것. 카메라/FPS/해상도/HSV와 Canny/Hough 비교 코드는 변경 없음.

## 최신 22:10 KST: 사용자 지정 초록 GIF 교체

Downloads/smooth_flipped (1).gif를 변경 없이 static/signals/vehicle_stop_green.gif에
복사하고 파이에도 원자적으로 교체했다. 1050x450, 8프레임, 주기960ms,
loop=0 무한 반복, 47997바이트. 초록 STOP/빨강 GO 매핑은 유지했다.
SHA256: d4b641b6308c97d1588f837762292868d61260bcb02be1b307bcfc2daf5bc481.
파이 HTTP200 image/gif 응답의 해시가 원본과 동일함을 확인, PC305 테스트 통과.
실행 중인 PID4678과 수동/자율/제스처 기능은 유지, 재시작·주행 명령 없음.
파이 이전 GIF 백업: outputs/green_gif_backup_20261020T131055Z/.
PC 이전 GIF 백업: outputs/green_gif_backup_20261020_221028/.
기존 브라우저에서 이전 GIF가 계속 보이면 새로고침이 필요할 수 있다.

## 최신 22:04 KST: 수동·자율주행 탭 복원

사용자가 제스처만 실행할 때 숨겨졌던 수동/자율주행 탭을 다시 요청했다.
원격 track_web.py/manual_drive.py가 검토한 로컬 파일과 해시가 일치함을
확인하고 기존 제스처 전용 PID1861을 정상 종료했다. 기존 실행 인자를
유지하며 --manual --motor-wiring-confirmed --autonomous --pilot-speed 0.30
추가. 새 PID4678/5001, Python3.11.17, --gesture --fps30 --preview-fps30.
화면의 수동주행/자율주행/제스처/디스플레이 표시와 HTTP200 확인.
hardware_enabled=true지만 armed=false, active=false, 출력[0,0],
pwm_active=false, motor_write_count=0. 주행·서보 이동 명령은 보내지 않았다.
연속주행/완주 모드/커브복구/횡단보도 제스처 제어는 모두 기본 OFF 유지.
인식 코드나 모델/안전장치를 수정하지 않았다. 새 캐니·허프 비교는 여전히
주행과 분리되어 있다. 사용자는 오래 사용한 게 문제라고 전달했지만 실제
정지 먹통 원인은 검증되지 않았으며 장시간 구동을 재현하지 않았다.
실행 기록: outputs/full_panels_gesture_20261020T130443Z.json 및 .log (파이).

## 최신 21:58 KST: 제스처 미리보기 재시작

사용자가 핫스팟 단절 후 파이를 재부팅하고 다시 실행을 요청했다.
.60 연결 성공, 5001/5002 및 기존 카메라 프로세스가 없는 상태를 확인했다.
Python 3.11로 track_web.py --gesture --port 5001 --fps 30 --preview-fps 30 실행.
PID1861, hardware_enabled=false, autonomous_panel=false, gesture_enabled=true.
카메라 온라인, 제스처 initialized=true/error=null, 실제 추론192프레임 확인.
확인 당시 손 미검출/unknown이며 실측 추론14.9FPS. 요청30FPS와 혼동 금지.
빨강/초록 GIF 모두 HTTP200 image/gif. 실제 GO/STOP 손동작 시연은 아직 미확인.
모터 제어를 켜거나 명령하지 않음. 5002 저장 비교 서버는 이번에 재시작하지 않음.
파이 실행 기록: outputs/gesture_preview_20261020T125836Z.json 및 .log.

## 최신 작업: 비교 화면 한글화

사용자 요청으로 compare_vision.py의 제목, 상태, 표, 단계별 설명을 한글화.
글자를 이미지에 넣는 대신 브라우저의 한글 설명과 개별 이미지를 사용한다.
이전 영문 합성 이미지는 파일로 보존하지만 페이지에는 표시하지 않는다.
파이 5002의 기존 결과 페이지를 갱신했고, 기존 report.json은 바이트 단위로
변경되지 않았음을 확인했다. 원본 해시와 재생성한 단계별 검출값도 일치한다.
PC/Pi 각각 305개 테스트 통과, 실제 브라우저의 한글 표시와 이미지 배치 확인.
5001 카메라 서버와 모터/주행 코드는 수정하거나 재시작하지 않았다.
백업: outputs/comparison_korean_backup_20261020T124522Z/ (파이).
한글 페이지 배포·브라우저 확인 후, 마지막 문서 업로드 단계에서 SSH 연결이
시간 초과됐다. 이후 5002 HTTP 재확인도 시간 초과. 한글 코드/화면은 이미
배포됐지만 이번 COMPARISON_RETEST 문서 추가분은 PC에만 있음.

## Latest 21:33 KST: Fresh Track Retest / Cleanup Blocked

Owner clarified "delete the old test" means comparison photos/results, NOT
replacing the live perception code. Verified exact comparison-only paths, but
local recursive deletion was rejected by execution-tool policy before running.
No old comparison files were deleted on PC or Pi. User informed; old report
server was stopped and its URL now serves new evidence instead. Do not bypass
the tool restriction or claim the requested disk cleanup is complete.

New raw track frames (six, stationary): captures/comparison_retest_20261020T123345Z/.
New result: outputs/hough_track_retest_20261020T123345Z/ on Pi. Current baseline
640/.20 plus9 Hough profiles (640/480/320, blur0/3/5). All6 current path candidates
valid without calibration, all profiles six two-sided groups; NOT accuracy,
drive readiness or curve/lap proof. No tuning or existing runtime changes.
See COMPARISON_RETEST_20261020.md for evidence, timing limitations and scope.

Camera-only Flask restarted with the exact prior command, now PID2663/5001.
New saved-report HTTP server PID2877/5002; old PID2142/2088 stopped. Camera
delivery30.0FPS observed, hardware disabled, both endpoints verified from PC.
No motor/GPIO command. The earlier manual-stop fault is still unresolved.

## Latest 21:27 KST: Existing Flask ON In Camera-Only Mode

Owner explicitly requested Flask ON, after choosing desk-only execution checks.
Started the existing unchanged track_web.py with this project's Python3.11.17
venv, --port5001 --fps30 --preview-fps30, NO manual/autonomous/gesture flags.
PID2142. Capture960x720, analysis640x480, rotation180 (existing defaults).
PC checked /status and /snapshot/processed.jpg: HTTP200, fresh frame numbers,
camera_online=true, hardware_enabled=false, autonomous_panel=false.
Observed camera delivery30.0FPS and vision29.3FPS at that check, not guarantees.
No GPIO/motor commands or runtime edits; the manual-stop fault remains open.

Live existing perception: http://192.168.137.60:5001/
Saved Hough comparison remains at5002/PID2088. Hough is NOT part of live Flask.
Startup log/metadata: outputs/camera_only_20261020T122702Z.log and .json on Pi.
This newer owner instruction supersedes older OFF-state notes for camera-only
use; it does not authorize movement or enabling the faulty manual controller.

## Latest: Pi Desk Execution Check / Static Report Only

Reconnected to192.168.137.60 after the owner restored the connection. Uptime
was about40seconds, consistent with a fresh reboot, but this does NOT establish
the cause of the earlier disconnection. All existing comparison dependencies
matched PC hashes. Uploaded4 new comparison/test files; Pi304 tests pass.
Adjusted report wording from "PC" to "host" and backed up its previous file.

Owner explicitly chose desk-only execution checks. Captured6 stationary frames
with the existing camera source/lock,960x720/rotation180, observed delivery30FPS,
then stopped the camera. No GPIO, arming, motion or existing-runtime changes.
No valid current paths or two-sided Hough groups on these desk frames. This
is not evidence of improved lane detection or a completed track trial.

See COMPARISON_RUN_20261020.md for exact evidence paths and limitations.
Saved comparison page: http://192.168.137.60:5002/ (PC HTTP200 verified).
Only static HTTP server PID2088 remains. Old driving Flask/rpicam are OFF.
This is not live video; do not confuse it with track_web.py or port5001.
Next track evaluation needs fresh stationary track frames, not more desk data.
The old manual-control stop fault remains unresolved.

## Newest: Offline Canny / Hough Comparison / No Pi Access

Owner requested a comparison version after discussing the professor's PDF,
not replacement of the live controller. Added hough_vision.py,
compare_vision.py and two test files. Runtime perception/control, Flask,
gesture model, camera/FPS and motor parameters remain untouched this turn.
No network/Pi connection, upload, server start, arming or motion was performed.
Keep Flask OFF; the earlier manual-control stop fault is still unresolved.

Experiment: resize/crop -> HSV colour mask -> optional Gaussian blur on mask
-> Canny -> polygon ROI -> optional perspective -> Hough segments -> image-side
endpoint means. Default ROI top=.20, no perspective; sizes480/320 and blur0/3/5.
The explicit --textbook-geometry preset uses .50 crop / PDF trapezoid / BEV.
It is NOT calibrated to this robot. White/both colour experiments are optional.
Missing one/both image-side groups yields no target/error, not fake straight.
Every Hough result has drive_authorized=False. A two-sided observation does not
prove distinct boundaries: one curved yellow edge can populate both halves.

PC Python3.11: all304 tests pass (16 new). Coverage includes missing/one-sided
lines, mean/sign, synthetic scale consistency, colour separation, crop,
small isolated specks, geometry mapping, binary Hough input, immutable raw
images, raw/screen guard, output preservation, hashes, report generation,
timing warmup exclusion and bounded video sampling/release. These are offline
tests, NOT physical lap, motor-stop, Pi FPS or live-camera validation.

Ran the same21 existing raw JPEG stills used by the prior replay. Assumed
reference=.5133757390238175 and heading=-2.43, lap+joint enabled, independent
frames with history reset. These assumptions are NOT a new calibration:
- outputs/hough_comparison_20261020_final/index.html and report.json:
  current480/.20 gives18 valid path observations (same as previous replay).
  Hough480 blur0/3/5 produces19 two-sided image groups in each profile;
  Hough320 blur0/3 gives18 and blur5 gives19. These counts are NOT comparable
  accuracy scores because the outputs, validations and target semantics differ.
- outputs/hough_textbook_20261020/index.html and report.json:
  exact-example320/.50/trapezoid/BEV/blur5 gives1 two-sided group in21 stills.
  The current baseline also changes to320/.50 in THIS report (5 path results).
  Do not attribute that baseline change solely to Hough or blur.
- Initial outputs/hough_comparison_20261020 is an intermediate report;
  prefer the _final version with the clarified grouping/legend warnings.

Visually inspected ordinary and sharp-curve comparison PNGs and the textbook
geometry result. In frame_0003 the ordinary Hough grouping includes pieces of
one curved outer edge on both image sides, yielding a misleading midpoint.
The textbook crop/trapezoid clips useful boundaries in the saved camera view.
No evidence yet justifies replacing current path logic. Review known targets
and geometry before considering Hough as corroborating direction evidence.
Do not discard white-dash/road/ownership/freshness checks to drive this output.
Reports include raw/code hashes, configurations, masks/edges and processing
timings, not screenshots passed off as raw. Timing excludes decode, rendering
and file IO; current does path validation while Hough only groups segments.
Raw JPEG is lossy; saved PNG evidence is preferred for threshold tuning.

## Newest: Pedestrian GIF Display / Flask Remains OFF

Owner supplied smooth_flipped.gif and stop_blink.gif, then explicitly requested
a rectangular box titled 디스플레이 BELOW the Flask camera. Colours refer to the
PEDESTRIAN, not the vehicle: GO (vehicle go request) -> RED stop_blink.gif;
STOP (vehicle stop request) -> GREEN walking smooth_flipped.gif. Original files
are copied byte-for-byte to static/signals/vehicle_go_red.gif and
vehicle_stop_green.gif. No image-generation/recolouring or model edits.

Implemented fixed7:3 native browser GIF display under the capture toolbar.
Added read-only /gesture/status, which reads only the existing worker snapshot,
not camera/pilot/GPIO. JS uses fresh ready decision_label with hand_detected,
never held label. Unknown/off/error hides signals; browser500ms expiry hides
on lost updates. Existing worker/control200ms guards unchanged. Same label
does not reassign src/restart animation. Hidden pages stop polling/unload GIF.
`--gesture` is still opt-in; without it the box shows 제스처 미사용. Existing
gesture pause during motion remains. No classification/decision/vehicle control,
crossing permission, GPIO, camera-FPS or driving-feature changes. GREEN is NOT
evidence the real vehicle stopped. Web GIFs are not baked into camera MP4s.

PC288 tests and six Node suites pass. Browser checked synthetic GO/STOP/unknown
fixtures on LOCAL5065, clearly labelled camera/motor disconnected. GIFs render,
390px mobile has no horizontal overflow. This is DISPLAY verification, NOT
live MediaPipe/KNN classification or motor-stop verification. Screenshots under
outputs/review_20261020/gesture_*.png. Ignored display_fixture.py is local-only,
MUST NOT be deployed or described as real recognition. Stop local fixture after
checking. Pi Flask remains off throughout. Upload/test checkpoint follows.

Deployment complete: SHA256 verified9 uploaded files; previous versions are in
outputs/backup_gesture_display_20261020_005448. Pi288 Python tests pass; Flask
absent/port5001 closed before and after. PC fixture PID38992 was terminated
after browser checks; no preview server is left running. Two GIF asset hashes
match the original Downloads files exactly. Actual live gesture inference was
NOT started/tested, because the owner requested Flask OFF. On a later explicit
Flask start for this feature, use the normal full profile WITH --gesture; do
not silently drop autonomous/manual/capture features, arm or enable crossing
control. Gesture source/model, GPIO/speed settings and stop guards unchanged.

## Deployment Checkpoint 2026-10-20 00:36 KST: Flask Still OFF

Supersedes the not-yet-deployed status below. Uploaded lossless diagnostics,
published-frame settings/reference-heading metadata, replay_path.py, associated
tests and docs to Pi192.168.137.60. SHA256 verified12 files; prior versions saved
in outputs/backup_lossless_review_20261020_003611. Pi Python3.11 ran all285 tests
successfully. No hardware was opened by the fake-device test suite. Verified
own Flask absent and port5001 closed BEFORE and AFTER the operation. No server
startup, arming, GPIO motion command, capture deletion or steering/speed tuning.
The stop-button fault remains unresolved; this is diagnostic infrastructure,
NOT a demonstrated curve-driving improvement or a physical safety validation.

## Newest: Flask OFF / PC-Only Lossless Diagnostics

Owner requested Flask off while working. Gracefully stopped exact PID14758 and
verified port5001 closed. No server has been restarted and no motor command sent
since. Keep it OFF; the unresponsive-stop fault is NOT fixed. The older online
PID14758 note below is historical and superseded by this paragraph.

PC-only changes, NOT uploaded/deployed to Pi:
- Automatic pilot failure snapshots save oriented raw BGR as lossless PNG after
  the existing motor-stop operation. Processed companion stays JPEG; ordinary
  photos and MP4 rates are unchanged. PNG is not sensor RAW. PNG download/list
  allowlists updated with the existing traversal guards preserved.
- Monitor stores settings actually used for each published frame; control
  observations/recording metadata preserve them even after a pending UI edit.
  Invalid path predictions also retain reference_heading_degrees. No vision
  threshold, steering gain/rate, speed, ownership, timeout or rejection change.
- replay_path.py is an offline, independent-still diagnostic utility. It accepts
  named raw PNG/JPEG images, no screen recordings, and never imports GPIO or
  opens a server. Each image starts a new tracker. Reports include hashes,
  settings, reference assumptions, candidate geometry and rejection reasons.
- PC285 Python tests pass, five Node suites pass. Coverage includes exact PNG
  pixel round-trip/download, source preservation, no motion-before-diagnostics,
  IO failure not preventing the existing stop, immutable frame settings and
  screen/profile/input validation. These are NOT hardware safety/lap tests.

Ran21 previous raw JPEG stills through the tool with an explicit assumed
reference.5133757390238175/heading-2.43/analysis480/ROI.20/lap+joint. Output:
outputs/review_20261020/existing_raw_replay/report.json and PNG review overlays.
18 selected paths valid,3 rejected (2 inconsistent chains,1 association failure).
This is NOT an accuracy score or improvement over the old controller. Crucially,
the prior140903 failure JSON records an invalid exact frame, while recompressed
JPEG now yields valid with unchanged perception code: do not tune thresholds
from a JPEG replay as if it exactly reproduces the captured failure. Preserve
new exact PNGs for the next reason-specific perception change. The latest screen
video contains no corresponding captured raw video/JSONL in Pi's listed files.

## Latest: Manual Screen Video Review 2026-10-20

After the fault discussion, the owner explicitly requested manual control and
asked NOT to remove autonomous features. The server was restarted with the
original full manual/autonomous/lap/boundary profile, disarmed/DC0/PWMoff and
zero motor writes. Latest launch PID14758. No agent arm/drive command was sent.
This overrides older OFF-state runtime notes, NOT the unresolved stop failure.
Do not claim the fault was repaired or that another autonomous trial is ready.

Owner supplied Downloads/recording20261020_001956.mp4:76.5seconds,1232x810,
screen recording30FPS. Source copied without modification to ignored
outputs/review_20261019/manual_screen_20261020_001956.mp4 (ASCII path for OpenCV).
Reviewed0.5-second samples and2-second visual contact sheets. Generated evidence:
manual_001956_review.json and manual_001956_contact_01..05.jpg in that folder.
These contain ONLY display-space colour counts, NOT raw perception reruns,
ground-truth accuracy, physical speed/angle or camera/inference-FPS estimates.

Findings:
- About5..14s: yellow boundary remains visible; displayed white paint reduces
  to1..2 marks then leaves view, and green path display disappears.
- About23..28s: actual displayed white marks remain, but green path flickers;
  many isolated yellow detections lie on apparent road reflection/wrinkles.
- About34..36s: markings from both lanes are visible across a near-horizontal
  scene; no selected green path. Do not average both lanes to force validity.
- About42..56s includes a prolonged stationary interval with sparse paint;
  do NOT count this as14seconds of moving perception failures.
- About66.5..70s: curve/paint visibility again degrades. Around72s crosswalk
  stripes coincide with missing displayed path; crossing handling is separate.
- Straight0s and W+A9s both show motor commands.250; manual mode has NO
  curve-slowdown policy. Later selected settings include.28/.31/.30. Reverse
  and stopped sections exist, so this is not a clean expert-imitation lap.

Useful as a failure catalogue/regression scene reference, NOT a ready training
dataset: camera pixels are overpainted with cyan/yellow/green/HUD/inset; manual
UI highlights and video commands need not be synchronized. No patch to runtime
perception/control, speed, steering, rejection guards, deployment or motion was
made during this review. Next perception work should use paired RAW frames and
JSONL to test sparse oblique path geometry, boundary continuity/noise handling
and curve-exit transitions. Do not tune raw HSV thresholds on overlaid frames,
infer a full lap, blindly clone maxA/D commands or bypass stop/freshness guards.

## URGENT 2026-10-20: Uncommanded DC Motion

CORRECTION FROM OWNER: stopping Flask DOES stop the wheels. The reported
unresponsive/maximum-speed motion happens WHILE Flask runs, not after shutdown.
Agent initially misinterpreted the timing. Off-state floating inputs are NOT
evidence of this fault and must not be presented as the cause. Keep Flask OFF
pending review of browser input delivery, accepted keys/output/sequence and PWM
behavior. Energized reproduction needs fresh supervised readiness. The prior
instruction below requiring proof that shutdown fails is superseded by this
clarification. No actual wheel speed/current/temperature measurement exists.

Owner adds: normal initially, intermittent fault after prolonged work. Fixed
wiring error is therefore NOT established; examine time-dependent input/PWM,
power and driver thermal behavior without assuming which one. No motor restart
performed. Local screen clip Downloads/manual recording234058 is4.233s/30FPS,
1252x864. OpenCV VideoCapture could not open its Unicode path; an ignored ASCII
copy at outputs/review_20261019/manual_screen_234058.mp4 decodes correctly.
Sampled0/2/4s frames show changing local pad highlights while camera HUD stays
MANUAL A+D / steer0 / motor0.000. This indicates possible display/command-sample
timing mismatch, NOT proof of physical motor speed or a complete fault trace.

Further clarification: while HOLDING W the robot suddenly runs away fast; the
web STOP button is also ineffective, but terminating Flask stops the wheels.
Treat this as a stop-path/control failure, not proven motor overload. Do NOT
re-enable hardware for an ordinary driving test. Code inspection shows GPIO
input, stop and watchdog tick share ManualDrive.lock in the same Python process;
a blocked hardware operation could block all of them. This is a structural
weakness, NOT proof a blocking operation caused this incident. No fault-time
stack trace/PWM waveform/current or exact command log exists yet. Installed Pi
gpiozero2.0.1.post3/lgpio0.2.2.0; no version/package changes were made. Latest
readback still has all four motor GPIOs OUTPUT LOW. No server/motion started.

Owner reported DC motors at maximum speed, not obeying manual commands, after
several Flask stop/start requests. Immediately instructed MOTOR BATTERY OFF /
disconnect power, do not restrain spinning wheels by hand. Physical power-off
and wheel stop have NOT yet been confirmed. Do not restart hardware-enabled
Flask or perform more movement until this is resolved.

Read-only SSH found NO own Flask or Python control process; all motor GPIOs
BCM20/21/23/24 were INPUT, pull NONE, sampled LOW. Issued ONLY the stop-state
command `pinctrl set 20,21,23,24 op dl`; verified all four OUTPUT LOW. No motor
enable/high/PWM command, server startup or servo command was sent. This is not
a physical stop confirmation and cannot protect against driver/wiring faults.
Released floating inputs are one plausible cause, NOT proven; inspect exact
driver, EN/STBY behavior, common ground, wiring and damage with power isolated.
Do not simply raise speed/timeout or repeatedly restart to test this fault.
CPU51.0C/get_throttled0x0 was measured before this report: it is NOT motor
temperature/current data. The controller has neither measurement.

## Latest Checkpoint: Compact Panels / Manual Video Collection

Supersedes the owner-away/no-motion/PID32273 note below. The owner returned and
authorized supervised trials:140130 (started with physically angled wheels),
140343 (3-second observation window, operator stop, no perception fault),140427
(near reflection contaminated a chain),140902 (insufficient_dash_span after a
different reflection). All UTC19Oct under captures/runs/. NO completed lap.
The completion-only near-reflection filter has two regression tests and fixes
the140427 still, but the140902 borderline glint is NOT solved. Do not claim it is.

Current task is collecting MANUAL video and improving controller visibility,
NOT permission to resume agent-driven motion. Preview defaults30 (previously15),
capture/analysis settings unchanged; paired video recording remains10FPS/120s.

UI: manual and autonomous control tabs, manual first, separate from the existing
camera view tabs. Advanced motor/pilot/camera/gesture settings are collapsed.
Desktop controls stay alongside the video with bounded independent scrolling;
mobile controls follow the video. Switching tabs stops this browser's owned
manual/pilot control; it does not arm, transfer ownership or start another mode.
ManualDrive stores a copy of accepted keys only AFTER live-owner/sequence checks;
stale/unauthorized input cannot replace them. Stop/pause/pilot clear manual keys.
No GPIO wiring, output, servo rate, lease or freshness behavior changed.

Processed camera/video adds a small upper-left command HUD. Raw frames remain
untouched. Recording metadata uses the SAME sampled command state as the HUD:
control.keys, command_sequence, control_observed_at. It is NOT a measured wheel
angle/speed or sensor-exposure sync. User must use paired JSONL for numeric data,
not expect Flask controls themselves to be part of the camera recording.

PC279 Python tests and five Node suites pass before deployment. Deployment must
backup/hash-check, verify disarmed/no recording, stop only this server PID,
run Pi tests then restart DISARMED with the same boundary-guidance lap profile,
base.30/curve.85/analysis480/preview30/port5001. Do not calibrate or move on upload.
Deployment completed: Pi279 tests pass, current Flask PID36838 on5001,
disarmed/DC0/PWMoff, motor_write_count0, no recording or new run. Backup:
outputs/backup_control_panels_20261019_232201. Mobile compact-template update
required one additional disarmed restart; its previous template is also backed
up there. No calibration, motion or recording was started in this UI task.
Browser verification: desktop manual/auto switching and detail expansion,
390x844 mobile no horizontal overflow, manual stop and all direction buttons
visible in the first viewport. Outputs/review_20261019/control_panels_desktop.png
and control_panels_mobile.png are ignored screenshot evidence. Browser restored
to desktop/manual tab. All original camera tabs remain. Reload existing user
tabs after restart; their old control tokens are intentionally invalidated.

## Latest Checkpoint 2026-10-19 22:56 KST: Joint Guidance, NO Motion

Owner requested joint white-central/yellow-boundary control, then left for
about20minutes. Agent explicitly deferred motion until the owner returns and
confirms placement/stop readiness. DO NOT run supervised_lap_client.py --ready
or arm/manual/follow on the basis of earlier readiness. Camera-only checking,
code upload, tests and disarmed server restart were performed, NOT driving.

Current Pi192.168.137.60 Flask PID32273 on5001, project-local Python3.11.17.
Command is the normal480-analysis lap profile plus --boundary-guidance. It is
DISARMED, DC0, PWMoff, motor_write_count0, last_motor_write_atNone, no reference,
no new run log. Crosswalk/gesture OFF. Profile Kp35/heading1.0/curve.85/base.30;
rate60 and-105..85 steering limits intact. This supersedes old diagnostic60/0.
Native capture960x720/30FPS and preview15FPS unchanged. Reference_required is
intentional: on return confirm the robot then set a fresh straight reference.

Implementation:
- boundary_guidance.py is a pure current-frame adapter after LanePath, enabled
  only by PilotConfig.boundary_guidance / CLI / Flask checkbox. Default remains
  OFF. Requires explicit lap mode and heading gain>=.25. Mode stamps block old
  observations at start/status/tick; changing mode resets path calibration on
  the next camera frame. No UI/config action arms or moves the robot.
- Full white paths still set the central target. A compatible current>=8-point
  edge can contribute35% to image heading in a white-confirmed bend; white65%.
  Opposing/flat cues are ignored. IMPORTANT: straight yellow edges converge in
  perspective. An initial stationary replay exposed an incorrect9deg preview;
  it was corrected BEFORE any motion by requiring the white path also indicate
  a bend>=12deg. A new mirrored regression verifies zero straight steering.
- When both signals confirm a bend and fused heading>=20deg, cap an opposing
  lateral term at half the heading term rather than allowing cancellation.
  Rate/caps/soft centre deadband remain. These are image-space heuristics/gains,
  not measured curvature or physical steering calibration. Test physically.
- Sparse-target fallback is limited to insufficient_dashes/span, an out-of-range
  observed target, or single_dash_uncorroborated. It NEVER overrides ambiguity,
  inconsistent fits, association failures, jumps or out-of-image targets.
  It requires actual current white paint: length>=.20H, fill>=.75, aspect>=2.5,
  thickness>=.02H, y-span>=.08H, unclipped endpoints and>=80% paint in a5x5
  target patch. Current connected yellow>=8 and near road>=.90 must agree.
  A .40.. .90H observed target is exclusive to this opt-in mode. No imaginary
  continuation beyond paint. Source stays single_dash_boundary: it cannot
  calibrate, seed full-path history or renew bounded recovery. Speed cap.8 stays.
- Boundary-side road probes label divider/outer/unknown for diagnostics. A
  central divider is not automatically an off-track failure. This classification
  is NOT physical wheel sensing. No fully yellow-only path/learned-width planner
  was added; zero credible white paint still stops. Do not claim otherwise.

Tests:272 Python tests pass on PC and Pi, four Node UI suites pass. Coverage
includes mirrored near curves, missing/wrong/fragmented edges, missing paint/
road/reference, weak/side-clipped shapes, conflicting candidates, hardware
clamps, stale frames, ownership/lease, no actuation at configuration/startup,
fresh mode/reference requirements and disabled recovery renewal. Desktop and
390px mobile browser screenshots show the checkbox with no horizontal overflow,
start disabled, output0.000. Browser was read/expanded/focused only; NO start,
reference, motor setting or manual-control action was submitted.

Ignored evidence:outputs/review_20261019/joint_guidance_replay.json (independent
saved stills, not a temporal lap), guided_photo_* previews, stationary JSON/JPEG,
joint_guidance_desktop.png and joint_guidance_mobile.png. The last133430 saved
failure now gives boundary_guided_curve with an observed target and left image
heading; this is NOT proof of a physical lap. Stationary runtime measurements
are not motion blur or camera-exposure-to-display latency measurements.
Backup:outputs/backup_joint_guidance_20261019_225039. Previous controller and UI
files are preserved there. No old data/gesture/other projects were deleted,
no GPIO polarity/trim change, no unattended heartbeat and no physical trial.

## Latest Checkpoint 2026-10-19 22:36 KST

Supersedes the PID, test count and latest run in the22:23 section below.
Current Flask PID30366 on5001; DISARMED, motors0, PWMoff. Same launch and
Kp60/heading0/curve.85/speed.30 diagnostic settings. Latest actual run:
run_20261019T133429_624855Z.jsonl, last command-44.7978. No completed lap.

Owner reported only slight body advance in132158 and no movement in133013.
Do not diagnose motor failure/stall solely from these brief interrupted trials.
Actual movement/footprint AFTER133429 has NOT been physically confirmed; obtain
that before additional motion. The controller has no encoder or angle feedback.

Two narrowly guarded perception additions, completion mode only:
- One oblique observed dash can supply its actual major-axis endpoints only
  with existing reference, length>=.20H, vertical span>=.08H, fill>=.75,
  aspect>=2.5, thickness>=.02H, endpoints inside the image and an observed target
  within .40.. .70H. Current boundary>=8 and near-road checks still apply. This
  remains single_dash_boundary, cannot calibrate or renew turn recovery, and
  keeps the.8 limited-path speed cap. No mark/edge/road/reference fails.
- If multiple centres are just BELOW the bounded target window, actual current
  dash pixels may support a target no more than.08H beyond the furthest centre,
  still within .40.. .70H and .20H Euclidean distance. Require>=80% paint in a
  5x5 patch, aligned paint axes, current near road>=.90 and a new>=8-sample edge
  validation connected to the original same-side yellow component. At most
  three candidate corridor checks per frame. Empty extrapolation is rejected.
  The drawn path includes this verified paint-supported target.

133013_045933Z: after single-dash addition, stopped at~.37s because two centres
became candidates again at minimum depth.70083H, outside the old target gate.
133429_624855Z: after paint-supported target addition, outputs.24/angle~-48..-45
with valid paths for~1.25s, then path_lost. Exact stop observation has centres
at.756H and.956H; current yellow9/near-road1.0 persist but no bounded target is
validated. The later status said insufficient_dashes; use the exact stop JSON,
not that later frame, to diagnose this fault. Source receipt age at stop80ms.
Stationary post-change10-sample processing median31.05ms/~27.7FPS, max source
age105ms. Neither software motor output nor camera motion measures body speed.

IMPORTANT: general yellow-boundary-driven path generation or curvature steering
is STILL NOT implemented. These changes retain the central-paint/observed-target
dependency. Owner explicitly asks to use the visible outer curve; do not claim
these corroboration changes already implement that request. Current heading gain
is0 for the earlier P-only comparison, not a validated production controller.
Do not blindly restore old paths or remove freshness/footprint/ownership guards.

PC and Pi257 Python tests pass. First Pi attempt with live camera load hit an
existing fresh/stable-path test timing failure; rerunning the complete suite
with stopped camera passed. No runtime freshness checks were weakened. Four
Node UI suites passed at the prior unchanged-UI checkpoint. Backups:
outputs/backup_single_oblique_20261019_222924 and backup_paint_target_20261019_223309.
All failure frames/logs remain ignored local evidence, not Git content.

## Latest Checkpoint 2026-10-19 22:23 KST

This checkpoint supersedes older P-only readiness, PID and test counts below.
Owner replaced at the straight start and later confirmed all wheels remained
on black road. Owner explicitly requested another drive at22:18. No full lap
has been completed. Before further motion, obtain fresh physical footprint and
actual movement feedback after the latest trial; do not infer wheel position
or travel distance from motor outputs or a first-person image.

Current Flask PID29134, port5001, DISARMED, DC outputs0 and PWMoff.
Launch: local3.11 venv, track_web.py --manual --motor-wiring-confirmed
--autonomous --lap-mode --pilot-speed0.30 --analysis-max-side480 --port5001
(CLI flags take separate values, e.g. --pilot-speed 0.30).
Live diagnostic settings: Kp60, heading_gain0, curve_scale.85, speed.30,
continuous/recovery/lap enabled, crossing OFF. Last command-41.9568 is NOT
measured steering. Latest straight reference:reference_20261019T130457_971028Z.json.

Latest runs, under captures/runs/ with run_20261019T prefix:
- 130458_799417Z: fresh straight P-only start; supervisor heartbeat HTTP timeout
  caused operator_stop, not a path failure. PC heartbeat now has its own bounded
  worker independent of status polling. Faults still stop without retry; no Pi
  heartbeat or widened backend leases. Supervisor tests now5.
- 130621_590489Z: path_lost around3.1s, three-point inconsistent global fit.
- 130705_074909Z: short-span failure reproduced as decimal quantization at
 208.8px versus .58*360. Round inclusive comparisons to observed .1px precision;
 strict mode retains its original intended window.
- 131147_571049Z: path_lost around1.3s after bounded recovery. Oblique two-point
 spans now use an observed target inside .40.. .70H in explicit completion mode,
 only with aligned paint, >=8 independent boundary samples and near road>=.90.
 Strict mode keeps its .52.. .58 centre window; no extrapolated short-span target.
- 131444_579814Z: path_lost around.2s. Seven row-boundary samples short-circuited
 a complete nine-normal observation. boundary_evidence now accepts the caller's
 minimum_samples (default7); short-span callers request8 and try normal evidence
 when row evidence is insufficient. No thresholds or negative checks removed.
- 132158_103533Z: latest supervised3s window, path_lost around2.4s (PC observed
 at2.62s). Commands around-42 with outputs.24; actual body movement not measured.
 Final path has only ONE dash candidate; current connected yellow evidence9 and
 near-road1.0 persist. General boundary-only path generation is NOT implemented.
 User proposed boundary-curvature guidance; do not claim this selector fix is it.

Capture delivers30FPS; processing around29-30FPS at480 analysis in these runs.
Preview is independently capped15FPS. Stationary HTTP snapshots took78-156ms;
these measurements are NOT exposure-to-browser latency or proof of no motion
blur. Source receipt age at latest failure was46ms. The recorded stop reason is
insufficient_dashes, not a demonstrated FPS timeout.

PC and Pi255 Python tests pass. One first PC run hit the existing reference-file
mtime guard in a test; immediate complete rerun and Pi run passed. No UI changed;
four Node UI suites are rechecked for this checkpoint. Runtime backup before
latest fix:outputs/backup_boundary_probe_20261019_222113. Earlier fixes backed up
under backup_quantized_20261019_221030 and backup_observed_target_20261019_221411.
Full raw/processed failure images and logs are ignored outputs/review_20261019/
on PC and captures/ on Pi; never stage them, tokens or credentials.

## Supervised Physical Trials 2026-10-19 21:29 Onward

This section supersedes the earlier "no motion/readiness pending" checkpoint.
Owner confirmed ready and authorized PC-supervised motor operation. Later the
owner explicitly allowed hand-repositioning at the start, superseding the
earlier no-return constraint. A completed lap is NOT established.

Hardware observations: D/+85 was pulsed three times with DC outputs0; owner
confirmed front wheels actually turn RIGHT. A subsequent servo-only0 command
was sent and stopped. Do not invert steering polarity. A stopped/detached servo
may physically return toward neutral; logged command units are NOT angle feedback.

Actual runs (UTC timestamps, all files under captures/runs/):
- 122907_733377Z: first calibrated straight run, path_error_large at~1.62s.
  Error+.558, heading-9.43, command+5.71: lateral/heading terms nearly cancel.
- 123643_812674Z:1s observation window, curve output.255, very little motion.
- 123706_636723Z:.5s window at.30; owner reports almost no movement.
- 123757_481376Z:path_lost at~.38s, inconsistent_dash_chain. New far points
  changed the global curve and alternated steering; near two-point corridor
  is independently supported on the exact saved failure image after the fix.
- 124003_100993Z:after explicit manual replacement and new straight reference,
  Kp60/heading.8/.85 curve scale,~1.8s bounded observation, operator_stop.
- 124605_402485Z:Kp35/heading1.5/curve_scale1 diagnostic, path_error_large~.6s.
- 124913_257093Z:same gains, path_error_large~.17s; yellow paint centre was
  wrongly included in a road-only corridor probe on wide projected bends.
- 125121_655202Z:same diagnostic gains, path_lost~.7s; valid near side-clipped
  paint had been excluded, leaving only a short span of distant paint.
- 125914_851506Z:Kp60/heading0/curve.85 from the stopped adjacent-lane pose,
  outputs.24, path_lost~.22s because only one associated near mark remained.
  This is NOT a clean P-only comparison from the straight start. No new blind
  single-mark/near-only exception was added; require a clean starting comparison.

operator_stop windows above are PC-supervisor observation stops, NOT a new
5-second backend trial limit. Server remains continuous; faults still stop.
Do not claim software output is measured wheel motion or these runs form a lap.
Full driving scenes/JSON are local outputs/review_20261019 and Pi captures/;
keep them out of Git. No reversing or unattended Pi-local heartbeat was used.

Deployed additions, explicit completion mode ONLY:
- Near yellow can bridge the near-road patch ONLY for a narrow actual yellow
  run with independently classified road on BOTH sides; outer paint/floor fails.
- Nine-normal evidence can corroborate shallow/perspective paths as well as
  steep paths; all existing raw-hit, component, road/gap/direction tests remain.
- A failed/complemented global fit can use observed target-band centres at
  .40.. .78H, with unchanged paint-axis, observed-depth and edge checks. That
  selected edge must also remain connected to the original nearest depth;
  a disconnected near edge cannot be hidden by cropping the fit.
- Observed-row corridor fallback needs>=3 aligned paint centres,>=.25H paint
  span, fresh near road,>=8 same-component raw yellow probes over>=.20H,
  >=90% road between fitted paint and its road-facing yellow edge, bounded gap
  variation/step/turn. It does NOT assume perspective curves share quadratic
  shape/parallel slope. Sample ends use road-facing paint edge, not paint centre.
- Strong side-clipped paint can anchor ONLY if long/thick/filled, not at the
  bottom corner, and aligned with>=2 intact forward marks. Every selected such
  anchor additionally requires current independent edge and near-road evidence.
  The old small bottom-right fragment remains rejected. Strict mode unchanged.
- Uncorroborated partial chains clear association memory, NOT calibration, so a
  stable fresh nearer lane can be re-associated after a stop. Both lanes allowed.

Explicit authenticated /auto/restore accepts only recent<=2h saved reference_*.json
and matching stopped run_*.jsonl from captures/runs, exact camera settings,
960x720 capture, a valid multi-dash straight reference, and bounded last command.
It requires disarmed lap mode, does NOT arm/start/move, clears association and
requires new stable frames before start. Never use it after physically changing
camera/geometry. New manual commands override its remembered command. Saved
reference for the latest placement:reference_20261019T124002_330991Z.json.

Latest deployed server PID25532 on5001 is DISARMED, reference restored, DC0,
PWMoff. Launch remains the explicit480-analysis/30FPS capture lap profile.
After restart its defaults were Kp35/heading1.0/curve.85/speed.30. Current live
diagnostic settings are Kp60/heading0/curve.85/speed.30 after125914, NOT the
temporary Kp35/heading1.5/curve1 from earlier runs. Last command-39.99; setting
a fresh straight reference or intentional new manual neutral command supersedes
it. No fresh neutral assumption is permitted just because a process initially0.

Owner clarified the wheels are in the ADJACENT LANE across centre yellow, NOT
white floor beyond an outer boundary. That was within the authorized corridor.
After125914, a new manual replacement at the straight start was requested for
the clean P-only comparison. That readiness is now PENDING; do not silently use
the earlier readiness/adjacent-lane pose as the new straight placement. Isolate
image-target P steering(heading gain0) before further controller changes. This
is a pending comparison, not a proven improvement/default change.

PC and Pi250 Python tests pass at the deployed source checkpoint; four Node UI
suites passed. PC-only supervised_lap_client.py now additionally requires --ready,
one .2..10s observation window, an external PC (rejects self-connection on Pi),
PC-origin heartbeats and same-owner finally-stop; it never retries a stopped run.
Three new supervisor tests also passed on Pi without any network or motion.
No server auto-startup boost or output-cap increase has been introduced.
Temporary curve_scale1 was explicit diagnostic runtime only.

## Completion Priority 2026-10-19 Evening

Owner explicitly reprioritized: complete one lap, both track lanes allowed,
not precise first-lane centring. Requests agent-operated supervised tests,
diagnose/resume where stopped, no reversing/return to start. Never interpret
this as permission to drive outside yellow boundaries or through missing/stale
perception. Placement/observer readiness was requested before any new motion.

Stopped disarmed PID12124 and preserved source/status/command under
outputs/backup_lap_20261019_204506/ before edits. New explicit --lap-mode config:
continuous=True, turn_recovery=True, lap_mode=True, Kp35, heading_gain1.0,
base output remains explicit0.30. Original defaults remain unchanged otherwise.
Soft centre-error band.12 reduces lane-centre corrections; a two-lane tolerance
still needs independent current road/connected-yellow support and hard bound1.05.
Normal turn entry keeps rate60; neutral unwind may use up to120, with a zero
crossing barrier before an opposite turn. Servo limits/PWM mapping unchanged.

Added side_clipped marking metadata and excluded side-clipped paint from chain
anchors (bottom-clipped near paint is NOT excluded). Exact saved failure
photo_20261019T114029_876215Z now connects five genuine dashes at480 AND640,
instead of anchoring on the right-bottom fragment and rejecting the chain.
In completion mode, independently checked near centres may be attempted after
the four-point far-curve fit is inconsistent. Saved photo_20261019T113045_532417Z
now validates the nearest three with paint/road/connected-edge evidence at both
resolutions. Old strict mode still rejects that sharp far fit. No fit threshold
was globally raised and no general inconsistent-path recovery was introduced.

PC/Pi238 Python tests and four Node UI suites pass, including mirrored sharp
curves, missing/fragmented edges, missing near road, wrong paint axes, clipped
fragment anchors, centre tolerance, camera-stop guard and bounded fast unwind.
This is offline/software evidence only; a physical lap is NOT established.

Further completion-only fallback verifies3..10 observed centres as a piecewise
polyline, with paint-tangent agreement, near-road confirmation and9 independent
normal-edge samples (>=8 hits, coherent component/gap/direction). This handles
compressed curved spans without forcing a global x(y) polynomial. Targets stay
inside observed depth; a sharp unsupported chord, wrong paint axis, missing
road, ambiguous chain or unmatched boundary still stops. Bounded recovery now
corroborates a previous polyline using current masks, not a mismatched old fit.
A5x5 closing is used ONLY to label tiny yellow print/crease gaps; ray hits must
still come from original observed yellow pixels. Large fragments still fail.
Saved-scenes replay is diagnostic selection, not an independent accuracy score;
several former failure poses remain rejected for missing/inconsistent evidence.
Historical deployed standby PID16820 ran the explicit lap profile on port5001.
The agent has NOT sent reference/arm/start/motor commands in this lap session:
the owner's message said they would place the robot, and the asynchronous
placement/observer-stop-readiness question has not yet been answered. Camera
shows a stable straight section; reference remains unset, motors0/PWMoff.
Await that readiness answer, then calibrate once on the straight and use the
existing authenticated Flask API with PC-origin heartbeat. Never run an
unattended Pi-local heartbeat loop that could outlive supervisor disconnection.
No reverse/return-to-start trial is authorized; diagnose and resume where safely
stopped. Both lanes inside the yellow corridor are allowed. Never automatically
retry after a stop fault without inspecting its frame/reason/current placement.

## High-Rate Analysis Profile 2026-10-19

Owner requested30FPS lane recognition after observing~19FPS; camera already
delivered30FPS and preview cap15FPS was not the processing bottleneck.
Backed up stopped/disarmed PID5687 source/status/command under
outputs/backup_fps_20261019_2019/ before edits; no motion command was sent.

Exact segmentation optimizations replace sorted component-pixel unique with
bincount presence, full-frame int64 where/casts with uint8 label lookup, signed
contrast/colour masks with equivalent OpenCV operations, and combined-preview
boolean colour writes with merged binary channels. All masks, markings,
metrics and combined previews matched the previous code on33 saved raw photos
at the SAME640 analysis geometry. Interleaved matched median full-frame CPU
pipeline time improved51.6ms to43.6ms on the saved failure image; this benchmark
alone did not achieve30FPS or establish live accuracy.

Added explicit --analysis-max-side320..640 (default640). Current supervised
hardware-panel process PID12124 uses480, pilot-speed0.30, no gesture, port5001.
Capture/raw/native-detail processed preview stay960x720; masks/path fit480x360.
Do not claim this lower-resolution profile has pixel-identical recognition:
small distant markings may be lost. No gains, servo limits/rate, output caps,
perception acceptance gates or control safety timers were changed in this step.
Restart cleared reference and session settings; new centred-straight calibration
is required before any drive. No automatic arm/start/reference was sent.

PC/Pi224 tests and four Node UI suites passed. Stationary480 profile initial
warm-up averaged28.75FPS; subsequent61 samples measured30.08 actual frame-count
FPS,23.8ms median processing, source age<=0.076s,61/61 valid paths, zero preview
clients. This is stationary timing, not proof of successful cornering. Reports
are outputs/fps_exact_benchmark_20261019.json, fps_live_20261019.json and
fps_steady_20261019.json. Earlier steering-unwind lag remains unfixed.
One actual PC-over-Wi-Fi processed-preview stream was then read while observing
71 status samples:30.01 actual frame-countFPS,24.4ms median processing, source
age<=0.066s and71/71 valid paths. Stream received29.7MB; data was discarded,
not recorded as a video. No hand inference or powered motion ran in this test.

## Integration Software Checkpoint 2026-10-19

The owner is away for an hour; NO physical motion, arming, powered wheel tests,
reference setting or implicit go authorization is permitted during this work.
Before edits, PC and Pi runtime sources matched; only this local handoff had
newer planning text. The Pi server was not running. GPIO mapping and the
preserved gesture_reference source/model are unchanged.

Added turn_recovery.py with source-time freshness and independent current
road/connected-boundary corroboration. Recovery is opt-in, missing-dash-only,
<=.20s from last full path, no budget reset on one valid flicker, no old-turn
resume after a new opposite turn. It never raises speed or bypasses a stop.
AutoPilot keeps recomputing normal steering whenever a valid path is present.

Added crosswalk.py, gesture_adapter.py and interaction.py. The optional
--gesture preview shares the camera. Crosswalk grouping uses pre-lane-filter
colour support; crossing pause retains ownership with outputs0/PWMoff. Fresh
wait epochs and unsmoothed current KNN decisions are separate from display hold.
GO requires5 results over0.5s and a valid fresh lane; it cannot arm/revive a
stopped run. New PilotConfig flags turn_recovery/crosswalk_gesture default OFF.
The crossing flag requires initialized worker and supervised continuous mode.

New read-only Flask state/gesture view preserves the existing five tabs. GPIO
output-change dispatch count/time are logged; they are NOT wheel-speed feedback.
No startup boost, output-cap increase or GPIO polarity change was introduced.
PC220 and Pi220 Python tests and four Node UI suites passed at the final
checkpoint. Actual Pi runtime is Python3.11.17; camera-only gesture preview
PID5535 uses track_web.py --gesture --port5001. Physical motion discrepancy,
crosswalk stop-depth calibration, visibility of a pedestrian hand at the driving
camera angle, object/idle-hand negatives and complete-lap repeatability remain
unverified. Do not call these physical features complete from software tests.

The first live gesture timing sample had33/100 results older than0.20s
(median0.179s, p950.236s), despite inference taking about39ms. The worker had
added its full cooldown AFTER inference and received frames AFTER road analysis.
Scheduling now caps start-to-start rate, and rotated/resized camera pixels are
offered before road analysis. The0.20s freshness guard is NOT relaxed. New
result-age/inference-FPS/sequence-fill observations distinguish pending input
from a held display label. A model's ordinary-hand/object false positives remain
an unresolved classifier limitation; temporal filtering is not proof of intent.
After deployment,100 samples had median0.134s/p950.179s/max0.203s result age;
1/100 exceeded0.20s, versus33/100 before. Inference updated at15FPS. Both samples
were stationary with NO hand; this is timing evidence, not recognition accuracy
or proof that the wait/go sequence succeeds with a pedestrian in view.

Read-only15-minute metadata soak and backup/manifests are under Pi outputs/;
local browser/health evidence is under outputs/integration_20261019/. No wheel
movement, arm, reference-setting, photo/video capture or gesture-model edits
were made while the owner was away. The deployed server is camera/gesture-only
on port5001, intentionally without a manual/autonomous hardware panel.
The pre-scheduling-patch15-minute soak passed300 samples, processed18.6..21.7FPS,
source age<=0.126s, zero transport errors, no hand/GO and no thermal throttling.
Final timing-patch verification is saved separately as integration_latest_soak:
61 samples over180.5s, processed18.3..19.5FPS, source age<=0.136s, no observed
gesture result older than0.20s and no camera/gesture/transport errors. This was
also a stationary no-hand preview, not physical drive or intent validation.

Wi-Fi power saving was temporarily disabled without reconnecting or changing
the network. This resets on reboot. Small unmatched request samples changed
median44ms to50ms and maximum451ms to157ms; this is NOT proof of a network fix.
Source/control freshness limits were not increased.

## Next Session Priority

Read NEXT_SESSION.md before the next change. The owner requests fastest viable
integration of track autonomy, crosswalk stop and fresh stop/go gestures; no
traffic lights. Brief missing-dash turn continuation is requested, but must be
an explicitly bounded, independently supported recovery mode, not blind turning.
The file defines implementation order, test gates and rollback checkpoints.
The plan alone did not implement control; the checkpoint above supersedes that
earlier implementation status. Physical validation gates still apply.

The owner subsequently reported manual0.22 does move, though slowly. Do not
retain the earlier unproven explanation that0.221 necessarily cannot start.
Latest inspected13:50/13:51 runs logged0.221 and ended operator_stop with valid
paths. Output commands do not establish actual wheel travel. Match manual and
auto conditions before changing starting torque behavior.

Runtime pilot speed was set to0.30 via the settings endpoint, without arming or
motion: normal curve0.255 and limited path0.24. Source default remains0.26.
Restart will clear this setting, continuous selection and the straight reference.
No startup boost was added. This planning update does not deploy or move the Pi.

## Current White Paint Restoration

The last failure run_20261018T132811_506849Z stopped dash_association_failed
after retaining one own-lane dash. Contrast segmentation left the nearest real
white stripe hollow/open; neighbour candidates belonged to other lanes. Do not
join all candidates or retain a stale steering command to bypass this failure.

track_vision now reconstructs within connected bright/low-saturation components
on the existing road mask. A component must have >=25% (and>=12px) original
contrast seeds and pass the existing area/aspect/fill>=0.60 gates. Only pixels
actually present in this colour support are added; dark holes/gaps, seedless
bright objects, huge/far patches and thin seams do not get filled by this step.
The old5x5 notch repair and downstream shape/path/safety checks remain.

The saved failure stripe also exceeded the centre-depth area budget by~4% after
restoration because it was clipped at the image bottom. Only bottom-clipped
paint at depth>=0.80 uses the already existing maximum near-area limit0.014*N,
in both restoration and marking measurement. This does not raise that maximum
or relax the fill0.60 threshold. Oversized bottom patches still fail.

Offline current and exact failed JPEGs now yield two observed own-lane centres
with dash_boundary_corroborated instead of dash_association_failed. Restored
pixels were~1759/~1938 on those images; the current nearest fill changed from
~0.43 to~0.79. Some far curved patches still fail the rectangle shape filter;
this change does NOT claim to recognize every stripe or complete a moving bend.
It leaves curve scale0.85, base0.26, limits-105..85 and all control guards intact.
PC172-test suite passed, including new seed/colour/no-gap/shape/clipping cases.
Pi3.11 also passed172 tests and the five uploaded files were SHA256 verified.
On the exact saved failure, matched alternating25-sample segmentation timing
was median24.7ms before/26.8ms after (camera stopped for the benchmark). Old
path association failed; new path had two centres and boundary corroboration.
Live stationary verification was25/25 valid two-dash paths, capture30FPS and
processed rate~20FPS. This is restoration, not a frame-rate improvement.
Preview direction may still say straight from the two near marks: some farther
curved paint remains rejected. Do not describe this as full-bend recognition.
Flask restarted disarmed, outputs0/PWMoff; no motion/reference/arm command sent.
Re-establish reference on a genuinely straight, centred placement, not here.

## Current Curve Slowdown And Stable Exit

The owner's latest request supersedes the no-braking trial below. Restored
curve_scale with default0.85 (range0.75..1), separate from independent limited
path scale0.8. Base0.26 therefore gives0.221 on full-evidence bends,0.208 on
limited-path bends. Manual0.30, gains, signed limits-105..85 and rate60 stay.

AutoPilot latches left/right turn mode across transient straight classifications.
Exit requires >=3 distinct valid fresh frames spanning >=0.3s, heading<5,
P/heading demand<4 and actual servo command<6. A frame gap>0.2s or renewed
turn evidence resets exit confirmation; a clear opposite bend switches directly.
Single-dash evidence cannot confirm exit. This is a mode/slowdown latch ONLY:
servo commands still use the current validated path and rate limiter. It never
continues through invalid/stale path, missing reference, ownership loss or
deadman/timeout. Turn state is reset on start/stop and logged each control frame.

Latest failed run_20261018T131436_514791Z stopped insufficient_dash_span, not
because two dashes were inherently forbidden. Its pair had48px vertical span
but122.6px chord at640x480. Narrow exception now allows oblique pairs with
span>=0.08H, chord>=0.20H, pronounced lateral chord, observed support near0.55H,
paint/chord alignment>=0.85, near road>=0.90 and>=8 connected matching boundary
samples. All ordinary span/ambiguity/jump/target checks remain. Saved failure
and current frames replay as valid left turns, supported by9 boundary samples.
This is offline/stationary evidence, NOT proof of moving corner completion.

165 Python tests passed on PC and Pi3.11; both Node UI suites passed on PC.
The10 deployed files were SHA256 verified. After disarmed restart,20/20 live
samples recognized the current two-dash left bend, with9 supporting boundary
samples; camera delivery30FPS, processing about23FPS. Outputs stayed0 and PWM
off. No motion/reference/arm command was sent. Restart requires a fresh straight
reference and explicit re-selection of continuous mode if desired.

## Previous Output And Centre Tracking Revision

This section supersedes the historical curve-braking policy below. The owner
requested removing turn slowdown and following observed lane centres regardless
of a fixed dash count. Removed curve_scale and heading/steering braking, low
output hold and delayed recovery from the pilot and Flask UI. Also removed the
path's heading-only0.85 factor. Base PWM remains0.26, manual0.30; independently
corroborated limited paths still carry0.8 (0.208 at base0.26). Loss/freshness,
ambiguity, ownership, rate60 and signed-105..85 hardware guards remain intact.
Faster travel does NOT establish a fix for fluctuating servo/path commands.

Live saved-frame analysis found a17px near seam reflection anchoring a false
two-point path, although four real left-turn dashes were visible. Depth-aware
minimum paint length now excludes that tiny candidate from path association
without hiding the candidate mask. Offline replay now identifies that left
bend instead of two_dashes_uncorroborated. This is not a moving-track result.

When an unfittable far bend fails the global fit, an independent near-path
fallback uses observed centres at y>=0.40H covering0.55H, near fit error<=0.02W,
paint tangent agreement>=0.85, near road>=0.90 and a matching connected yellow
edge. Median residual recentres the near fit; this is NOT a global average of
all visible lane marks. It cannot override known bad near-paint/tangent checks.
Single-dash support is only for an already referenced path: sufficient observed
length/y-span, target within the observed stripe, matching axis/road/boundary.
It is tagged single_dash_boundary with observed_dash_count=1, and cannot set a
new reference. Zero/short/ambiguous marks still stop; there is no stale fallback.

PC regression tests include both turn directions, seam rejection, far-bend
isolation, bad paint/fragmented-edge/road negatives, single-mark constraints,
base output in turns, preserved limited-path cap and lost-path stopping.
155 Python tests passed on PC and Pi3.11; both Node UI suites passed on PC.
Ten uploaded files were SHA256 verified. After disarmed restart,20/20 live
stationary samples returned central_dash_chain/left with4 observed centres,
where the previous version returned two_dashes_uncorroborated. Camera delivery
was30FPS and processed rate about20FPS. No motion/arm/reference command was
sent. A new straight reference is required; do not calibrate on this bend.

## Asymmetric Pilot Limits: 2026-10-18

The owner requested raising autonomous steering travel to the already confirmed
A=-105/D=85 command limits. Replaced symmetric max_angle=20 with positive
magnitude settings max_left_angle=105/max_right_angle=85, including separate
Flask sliders, default initialization, restart clamp and P/heading clamp.
Each setting is validated against both the confirmed105/85 bounds and the
actual ManualDrive configuration. Old max_angle API payloads are rejected;
reload the browser after deployment. Commands are NOT measured wheel angles.

Rate60, gains, motor outputs, freshness/ownership/deadman and loss guards stay
unchanged. Curve braking retains its existing20-unit severity reference so
raising travel cannot weaken the previous braking policy. The P controller
does not command full lock unless the calculated correction calls for it.

Latest failure run_20261018T125026_465841Z lasted~7s:115/155 command frames hit
-20. The last valid path demanded about-85.52 before the old clamp. It then
lost its second dash and stopped insufficient_dashes/path_lost. This supports
steering saturation, but does not measure physical wheel angle or prove the
new limits complete the turn. Verify in a fresh supervised short trial.

149 Python tests passed on both PC and Pi3.11; both Node UI suites passed on PC.
Tests cover asymmetric clamps, the last logged-85.52 correction, rate-limited
travel to both ends, restart without actuation, invalid/over-hardware requests,
unchanged braking and stopping on lost paths. Uploaded source hashes verified.
Flask restarted disarmed; no motion test was performed for this change.

## New SD And Preview Check: 2026-10-18

The owner's NEW Pi is192.168.137.60. Its project-local Python3.11.17 venv was
installed and validated with the37-package optional gesture dependency lock.
The camera backend is rpicam-vid. Do not contact or clean the old borrowed Pi.

Browser transmission now defaults to15FPS independently of capture/vision,
with per-view/frame JPEG caching, hidden-page stream suspension and explicit
camera-delivery/processed-FPS metrics. JPEG quality, recognition resolution,
capture/recording settings and ALL hardware/path safety policies are unchanged.
142 Python tests passed on PC and Pi; both Node UI contract suites passed on PC.
The live browser showed960x720 images, ROI/combined inset and a valid straight
dash path. No drive/reference/arm command was sent during these checks.

Short two-client8s comparisons (stationary scene, not a latency guarantee):
before, about19-21FPS/client and94ms p95 JPEG arrival gaps; capped, about14FPS
and110-125ms p95 gaps. Processing remained about21FPS/~43ms, with camera
delivery around30FPS. Bandwidth fell, but this DOES NOT prove lag was fixed.
No sensor-to-display latency measurement was made. frame_age_seconds is only
age since the last completed processing step; UI now calls it processing age.

Wi-Fi power saving was temporarily disabled with iw (not persisted). Ten ping
samples changed from mean30ms/max57ms to mean6ms/max24ms, no packet loss in
either sample. This is a small uncontrolled network observation, not proof of
the sole cause. Reconnection/reboot may reset the temporary setting.

Offline65-frame threading benchmarks (5 warmups) on the same saved raw frame:
OpenCV4 threads median37.6/37.7ms,1 thread52.3ms,2 threads42.1ms. Image hashes
were identical. Keep the existing4-thread setting; fewer threads were slower.
Evidence and previous-source backups are under ignored outputs/ on the Pi.

A separate earlier continuous-run stop was reproduced offline: a7-point dash
chain extending into a far near-horizontal bend failed inconsistent_dash_chain
with global fit error54.7px against25.6px. Frame age at stop was34ms, so that
specific stop was not the stale-frame guard. This preview work DOES NOT fix it.
Evaluate a bounded local control horizon with independent boundary/road/axis
checks and false-chain regression tests; do not simply disable fit/loss guards.
Fresh straight reference is still required after restart; trial defaults1s.

## Ownership And Provenance

The owner is moving to their own SD. Do not deploy, delete files, stop user tests
or format the borrowed card as part of restoring this snapshot. Runtime sources
and gesture files were read from the Pi, byte-copied and SHA256-verified. They
were NOT inferred from the older PC archive. SOURCE_MANIFEST.json maps each
copied file to its old Pi path and hash. README/requirements/this handoff are new
migration material; the original source handoff is retained under history/.

## What Is Working

- Flask tabs: OpenCV, raw, white dashes, yellow boundary and road. Only the
  OpenCV upper-right inset combines yellow/white lines without road fill.
- Native960x720 camera/media with640x480 analysis, ROI border and thresholds.
- Motor1=left BCM20/21, motor2=right BCM23/24, both forward multipliers+1.
  Servo BCM18; manual A=-105/D=85, neutral command0. Startup initial_angle=None.
- Manual controls detach servo PWM after the configured interval; autonomous
  holds it while steering. Stop disarms DC and detaches PWM; do not force centre.
- Pilot P gain60, heading gain.8, left cap105/right cap85, rate60, basePWM.26.
  These limits supersede the original snapshot's symmetric20 cap. Curve-only
  reduction is removed; limited-path scale remains. Manual startup is.30.
- Single-owner browser control, token validation, .7s lease/deadman, fresh camera
  and path gates, finite trial or explicit continuous mode. Defaults do not arm.
- On3.11 missing Picamera2/libcamera bindings use rpicam-vid MJPEG95. Native
  system3.13 libcamera modules must not be grafted into the3.11 site-packages.

## Known Limits / Next Test

The robot has progressed through multiple bends in user-supervised trials, but
there is no measured full-lap autonomous reliability result. Global curve fits,
short/ambiguous dashed chains, disconnected yellow support and near-road loss
can stop it. Do not relax all failures or continue blindly to hide these stops.
Thin seams/reflection/camera angle can create false candidates. A contour is not
a validated path and road_fraction is not a confidence score.

User reported sharp-turn low-PWM near-stall; curve_scale was raised from.55 to.75.
There are no wheel encoders, physical speed measurements or fully validated motor
trims. Active positive-servo physical direction must be reconfirmed after changes:
earlier stopped-wheel observations did not independently prove active polarity.
Do not invert sign or raise max angle based on an image alone. D was previously
reported right, but hardware was subsequently changed/tested. Reconfirm safely.

Crosswalks, traffic lights, YOLO person detection and gesture-based traffic
decisions are NOT implemented in this new track Flask. Do not describe the old
white-paper dataset/model experiments as this controller's learning method. This
controller is OpenCV heuristics plus P/heading control, not online learning.

## Gesture Reference

gesture_reference/gesture_recognition_module.py and hand_utils.py are unchanged
copies; models/gesture_knn_model.npz is the old Pi model. The module normalizes
21x3 landmarks for30 frames (1890 features), then NumPy KNN(k3), distance threshold30,
minimum detected-hand ratio.6, smoothing and last-label hold1s. MediaPipe Hands is
one-hand/model_complexity0, detection/tracking confidence.6. No YOLO is used here.
This is reference code ONLY, not a Flask tab or a motor-command source.

Its original default model path is /home/pi/gesture_knn_model.npz. On integration,
pass the path to gesture_reference/models/gesture_knn_model.npz explicitly instead
of assuming the old home directory. Check model feature dimension/labels before
use. The user reported false positives from resting hands/holding objects; these
have not been fixed. The KNN distance shown in this reference is a feature-space
distance, NOT a physical pedestrian-distance estimate.

## Restore / Evidence

Use README.md. First validate a new3.11 venv and camera-only Flask. Check GPIO
permissions and pin directions with the owner before arming. Recheck mechanical
neutral and the A/D limits, start with short supervised trials and fresh straight
reference. Preserve all stop/freshness guards. Do not automatically restore a
path reference, prior run owner, armed status or continuous selection.

135 prior tests passed on Pi3.11 and PC. After snapshotting,135 tests passed again
from THIS new folder on PC and the Node pilot-UI contract test passed. All33
copied source/model hashes were rechecked, including a256x1890 float32 KNN
feature matrix and256 labels spanning0/1/2. The3.11 camera test measured30.03FPS,
median26.55ms processing on a floor scene, disarmed with outputs0/PWMoff. It did
not run gesture inference or drive. Camera frame_age is since completed processing,
NOT sensor-to-actuation latency. New lock resolution and PC tests do not prove
fresh ARM installation or hardware operation; validate those on the new SD.

Do not include the old .venv, credentials, live videos or smart_factory in commits.
The old smart_factory and its environment were explicitly left untouched.

Fresh dependency locks were resolved with uv for ARM64/manylinux2.36/Python3.11,
requiring available binary wheels. Core has13 packages; optional gesture set has37.
Only opencv-contrib-python4.11 is installed in that proposed NEW environment;
compatible JAX/JAXLIB0.6.2 replaces the inconsistent old installed0.7.1 pair there.
Nothing was installed/changed in the borrowed SD environment. These are resolved
installation plans, NOT a claim that either fresh environment has been executed.
