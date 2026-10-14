# Auto Driving handoff

Last reviewed: 2026-10-14. Source: local `Steering robot test` folder on the
owner's Windows PC. The Raspberry Pi was off during this GitHub publication,
so the exact deployed Pi revision was **not** verified.

## What was built

1. A camera-driven Flask monitor with raw, OpenCV, and optional gesture views.
2. OpenCV road/line detection in `road_vision.py`, including white-road
   surface checks, dark-line candidates, one-line curve interpretation, and
   safeguards against pairing unrelated line fragments or paper edges.
3. A bounded steering controller in `road_drive_web.py`: P/heading steering,
   manual W/A/S/D controls, independent motor-channel scale controls,
   camera-frame freshness checks, vision-loss stopping, run time limits,
   manual-command timeout, and a Pi CPU temperature shutdown.
4. PC-side manual-driving data collection and offline imitation/hybrid
   comparisons. These experiments did not replace the live OpenCV controller.
5. Regression tests using small saved track images in `test_fixtures/`.

## Current system split

`camera_test.Camera` -> `road_camera_web.Monitor` -> `road_vision.analyze` ->
`road_drive_web.DriveController` -> GPIO Zero motor/servo outputs.

`road_camera_web.Monitor` can separately call `GestureRecognizer` on camera
frames for a displayed label. The gesture label is **not** an input to
`DriveController`; there is no gesture-triggered motor start/stop here.

The core controller has no `imitation_runtime` import and does not learn
online. Treat `manual_dataset/` and training scripts as experimental work,
not as evidence that the present robot is driven by a trained policy.

## Evidence and limitations

- Tests and screenshots showed improved curve recognition and several short
  supervised runs progressing through part of the track. Other runs stopped
  on uncertain one-line detection or low near-road coverage; a continuous
  autonomous lap was not demonstrated.
- Paper seams, track boundaries, thin gray markings, camera vibration, and
  low camera angle caused intermittent or false line detections. A visible
  overlay is not proof that the commanded path is safe.
- The physical left/right identity of motor channels 1 and 2 and the true
  neutral servo angle were not established as universal calibrations. Do not
  replace motor-number labels with left/right labels without a physical test.
- The model/dataset metrics in the older local README were *offline key-state
  agreement*, not autonomous lane-keeping success rates. Those raw sessions
  are intentionally not part of this Git commit.
- `road_drive_web_v2_active.py` from the local workspace was not included:
  the canonical version here is `road_drive_web.py`. Do not silently merge
  an alternate deployed Pi copy over it. Compare and review first.

## Team workflow

1. Pull the latest repository commit. Read root `AGENTS.md`, this file, and
   `README.md`. Keep changes to this folder unless a cross-module change is
   explicitly agreed upon.
2. For vision/control changes, add or update a saved-image regression test.
   Run PC tests before proposing a Pi deployment.
3. Record the commit, camera angle, motor scales, servo calibration, speed,
   trial duration, and observed outcome for each supervised physical test.
4. Separate offline model experiments from the Pi controller. Do not change
   GPIO mapping, steering sign, safety thresholds, or gesture motor behavior
   based solely on a screenshot or offline metric.
5. Keep a human next to the robot with immediate power-off access during
   motion. Confirm clear track and actual wheel direction before each test.
6. Use a branch or PR for shared changes. Do not force-push over another
   teammate's work or overwrite `Lee/`, `Driving test/`, or `Dataset Project/`.

## Next work

- Reconcile this PC snapshot with the current Pi copy once the Pi is on.
- Build a time-aligned record of raw camera frames, recognition readings,
  steering commands, and actual robot position for failures at curves.
- Validate detection and stop behavior on held-out off-track/seam cases
  before loosening any stop threshold or extending trial duration.
- If gesture control is added later, specify the state machine and make
  `stop` higher priority than `go`; test without motor power first.
