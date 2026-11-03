# Fresh Track Snapshot Retest: 2026-10-20 21:33 KST

## 추가 작업: 비교 페이지 한글화

- 제목, 검출 상태, 표의 항목, 처리 단계, 결과 해석 설명을 한국어로 변경.
- 영문 합성 사진 대신 개별 결과 이미지와 한글 설명을 페이지에 표시.
- 기존 원본과 report.json 측정값은 그대로 보존. 단계 이미지 재생성 시
  원본 해시와 검출값이 기존 기록과 동일함을 확인.
- 5002 페이지 반영 및 브라우저 확인 완료. PC/Pi 테스트 각각 305개 통과.
- 5001 카메라 서버, 인식·주행 설정, 모터 상태는 변경하지 않음.
- 파이 백업: outputs/comparison_korean_backup_20261020T124522Z/.
- 이전 비교 파일 삭제가 차단된 상태는 그대로이며 삭제 완료를 의미하지 않음.

Owner clarified deletion scope: previous comparison photos/results ONLY, not
runtime perception code or original track recordings. Local recursive removal
of the four allowlisted comparison directories was rejected by the execution
tool BEFORE execution. No old comparison files were deleted on PC or Pi.
Do not claim cleanup succeeded or work around that tool-policy restriction.
Code, backups, original captures/photos and captures/runs remain preserved.

Old static-report server PID2088 was stopped after verifying its exact command.
The previous desk report is no longer served on port5002, but remains on disk.
User was informed that deleting reports cannot change the live algorithm:
track_web.py processes live camera input and does not read comparison reports.

## New Evidence And Runtime

Paused camera-only Flask PID2142, captured six NEW stationary track frames
under the shared camera lock, then restored the exact camera-only command.
No GPIO, manual/autonomous activation, code or tuning changes occurred.
Camera:960x720, requested30FPS, observed delivery30.0FPS, rotation180.
Two-second warmup, roughly0.5seconds between captures.

New raw frames/metadata on Pi:
captures/comparison_retest_20261020T123345Z/

New report on Pi:
outputs/hough_track_retest_20261020T123345Z/

Current live Flask: http://192.168.137.60:5001/ PID2663, hardware disabled.
Fresh saved report: http://192.168.137.60:5002/ PID2877.
The latter is NOT live Hough; existing Flask recognition remains unchanged.
Both URLs checked from PC; report HTTP200 and camera_online=true.

## Comparison

Six fresh track images,9 Hough profiles: max sides640/480/320, blur0/3/5.
Baseline current pipeline640/.20 matches the live resolution and crop.
No reference calibration, lap mode or boundary-guidance mode was supplied.
All6 baseline path predictions were valid but reference_set=false; this is
NOT permission/readiness to drive. All9 Hough profiles produced two image-side
groups on all6 frames; counts are NOT accuracy or proof of distinct boundaries.

The current view includes near white dashes, yellow boundaries, a distant
curve and substantial near-road reflection. Visual overlays/stages checked.
No label ground truth, temporal moving test, curve control or lap was tested.
The camera-only Flask ran concurrently with offline comparison, so timing is
not an isolated benchmark or live control/preview FPS. OpenCV threads=2 was
used only for the capture/comparison processes. Existing Flask settings stayed.
The earlier manual-control stop fault remains unresolved.
