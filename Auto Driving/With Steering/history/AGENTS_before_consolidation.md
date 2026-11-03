# Dated Pi snapshot: 2026-10-18

Read README.md and HANDOFF.md before modifying or running hardware.

- Newest owner request: Flask OFF. Sent SIGTERM only to verified track_web.py
  PID1985; process exited, port5001 closed, no rpicam/libcamera video process.
  Keep Flask OFF until requested. Pi remains ON. Diagnostic patch below remains
  PC-only; shutdown request was not approval to deploy or resume testing.

- Newest 2026-10-21: investigating intermittent manual-only stop while video
  continues. Owner power-cycled Pi; restarted full Flask as PID1985/5001.
  Direct manual UI and angle controls remain deployed. New stop-source logging
  in manual_drive.py/track_web.py/static/manual.js plus tests is PC-ONLY,332
  Python/seven Node suites passed. Deployment ABORTED BEFORE edits/shutdown:
  owner is actively driving. Do not restart until stopped and confirmed.
  HTTP samples during driving46..388ms; no observed450ms timeout yet. Cause is
  unproven. Keep450ms client/700ms server limits; no agent motion. See HANDOFF.

- Latest 2026-10-21 20:55: owner requested Flask ON and no manual enable toggle.
  Pi .60 now runs track_web.py PID5309/5001 with manual/auto/gesture panels.
  PC-only manual-angle changes below ARE NOW DEPLOYED with direct manual input.
  Only a fresh W/S/A/D or direction-button press in the visible manual panel
  acquires control; loading/refresh/timers/sliders never arm. Key release stops
  corresponding output. Stop/blur/tab-hide/lease faults clear inputs and late
  arm/input replies cannot revive them. Keep server ownership/leases/watchdog.
  PC/Pi331 Python tests and seven PC Node suites pass; fake browser tested.
  Real Pi restart verified disarmed, outputs0, PWMoff, motor_write_count0.
  No agent motion. Backup outputs/manual_direct_20261021_205242/.
  Unresponsive-stop root cause remains unresolved; do not claim this fixes it.

- Latest 2026-10-21 PC-only manual steering update: owner confirmed Pi is OFF.
  Do not reconnect/start hardware until requested. Last Flask PID1887 and camera
  child1892 were stopped; port5001 closed before the owner powered down.
  Manual panel now has independent A/D magnitudes under `수동 조향 설정`.
  Bounds remain A=-105/D=85; auto steering limits, motor speed and trims unchanged.
  Sliders lock while movement keys are held; no arm/motion from slider input.
  Values persist only in server memory after accepted input, not across restart.
  PC331 Python tests, seven Node suites and fake-GPIO desktop/mobile browser tests
  pass. Not deployed or physically tested; manual stop fault remains unresolved.
  Read the latest HANDOFF for deployment files and performance limitations.

- 최신2026-10-21 01:53: 횡단보도 원근/ROI 잘림 보완. crosswalk.py의 새
  가로 행 묶음은4개 이상 서로 다른 흰 영역, 폭/간격/높이 지속/기준점 포함을
  검사한다. 기존 평행 막대 검출도 보존. 확인된 줄무늬는 조향 점선에서 제외.
  횡단보도 모드 ON일 때만 연속 신선 프레임 확인 후 근거리70%까지 기다리지
  않고 정지 조건을 만든다. 레고 감지는 구현하지 않았고 사용자가 생략 허용.
  현재 범위는 횡단보도->정지->실제 손 제스처. GO3초/STOP해제5초/무인3초
  시나리오 타이머는 아직 구현하지 않음; 기존 새 GO5프레임/0.5초 gate 유지.
  PC/Pi324 테스트 통과, 이전8장 경로 결과 불변, 실패/현재2장 점선 연결 복원.
  PID31297/5001, 모든 사용자 주행 설정 보존, 모터0/0·disarmed·PWMoff.
  중앙 기준 없음. 정지 실측12회 모두 횡단보도5개/안정/정지조건/경로 유효.
  제스처 동시 도로 처리13.8~14.8FPS. 실제 주행/정차 거리 검증은 하지 않음.
  백업 outputs/crosswalk_fix_20261021/. 정지 먹통 원인은 여전히 미해결.

- 최신2026-10-21 01:16: 열린 노란 경계 때문에 도로/바깥 흰 바닥이 한 영역으로
  묶여 노면70% 조건에서 통째로 탈락하는 문제를 track_vision.py에서 보완.
  기존 승인 노면은 유지. 탈락 영역의 실제 어두운 연결부에 양쪽 노란 경계가
  6행 이상·영상높이20% 이상 지지할 때만 복원하며, 흰 점선은 어두운 노면
  둘레85%·색/크기/형상 조건으로 복원. 전체영역 임계값을 낮춘 것이 아님.
  PC/Pi318 테스트 통과. 이전8장 노면 마스크/경로 유효 여부/방향 불변.
  현재 정지 사진 점선0->5, 파이12회 관측 모두 유효 좌회전. 주행 검증 아님.
  PID15240/5001, 제스처 ON, 수동0.28/자율0.27, 사용자 변경 좌100/우80 및
  boundary_guidance=true 보존. 모터0/0·disarmed·PWMoff·중앙 기준 없음.
  카메라30FPS, 제스처 동시 도로 처리18.6~20.3FPS 관측. 30고정으로 말하지 말 것.
  백업 outputs/open_road_fix_20261021_011550/. 수동 정지 먹통은 여전히 미해결.

- 최신2026-10-21 00:49: 재부팅 후 사용자 요청으로 수동/자율 탭과 제스처를
  함께 켬. PID1867/5001, --gesture 추가, 카메라/전송상한30·분석544 유지.
  제스처 초기화·추론 및 두 GIF HTTP200 확인. 수동 출력0.30, 자율0.27,
  완주/연속/복구 ON 유지. armed=false, 모터0/0, PWMoff, 주행 명령 없음.
  제스처는 수동제어 활성화 중 기존 방식대로 일시중지됨. 정지 먹통 미해결.
  아래 제스처 OFF 실행 상태는 이 사용자 요청으로 대체됨.

- 최신2026-10-21 00:03 이후: 사용자 요청으로 제스처 실행 OFF, 파일/GIF는 보존.
  Flask PID43588/5001, 원본960x720/30FPS, 분석544x408, 전송상한30.
  수동/자율 탭 유지, armed=false/모터0/0. 중앙 기준 없음, 주행 명령 없음.
  기존480 분석은 과거 직선1장에 회귀가 있어 채택하지 않음. 544는 비교8장
  유효/무효 및 방향이640과 같았으나 주행 안정성/모든 장면 동일성을 보장하지 않음.
  JPEG 디코드를 수신 스레드로 이동, 수신시각·최신1장·오류/정지 차단 유지.
  전송 대기시간에 JPEG 압축시간을 포함. PC/Pi311 테스트 통과.
  실측: 영상 수신 중 도로27.5~29.1FPS, MJPEG26.75FPS, 카메라30.0~30.1.
  모두 고정30FPS 달성으로 설명하지 말 것. 완주/연속/복구 ON, speed0.27은
  이번 작업 전 사용자가 바꾼 실행 설정을 보존한 것. 제스처를 임의로 다시 켜지 말 것.

- 최신23:29 KST: 감독2초 시험은 약0.68초에 반사 조각 시작점 오검출로 정지.
  사용자는 거의 안 움직였고 검은 노면 안이라고 확인. 실패 PNG 재현 후
  lane_path.py 근거리 반사 필터 보완, PC/Pi308 테스트 통과 및 배포.
  새 예외는 완주 모드+보정 기준+정렬된 앞쪽 점선3개+현재 연결 경계8개+
  근거리 노면90%가 필요하다. 안전장치 및 기존 음성 테스트 유지.
  Flask PID37736/5001, 수동/자율/제스처 유지, 모터0/0·disarmed·PWMoff.
  lap_mode/continuous ON, Kp35/heading1/speed0.30; 복구/경계추가조향/횡단보도 OFF.
  재시작으로 중앙 기준 없음. 다음 주행은 직선 배치·보정·감독 준비 재확인.
  코너 짧은 간격 보완은 원래 완주 모드에 있었음. Canny/Hough는 여전히
  비교 전용. 단일 PNG 개선을 완주나 정지 먹통 해결로 설명하지 말 것.

- 최신 초록 GIF: 사용자 첨부 smooth_flipped (1).gif로 vehicle_stop_green.gif 교체.
  파이 반영 및 HTTP 응답 해시 일치 확인. 1050x450, 8프레임, 960ms 무한 반복.
  STOP=초록/GO=빨강 유지, PID4678 재시작이나 주행 설정 변경 없음.

- 최신 22:04 KST: 사용자 요청으로 수동/자율주행 탭 복원. PID1861을 정상 종료,
  PID4678/5001에 --manual --motor-wiring-confirmed --autonomous --pilot-speed 0.30
  추가 실행. --gesture와 요청30FPS 유지. GPIO는 열려 있지만 armed=false,
  auto active=false, 모터 출력0/0, 서보PWM 꺼짐 확인. 주행 명령은 보내지 않음.
  사용자는 오래 사용한 것이 원인이라고 전달했지만 정지 먹통 원인은 검증되지
  않았음. 안전장치 유지, 원격 주행을 새로 허가받은 것으로 해석하지 말 것.

- 최신 21:58 KST: 핫스팟/파이 재부팅 후 사용자 요청으로 제스처 미리보기 실행.
  파이 .60의 track_web.py PID1861/5001, --gesture --fps 30 --preview-fps 30.
  hardware_enabled=false, autonomous_panel=false. 제스처 추론과 GIF HTTP200
  확인. 손 미검출 상태이며 실제 GO/STOP 시연 성공으로 해석하지 말 것.
  5002 비교 서버는 재부팅으로 종료됐으며 이번에는 다시 켜지 않음.

- 최신 한글화: compare_vision.py의 비교 화면을 한국어로 변경해 파이에 반영.
  5002는 저장 사진 비교이며 실시간 허프 인식이 아님. 5001과 모터 설정은
  변경하지 않음. 기존 report.json 측정값 보존, PC/Pi 테스트 각각 305개 통과.
  상세 기록은 COMPARISON_RETEST_20261020.md의 한글화 항목 참조.

- LATEST21:33KST fresh track retest: camera-only Flask now PID2663/5001;
  saved NEW comparison report PID2877/5002. Old PID2142/2088 are stopped.
  Six fresh track frames,9 Hough profiles; no runtime algorithm/tuning change
  or motor command. Read COMPARISON_RETEST_20261020.md. Owner requested old
  comparison-file deletion only, but tool policy rejected deletion BEFORE
  execution. No old PC/Pi comparison files were deleted; do not claim otherwise.

- LATEST21:27KST: owner explicitly requested Flask ON after the desk-only check.
  track_web.py is running CAMERA-ONLY on5001, PID2142, Python3.11, without
  --manual/--autonomous/--gesture. Hardware disabled; no GPIO/motion commands.
  This supersedes the older blanket Flask-OFF runtime status, NOT the unresolved
  manual-stop fault or the need for fresh supervised readiness before motion.
  Port5002 still serves saved comparison snapshots, not live Hough. No runtime
  code changed and Hough is NOT integrated into the live Flask pipeline.

- NEW Pi desk-only checkpoint: owner requested connection then explicitly chose
  desk execution checks, not track motion. Comparison files uploaded to .60;
  Pi304 tests pass. Camera captured6 static desk frames and is now OFF.
  Only saved-report HTTP server port5002/PID2088 is running, NOT live Flask.
  Read COMPARISON_RUN_20261020.md. No motor access, drive tuning or track test.
  This supersedes the PC-only/not-deployed status below for comparison files.

- NEW2026-10-20 offline comparison: hough_vision.py and compare_vision.py are
  PC-only experiments, NOT imported into Flask/control and NOT deployed to Pi.
  Same raw inputs compare current segmentation/path with HSV/blur/Canny/Hough.
  A two-sided image grouping is NOT proof of two lane boundaries; a single
  curved edge can enter both groups. Never use these outputs to command motion.
  Missing lines yield no target; PDF BEV geometry is not physically calibrated.
  PC304 tests pass. Generated reports and limitations are in the latest
  HANDOFF. Preserve existing runtime and the Flask-OFF instruction below.

- GIF display checkpoint: below camera/capture toolbar, titled 디스플레이.
  Colours address the PEDESTRIAN: vehicle GO -> RED stop_blink.gif; vehicle
  STOP -> GREEN smooth_flipped.gif. Do NOT reverse this to conventional vehicle
  light colours. Read-only display does not confirm a stopped car or authorize
  crossing. GIFs and UI deployed; PC/Pi288 tests pass; six Node suites pass.
  Pi Flask remains OFF. Local browser fixture was synthetic, now stopped.
  On a later explicit start for this feature include --gesture with existing
  full driving/capture flags; no automatic arming or crosswalk-control change.
- NEWEST: owner requested Flask OFF; PID14758 stopped and port5001 verified
  closed. Keep it off. Lossless failure PNGs, frame-used settings/reference-
  heading metadata and replay_path.py are now uploaded to Pi with hashes and
  backup_lossless_review_20261020_003611. PC/Pi285 tests pass. No server restart,
  perception/control tuning or motion occurred during this deployment.
  A JPEG replay of140903 differs from its exact failure log: raw PNG evidence
  is needed before claiming a threshold fix. The stop-path fault remains open.
- URGENT 2026-10-20 manual-control fault: owner CLARIFIED that stopping Flask
  DOES stop the wheels. Maximum-speed/unresponsive behavior is reported DURING
  Flask operation, NOT after shutdown. The earlier floating-input diagnosis was
  unsupported and must not be repeated as fact. Off-state BCM20/21/23/24 were
  input/no-pull/LOW and were set output LOW; this does not establish causation.
  Keep Flask OFF while reviewing input delivery, command state and motor PWM.
  No autonomous/agent motion or energized reproduction without fresh supervised
  readiness. No encoder, current or motor-temperature sensing is available.
  A software speed fraction is NOT a measured physical wheel speed.
- NEW compact-panel checkpoint supersedes the owner-away paragraph below:
  supervised140130/140343/140427/140902 trials ended stopped; no completed lap.
  Current task is manual-video UI, NOT authorization for more agent motion.
  Manual/autonomous tabs release this browser's owned control on switching,
  never arm or start. Preserve command-key logging and raw-video separation.
  Preview30FPS is independent of recording10FPS/120s. HUD values are sampled
  software commands, NOT actual wheel angle/speed or exposure synchronization.
- NEW22:56 checkpoint: --boundary-guidance is explicit and requires lap mode
  plus heading gain>=.25. It combines CURRENT white and yellow image direction,
  not a cached/boundary-only width planner. Its near-paint fallback may use
  .40.. .90H ONLY with strong visible white paint, current>=8 connected edge
  probes and near road>=.90. Keep all freshness/owner/lease/rate/output caps.
- Straight boundary convergence in perspective must NOT initiate steering;
  only corroborate a white bend>=12deg. Mode stamps prevent starting on an old
  model's frame. A single-mark fallback cannot calibrate or renew recovery.
- Owner is away for20minutes. No motion was authorized for that unattended
  period. Latest server PID32273 is disarmed with no central reference, motors0
  and PWMoff. Obtain fresh return/placement/stop readiness BEFORE ANY movement.
  See the newest HANDOFF section; old trial readiness is not current permission.

- This folder is the NEW black/yellow/white track project, copied from the
  deployed Pi, NOT Auto Driving/ or Auto Driving@/. Do not merge old controllers.
- Flask, OpenCV, GPIO and future MediaPipe integration MUST use Python 3.11.
  Install a fresh local .venv on the owner's NEW SD. The old external interpreter
  directory is historical; no dependence on that old folder is required here.
- Start camera-only first. Hardware is opt-in. Never start motion to validate a
  migration, upload, unit test or server startup. New readiness is required.
- motor1 LEFT BCM20/21; motor2 RIGHT BCM23/24; forward multiplier +1 for BOTH.
  These were physically confirmed for this new robot and supersede old wiring
  polarity notes in root handoff files. Servo BCM18, A=-105, D=85. Values are
  servo command units, not measured wheel angles. Reconfirm after reassembly.
- Keep disarmed startup, detached servo PWM, camera/path freshness, ownership,
  browser lease, hardware deadman, bounded angle/rate and all stop guards.
  Continuous mode removes only the elapsed trial deadline, not these guards.
- Keep defaults manual=.30 and pilot=.26. The owner explicitly restored curve
  slowdown after the no-braking test: curve_scale=.85 (range.75..1), plus the
  independent .8 limited-path cap. Never restore the old near-stalling .55.
- Turn mode persists until >=3 distinct fresh straight frames span >=.3s with
  heading<5, wanted<4 and actual command<6. It never freezes the servo command
  or bypasses invalid/stale-path stops. New opposite bends may switch directly.
- PilotConfig.turn_recovery is OFF by default. Its explicit missing-dash
  exception requires current road/connected-boundary corroboration of the last
  curve, a distinct source frame and a nonrenewable <=.20s budget. Never use it
  for ambiguity, unexplained jumps, stale camera, straight paths or a stop fault.
  Full fresh evidence>=3 frames/0.30s is needed to renew an episode. Recovery
  preserves the last validated command and may not raise its speed.
- Source receipt/retrieval-start timestamp now participates in control age.
  This is NOT sensor exposure time or a full end-to-end latency measurement.
- --gesture enables a latest-only worker and sixth preview tab; it opens no
  second camera. Inference pauses during motion except the zero-output crossing
  wait. PilotConfig.crosswalk_gesture is OFF by default and needs initialized
  gesture worker plus supervised continuous mode. A new30-frame wait epoch,
  unsmoothed current KNN decisions, visible hand and >=5 fresh GO results over
  >=.5s are required. Never authorize from display_label or held/smoothed raw.
- Crossing pause keeps the SAME owner's lease but commands motors0 and detaches
  servo. GO cannot arm, steal ownership, bypass lane validation or revive any
  stop. ManualDrive remains the only GPIO writer. Unknown/error remains stopped.
- Crosswalk shape/stop depth and gesture false positives are NOT physically
  calibrated yet. All added control modes must stay opt-in until supervised
  testing; unit tests are not proof of pedestrian intent or a successful lap.
- Every ManualDrive input/follow/pause dispatch checks lease/deadline before
  GPIO, even if the watchdog thread has not polled yet. A late command cannot
  renew an expired lease. Do not remove this guard to make a timeout disappear.
- Runtime accepts --pilot-speed0.10..0.30 (default0.26); explicit0.30 is the
  owner's last test selection. It does not change caps, arm or enable new flags.
- Pilot now uses separate max_left_angle=105 and max_right_angle=85, bounded
  by the confirmed hardware A/D limits. Do not restore the historical +/-20 cap.
  Normal entry rate stays60. Explicit lap_mode may unwind toward neutral at
  min(120,2*rate), never jumping across zero into the opposite turn in one tick.
  Do not interpret command units as measured wheel angles.
- Path association filters tiny near seam candidates. A failed far/global fit
  may use separately corroborated near centres, NOT an average of all lanes.
  A single long mark requires prior reference, observed target/axis, road and
  matching yellow boundary; no blind single-dot or cached-path driving.
- White repair may add only observed bright/low-saturation road pixels in a
  colour component with >=25% contrast seeds and unchanged shape/fill checks.
  Bottom-clipped paint at depth>=.80 may use the existing maximum near-area
  cap .014*image_area; do not raise the global cap or lower fill .60 blindly.
- Oblique two-dash spans may be compressed to .08H only with chord>=.20H,
  observed target-depth support, aligned paint, near road>=.90 and >=8 connected
  matching boundary samples. Preserve all negative tests for this exception.
- Camera source uses Picamera2 when available and OS rpicam-vid otherwise.
  The 3.11 venv must NOT import system3.13 native libcamera binaries via PYTHONPATH.
- Current camera is OV5647 Rev1.3, NOT IMX219. Do not force IMX219 sensor mode.
  Capture960x720, analysis640x480, requested30FPS; no speed/accuracy guarantee.
- --analysis-max-side480 is an opt-in480x360 lane-analysis speed profile; default
  remains640. Native capture/preview detail stays960x720. Do not silently lower
  resolution or claim unchanged far-paint accuracy. Recalibrate after restart.
- Owner now prioritizes a full lap over first-lane centre precision; both lanes
  inside yellow boundaries are allowed. --lap-mode is explicit, continuous and
  disarmed at startup; Kp35/heading1.0, soft error band.12, bounded recovery.
  It is NOT blind invalid-path turning or an automatic verified-lap counter.
  Side-clipped white fragments cannot anchor a dash chain. Completion mode may
  independently validate near centres after an inconsistent far fit, but paint
  tangents, fresh near road and connected yellow-edge checks are NOT waived.
- Completion-only observed polylines require3..10 aligned paint centres, coherent
  local turns, current near road and9 path-normal edge probes. No extrapolated
  polyline target is allowed. Tiny5x5 closing links edge component IDs only;
  ray-hit evidence still comes from original yellow pixels. Large edge gaps,
  ambiguous chains and uncorroborated paths still stop. The recovery episode
  remains nonrenewable<=.20s and uses fresh masks for the same previous corridor.
- Later supervised lap fixes may accept shallow path-normal evidence and an
  observed-row corridor with>=8 connected edge probes, current road between
  paint/edge, bounded observed geometry and aligned paint. Yellow probe endpoints
  must be road-facing edges, not centres of wide projected yellow paint.
- Completion near-road checks may bridge narrow yellow ONLY when independently
  classified road exists on BOTH sides. Never treat outer yellow/floor as road.
- A target-band near fit must retain connected edge evidence at the original
  nearest depth; cropping cannot hide a broken boundary. Strong side-clipped
  paint needs>=2 intact aligned forward marks PLUS independent corridor proof;
  small/bottom-corner fragments still cannot anchor a chain.
- Explicit /auto/restore requires recent matching saved straight calibration and
  stopped-run evidence, exact unchanged camera settings, disarmed lap mode and
  fresh stable observations. It never starts motion. A later manual neutral or
  steering command overrides the remembered command. Owner clarified the wheels
  stayed within the adjacent allowed lane, NOT white floor. See HANDOFF.md for
  the latest replacement/readiness request before starting the next trial.
- supervised_lap_client.py is an opt-in external-PC trial tool, NOT a Pi daemon.
  It needs --ready, a bounded observation window, PC heartbeats and finally-stop;
  never remove its robot-self-connection rejection or auto-retry a fault.
  Its heartbeat worker has a separate bounded PC deadline so status polling
  cannot starve the lease. Any transport fault stops; it never revives a pilot.
- Short-span completion targets must lie within observed paint and .40.. .70H.
  Keep independent boundary>=8, aligned paint and near-road>=.90 requirements.
  A seven-sample row result must not hide a valid nine-normal result: callers
  state minimum_samples, retaining normal corridor and strict-mode checks.
  Boundary-only path generation is NOT implemented at the22:36 checkpoint.
  See the newest HANDOFF section, not the older pending-placement paragraph.
- Completion-only oblique single-paint support must remain single_dash_boundary
  (no calibration/recovery renewal), using actual observed endpoints, strict
  shape/current edge/near-road checks and the existing.8 speed cap. An observed
  paint-supported target beyond a centre still needs current paint pixels and
  newly validated SAME connected yellow component; at most3 corridor retries.
  Keep the .40.. .70H target window; do not treat these exceptions as a general
  yellow-only curve controller. Obtain post-trial footprint feedback before
  continuing after the latest133429 stop.
- gesture_reference/ source/model is preserved unchanged. gesture_adapter.py
  optionally wraps it in track_web.py; integration code is not a proven physical
  demonstration. Do not modify the preserved model/source casually.
- SOURCE_MANIFEST.json records exact original source/model hashes. New docs,
  launchers and dependency files are migration additions, not Pi-proven changes.
- Do not stage raw captures, credentials, venvs, smart_factory, other people's
  edits or any other project. Do not delete/reformat the borrowed SD.
- Run `python -B -m unittest discover -p 'test_*.py'` in this folder after edits.
  Historical notes under history/ do not override this file or HANDOFF.md.
