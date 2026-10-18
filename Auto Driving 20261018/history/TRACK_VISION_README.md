# New Track Vision

Pi runtime: use the existing Python 3.11 environment for future MediaPipe
integration, NOT `/usr/bin/python3`. See the final Python 3.11 section for the
current launch command; earlier system-Python commands are historical.

Separate prototype for the new black road, yellow boundaries, and white
markings. No old driving dataset, steering gain, motor trim, gesture code,
or learned model is loaded. Camera-only execution remains the default; manual
GPIO and the new bounded P-control pilot are opt-in as documented below.
Gesture projects are unchanged. On
2026-10-16 the user authorized Pi deployment and verified legacy-file cleanup.

## Scope

1. HSV colour thresholding extracts yellow boundary pixels.
2. Closed yellow barriers partition image regions. Sufficiently dark interiors
   adjacent to yellow barriers are accepted as road candidates.
3. Bright, low-saturation pixels with local contrast inside road regions become
   white marking candidates. Elongation/area filters flag dashed-line candidates.
4. The report shows original images, overlays, individual masks, and diagnostics.

This is image segmentation, not training. A dash candidate is NOT a confirmed
centreline. Multiple lanes, reflections, crosswalks and robot components can
confuse the current heuristic. Broken yellow boundaries may prevent road-region
confirmation. Absence of a confirmed region does not prove a physical off-road
condition. The default camera-only mode generates no steering or PWM.
The separately enabled pilot uses a provisional dash path, not a learned model.

## Run

Use Python 3.11+. For a separate environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe analyze_photos.py 'C:\path\track.jpg' 'C:\path\other.jpg'
.\.venv\Scripts\python.exe preview.py --video 'C:\path\track.mp4'
.\.venv\Scripts\python.exe -m unittest discover -p 'test_*.py' -v
```

For initial PC validation we use the existing `Gesture PC/.venv` interpreter,
which already supplies NumPy and OpenCV. This does not import gesture code or
change that environment. Do not install a second OpenCV wheel into that venv.

Open `outputs/index.html` directly; no server or internet connection is needed.
`outputs/report.json` contains configuration, candidate coordinates and counts.
Coordinates are pixels in `analysis_size`, not physical lengths. `road_fraction`
is an image-area ratio, NOT a recognition confidence or an accuracy score.

Options: `--roi-top 0.3`, `--max-side 960`, `--white-min-value 175`,
`--road-max-value 155`. Defaults are initial photo-review settings, not calibrated
onboard-camera settings. The ROI fraction describes excluded image rows.

`preview.py --video ...` displays saved video. `--camera 0` explicitly selects
a PC webcam; it is never opened automatically. Close other camera applications
first. Exit the window with Q/Escape or its close button. `--view dashes` shows
the candidate mask; `--headless --frames 60` checks video without opening a GUI.
Nothing is recorded or sent to the robot. There is no temporal tracker yet.

## Validation Boundary / Next Work

- Synthetic tests cover blank inputs, region gating, yellow/white separation,
  ROI exclusion, scaling, and no-control/no-path outputs.
- The three supplied classroom photos are reference views, not robot-eye views.
  Reviewing these photos is not evidence of real-time tracking or driving success.
- Once the new steering hardware is ready, collect forward-camera frames/videos
  to validate lane selection, continuity through dashed gaps, glare, curves and
  crosswalk rejection. Traffic-light recognition is not implemented.
- Only after physical straight-line and turning calibration should the vision
  output be connected to a separately tested controller.

## Pi camera monitor (2026-10-16)

Entry point: `track_web.py`; deployment: `/home/pi/track_vision_20261016/`.
The camera-only Flask monitor keeps the previous dark two-column appearance,
with OpenCV/raw/white-dash/yellow-boundary/road tabs and vision threshold sliders.
The OpenCV inset alone shows the combined line mask. Default execution has no
drive routes, motor buttons, GPIO initialization, servo output or gesture execution.

```bash
/usr/bin/python3 /home/pi/track_vision_20261016/track_web.py --port 5001
```

Use the Pi's installed system Python (currently 3.13), NumPy, OpenCV, Flask and
Picamera2. No Pi package installation was needed. RGB888 is requested because
libcamera's corresponding NumPy array has BGR byte order for OpenCV.
The application owns one capture thread and one Picamera2 instance. There is no
Flask reloader. A file lock prevents duplicate instances of this new monitor;
unrelated old camera programs still need to be stopped before it is launched.

The current URL is `http://192.168.137.72:5001/`; addresses can change with DHCP.
`/status` provides measured update FPS and processing time, candidate counts,
region area, freshness and settings. Neither area nor candidate count is an
accuracy/confidence score. `/snapshot/raw.jpg`, `/snapshot/processed.jpg` and
`/stream/processed` expose fresh frames. Stale snapshots return HTTP 503.
Settings are in memory and reset on restart. Default rotation is 180 degrees,
adjustable in the page without starting another camera process.

For PC-only web review, use the new local `.venv` with Flask installed:

```powershell
.\.venv\Scripts\python.exe track_web.py --image 'C:\path\track.jpg' --rotation 0 --host 127.0.0.1 --port 5002
```

PC validation: 28 tests pass, including web routes, freshness, settings, MJPEG,
perspective-sensitive dash filtering, combined-mask colours, absence of road
tinting and equality of the inset/tab masks.
On the Pi, the stationary live view shows yellow edges and white markings at
about 15 updates per second. Broad crosswalk stripes are white candidates too;
there is no crosswalk decision or selected centreline.
This is a static recognition check, not steering or autonomous-driving proof.

### Dash-display correction (2026-10-16)

The old OpenCV inset showed all white marks, while the dash tab showed only
shape-filtered marks. These were initially aligned to the same dash mask.
The old 0.4%-of-image area cap rejected a nearby central dash of about 2,036
pixels at 640x480. The new cap grows with image depth. Distant, foreshortened
marks with aspect ratios below 1.8 require at least two spatial neighbours;
isolated compact white patches remain rejected. This is a spatial heuristic,
not a temporal tracker, crosswalk classifier or lane-selection algorithm.

On one saved live frame, only 1 of 6 visible central marks passed the original
filter; all 6 pass the updated filter. This is a regression example, not a
measured general recognition accuracy. The updated Pi monitor remains about
15 FPS with control disabled. Vision settings were restored across the restart.

### Combined-line display (2026-10-16)

The visible tabs are OpenCV, original, white dashes, yellow boundary, and road.
The user clarified that the three individual diagnostic tabs must remain; the
separate combined-recognition tab was removed. Only the OpenCV inset combines
a black background, yellow boundary pixels and white dash pixels. OpenCV overlays
show only yellow boundary and cyan dash outlines, with no road tint, generic
white-mark outlines or artificial yellow ROI rectangle. A neutral grey ROI box
and ROI label show the actual active region and follow the top-exclusion slider;
they are annotations on the processed image only, not detected boundaries.
Offline photo-report
overlays retain their previous diagnostic rendering.

The road mask and old diagnostic snapshot endpoints still exist internally for
colour gating and API compatibility. Detection thresholds and candidate selection
were not changed by this display-only update. The combined snapshot is available
at `/snapshot/lines.jpg` and stream at `/stream/lines`.

## Verified Pi cleanup

Only 13 regular legacy files, totaling 215,907 bytes, matched Git blobs in
`Auto Driving/` or `Auto Driving@/` at remote commit
`7fc9dcb8bcee866c2ecf8d1f4e8655774cb505e5`. Those files were deleted after a
second SHA-256 verification. The generated local manifest at
`outputs/pi_cleanup_manifest_20261016.json` records each path and its Git restore
location. Gesture files, shared `.venv`, raw recordings and unmatched source or
backup versions were retained. This was partial verified cleanup, NOT deletion
of every old project or a full Pi backup. Approximately 407 MiB was free before
the deployment; deleting code alone does not recover the roughly 858 MiB shared
Python environment. No new GitHub push was performed by this task.

## Opt-in manual control (2026-10-17)

The user explicitly requested manual control after installing the new steering
mechanism. `manual_drive.py` is isolated from vision. This is NOT autonomous
driving, a P controller, training or a reused old driving policy.

User-observed command endpoints: A=-105, D=85, released=0. These are command
coordinates, not measured wheel angles or manufacturer-certified servo travel.
The pulse calibration remains -90=1ms, 0=1.5ms, +90=2ms; widening the configured
range to -120..120 must not shift neutral or rescale older commands. Each changed
target gets 0.7 seconds of PWM, then detach; heartbeats do not restart PWM.
External force can move a detached servo.

```bash
/usr/bin/python3 /home/pi/track_vision_20261016/track_web.py --manual --port 5001
```

Close the standalone servo test before running this command: both use BCM18.
Starting the server and loading/arming the page do not issue a movement command.
The manual checkbox explicitly arms one browser; keys/buttons then control it.
W/S and A/D can be combined. Releasing W/S stops DC output; releasing A/D sends
neutral once, then detaches. Space/Escape or the red stop button disarms and
stops DC/detaches without forcing a new steering angle. Losing focus, hiding the
page, disconnecting, stale camera frames or device errors also disarm; an old
delayed command cannot re-arm. The independent 0.7s deadman runs even without
HTTP input. This is a software safeguard, not an independent hardware E-stop.

**User-confirmed on 2026-10-17:** motor1=left (20/21), motor2=right (23/24),
`forward()` moves forward and `backward()` reverses for BOTH motors. Both forward
direction multipliers are +1; the historical -1/+1 is wrong for this assembly.
The default manual mode
does not construct GPIO Motor objects. W/S and motor speed/trim UI remain locked;
A/D can be tested after arming. DC still requires explicit opt-in, even though
the wiring and polarity are now confirmed. The slider labels reflect the observed sides.

Only after physical wiring/polarity confirmation may the operator explicitly add
`--motor-wiring-confirmed` with verified `--motor1-pins F B`, `--motor2-pins F B`,
`--motor1-direction 1` and `--motor2-direction 1` for this verified assembly.
DC speed defaults to 0.30 and is capped at 0.50 per motor after individual 0..1.5x
trim; no speed asymmetry or automatic inside/outside-wheel policy is applied.
Forward/reverse changes stop both channels before a 50ms pause. Initial motion
must be checked with the robot supported and an immediate physical power cutoff.

Manual POST routes require the page token and a browser ID. Inputs additionally
carry increasing sequence numbers so late packets cannot undo a newer release.
The page is intended for a trusted LAN, not public hosting; it is not an authenticated
multiuser control service. No gesture, dataset or learned model is integrated.
Control and web tests use fake hardware only; actual motor performance is unverified.

### Straight-line calibration checkpoint

The next physical task is straight-line DC output calibration, not autonomous
driving or adding more manual UI. The user warned that visually straight wheels
may not actually be mechanically neutral. Treat command 0 as provisional; neither
0 nor the arithmetic midpoint of A=-105/D=85 proves the true wheel-neutral position.
Do not change motor gains and steering neutral together. Begin with confirmed
wiring/polarity, consistent low test speed and measured starting pose, then vary
one setting at a time. Persistent drift or a correction that changes with speed
requires checking steering neutral, linkage alignment/play, unequal rolling
resistance and power conditions, not endlessly increasing a motor gain. Failure
to correct drift does not alone prove a steering defect. Detached PWM does not
hold the front wheels against external forces. With no wheel encoders, these
tests tune observed straight-line drift, not measured equality of wheel RPM.
Forward polarity is now confirmed, but initial straight-line calibration is NOT
yet complete. Start K1=K2=1.00, low equal output and a short bounded trial only
after the robot is back on the track, the test program is closed and immediate
physical stop is ready. Do not assume the wheels are still lifted or still on
the track after the motor-identification procedure.

The separate repo-root `motor_identify.py` uses confirmed BCM20/21 and 23/24,
never touches GPIO18, and tests only one selected motor per entered command.
Pi path: `/home/pi/motor_test_20261017/motor_identify.py`. Default command duration
is 0.4s at 0.25 output; both channels stop before/after each pulse and on normal
exit, Ctrl+C or SIGTERM. Run with wheels lifted, not as a straight-driving test.
Commands `1f`, `1b`, `2f`, `2b` describe gpiozero polarity; this user's test confirmed
both `f` commands roll forward, both `b` commands reverse, motor1 left/motor2 right.

### Manual forward and curve check

On 2026-10-17 the user requested forward motion in Flask to test whether the new
steering can negotiate a curve before adding an inside/outside motor-speed ratio.
Run `track_web.py --manual --motor-wiring-confirmed --port 5001` after closing
other motor/servo tests. Both verified direction multipliers default to +1.
The page starts DISARMED with motors stopped and servo PWM off. Enable the manual
checkbox explicitly, then hold W or the up-arrow button to advance. Hold A/D
simultaneously for -105/+85 steering. Release W to stop motor output; release
A/D to command 0 once, then detach after 0.7s. Space/Escape or the red stop button
disarms and detaches immediately. Defaults are speed 0.30, K1=K2=1.00; there is
no automatic turn-speed ratio, autonomous steering or lane-departure stop here.
The camera/transport watchdog is still active. Manual output is not gated by
segmentation success: the crosswalk can currently make road_fraction zero while
yellow is still present in raw HSV pixels. The 1.48s diagnostic-trial stop was a
false road-view-loss trigger, not demonstrated motor imbalance. That trial-only
guard must not be mistaken for production lane-departure detection.
Detached steering may move under load. A failed curve trial does not by itself
prove that a wheel-speed ratio is the missing fix; check linkage travel/neutral,
steering retention, traction and physical turning radius first.

## Bounded autonomous pilot and capture (2026-10-17)

The user requested autonomous and photo/video controls in the existing monitor.
This is a NEW deterministic OpenCV/P prototype, not the historical dataset-based
controller. GPIO wiring and the five image tabs are unchanged. No real autonomous
start was issued during implementation or deployment verification.

```bash
/usr/bin/python3 -B /home/pi/track_vision_20261016/track_web.py --manual --motor-wiring-confirmed --autonomous --initial-speed 0.26 --port 5001
```

Only the Pi URL controls the physical robot: `http://192.168.137.72:5001/`.
The development-only localhost:5013 QA process uses fake motors and a saved image;
pressing its start button cannot move the robot. Never use an image fixture to
judge live tracking or physical movement. That QA process is not an installed
robot service or an alternative production entry point.

### Pilot sequence and limitations

1. Put the robot facing forward at the intended lane centre on a straight section,
   with camera fixed and a physical power cutoff ready. Command zero is still only
   a provisional mechanical steering neutral.
2. Leave manual control disarmed. Select the central reference button while
   stationary. This records the current detected path position as zero lateral
   error; it does not prove the chosen marking is the correct lane centre.
3. Use autonomous start for the first 1-second trial. Stop remains available;
   Space/Escape, window blur/hidden state, browser heartbeat loss, invalid/stale
   path or the independent time deadline disarms and stops the hardware.
4. Inspect physical travel and the saved per-frame log before increasing duration.
   Finite trials are limited to 0.5..3 seconds. The explicit continuous-mode
   checkbox added on 2026-10-18 disables only this elapsed-time limit (see below).
   A normal time-limit stop is expected and is not a recognition failure.

`lane_path.py` chains spatially compatible, shape-filtered white dash candidates
near the reference, with at least three points spanning 22% of image height.
It fits a line/quadratic and evaluates it at 55% of frame height with limited
extrapolation, ambiguity, fit-residual and target-jump checks. The target is
temporally smoothed. It is NOT a metric bird's-eye model or guaranteed lane
selection, and cannot reconstruct a missing route through a crosswalk. Camera
geometry/threshold changes invalidate the reference; set it again while stopped.

`autonomous.py` computes command angle = Kp * normalized horizontal error.
Rightward target produces positive (D) command. Defaults: Kp=60, maximum command
20 degrees either side, slew limit 60 command degrees/second, DC output 0.26,
duration 1 second. These are conservative trial settings, not calibrated gains.
Limits are Kp 1..120, maximum 5..40, rate 10..120, output 0.10..0.30 and duration
0.5..3 for finite trials. Continuous mode retains that slider value for the next
finite trial but ignores it while running. Both motor scales are 1.00 in pilot mode; no automatic turn differential,
encoder speed feedback, crosswalk pause or traffic-light decision is implemented.

The pilot requires three valid frames, a reference and a path no older than
0.2 seconds. During a run, loss of a valid/fresh path or normalized error above
0.55 stops immediately (except the corroborated-curve case documented below).
A separate software watchdog enforces finite-mode deadlines and
0.7-second command deadman even if pilot processing stalls. It is software, NOT
an independent hardware emergency stop or verified lane-departure detector.
Crosswalk work remains deferred; current segmentation can reject the crosswalk's
bright area, so a run there may stop. Do not bypass this by continuing blind.

Unlike manual mode's timed detach, pilot mode keeps servo PWM active during the
run to retain the selected angle under load; all stops detach without commanding
a new neutral. Check for jitter, binding and actual steering retention physically.
The first real pilot trial, physical Kp tuning and continuous-curve driving remain
unverified. Previous straight tests did not establish completed RPM calibration.

### Local media and telemetry

Photo and record controls sit directly BELOW the first-person image. They save
both raw and annotated OpenCV views, regardless of the selected diagnostic tab.
They reuse the existing camera, do not start motors and are available without
`--manual` or `--autonomous` too. Nothing uploads to GitHub or a cloud service.

Default root: `/home/pi/track_vision_20261016/captures/`.

- `photos/`: matching `*_raw.jpg`, `*_opencv.jpg` and JSON status metadata.
- `videos/`: matching `*_raw.mp4`, `*_opencv.mp4` and per-frame JSONL metadata.
- `runs/`: central-reference JSON and autonomous-run JSONL (settings, prediction,
  requested/limited steering, motor output and stop reason).

Names use UTC timestamps, including microseconds. The saved-files disclosure
shows the absolute server directory and recent download links. Files stay on
the Pi until explicitly downloaded; downloading creates a PC copy through the
browser's usual download location. `--capture-dir` changes the server destination.
The directory is ignored by Git. Existing recordings/data are never auto-deleted.

Video uses MP4V at nominal 10 FPS, a bounded encoder queue and a 120-second
per-recording maximum. Queue drops are counted; variable capture timing/drops can
affect playback duration, so JSONL timestamps are authoritative for measurements.
Downloads for currently open recordings are disabled until stop/finalization.
Recording stops on encoder/storage error or before available space falls below
the 150 MiB reserve. Stop video before shutting down Pi to finalize the MP4.

All new control/capture POST routes use the existing page token and browser ID.
This remains a trusted-LAN Flask development service, not an authenticated public
robot controller. Tests cover fake-hardware pilot ownership, limits/watchdogs,
path failures, startup inactivity and photo/video round-trips; passing them does
not demonstrate safe real-world driving.

### Curve-path correction (2026-10-17)

This section supersedes the pilot's initial three-dash-only rule and pure
horizontal-error formula described above. The recorded failure ended in
`path_lost`, not the trial time limit: only two dash candidates remained, one near
the image edge. The last command was about -14.9 (A direction). The user has now
confirmed D physically turns RIGHT; do not invert steering to force a right turn.
The saved stopped-camera image shows the dash path extending toward image LEFT;
the software reports the observed direction, not the operator's curve label.

- The path search includes dashes near either horizontal image edge, instead of
  discarding the outer 12% before evaluating the route. The one-lane chain still
  rejects competing equally plausible candidates and abrupt target jumps.
- Three or more dashes retain the original geometric checks. TWO dashes are
  accepted only if vertically separated by at least 18% of frame height, their
  long axes align with their connection, and a separate yellow edge corroborates
  their direction. That edge must belong to one connected component, have at least
  seven of nine sampled rows and a smooth fit; at least eight path samples must
  lie in the segmented road. One dash, yellow alone, conflicting edges or
  crosswalk-like transverse axes are not accepted as a fallback route.
- Command = Kp * horizontal error + heading_gain * image-path heading error,
  then the existing angle/rate limits. The heading comes from the fitted path
  between observed forward rows (clipped to 30%..65% frame height), relative to
  the stationary straight reference, not a measured
  robot yaw angle. Default heading_gain=0.8, adjustable 0..2. It anticipates path
  direction before the target drifts far sideways; it is not learned prediction
  or a complete physical curvature/steering model.
- Two-dash corroborated mode uses 80% of the configured DC output. Other visible
  bends use 85%; output never falls below 0.10. This is PWM reduction, not measured
  speed control. Both motor scales remain 1.00, with no inside/outside ratio.
- Horizontal target error above 0.55 is no longer automatically treated as
  departure in a corroborated bend. The exception requires the fresh yellow-edge
  support, heading above 8 degrees, at least 85% road coverage in the near-field
  reference window, and absolute normalized error no greater than 1.05. Such
  bends run at no more than 80% output and retain the same short time/angle caps.
  This image-space check is NOT proof of physical lane containment.
- There is NO timed blind hold of the last curve command. Loss of current
  corroboration, stale frames, ambiguous selection and normal watchdog conditions
  still stop. Crosswalk handling remains deferred. Sharp bends over 12 degrees
  cannot be reset as the straight reference: reposition on a straight to calibrate.
- Flask shows the path source, failure detail, observed forward direction and
  readiness separately from the final stop reason. Run JSONL includes heading,
  corroborating edge samples, reduced output and the observation at stop.

After updating, the reference intentionally starts unset. Keep manual disarmed,
place the robot on the straight lane centre, set the reference and perform a
short operator-started run. Initial steering cap stays 20 command degrees; it
has NOT been proven sufficient for the rebuilt robot's minimum turning radius.
Do not increase speed or remove guards to conceal insufficient steering travel.
Regression tests include both curve directions, edge-of-frame dashes, absent or
contradictory yellow evidence, transverse bars, near-road loss and watchdog stops.
Offline acceptance of the saved failure frame is not physical driving success.

### Agent-operated trial checkpoint (2026-10-17/18 KST)

The user later explicitly asked the agent to operate short trials from lane 1
centre. This superseded the earlier deployment-only/no-agent-motion scope for
that supervised trial session. All trials kept the camera/path gates, heartbeat,
independent deadline and explicit final stop verification. The agent did not
remove guards, change wiring/polarity or tune either rear-motor scale (both 1.00).

Three issues were identified and corrected:

1. On the actual straight view, two successive dashes at roughly y=118 and y=172
   occupied one 12%-height row band. Their similar horizontal cost incorrectly
   triggered `ambiguous_dash_chain`, even though they were on the SAME line.
   Association now compares lateral residuals at each candidate's own y, keeps
   longitudinally separated compatible observations, and still rejects genuinely
   competing lateral paths. The saved straight regression retains four points.
2. `AutoPilot.start` previously initialized its steering/rate-limiter state to
   zero on every run, even after stopping with a curve command. It now seeds the
   state from the last hardware command (clamped to the current trial cap).
   A newly calibrated straight reference explicitly resets that baseline to zero.
   Neither reference nor start reservation actuates the servo; the first valid
   tick issues the command. The stored command is NOT an angle-sensor measurement;
   a detached linkage can move, so physical straight placement still matters.
3. Pilot speed reduction previously overwrote the manual speed/trim preferences
   through the shared command path. Pilot commands now leave those preferences
   intact. Actual reduced outputs remain in status motor_outputs and run logs.

The first five physical probes were 1s, 2s, then after the user's physical reset
2s, 1s and 1s. All five ended with `time_limit`, not a path-loss stop. Requested
base output was 0.26; corroborated bend output was 0.208, command cap 20 degrees,
Kp=60, heading_gain=0.8 and rate=60. No inside/outside wheel ratio was introduced.
Per-frame coverage is not a physical containment measurement. During the final
probe, the restart event recorded initial_angle=-20 and its first command was
-20, rather than a return to zero. The target's absolute horizontal error fell
from about 44px to 27px during that probe. This is image-space improvement in
one partial bend, NOT a calibrated lateral distance or full-corner success rate.

The user then confirmed all four wheels were inside lane 1. One further 1s probe
ended at its time limit; a PC image request timed out once, while the independent
Pi deadline still stopped the motors. The following requested 3s probe stopped
at about 2.65s with `path_lost`. Its 10 FPS video did not contain the exact failed
15 FPS vision frame: offline replay of all 28 raw frames found valid routes.
Do not infer that transient failure's exact cause from a later recovered frame.

The next update added paint-axis prediction for the first dash neighbour and
allowed steep local slopes (bounded to +/-3). It also retains three recent
raw/processed pairs. On path-loss, excessive-error or controller/camera failure,
motors stop FIRST, then the exact triggering pair and observation are saved in
`captures/photos/`; run JSONL links those files. Capture I/O failure cannot prevent
motor stop. Normal time-limit stops do not create these automatic failure photos.

After another user-confirmed straight reset, four probes (2s, 1s, 1s, 1s) all
ended at their time limits with 30, 16, 15 and 15 valid control frames. Steering
reached -20 in the bend, and motor output was 0.208. After the final stop, the
stationary route became consistently invalid. Twelve new stationary snapshots
reproduced the same defect: three legitimate dashes were detected, but two shared
one coarse row band; the one-pass compatibility filter retained only two points
and failed the vertical-span requirement. Association now recomputes its local
slope after EACH accepted point inside a band, preserving the existing residual,
ambiguity, separation, fit and corroboration guards. All twelve saved snapshots
then produced valid three-point routes. This latest fix requires a restarted
server and a new straight reference; it has NOT yet had a physical driving test.

The observed bend extends LEFT in image coordinates; do not rename this a
successful right-turn trial. No third-person view was used. Full-corner passage,
final wheel containment, neutral repeatability and continuous-lap performance
remain unverified. A reference reset must not be performed in this sharp bend.

PC evidence (ignored by Git):
`outputs/agent_trial_20261017T145920/`, `...T150014/`, `...T150513/`,
`...T150622/`, `...T150716/`, `...T151013/`, `...T151219/`, `...T152256/`,
`...T152348/`, `...T152358/`, `...T152409/`. The stationary reproduction is in
`outputs/curve_stationary_20261017T1524/`. Each trial has before/after JPEGs, sampled frames,
status.json and run.jsonl; the later folders also contain downloaded raw.mp4.
All raw/OpenCV video pairs and original JSONL logs remain on the Pi under
`captures/videos/` and `captures/runs/`. No dataset training or cloud upload
was performed. The final row-band correction passes 87 unit tests on PC and Pi;
those tests use fake hardware and are distinct from the physical probes.
After deployment, 19 of 20 sampled live observations were valid. The view changed
from the curve to a straight section during this check, so it is not a stationary
stability measurement or proof of zero dropouts. Motors remained disarmed,
outputs zero and servo PWM off. Wait for the user's renewed placement confirmation
before calibrating or moving again.

### Exact-frame paint-mask failure (2026-10-18 KST)

After the next confirmed reset, the requested 2s probe
`outputs/agent_trial_20261017T152758/` stopped after about 1.3s with `path_lost`.
The exact observation reason was `target_outside_observed_path`. Unlike the
earlier unsampled transient, its raw/processed failure pair was captured and
downloaded. Replaying that exact raw JPEG reproduces the failure: the nearby
paint at about (215,336) has fill_ratio=0.584 and fails the unchanged 0.60 shape
threshold. The remaining three far dashes cannot support the y=264 target. The
image has motion blur and small mask gaps; this does not establish whether mount
vibration, exposure or both caused the blur.

The marking mask now receives a 5x5 morphological CLOSE before contour shape
measurement. The existing fill/aspect/area, path-fit, target-support and stop
guards remain unchanged. This repairs the triggering frame to four valid path
points; all twelve previous stationary curve snapshots still pass. Tests also
verify that full dash gaps stay separate and thin seams are rejected. The update
passes 89 tests on both PC and Pi. Deployment was verified with matching camera
settings, camera online, outputs zero, motors disarmed and servo PWM off. The
reference is unset after restart. It still needs a new physical trial; neither
offline reproduction nor unit tests prove continuous driving.

### Oblique Two-Dash Curve Update (2026-10-18)

The user subsequently reported about four 3s starts from the red-marked bottom
section to the robot position in the full-track photo. The provided Flask screen
ends with path-unconfirmed, TWO white candidates and last command -20, not a
displayed time-limit stop. Pi is powered off, so the corresponding run log and
exact raw trigger frame have NOT been read. Do not call this a continuous lap or
claim that the stopped screen proves the precise trigger event.

The supplied screen's camera area is 764x573 pixels at x=42,y=119. Geometry replay
resizes it to 640x480, excludes the inset, fills the displayed cyan paint outlines
and uses the displayed yellow line. It is NOT a replay of raw segmentation:
the road side is reconstructed from the shown boundary, not the original road
mask. The two centres are about (78,313) and (256,404), axes align, but the prior
same-image-row boundary check returns None. The former fixed y=264 target also
lies outside their observed vertical interval. This proves a geometry limitation
for this displayed arrangement, not what every moving-camera frame contained.

The PC-only update changes `lane_path.py` and `test_curve_path.py`:

- Existing same-row corroboration is tried first. For paths at least 45 degrees
  from image vertical, a second method searches along nine path-normal rays.
  At least eight stations need paint-road and intervening-road support, and at
  least seven edge hits must share ONE connected yellow component. Signed gaps
  are limited to 4%..70% of image width, fitted gap residual to 2.5% of width,
  gap ratio to 2, and the edge must progress in the dash-chord direction.
- The >=18%-height dash span, axis alignment and existing association/fit checks
  remain. No yellow-only, one-dash or timed cached-steering continuation is added.
- If fixed y=55% is outside the observed interval plus the existing 8% margin,
  only a corroborated, aligned steep path may use the nearest OBSERVED depth.
  The replacement must lie between 40% and 70% of frame height; otherwise stop.
- Heading endpoints remain ordered inside the observed interval. Near-only
  observations previously could reverse/collapse the fixed 30%..65% endpoints.
  Look-ahead changes reproject the previous target before jump checking/EMA;
  genuine >15%-width jumps still stop. The straight-reference heading compensates
  its reference x at the new depth, and the overlay uses that same reference.
- Failure observations now include row/normal corroboration diagnostics, road and
  edge station counts, alignment and observed depth. Existing run/failure-frame
  recording carries these checks without a separate camera or log pipeline.
- DC output reduction, steering/rate caps, reference gating, lease, freshness,
  emergency stop and maximum 3s trial duration remain unchanged. GPIO, motor
  trim/polarity, gestures and the UI layout are untouched.

Geometry replay now accepts the displayed left curve via nine normal-supported
edge samples and an observed target at y=313 (65.2% height). Mirrored synthetic
geometry returns right, while missing/fragmented/crossing edges, missing road,
unaligned paint and too-close-only paths remain rejected. There are 98 passing
PC tests, including pilot output/rate caps, true-jump rejection and reference
projection. All 13 saved previous photo fixtures remain valid. A PC-only timing
sample for 100 synthetic oblique predictions averaged 3.54ms; this is NOT Pi FPS.

Evidence stays ignored/local in `outputs/oblique_curve_fix_20261018/`:
`geometry_replay.jpg` is explicitly labelled NOT LIVE; `replay.json` explains its
scope; `regressions.json` lists the previous fixtures. Do not publish the user's
photos or generated evidence as a training dataset or accuracy measurement.

Originally held on PC at the user's request until Pi was powered on. Deployment
and the subsequent physical checkpoint are recorded below; completing this patch
does not establish curve completion.

### Deployment And Supervised Checkpoint (2026-10-18)

The user reconnected Pi, requested upload and explicitly authorized supervised
driving from lane 1 centre. Preflight found no running track server. All unchanged
runtime files matched PC exactly; diffs in the four deployed files consisted only
of the prepared oblique-path patch, regression tests and handoff documentation.
Existing files were backed up to
`/home/pi/track_vision_20261016/backups_oblique_20261018_072915/`. Runtime code,
tests and docs were transferred without modifying other people's gesture code,
GPIO mappings, motor scales, source videos or datasets. Pi passed all 98 tests.

Flask was started with `/usr/bin/python3 -B track_web.py --manual
--motor-wiring-confirmed --autonomous --initial-speed 0.26 --port 5001` in the
same project directory. Saved camera settings matched after restoration. Startup
was disarmed with outputs zero and PWM off. A fresh straight camera view was
verified and a new reference set to about 0.475261 at heading 3.0 degrees.

Two recorded, bounded trials followed, without recalibration between them:

- `outputs/agent_trial_20261018T073017/`: 1s, 15 valid control frames, time-limit
  stop. Final image target error was about +8.7px; maximum absolute command 2.19.
- `outputs/agent_trial_20261018T073025/`: 2s, 30 valid control frames, time-limit
  stop. Error increased from about +18px to +182px, with positive commands up to
  +15.58 and final +8.25 as the visible path bent left. Final controlled near-road
  coverage was 0.895; stop observation coverage was 0.807. The PC's additional
  guard requested a stop near the endpoint, but run JSONL records `time_limit`.
  Do NOT relabel it a production path-loss stop or a completed curve.

After the second stop, the still image path became `inconsistent_dash_chain` and
the near yellow marking approached the reference footprint. Both motors were
verified zero, disarmed, servo PWM off and recording finalized. No further trial
was performed. The agent asked the user to confirm all-wheel containment and
whether the last positive command physically pointed the front wheels right.
These observations do not distinguish inadequate small-angle correction,
mechanical neutral, motor imbalance, steering polarity or model limitations.
Do not invert steering or tune motor scales without fresh physical evidence.
The oblique two-dash fallback was NOT yet demonstrated during a successful
physical curve traversal; the successful evidence remains its offline geometry
replay and synthetic tests. Continue only after renewed physical confirmation.

The user then confirmed ALL four wheels are inside lane 1, but the stopped front
wheels point LEFT. This conflicts with the last positive steering command and
the earlier physical D=right confirmation. Because stop detaches PWM, the stopped
pose is not proof of what happened during an active command. No further motion
was issued. The agent asked whether servo-horn/link mounting orientation changed
since the previous D-direction check. Resolve active steering direction before
another powered-forward trial; do not silently flip polarity based on this pose.

### Conditional Sharp-Curve Fit Exception (2026-10-18)

The user reported traversing the first corner and stopping at the second, then
explicitly requested less false rejection in corroborated curves, upload and
supervised driving from a newly confirmed lane-1-centre placement. Read-only
inspection saved recent run logs and exact raw failure frames under
`outputs/second_corner_20261018/`. Repeated stops were `path_lost` with
`inconsistent_dash_chain`, often within one second rather than at the 3s limit.
Immediately preceding frames already reported LEFT and commanded -20. Current
images contained five real dash candidates, not a missing-paint condition.

Replaying the exact 073509 failure gives 35.08px maximum error for a global
quadratic at width 640, above the original 25.6px threshold. The nearest FOUR
points fit within 7.63px and have independent yellow-edge support. This motivated
a conditional local exception, not a blanket loosening of all path checks:

- The original global threshold remains 4% of image width. Only failed chains
  containing at least five associated points and error <=6.5% width (41.6px at
  640) may attempt the exception. Larger errors still fail.
- Fit only the nearest four points. Their span must be >=30% frame height and
  contain the normal 55%-height target, with max fit error <=2% width (12.8px).
- Their chord must turn >=20 degrees from image vertical, with >=15-degree
  tangent variation. Straight/merely tilted straight paths do not qualify.
- EACH of the four paint axes must match its local fitted tangent (absolute
  dot product >=0.85). Comparing all points with one straight chord would falsely
  reject curved paint, so this stricter local-tangent check is used instead.
- Near-reference road coverage must be >=90% and the existing continuous yellow
  boundary corroboration must pass. No missing-edge/road or one-dash fallback.
- The controller uses only the validated local polynomial, not the poorly
  fitting global polynomial. Omitted points can only be the farther tail; no
  arbitrary interior-point deletion. Jump, ambiguity, target, camera freshness,
  lease, angle/rate and hard-time stops remain unchanged. Curve speed is 80%.
- New reason `local_curve_corroborated` is labelled in Flask. Status/run logs
  include global/local errors, effective global cap, fit mode and omitted count.

PC verification: 104 tests pass, JavaScript syntax passes, all 19 saved original
photo fixtures produce valid routes. Synthetic tests cover both turn directions,
hard-cap rejection, no relaxation for straight paths, contradictory near paint,
bad near points, missing edge/road, and controller speed/rate/angle limits. These
are offline results, not evidence of physical second-corner completion. Deployment
and any subsequent physical result must be recorded separately.

Deployment completed after comparing live files with the expected previous
version. Backup: `/home/pi/track_vision_20261016/backups_local_curve_20261018_075347/`.
Five files changed: `lane_path.py`, `test_curve_path.py`, `static/pilot.js`,
`README.md`, `AGENTS.md`. Pi passed all 104 tests. Camera and pilot settings were
restored, and the owned server restarted with disarmed motors, outputs zero,
servo PWM off and reference unset. The browser was reloaded for its new page token.

Before any powered-forward trial, a stationary direction probe used the SAME
DriveConfig pulse calibration and GPIO pairs, with temporary command limits
[-20,+20]. It sent +20 for 0.7s with DC output exactly zero, an independent 0.8s
deadline/watchdog and explicit final stop/close. No forward command was issued.
The user was asked to report the direction DURING the movement, not after PWM
detach. **Awaiting that observation.** The last physical servo command is +20,
but the restarted server starts its unmeasured command state at zero; do not
mistake that for measured neutral. After confirming direction, explicitly pulse
neutral with motors zero, verify the placement, then calibrate and start a 1s
recorded trial. Do not resume driving with the wheels still at the probe angle.

While awaiting the user's direction reply, neutral was explicitly pulsed through
the existing manual route with BOTH A and D true (angle zero), W/S false and
speed zero, then all keys released, preferences restored and emergency stop sent.
Both DC outputs stayed zero; final state is disarmed, angle command zero, PWM off.
This establishes a neutral COMMAND, not measured mechanical straightness. No
forward trial of this latest patch has occurred yet; direction/pose confirmation
is still required before setting the reference and proceeding.

The user renewed the direct request to drive after that pause. With the existing
steering mapping unchanged, neutral already pulsed, fresh straight camera/path
and the user's earlier centre placement, the agent reset reference to 0.477316
at heading 3.68 and performed THREE separate 1s recorded probes. Active direction
was still not independently observed/reported; do not claim polarity was verified.

Evidence folders: `outputs/agent_trial_20261018T080523/`, `...T080536/`,
`...T080608/`. The runs had 16,15,15 valid control frames respectively, all ending
at `time_limit` without path-loss or client errors. Final controlled target errors
increased to about +10,+37,+113px, with last commands +1.72,+5.46,+11.45. No local
sharp-curve fallback frame was used: the new second-corner exception remains
physically unproven. On seeing the growing error, the agent stopped additional
trials rather than silently changing steering sign, gain, angle cap or motor trim.
This does not prove polarity reversal; mechanical neutral/small-angle response,
motor imbalance and control/model behaviour remain possible contributors.
Final outputs are zero, disarmed, servo PWM off and recording finalized. The
user's 3s UI setting was restored without starting motion. Confirm containment
and actual steering response before continuing beyond this checkpoint.

### Supervised Continuous Mode And Compressed Dash Span (2026-10-18)

The user reported reaching the second corner using repeated starts and explicitly
requested a version with no trial-time maximum. The existing monitor now has an
opt-in continuous checkbox (`continuous: true` in pilot settings). When enabled,
the duration slider is disabled and labelled unlimited; active remaining time is
JSON null and displayed as continuous. There is no elapsed-time deadline in either
the pilot or manual controller in this mode. Finite mode is still the default and
retains both 0.5..3s pilot and independent software-watchdog deadlines. Changing
mode/settings while active is forbidden. Restart defaults to finite mode, disarmed,
without a reference; set a fresh reference only on a straight, centred placement.

Continuous is NOT unattended operation. Browser heartbeat loss (0.7s), blur,
hidden/page leave, stale camera (0.2s), path loss, uncorroborated large error,
hardware-command deadman (0.7s), emergency stop and owner conflicts still stop
motion. Keep the controlling page focused and remain beside the robot with an
immediate stop available. Angle/slew/speed/GPIO/trims are unchanged. JSONL logs
continue for the run; storage reserve is rechecked once per second and low storage
stops motion. Recording remains independently limited to 120s with a 150 MiB
reserve; stopping recording does not end a healthy continuous run.

Read-only evidence from recent user runs is in ignored
`outputs/third_corner_20261018/`. Stops include `insufficient_dash_span`,
`dash_association_failed`, a browser timeout and a normal time limit. These are
different causes; do not label all of them time-limit failures. The 081257 run
contains four `local_curve_corroborated` frames, but that is not proof of physical
corner completion. An apparent transverse seam candidate at (356,430) blocks
association in the 081258 failure. No arbitrary candidate/root deletion or blind
continuation has been added to bypass that unresolved condition.

The 081250 failure JPEG replays with two real dashes at (127,320.5),(47.3,241.3).
Their vertical span is only 79.2px, below the normal 86.4px minimum at height480,
but chord length is 112.36px, axes agree and nine points on one continuous yellow
edge support the path with near-reference road coverage1.0. A new narrow exception
for TWO dashes requires ALL: vertical span >=15% height, chord >=20% height,
obliqueness >=30 degrees, the usual 55%-height target inside the observed span,
each paint-axis/chord absolute dot >=0.85, at least eight independent continuous
yellow support samples and near-reference road coverage >=90%. All remaining fit,
jump, target and control stops apply; complemented-path output remains80%.
Without these conditions, the original18% minimum is unchanged.

PC validation:110 Python tests pass, plus `node test_pilot_ui.cjs` and JS syntax
validation. Tests cover mode validation/transitions, null remaining time, ownership,
all independent stop paths, disk reserve, API emergency stop, UI active/finite/error
states, both mirrored compressed curves and missing/misaligned evidence rejection.
The 081250 JPEG replay becomes valid; the 081302 JPEG re-segments with no candidates
(its original live log had two), so JPEG replays are not exact lossless reproductions
of every raw segmentation result. No new physical driving was performed for this
change. Deployment verification is recorded separately after installation.

Deployment completed to `/home/pi/track_vision_20261016`; backup is
`backups_continuous_20261018_082446`. All nine uploaded files match PC SHA256;
Pi passed110 Python tests. The unchanged source files matched before deployment.
Existing vision/pilot settings were restored except continuous remains false.
Flask5001 is online with outputs[0,0], disarmed and servo PWM off. The reference
was intentionally not restored in the bend. Browser verification toggled ONLY
settings and restored finite3s; no arm/start/motor command was sent to Pi.
An isolated PC fake-hardware browser run lasted12.344s (148 frames), then stopped
via the UI. Desktop and390px mobile layout were checked, with no horizontal
overflow; UI contract tests passed. This validates timing/UI, not physical travel.

### Adaptive Curve Output (2026-10-18)

The user tried continuous driving and reported excessive travel during camera
updates in curves. The latest two runs (`082737`, `082743`) contain66 and62
control frames over roughly4.3 and4.1 seconds. Curves still used PWM0.208..0.221
at base0.26 (only15..20% reduction), with repeated steering saturation at-20.
Both stopped on `insufficient_dash_span`, not a camera timeout; failure frame
ages were22ms and11ms. Camera status remained about15FPS. This does NOT prove
the robot outran camera processing: physical speed, blur/exposure, steering
geometry and path visibility are not measured by these logs. Slowing curves is
a controlled experiment, not an established root-cause diagnosis.

The controller now brakes on look-ahead heading error (>=8 degrees), desired OR
commanded steering (>=6 command degrees), or boundary-complemented/limited path
evidence. Turn severity is the larger of heading/45 and steering/angle-cap,
clipped to1. The curve ceiling interpolates from80% of base output to the
configurable `curve_scale` (default55%, allowed40..80%). Complemented/corridor
paths are capped directly at that ratio. Existing path output ceilings still
apply, as does the motor's existing0.10 minimum command. At base0.26 a sharp
turn therefore requests0.143 per motor, not the previous0.208. This is duty-cycle
command, NOT speed in m/s or guaranteed45% physical deceleration. Both motors
receive the same pilot command; pin mapping, polarity, manual trims and steering
gains/caps are unchanged. No minimum-power calibration or encoder is available;
if low output stalls the robot, stop and adjust the curve ratio rather than
silently increasing all outputs.

Reductions take effect on the next fresh control frame, including before the
servo has reached the requested angle. Increased output is held until heading
error<5, desired AND commanded steering<4, full-strength path support and stable
straight evidence for0.7 seconds. Then it rises by at most0.04 PWM units/second
(elapsed-step cap0.1s). Any renewed turn or uncertain support resets the wait.
No cached path/angle is used to keep driving after recognition loss. Finite and
continuous-mode stop/lease/watchdog/error/storage safeguards remain unchanged.

Flask labels base output separately from commanded output and shows speed state;
the curve-ratio slider can only change while stopped. Run JSONL adds commanded
target/reason, control interval and frame age to support the next comparison.
PC verification:119 Python tests and Node UI contract/syntax tests pass, covering
both turn signs, pre-steering braking, weak-path limits, transient straight
evidence, held steering, gradual recovery, output floor/caps and existing stops.
Offline replay of all128 logged frames requests0.143 on the sharper segments
and preserves0.26 on initial straight frames. Replay uses the OLD observations,
so it cannot prove changed travel or corner completion. Evidence remains ignored
under `outputs/curve_speed_20261018/`; no new physical driving was performed.

Deployment completed with backup
`/home/pi/track_vision_20261016/backups_curve_speed_20261018_083420/`.
Pi passed all 119 tests; uploaded files matched PC SHA256. Camera settings and
pilot gains/base output were preserved. Server 5001 is online, disarmed, outputs
zero and PWM off; startup is finite 3s with curve ratio 55% and reference unset.
The new output/state rows and ratio slider were verified on desktop and 390px
mobile without changing motor controls. No powered run was started. Reposition
on a straight and set the reference again before the next supervised trial.

#### User Near-Stall Feedback: Default Revised To 75%

The user reported almost no movement when the 55% curve command was applied.
That ratio was not a measured minimum-drive-power calibration and was too
aggressive for the reported load. The default and current stopped pilot setting
are now 75%: base 0.26 requests 0.195 on sharp curves, compared with the old 0.208
and the attempted 0.143. Stable-straight hold/recovery and all safety stops remain.
The server was NOT restarted and the reference/continuous selection were retained;
no movement was commanded. The previous 55% values in this section are historical,
not the current recommended starting setting. Existing 55% regression tests now
select that ratio explicitly; a new default-policy test expects 0.195.

Latest two user logs (083900,083925) also stopped after about 0.3/0.45s with
`inconsistent_dash_chain`, local fit about 7px but yellow boundary unconfirmed.
Those are recognition stops, not proof that low PWM was the sole cause of no
travel. Raising the ratio does not bypass this separate path validation failure.
Physical torque threshold and sustained curve motion at 75% remain unmeasured.

### Camera Module 2 / IMX219 Setup (2026-10-18)

The user replaced the OV5647 camera with a v2.1 module. Pi detected `imx219`
(3280x2464). Sensor identification alone does not establish IR-filter variant.
No old camera server or other camera consumer was running after reboot.

The earlier new-track monitor had requested15FPS from its first saved version;
there is no recorded30-to15 performance experiment justifying that default.
`PiCameraSource` and CLI now default to30FPS, with `--fps 15` still available.
For IMX219, the automatically selected640x480 sensor mode uses a central
1280x960 crop. This does NOT provide the lens's full nominal field of view.
The new optional `--sensor-size 1640 1232` selects the sensor's full-field binned
mode; ISP output and OpenCV analysis remain640x480. Do not force this IMX219 mode
on an unknown camera. Runtime logs verified actual1640x1232 sensor selection.

Current startup (same opt-in/disarmed manual and pilot panels):

```bash
/usr/bin/python3 -B /home/pi/track_vision_20261016/track_web.py --manual --motor-wiring-confirmed --autonomous --initial-speed 0.26 --fps 30 --sensor-size 1640 1232 --port 5001
```

Camera-only checks were run with no GPIO opened. The initial cropped15/30FPS
checks viewed a keyboard, then the user placed the robot on a straight. Therefore
their detection counts are NOT a camera/accuracy A/B comparison. The30FPS cropped
keyboard test processed about29.97FPS with median20.9ms. The subsequent full-field
track benchmark processed about30.03FPS with median29.9ms and a98.6ms maximum.
After Flask startup, with one browser stream active, completed-frame increments
over wall time measured29.79FPS; median processing29.2ms, maximum33.9ms in20
status samples. These are short stationary measurements, not sustained-load or
moving-camera guarantees. `frame_age_seconds` measures time since processing
completion, NOT sensor exposure-to-browser/control latency. Exposure in the
initial30FPS check was about33.3ms, so30FPS does not prove absence of motion blur.

Both yellow edges and several white dashes are visible. BUT nearby paint appears
soft and a lower-image reflection candidate sometimes enters the chain. Only6
of20 sampled path predictions were valid, with occasional straight-reference
heading rejection. Do not calibrate on that unstable/incorrect chain or claim
the new camera has improved autonomous driving. Check near-road focus, lighting,
reflection and alignment first. No detection thresholds, speed ratios, motor
pins/signs/trims or steering gains were changed during this camera setup.

Backup: `/home/pi/track_vision_20261016/backups_imx219_20261018_090338/`.
PC and Pi passed123 tests, including mocked camera configuration and explicit
15FPS override. Flask5001 is running with30FPS/full-field mode, disarmed, both
motor outputs zero and servo PWM off. No arm/start/reference command was issued.
The previous3s preference was restored; continuous defaults off and curve ratio
remains75%. Local ignored evidence: `outputs/imx219_check_20261018/` and
`outputs/imx219_full_check_20261018/`. Hardware replacement/restart invalidates
the old reference; require a new reliable straight reference before any run.

### Native 960x720 Display, 640x480 Analysis (2026-10-18)

The user requested higher resolution and raised the physical camera angle.
CLI capture defaults are now960x720 (30FPS request); IMX219 still uses the
1640x1232 full-field sensor mode. Earlier640x480 defaults in this document are
historical. Native capture/raw JPEG, processed display, diagnostic photos and
paired video frames are now960x720. Binary-mask tabs and path calculations stay
640x480. The overlay is NOT produced by enlarging the whole640 image: annotations
are enlarged, but unannotated background retains native camera pixels. Path/target
pixel coordinates in status/logs remain analysis coordinates; original_size and
analysis_size distinguish the two. Source arrays are copied to protect buffered
raw diagnostics; rotation and raw/processed recording dimensions remain matched.

Before this change, merely raising CLI capture dimensions would still downsize
the exposed raw image via VisionResult.frame. That path is now corrected.
A stationary960x720 full-analysis experiment measured14.91FPS, median61.9ms;
960 capture with640 analysis before native compositing measured27.18FPS. Final
Flask with browser video measured27.36FPS over16 status samples, median34.2ms
processing. This is not guaranteed30FPS; the previous full-field640 setup measured
29.79FPS. Higher resolution costs CPU even with smaller analysis. These short
tests are not moving-robot proof. Camera focus/softness/reflection remain unresolved;
the user changed angle, so do not attribute a different detection rate solely to
resolution. The final sampling window had no valid paths; no reference was set.

Current startup:

```bash
/usr/bin/python3 -B /home/pi/track_vision_20261016/track_web.py --manual --motor-wiring-confirmed --autonomous --initial-speed 0.26 --width 960 --height 720 --fps 30 --sensor-size 1640 1232 --port 5001
```

No segmentation thresholds, path guards, steering, motor pins/signs/trims, or speed
ratios were changed. Previous vision/pilot preferences were restored, except
continuous remains off after restart and reference unset. No powered motion or
calibration was issued. Backup: backups_resolution_20261018_091353 in the Pi
project. Tests cover native high-frequency detail, no source mutation, rotation,
snapshot dimensions and matching raw/processed MP4 decoding. Evidence remains
local under outputs/resolution_check_20261018/. Check focus and a trustworthy
straight path before calibrating or starting a physical test.

PC and Pi passed126 tests, including decoding both960x720 MP4 streams after
recording. Browser natural image dimensions were verified960x720. During final
read-only UI verification, another client had set a reference, enabled continuous
and started run_20261018T091447_222941Z.jsonl. The agent did not issue those
commands. Latest handoff is path_lost/disarmed, outputs[0,0], PWM off, reference
set and continuous selected; those external/user preferences were NOT reset.
Do not confuse this later state with the safe startup defaults above, or treat
the user's subsequent movement as a stationary resolution comparison.

### Returned To Rev 1.3 / OV5647 (2026-10-18)

The user reinstalled the original camera after the IMX219 image appeared soft.
Pi now detects `ov5647` (2592x1944). No camera server survived the reboot. Runtime
sources matched PC SHA256; no runtime code, detector thresholds, motor wiring,
steering or speed policy was changed for this return. IMX219's sensor-size override
was REMOVED from the launch command. Do not reuse --sensor-size1640x1232 on OV5647.

Current command:

```bash
/usr/bin/python3 -B /home/pi/track_vision_20261016/track_web.py --manual --motor-wiring-confirmed --autonomous --initial-speed 0.26 --width 960 --height 720 --fps 30 --port 5001
```

Both native JPEGs were verified960x720; analysis remains640x480. The first image
viewed a keyboard; later the user placed the robot on the track while verification
continued. In the final straight-road image, dash edges and road texture appear
clearer than the earlier IMX219 examples, but placement/angle/lighting were not
controlled, so this is NOT a sensor-quality benchmark. Twelve stationary status
samples all reported a valid straight chain with yellow support. Completed-frame
rate over wall time measured25.65FPS, median processing37.75ms with browser video.
The30FPS request is not a guarantee of30FPS processing or motion-blur absence.

Flask5001 is online, disarmed, both DC outputs0 and servo PWM off. No arm/start,
steering, reference or motor command was issued. Startup reference is unset,
continuous off, restored duration3s, curve ratio75%, base output0.26. A transient
camera_error reason remained in manual status while current camera frames and
path samples were live; it is not evidence of ongoing armed motion. Evidence is
local under outputs/ov5647_return_20261018/. Require a fresh trustworthy straight
reference before a future user-authorized driving trial. Earlier IMX219-specific
startup instructions are historical and do not apply to the current camera.

### Python 3.11 Runtime Restored (2026-10-18)

The required application runtime is the preserved Python 3.11.17 environment:

```bash
/home/pi/steering_robot_drive_eval_20261012/.venv/bin/python -B /home/pi/track_vision_20261016/track_web.py --manual --motor-wiring-confirmed --autonomous --width 960 --height 720 --fps 30 --port 5001
```

The old directory name here identifies the SHARED interpreter, not the old driving
controller. Do not delete this environment. MediaPipe 0.10.18, NumPy 1.26.4,
OpenCV 4.11.0, Flask, GPIO Zero and lgpio import successfully in it. This change
does NOT add gesture inference or gesture-driven motor commands to Track Vision.
No packages were installed, upgraded or removed from the environment.

The OS Picamera2/libcamera bindings are available in Python 3.13 but not 3.11.
`PiCameraSource` now falls back to the OS `rpicam-vid` application if those specific
bindings are missing. Flask, perception and control remain in Python 3.11; no
Python 3.13 application/helper is started. The application captures MJPEG at
quality95, requested960x720/30FPS, and OpenCV decodes BGR. Direct Picamera2 remains
available in environments that already provide it. This adds a lossy JPEG encode/
decode step: masks need fresh track validation, not an assumption of identical
pixels. No motor mapping, trim, steering, perception threshold or gain was changed.
OV5647 uses no forced sensor-size. Requested sensor-size is forwarded as --mode
only if explicitly supplied (the optional IMX219 mode has not been revalidated).

The reader drains frames into ONE latest JPEG, dropping older queued application
frames. EOF/corrupt frames/2s read timeout raise an error rather than replaying a
cached image; the existing monitor freshness and motor watchdog guards remain.
Child process and both reader threads are stopped when Flask closes. Startup waits
up to10s for the first frame and cleans up on timeout. No camera timestamps are
transported, so completed-frame age is still NOT sensor-to-actuation latency.

PC and Pi Python3.11 passed135 tests. A temporary localhost:5002 Flask verification
opened the real camera and manual/autonomous panels WITHOUT arming or commanding
movement: outputs[0,0], PWM off throughout. Twelve stationary samples over5.59s
measured30.03 completedFPS, median26.55ms processing. This was a floor-facing scene,
not track recognition, gesture performance or a moving-robot benchmark. Both
snapshots are960x720. The test server and its camera child exited; production5001
was left OFF as requested. Evidence: outputs/python311_camera_20261018/.
Pi source backup: backups_python311_20261018_192649.

This command does not force --initial-speed0.26: manual defaults to0.30; autonomous
base output remains0.26 and curve_scale0.75. These are PWM fractions, not measured
vehicle speeds. Starting does not arm/move hardware. A fresh straight-path reference
is still required before autonomous driving. Runtime is fixed at3.11 for future
gesture integration; do not substitute the system3.13 interpreter again.
