# Auto Driving 20261018

Python 3.11 snapshot of the NEW track robot, saved before moving from a borrowed
SD card to the owner's new OS installation. This is NOT the older white-paper
road controller in `Auto Driving/` or the teammate snapshot in `Auto Driving@/`.

## Entry Point

`track_web.py` is the Flask application. Without flags it shows camera/vision
only. Manual control and the autonomous panel are deliberately opt-in:

```bash
cd "$HOME/Capstone-Design/Auto Driving 20261018"
./.venv/bin/python -B track_web.py --manual --motor-wiring-confirmed --autonomous --port 5001
```

Open `http://<new-pi-ip>:5001/`. Starting the server does NOT arm or move motors.
The `--motor-wiring-confirmed` flag must only be used after checking the wiring
on the actual reassembled robot. A fresh straight-path reference is needed for
autonomous driving after every restart. Bare IDE "Run Python File" launches the
camera-only mode; missing driving panels do not mean this is an old file.

The earlier `/home/pi/steering_robot_drive_eval_20261012/.venv/bin/python` path
was a shared interpreter on the old SD, NOT a requirement of this source tree.
On the new SD use this folder's `.venv`. Do not copy an old venv or replace the
OS Python: native packages and script shebangs must be installed afresh.

## Included

### Road-Only 30 FPS Target (2026-10-21)

The current speed profile omits `--gesture` without deleting gesture files.
Capture stays960x720; `--analysis-max-side 544` selects544x408 analysis.
`--fps 30 --preview-fps 30` request30FPS camera input and cap preview at30FPS.
JPEG decode now runs on the camera receipt thread and preserves that receipt
timestamp; preview encoding is included in its frame-time budget.

The measured stationary result with one PC MJPEG reader was camera30.0..30.1FPS,
vision27.5..29.1FPS and received preview26.75FPS. This is NOT a fixed30FPS
guarantee or a driving test. Lower analysis resolution can change small-paint
detection. Current544 and640 profiles agreed on eight reviewed stills, whereas
480 introduced one extra failure, so480 was not selected for this session.
Motor/steering settings, ownership and stale-frame stops remain unchanged.
Recalibrate on a supervised straight placement after restarting or changing
camera settings. The manual/autonomous controls are still opt-in and disarmed
at startup. See HANDOFF.md for the exact latest runtime settings.

### Offline Canny / Hough Comparison (2026-10-20)

Pi desk execution/deployment checkpoint: [COMPARISON_RUN_20261020.md](COMPARISON_RUN_20261020.md).
The port5002 page is a saved report, not live Flask or a driving interface.

`hough_vision.py` and `compare_vision.py` are NEW, separate experiments.
They are not imported by Flask or the autonomous controller. Existing runtime
perception, camera configuration, gesture code and motor settings are unchanged.
No server or hardware is accessed. Do not replace the driving pipeline with
this experiment based on segment counts.

The experiment resizes/crops the original BGR image, extracts HSV yellow
(`20,100,100` to `40,255,255`), applies optional Gaussian blur to that MASK,
runs Canny50/150, polygon ROI, optional perspective transform and HoughLinesP.
It groups segment endpoints by image half and calculates their midpoint.
Missing either side produces NO midpoint/error, never a default straight target.
`two_sided_observation` means two IMAGE-SIDE groups, not two verified boundaries;
even two groups never authorize driving. A single curved edge can cross both
halves. This reproduces the teaching example's endpoint-mean limitation without
silently substituting image edges when detection fails.

Run with Python3.11 containing OpenCV and NumPy, from this folder:

```bash
python -B compare_vision.py captures/photos/photo_TIMESTAMP_raw.png --output outputs/hough_RUN --sizes 480 320 --blurs 0 3 5
```

Use a NEW output directory each time. Open its `index.html` directly; Flask is
not needed. It shows the original, current pipeline and six Hough profiles,
intermediate masks/edges, PC timings and JSON evidence with file/code hashes.
The current baseline uses the largest requested analysis size and the same
crop-top setting, not necessarily the live robot's configuration. Add actual
saved `--reference`, `--reference-heading`, `--lap-mode --boundary-guidance`
settings when comparing a prior run. Without a reference, current paths may be
unavailable; the report does not invent a calibration.

Default crop top=.20 retains more near/far evidence than the textbook example.
Perspective is OFF by default because physical camera geometry is uncalibrated.
For a separate literal geometry comparison:

```bash
python -B compare_vision.py captures/photos/photo_TIMESTAMP_raw.png --output outputs/hough_PDF_RUN --sizes 320 --blurs 5 --textbook-geometry
```

This uses crop top=.50 and the PDF trapezoid mapped to a rectangular view.
It is an example, NOT a camera calibration. Alternatively `--geometry-file`
accepts exactly `roi_top`, `polygon` (four normalized crop coordinates ordered
bottom-left, top-left, top-right, bottom-right) and boolean `bird_eye`.
`--colour white` / `both` are explicit experiments, not road-validated masks.

Saved `*_raw.mp4` or `*_raw.avi` can be sampled with `--sample-seconds .5
--max-frames 40` (limit per video). Each sampled frame resets history; this is
not a temporal control replay. Screens/overlays must not be renamed to raw.
Timings exclude decode/render/file IO, but the two pipelines perform different
work: current validates a path; Hough only groups lines. PC timings are not Pi
FPS. JPEG artifacts, broad glare, curve geometry and unknown lane identity
remain limitations. Blur does not establish immunity to light reflections.

### Pedestrian GIF Display

The fixed-aspect `디스플레이` box below the camera/capture toolbar displays
the owner's original GIFs with PEDESTRIAN-facing colours:
- Vehicle `go` decision -> RED `static/signals/vehicle_go_red.gif`, copied
  unchanged from `stop_blink.gif`: pedestrian waits while vehicle is requested to go.
- Vehicle `stop` decision -> GREEN `static/signals/vehicle_stop_green.gif`,
  copied unchanged from `smooth_flipped.gif`: vehicle stop request recognized.

This is recognition feedback, NOT confirmation of a stopped vehicle or a safe
crossing authorization. No KNN/model, gesture decision, crossing gate or motor
behavior was changed. Use the existing explicit `--gesture` flag to enable the
worker. Without it, the box says `제스처 미사용`. The existing worker pauses
gesture inference during ordinary motion; this display does not bypass that.

GIF playback is native in the browser, not decoded/composited by the Pi.
`/gesture/status` reads only the existing worker snapshot. Fresh ready decisions
with a visible hand select GIFs; unknown/off/error hides them. Repeated identical
decisions do not restart the animation. A browser-side500ms expiry also hides
signals when updates stop; this does not alter the worker/control200ms freshness
requirements. Hidden pages pause display polling and unload the GIF.
The GIF is a webpage element, not part of saved raw/OpenCV camera MP4s; a screen
recording can include it. Existing camera/control tabs and capture controls stay.

### Offline Failure Review (2026-10-20)

Automatic autonomous failure diagnostics now save `_raw.png` losslessly after
commanding motor stop; the processed companion remains JPEG. Ordinary photo
buttons and paired MP4 recording keep their existing formats/rates. PNG means
the captured, oriented BGR pixels are preserved without another lossy encode;
it is NOT sensor RAW. Failure observations/recording metadata also carry the
settings of the published frame, not a pending UI edit. Invalid path packets
retain the reference heading so that rejection cases can be reproduced.

`replay_path.py` runs the current segmentation/path code on named raw stills
without Flask, network, GPIO or motor access:

```bash
python -B replay_path.py captures/photos/photo_TIMESTAMP_raw.png --output outputs/replay_TIMESTAMP --reference 0.5 --reference-heading 0 --lap-mode --boundary-guidance
```

Use the actual frame's settings/reference, not the example values above. Saved
Flask raw frames are already oriented; do not rotate them a second time. Each
still resets temporal path history. The JSON report contains source/code hashes,
markings, baseline/selected predictions and precise rejection checks, plus PNG
review overlays. Counts are NOT accuracy, a temporal lap test or evidence the
robot is safe to drive. Screen recordings/processed filenames are rejected;
renaming an overlaid frame does not turn it into raw input. Existing JPEG stills
can be reviewed, but compression may change their classification. No thresholds,
steering, speed, guard or manual-control behavior changed in this revision.

### Compact Driving Panels And Recording Commands

The driving panel opens on `수동주행`; `자율주행` has its own tab. Camera
statistics, detection settings, motor trims and pilot tuning remain available
in collapsed sections. Switching control tabs releases this browser's owned
controller; it never arms or starts another controller. The sticky header stop
remains available while hardware is armed, including when details are collapsed.

Manual driving needs no enable toggle: a fresh W/A/S/D or direction-button press
in the visible manual tab requests guarded control. Opening the page never
starts motion. Release keys to remove their commands; stop, tab change, loss of
focus or expired connection releases control. After a stop, press again rather
than continuing to hold a key. Server ownership and safety guards remain active.

`수동 조향 설정` provides independent A/D steering magnitudes, bounded by the
hardware commands A=-105 and D=85. Set them with driving keys released, then
use A/D normally. Slider edits do not arm or move the robot; sliders lock while
a driving key is held. Releasing A/D returns command0. These settings do not
change autonomous limits, speed or motor trims. Accepted values are kept in
server memory only; restart restores defaults. Command degrees are not measured
wheel angles. These additions were deployed to Pi on 2026-10-21 after PC/Pi
tests and fake-GPIO browser checks; actual physical driving was not tested.

Preview defaults to30FPS, independent of camera/analysis delivery. Recording
remains10FPS with the existing120-second cap. `녹화 시작` saves camera frames,
NOT the web page or its controller widget. The paired `_opencv.mp4` now contains
a small upper-left HUD with accepted W/A/S/D state, steering command and left/
right motor output commands. `_raw.mp4` remains unannotated. The paired JSONL
contains `control.keys`, `command_sequence` and `control_observed_at` for each
recorded frame. These are software commands sampled during frame processing,
not encoder measurements, actual wheel angles or sensor-exposure synchronization.

Files remain under `captures/videos/` and are listed in `저장 파일`.

- Current Pi runtime, Flask HTML/JS/icons, synthetic regression tests.
- OpenCV yellow-boundary/white-dash/road segmentation and guarded path tracking.
- Manual W/A/S/D, independent motor trims, opt-in P/heading autonomous pilot.
- Finite trial, opt-in continuous mode, curve slowdown and limited-path output cap.
- Photo/paired-video capture under `captures/`, which is excluded from Git.
- Preserved gesture source and KNN model under `gesture_reference/`; optional
  latest-only preview and supervised crosswalk stop/go adapter via `--gesture`.
- Exact Pi source SHA256s in `SOURCE_MANIFEST.json` and installed-package
  inventory in `environment/installed-pi311.json`.

Runtime flow: camera_source -> track_web.Monitor -> track_vision -> lane_path ->
autonomous.AutoPilot -> manual_drive. GPIO initialization only happens in the
explicit hardware mode. Read HANDOFF.md for physical limits and known failures.

## Optional Crossing And Recovery

### Joint White / Yellow Guidance (2026-10-19)

The new optional profile combines a continuously updated white target with
current yellow-edge direction. It does not drive to individual dots and stop.

```bash
./.venv/bin/python -B track_web.py --manual --motor-wiring-confirmed --autonomous --lap-mode --boundary-guidance --pilot-speed 0.30 --analysis-max-side 480 --port 5001
```

The Flask checkbox `흰점·경계 조향` controls the same mode. Enabling it selects
the lap profile (Kp35, heading gain1), but NEVER arms or starts motors. Mode
changes require new observations and a fresh straight central reference.
On return, confirm placement and immediate stop readiness, then set the central
reference before an explicit supervised start. Hardware/ownership/freshness,
rate60, steering-105..85, curve.85 and limited-path.8 caps remain in force.
Base.30 still gives.24 on limited paths; this is not a motor-start boost.

Normal white paths stay primary. In a corroborated bend, direction is a65/35
white/yellow image-heading blend. Opposing/flat edge cues are ignored rather
than cancelling a valid white path. A confirmed bend cannot be cancelled by
an opposite lateral term. Straight-edge perspective convergence CANNOT initiate
a turn: white heading relative to the straight reference must also indicate
a bend. These are image-space gains, not measured physical wheel angles/radii.

If the old target-height gate fails, a long, well-filled CURRENT white mark
plus>=8 matching CURRENT edge probes and near road>=.90 can supply a short
observed-paint target at.40.. .90H. This wider near window is exclusive to the
explicit joint mode; the legacy target rules are unchanged. No extrapolated
pixel, missing/ambiguous mark, off-road or stale frame can drive this fallback.
It cannot calibrate or renew the brief turn-recovery budget. With no credible
white paint, it still stops; a fully yellow-only estimated-width planner is NOT
implemented. Divider/outer classification is diagnostic, not wheel-footprint
feedback or a guarantee of staying on track. Both lanes remain allowed.

272 Python tests pass on PC/Pi; four Node UI suites pass. Saved last-failure
frames now yield joint paths, but no physical motion was performed for this
profile while the owner was away. A completed lap is NOT established.

The owner's2026-10-19 priority is a supervised full-track lap, allowing both
lanes inside the yellow road boundaries, rather than exact first-lane centring.
Use the explicit completion profile after confirming placement/stop readiness:

```bash
./.venv/bin/python -B track_web.py --manual --motor-wiring-confirmed --autonomous --lap-mode --pilot-speed 0.30 --analysis-max-side 480 --port 5001
```

`--lap-mode` configures continuous mode, bounded turn recovery, Kp35 and heading
gain1.0. It NEVER arms, starts, calibrates or confirms a completed lap by itself.
Crosswalk/gesture control stays OFF for this driving trial. The profile uses a
soft normalized centre-error band0.12; a larger lateral error still requires
independent road/connected-edge evidence within the existing hard bound1.05.
Both lanes may be used; this is NOT permission to cross a yellow track boundary.
Entry steering keeps the configured rate60; neutral return may use up to120
command units/s. An opposite turn unwinds to zero before building the other sign.
Hardware limits-105..85, source freshness, leases and emergency stop stay intact.
Physical lap validation and steering calibration are still required.
Completion mode can validate an observed piecewise curve when a global curve
fit or vertical span fails. It still needs matching paint directions, current
road and a coherent independent yellow edge. No old-path indefinite driving or
automatic lap-success detection is included. Standalone gesture sources/models
and physical GPIO wiring remain untouched.

New interaction/recovery code is opt-in and requires physical calibration.
For a no-GPIO gesture/crosswalk preview (safe default during unattended work):

```bash
./.venv/bin/python -B track_web.py --gesture --port 5001
```

For supervised integration, stop that server first, then use the original
hardware launch command with `--gesture` appended. Starting it never arms or
moves motors. In the pilot panel, `turn_recovery` opts into a supported brief
missing-dash exception, and `crosswalk_gesture` opts into crossing interaction.
Both default OFF. The latter requires the initialized gesture worker and
continuous mode; restart still requires a fresh straight reference.

The last selected test base was0.30; make that explicit at launch rather than
assuming runtime slider values survive restart:

```bash
./.venv/bin/python -B track_web.py --manual --motor-wiring-confirmed --autonomous --gesture --pilot-speed 0.30 --port 5001
```

This does NOT enable either new control flag or begin movement. GPIO mapping
and new physical readiness must be confirmed before the supervised session.
Python other than3.11 is rejected with a venv instruction before camera/GPIO
initialization. Expand execution information below the image to see the actual
file, interpreter and PID. Never kill an unrelated process to free the port.

Read-only health check, without any drive commands:

```bash
./.venv/bin/python -B check_runtime.py --expect-preview --output outputs/health.json
```

Omit `--expect-preview` for an intentionally enabled but disarmed hardware
server. This checks commands/freshness, not measured wheel speed or accuracy.

Recovery lasts at most0.20s from the last fully valid path, not0.20s per failed
frame. Current road/connected yellow edge must corroborate that same curve;
ambiguity/jumps/stale input and all lease/deadman/stop checks still stop. Fresh
full evidence over3 frames/0.30s is required to replenish the recovery budget.

Crosswalk detection groups white stripes on road before lane-mark size filters.
It needs fresh persistent evidence; stop depth0.70 is an INITIAL IMAGE threshold,
not metres or a validated stopping distance. At a crossing the same pilot owner
pauses motors at0 and detaches servo PWM. Hand/gesture inference runs while
stopped, with a fresh30-frame history per wait. Departure requires >=5 distinct
fresh unsmoothed GO decisions over>=0.5s, a visible hand, fresh valid lane,
unchanged ownership and live supervisor lease. STOP/unknown/error remains stopped.
One crossing event is latched until observed absent after departure. A fault or
operator stop cannot be restarted by GO. Held display labels never authorize.

No new pedestrian detector, hand/person association or traffic-light control is
included. Known idle-hand/object false positives need negative live trials;
temporal filtering alone does not prove an intentional pedestrian request.
Read NEXT_SESSION.md for the pending supervised validation sequence.

Autonomous steering uses separate left/right magnitude limits105/85 (signed
commands -105..85), matching the owner's manual A/D calibration. Both can be
lowered independently under steering settings. P/heading control remains
proportional and rate-limited at60 command units/s; this is not a measured
wheel-angle calibration. Hardware bounds and all stop guards remain enforced.

## Preview And Timing

For the optional high-rate analysis profile, append `--analysis-max-side 480`
to the supervised launch command. Native capture/photos/processed-preview size
remain960x720; lane masks/path fitting use480x360 instead of640x480. Smaller far
paint can be lost, so this is an explicit tradeoff, not a free accuracy gain.
Omit the option (or use640) to retain the original analysis dimensions. Allowed
range320..640. Restart disarmed and recalibrate on a straight centred placement;
never reuse a reference established at another analysis geometry.

2026-10-19 timing: after warm-up the480 profile delivered30.1 processedFPS over
61 stationary samples with no preview client, median23.8ms/frame. This is not a
moving-track accuracy or worst-case sustained-rate guarantee. Initial warm-up
averaged28.8FPS. The native camera request remains30FPS, preview cap15FPS.
With one processed-preview stream over Wi-Fi,71 further stationary observations
measured30.01 actual frame-countFPS,24.4ms median processing and source age
<=0.066s. This still does not establish moving-scene recognition accuracy.

Camera capture still requests30FPS at960x720, with640x480 vision analysis.
`--preview-fps 30` is the default browser-only transmission cap (range1..30),
not the vision/control rate. Hidden pages suspend their preview stream; a shared
latest-frame JPEG cache avoids duplicate encoding for the same view/frame.
Photos and paired recordings keep their existing size/rate settings.

The monitor separates camera delivery FPS, processed FPS and preview cap.
Separate displayed ages track processing completion and source receipt/retrieval
start. Neither is a sensor exposure timestamp, sensor-to-browser or measured
sensor-to-motor latency. Lower bandwidth alone does not establish lower latency.
See HANDOFF.md for measured results and the outstanding curve-path failure.

## Restore On The New SD

Use a Raspberry Pi OS **64-bit** installation with working camera support.
The dependency locks target ARM64 Python3.11 and glibc2.36+ (Bookworm or newer);
they are not Windows/32-bit/general-purpose dependency locks.
This procedure is for the owner's new SD, not permission to erase the borrowed SD.
Enable SSH, configure networking, and confirm `uname -m` is `aarch64`.

1. Install OS tools/libraries. Do not install Python3.13 camera bindings into
   the Python3.11 venv:

```bash
sudo apt update
sudo apt install git curl rpicam-apps libgl1 libportaudio2
```

2. Install uv using its [official instructions](https://docs.astral.sh/uv/getting-started/installation/).
   The official Linux installer is:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart the terminal if `uv` is not on PATH. Clone the repository and create a
NEW Python3.11 environment (see [uv Python setup](https://docs.astral.sh/uv/guides/install-python/)):

```bash
git clone https://github.com/chan-1215/Capstone-Design.git
cd "Capstone-Design/Auto Driving 20261018"
uv python install 3.11
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-core-pi311.txt
```

For future gesture work install the compatible, separate gesture environment
lock instead (it includes the core packages):

```bash
uv pip install --python .venv/bin/python -r requirements-gesture-pi311.txt
```

If OpenCV reports missing `libglib-2.0.so.0`, install the matching OS library:
Bookworm `libglib2.0-0`, Trixie `libglib2.0-0t64`. Do not install opencv-python
alongside opencv-contrib-python: they overwrite the same cv2 namespace.
The exact package list from the old SD is an INVENTORY, not an install lock:
it contained duplicate OpenCV distributions and an incompatible JAX/NumPy pair.
Fresh lock resolution is not proof of a successful fresh-SD hardware setup.

3. Verify without motors first:

```bash
./.venv/bin/python -c "import sys,cv2,numpy,flask,gpiozero,lgpio; print(sys.version); print(cv2.__version__)"
./.venv/bin/python -B -m unittest discover -p 'test_*.py'
rpicam-hello --list-cameras
./.venv/bin/python -B track_web.py --port 5001
```

For gesture dependencies only: `./.venv/bin/python -c "import mediapipe; print(mediapipe.__version__)"`.
When camera input works, stop the camera-only server with Ctrl+C before opening
hardware mode. No two camera servers may run together. New GPIO permissions,
physical steering centre, battery, motor directions and stop operation still
need verification before any powered-forward test.

## Camera And Defaults

The old SD's Picamera2 bindings exist only for OS Python3.13. In Python3.11,
camera_source falls back to the [official rpicam-vid application](https://www.raspberrypi.com/documentation/computers/camera_software.html),
quality95 MJPEG decoded by OpenCV. Flask/perception/control stay in3.11. The
latest JPEG replaces old application frames; no cached-frame driving fallback
exists. JPEG changes pixels, so validate masks on the new track/camera setup.

Capture defaults960x720, analysis640x480, requested30FPS, rotation180. Current
camera: OV5647 Rev1.3. Do NOT use the old IMX219 `--sensor-size 1640 1232` override.
Manual output defaults0.30 and pilot base0.26. The owner restored curve slowdown
after testing without it: curve_scale defaults0.85, adjustable0.75..1. This gives
0.221PWM in a full-evidence turn; limited paths keep their independent0.8 cap
(0.208PWM at base0.26). Turn mode exits after at least3 fresh straight frames
span0.3s, not a single straight flicker. Steering still follows current evidence;
invalid/stale paths stop rather than blindly retaining the previous angle.
Near centres can replace an unfittable far bend only with paint/road/yellow
corroboration. One long observed dash can support an existing reference with
its axis and boundary; isolated short dots cannot. Outputs are PWM
fractions, not measured physical speeds. These values are not universal motor
calibrations. See HANDOFF.md before changing steering or safety limits.

White segmentation retains the contrast gate, then restores only connected
colour-confirmed white interiors on validated road. Restoration requires
substantial contrast seed coverage plus the existing area/aspect/fill checks;
it does not fill dark gaps or invent white beyond the colour mask. Near paint
clipped by the bottom image edge uses the existing maximum near-area budget.
`white_restored_pixels` in status records the added observed white pixels.

## Evidence And Exclusions

2026-10-19 software checkpoint:220 Python tests passed on PC and Pi3.11, plus
four Node UI suites. Camera-only15-minute metadata monitoring passed300 samples
without transport errors; it did not test motor movement or gesture accuracy.
Gesture inputs now share the rotated/resized capture before road processing,
and inference is start-rate-limited rather than delayed again after each call.
The live result-age guard remains0.20s. A short stationary/no-hand comparison
reduced stale results from33/100 to1/100; do not equate this with reliable GO
intent recognition. Read HANDOFF.md and NEXT_SESSION.md for remaining physical
gates and the latest launch mode. Existing gesture models are unchanged.

Before this snapshot,135 tests passed on PC and Pi Python3.11; a temporary Pi
Flask test at960x720 measured30.03 completedFPS on a stationary floor scene.
DC outputs stayed0 and servo PWM stayed off. This does NOT prove track accuracy,
a complete autonomous lap, gesture integration or fresh-OS compatibility.

Raw recordings, run logs, previous source backups, whole virtualenvs, OS images,
credentials, VS Code data and the unrelated smart_factory project are not in Git.
The chronological original README/AGENTS are preserved under history/ for review;
their old launch commands are historical, not instructions for the new SD.
