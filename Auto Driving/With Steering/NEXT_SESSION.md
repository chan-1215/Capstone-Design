# Next Session Integration Pipeline

## Execution Checkpoint 2026-10-19

Software adapters, opt-in bounded turn recovery, crossing/gesture state gate
and Flask observations have now been implemented. Existing preserved gesture
source/model and GPIO mapping remain unchanged. The owner's robot is on a desk
or lifted; no motion tests are authorized while the owner is away. Continue
with the physical-motion comparison and supervised gates below after return.
The software checkpoint is NOT a verified complete lap or crossing demonstration.
PC/Pi220 Python tests and four Node UI suites passed. Camera-only gesture preview
is running on port5001, hardware disabled. Stop that preview before opening a
supervised hardware-mode process; do not accidentally run a second camera owner.
First obtain new placement/readiness, verify stop/steering direction and compare
manual/auto motion at matching output. Then test bounded recovery separately
from crosswalk stop. Calibrate real stripe/stop-depth footage before enabling
crosswalk_gesture. Test ordinary hands/objects/unknown/STOP before any GO release.
Three consecutive complete demonstrations remain the final validation gate.

Prepared 2026-10-18 for the next supervised robot session. Scope: existing
track autonomy, crosswalk stop, and MediaPipe/KNN stop/go. Traffic lights are
excluded. These are implementation steps and initial test parameters, NOT
features already implemented or a promise of next-day completion.

## Starting Point

- Work only here and on pi@192.168.137.60 in the matching project directory.
- Entry point: track_web.py, project-local Python3.11 .venv, port5001.
- Read AGENTS.md and HANDOFF.md; preserve other projects and gesture originals.
- gesture_reference/ is preserved source/model; gesture_adapter.py now provides
  optional integration without modifying those originals. Physical validation
  is pending; integration options remain OFF by default.
- Camera is opened once. Reuse camera frames; do not start a second capture.
- User observed motion at manual0.22, earlier startup at0.30 and continued
  motion at0.26. This does not establish equal torque under steering load.
- The latest inspected autonomous trials sent0.221 to both motors and ended
  operator_stop with valid paths. Logs are commands, not motion measurements.
  Do not treat those trials as proof of a stall, GPIO failure or path rejection.
- Session-only pilot speed was changed to0.30; ordinary curve0.255, limited
  path0.24. Source default remains0.26. Restart clears runtime configuration,
  straight reference and continuous mode. Do not silently restore/arm these.

## Order And Timeboxes

Times are debugging budgets, not completion estimates. Finish one checkpoint
before integrating the next. Save the last passing version at each checkpoint.

| Stage | Budget | Exit criterion |
| --- | --- | --- |
| Establish baseline | 15 min | Correct process, fresh camera, zero outputs, dependency imports |
| Reproduce motion issue | 30 min | Same-place manual/auto comparison explains command vs travel |
| Stabilize turns | 60 min | Both turn directions repeat without operator rescue |
| Crosswalk stop | 45 min | Approach/stop works; seams/dashes do not trigger repeatedly |
| Gesture gate | 45 min | Fresh go releases; stop/unknown/stale never releases |
| Combined validation | 45 min | Three consecutive complete demonstrations |

If a budget expires, stop adding features and isolate the failing stage. Do
not substitute a successful standalone gesture overlay for integrated control.
If repeatability is not reached, present separately verified demonstrations
and identify the integration gap instead of calling the system complete.

## Baseline And Motion Diagnosis

1. Compare PC and Pi source hashes and preserve the current Pi source/config
   before any upload; another person may have changed it. Do not overwrite an
   unreviewed Pi version. Capture /status, last run and failure images.
2. Confirm no competing camera/GPIO process. Import OpenCV, Flask, gpiozero,
   MediaPipe and the existing model in3.11 without opening motors.
3. Restart disarmed only if needed. Verify motor outputs0 and servo PWMoff.
4. Obtain new placement/readiness before any motion. Use straight1st-lane
   centre, neutral wheels and an observer ready to stop. Set reference there.
5. Compare short manual and autonomous trials at the SAME duty, wheel command,
   placement and battery condition. Record actual travel separately from PWM.
   Inspect follow(), _apply(), actual motor-device writes, ownership, heartbeat,
   timeout and stop reasons. A successful output log is not physical feedback.
6. Do not add a startup boost unless this comparison demonstrates a starting
   torque problem. Do not change speed, gains and perception gates together.

## Bounded Turn Continuation

The user requests continuing a bend through brief missing dash detections.
Implement this as an explicit, observable recovery state, not unconditional
invalid-path driving or a timer that continually resets itself.

Proposed starting policy, to be replay-tested before powered trials:

- Enter TURN_RECOVERY only from a recently validated left/right turn, when
  dash evidence briefly becomes insufficient. Never enter from idle/straight,
  ambiguous competing lanes, a large unexplained jump or an out-of-road result.
- Require a NEW camera observation with independently consistent road and
  yellow-boundary geometry confirming the same corridor/direction. Yellow
  reflections are already a known problem; any yellow pixel is not enough.
- Limit the complete episode to0.20s measured from the last fully valid path,
  including time already elapsed before entering recovery. No fresh compatible
  support, missing camera or exhausted budget means immediate stop.
- Keep the last validated steering COMMAND; do not ramp to full lock, reverse
  the sign, invent a centre, increase output or apply a startup boost here.
  Keep the existing angle/output bounds and ordinary curve/limited-path caps.
- Restore normal steering immediately on a validated new path. Rearm the
  recovery budget only after >=3 fresh full-path frames spanning>=0.30s, not
  after a single flickering valid frame. Repeated losses cannot extend motion.
- Preserve operator stop, browser lease, hardware deadman, camera/storage
  faults and ownership checks in every state. Recovery cannot revive a stop.
- Log entry cause, source-frame ID/receipt time, evidence, steering/output,
  elapsed budget and exit reason. Label recovery distinctly in Flask.

Control snapshots now carry source-frame receipt/retrieval-start time/identity
as well as processing completion age; stale input participates in control stops.
Neither is a sensor exposure timestamp or measured full end-to-end latency.
This policy intentionally changes the current invalid-path stop behavior;
update AGENTS.md/HANDOFF.md and negative tests together with its implementation.

## Crosswalk Detection

- Add crosswalk.py as a separate observation module. Reuse the colour-confirmed
  WHITE support on road, not only result.dashes: the latter filters for lane
  marks and can discard large crosswalk stripes.
- Associate multiple wide stripe candidates by orientation, spacing and common
  depth across the current lane corridor. Do not assume stripes are horizontal
  in the image; track orientation and perspective change their projection.
- Require persistence across distinct fresh frames. Log an overlay and evidence
  before wiring a stop. Test actual approach images and negative seams, glare,
  adjacent-lane dashes and curved lane paint. Counts/ROI must be calibrated on
  this track, not treated as universal hardcoded geometry.
- Stop before entering the pedestrian zone. A pixel-depth threshold is not a
  distance measurement; set the stop ROI by supervised approaches at test duty.
- Exclude confirmed crosswalk paint from lane-dash association where needed,
  without erasing the raw white mask or bypassing lane/corridor validation.
- Latch one crossing event. After permitted departure, keep it latched until
  the crosswalk is absent on fresh frames for a calibrated interval. A timeout
  alone must not repeatedly rearm while still on the same painted stripes.

## Gesture Worker And Fresh Authorization

- Reuse gesture_reference/gesture_recognition_module.py and its existing NPZ
  through an adapter; do not retrain or change the preserved model first.
- Run MediaPipe/KNN on one bounded latest-frame worker while stopped waiting
  at a crossing. Keep road/freshness monitoring alive and GPIO watchdog separate.
  Initialize/warm the model disarmed; measure inference time on the Pi.
- Use one pending frame, never an unbounded queue. Results carry capture/frame
  identity and monotonic timestamps. Discard duplicate/stale observations.
- Confirm a person's hand is visible at the stopped camera angle WITHOUT
  ruining the driving view. This is a prerequisite, not something software
  automatically solves. Do not change camera rotation/ROI during driving.
- Existing label is a held DISPLAY value. raw_label also has a five-prediction
  smoothing history; neither is automatically a fresh go authorization.
- Start a new gesture observation epoch at WAIT_GESTURE, clearing sequence,
  prediction and display histories in the adapter-owned recognizer. Require
  a newly filled30-observation window and a currently visible hand.
- Initial go gate: >=5 distinct fresh eligible go results spanning>=0.5s,
  result age<=0.2s; hand loss, stop, unknown or excessive result gaps reset it.
  Validate feasibility against measured worker rate; do not silently increase
  freshness timeouts merely to make inference appear to work.
- STOP/unknown mean remain stopped. Tumbler holding, idle hands and hand/hair
  movements must be explicit negative trials; temporal filtering cannot prove
  that a consistently misclassified gesture is intentional.
- Before departure require a fresh valid lane/reference, active supervisor
  lease and unchanged control ownership. Old go, manual override, browser loss
  or a previous fault cannot arm/restart the robot.
- Do not add new YOLO/person-segmentation work to this deadline. No current
  hand/person association exists; demonstrate a single designated participant
  and do not claim this is deployment-ready pedestrian intent recognition.

## Coordinator And Interface

One coordinator owns the existing control API; no new GPIO writer.

DISARMED -> FOLLOW -> CROSSWALK_APPROACH -> WAIT_GESTURE -> DEPART -> FOLLOW

FOLLOW <-> TURN_RECOVERY is bounded by the rules above. Any emergency/fault
goes to STOPPED/DISARMED and requires explicit operator recovery, never auto-go.
The transitions are implemented behind opt-in flags; physical operation remains
to be validated. The no-GPIO preview cannot execute any of these motion states.

Suggested isolated additions: crosswalk.py, gesture_adapter.py,
interaction.py, and focused test files. Integrate at Monitor observation output
and AutoPilot's guarded tick/follow path, not by replacing manual_drive.py.
Ensure crosswalk stops do not fight AutoPilot's ownership/disarm behavior.

Keep current Flask tabs, ROI, combined inset and capture controls. Add gesture
view and state/readiness/stop-reason indicators. Existing emergency stop must
take priority even during worker failure or an HTTP request in flight.

## Verification And Release

1. Replay saved failure frames and negative synthetic cases before Pi upload.
2. Fake-clock/controller tests: recovery expiry, repeated flicker, stale frames,
   wrong-direction boundary, ambiguity and stop override; crossing event latch;
   pre-wait/display-held/duplicate go rejection; hand loss and manual takeover.
3. Run Python and both existing Node suites; add new regression cases, preserve
   the existing172-test baseline. Then test Pi3.11 disarmed, not just PC imports.
4. Save/hash only changed source, upload, verify hashes and restart disarmed.
   Never copy a venv, overwrite unrelated work or run motion as an upload check.
5. Verify each stage independently, then repeat a complete demonstration3times:
   depart -> turns -> crosswalk stop -> stop/unknown wait -> deliberate go ->
   resume lane. No intervention during successful runs; intervention is failure.
6. Keep run JSONL, matched frame IDs, stage transitions, command vs observed
   movement notes and video. Record all failures, not only a successful clip.
7. Freeze the last passing source/settings before demonstration. Do not claim
   general road safety, reliable pedestrian intent or a completed autonomous
   lap from unit tests or stationary recognition alone.

No Pi deployment, automatic future execution or motion is scheduled by this
file. Next session begins with source comparison and new physical readiness.
