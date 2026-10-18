# New track vision scope

This is a fresh vision-only prototype for the black track, yellow boundaries,
and white dashed markings introduced on 2026-10-15. Read README.md before editing.
Do not import old learned driving models, gains, GPIO code, or gesture modules.
Do not modify other projects. The user authorized a camera-only Raspberry Pi
deployment on 2026-10-16, and cleanup of old Pi files verified against GitHub.
Preserve gestures and shared environments; retain unmatched source files.
On 2026-10-17 the user explicitly requested opt-in manual control in this Flask
monitor. Keep GPIO isolated in manual_drive.py; default camera-only execution must
remain read-only. A=-105 and D=85 are user-observed steering command limits, not
measured wheel angles. The user confirmed the old DC pin pairs (20/21, 23/24)
unchanged on 2026-10-17, then physically verified motor1=left, motor2=right,
forward()=vehicle forward and backward()=vehicle reverse for BOTH motors. Both
forward multipliers are +1, NOT the historical -1/+1. Keep DC opt-in and require
new physical readiness before running a driving trial. motor_identify.py in the repo root is a
separate user-run, one-motor-at-a-time terminal test; never run it automatically. Do not
import old controllers. On 2026-10-17 the user authorized a new OpenCV/P-control
autonomous pilot and media capture in Flask. Keep it opt-in, disarmed on startup,
single-owner, fresh-path gated, browser-lease gated and time/angle limited. The
agent must not start a physical run merely to verify a deployment. Subsequently
on 2026-10-17 the user explicitly authorized agent-operated short driving trials
and stated that the robot was at lane 1 centre. For that trial session only,
freshly verify the camera/pose, start with one second, record observations and
always stop/disarm in finally. Keep all path/lease/deadline safeguards; do not
silently turn this into unattended or unbounded driving. New placement/readiness
is needed if the robot leaves view/track or the user moves it.
Keep crosswalk work deferred: loss of a valid path stops the pilot, not blind
continuation. Recordings go under captures/, stay out of Git and stop before disk
space is exhausted. Preserve user-tuned settings and other people's edits.
The user confirmed D physically turns right on 2026-10-17. Do not invert steering
to force a desired curve direction. The curve update accepts two aligned dashes
only with a continuous yellow edge and road support, adds a bounded heading term,
and slows corroborated curves. A large target error alone is not proof of departure;
its narrow curve exception requires near-road support and fresh boundary evidence.
Do not continue from cached steering after losing current evidence. The reference
must be set on a straight section; sharp-curve reference reset is rejected.
The latest stationary reproduction retained only two of three legitimate curved
dashes sharing a row band. Recompute the local association after each accepted
point within a band; do not weaken span/ambiguity/road guards to hide this defect.
On pilot evidence failure, stop motors before saving the exact triggering frame
from the monitor's three-frame history. A later recovered frame or 10 FPS video
is not proof of what failed in the 15 FPS vision pipeline. Server restart clears
the reference: require a fresh straight placement, never calibrate in a bend.
The exact 20261017T152759 failure JPEG reproduces a nearby paint-mask fill-ratio
rejection. A 5x5 CLOSE before contour measurements repairs small threshold gaps;
keep full dash gaps separate and preserve fill/aspect/area and path-stop guards.
Do not attribute all blur to camera vibration without exposure/mount evidence.
The 2026-10-18 oblique two-dash fix is now deployed on Pi with 98 tests passing.
Read the last README section before continuing. Same-row yellow checking
has a guarded path-normal fallback; adaptive look-ahead uses an actually observed
depth only within 40%..70% height. Keep every fit/axis/road/component/jump and
physical watchdog guard. Failure logs include corroboration checks. The user's
processed screenshot geometry replay is NOT raw-camera segmentation validation.
Two supervised probes (1s, 2s) ended at time limits; the second had growing target
error and near-road loss around the final stop. Motors were stopped and physical
wheel containment/positive-command direction confirmation requested. Do not claim
a successful curve, invert steering, or continue motion without that confirmation.
The user subsequently confirmed all wheels inside lane 1 and stopped front wheels
LEFT, despite the last positive command. PWM was detached, so active polarity is
not yet proven. Ask/verify whether the servo-horn/link mounting changed, then
confirm active steering direction before any additional forward trial.
The user then reported first-corner passage, requested a guarded sharp-curve
rejection exception and upload, and confirmed a fresh lane-1-centre placement.
The new local-four-point exception keeps the global error capped at 6.5% width,
local error at 2%, span >=30%, per-paint tangent alignment, fresh yellow support
and near-road >=90%. Straight paths retain the old 4% global rule. Read the last
README section for exact validation and pending deployment/trial status. Do not
increase angle/speed or invert steering as part of this vision-only change.
The conditional exception is deployed and Pi passed 104 tests. Backup ends in
backups_local_curve_20261018_075347. A stationary +20 servo probe (0.7s, DC zero)
was performed while the server was stopped; user observation of ACTIVE direction
is still pending. The server is restarted/disarmed but its angle=0 is not measured
neutral: physical last command was +20. Confirm direction and explicitly pulse
neutral with DC zero BEFORE calibrating or doing any 1s forward trial.
Neutral has now been explicitly pulsed with DC zero, then stopped/disarmed with
PWM off and preferences restored. Physical straightness and active +20 direction
still need the user's observation; latest patch has not had a forward trial yet.
The user then explicitly renewed the drive request. Three bounded 1s probes were
performed with the existing mapping and a fresh straight reference; all ended at
time limits, but target error grew to about +10,+37,+113px. No local-curve fallback
frame was exercised. Motors are stopped and the 3s UI preference restored. Active
polarity was not independently confirmed; do not claim curve completion or invert
sign from these image errors. Inspect physical response/containment before more
powered-forward trials. The last README paragraph supersedes the no-trial status.
Generated reports and photos stay
local and out of Git. Tests on reference photos do not prove autonomous driving.
Do not interpret all detected white markings as a selected driving centreline.

On 2026-10-18 the user explicitly requested a time-unlimited version. This
supersedes earlier 3s-only rules ONLY for the opt-in continuous=true mode.
Default is still a finite trial; continuous mode has no elapsed-time deadline,
but ALL ownership, browser lease, hardware deadman, camera/path/error, stop,
angle/rate/speed guards remain. Check log storage reserve every second. Continuous
does not mean unattended: never start it automatically to validate deployment.
Restart clears reference and defaults continuous=false. Never restore a reference
by calibrating in a curve. Video still has its independent 120s cap.
The compressed two-dash exception requires y-span >=15% height, chord >=20%,
>=30-degree obliqueness, target inside observed span, each axis dot >=.85,
>=8 continuous yellow samples and near-road >=90%. Keep the ordinary 18% rule
without those conditions. This is not a seam/root association fallback.
Continuous/span changes are deployed; backup ends in
backups_continuous_20261018_082446. PC and Pi passed110 tests; node UI contract
tests passed. A12.344s browser trial used FAKE hardware on PC only. Pi has NOT
been driven for this change. Server5001 is online/disarmed/PWM-off with finite3s
restored and reference unset. Require fresh straight reference before testing.

The user's next continuous runs stopped on insufficient_dash_span with fresh
camera frames (11/22ms age); do not assert camera overload from the observation
alone. Adaptive curve output now uses fresh heading, requested/current steering
and weak/boundary path evidence. Default curve_scale=.55 (UI40..80%); sharp turns
at base.26 request.143, NOT measured speed. Brake immediately, hold increases until
0.7s stable straight evidence and ramp at.04 PWM/s. Keep floor.10 and ALL stop,
ownership/freshness guards; do not change pins/trims/steering or perception masks.
119 PC tests pass; read the final README section for limits and deployment status.
Physical motion/stall response at the reduced output is untested.
Deployed with backup backups_curve_speed_20261018_083420; Pi passed 119 tests.
Server 5001 remains disarmed/PWM-off, finite3s, curve_scale=.55, reference unset.
Desktop/mobile UI verified; no motion was issued. Require straight reference and
fresh readiness for physical testing; user may need to tune the reduced PWM if
it cannot overcome motor/load friction. Do not claim physical speed calibration.
The user then reported near-stall at 55%. Current setting and code default were
revised to 75% (base.26 -> PWM.195), WITHOUT server restart, arm or movement.
Reference and continuous selection are retained. Treat earlier55% guidance as
historical, not the current default. Latest user logs also have path_lost from
inconsistent_dash_chain/boundary_unconfirmed within0.3..0.45s, so do not attribute
all immobility to low PWM or bypass that failure. Physical minimum drive power
and75% motion are still unverified; 55% remains an explicit regression fixture.

The user replaced the camera with v2.1; Pi identified IMX219. Default FPS is now
30 (not15). Launch with --sensor-size 1640 1232 to avoid IMX219's central-cropped
640x480 sensor mode; analysis output remains640x480. This mode is IMX219-specific,
not a safe universal default. Read the last README section. PC/Pi passed123 tests.
Full-field Flask measured29.79FPS with one browser stream, but near paint is soft
and a bottom reflection sometimes joins the path (only6/20 valid sampled paths).
Do not claim improved accuracy or calibrate that false/unstable chain. Check
focus/lighting/reflection/alignment before further physical tests. Sensor filter
variant is unverified. Backup ends in backups_imx219_20261018_090338.
Flask5001 is running disarmed/PWM-off, finite3s, ratio75%, reference unset; no
arm/start/reference or motion was issued. Last pre-camera physical wheel pose is
not measured by the new process's angle=0. frame_age_seconds is post-processing
age, NOT sensor-to-actuation latency. Camera data/evidence stays ignored/local.

The user then raised the camera angle and requested higher resolution. CLI capture
default is now960x720, analysis remains640x480. Raw AND processed displays/photos/
videos use960x720; only annotations are scaled over native camera background.
Status/log path coordinates remain640 analysis coordinates, not display pixels.
Full960 analysis measured14.91FPS; final split-resolution Flask measured27.36FPS
with median34.2ms processing, NOT sustained30FPS. Angle/focus/reflection confound
recognition comparisons; final sampling had no valid paths. Do not claim higher
resolution fixed focus or accuracy. Backup: backups_resolution_20261018_091353.
Flask5001 remains disarmed/PWM-off, finite3s, ratio75%, reference unset. No motion
or calibration was issued. The latest README section supersedes640 display defaults.
PC/Pi passed126 tests, including native paired video decoding. During final UI
check another client set the reference/enabled continuous/started run091447;
the agent did NOT command it. Latest is path_lost/disarmed/PWM-off, reference
set and continuous selected. Preserve that externally changed state; do not
restore startup preferences or claim a stationary comparison after that movement.

The user switched BACK to Rev1.3; Pi now identifies OV5647, not IMX219. Current
Flask5001 launch uses960x720/30FPS request with NO --sensor-size override. Runtime
code SHA256 matched PC; no logic/threshold/gain/motor changes were needed. Current
track image has clearer-looking edges/texture, but comparison is uncontrolled.
Twelve straight stationary samples were valid; measured25.65FPS, median37.75ms,
not guaranteed30FPS. See final README for command/evidence. Startup is disarmed,
outputs0, PWM off, finite3s, ratio75%, reference unset; no arm/start/reference or
movement was issued. Earlier IMX219-only1640x1232 instructions are historical.

The user reaffirmed that Flask/OpenCV/control must run in the existing Python3.11
environment for future MediaPipe integration. Earlier /usr/bin/python3 launch
commands are superseded; use the preserved steering_robot_drive_eval_20261012/
.venv/bin/python to run CURRENT track_vision_20261016/track_web.py. The interpreter
path does not imply old control logic. Do not remove/change that shared environment.
Camera input falls back to OS rpicam-vid (quality95 MJPEG) when Python Picamera2/
libcamera bindings are unavailable. No Python3.13 helper or gesture integration
was added. Read the final README section for the current command and JPEG limits.
PC/Pi3.11 passed135 tests; real960x720 camera+Flask+disarmed GPIO initialization
passed, measured30.03FPS on a stationary floor scene, not driving/track accuracy.
The verification server/child were stopped; Flask5001 remains OFF per user request.
No arm/reference/start/motor/servo command was issued. Manual default is0.30 when
--initial-speed is omitted; pilot remains0.26/curve_scale0.75. Preserve hardware,
thresholds, gains, guards and require fresh placement/readiness before driving.
