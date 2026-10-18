# Handoff: New Track / Python 3.11 / 2026-10-18

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
- Pilot P gain60, heading gain.8, cap20, rate60, basePWM.26, curve_scale.75.
  Curve reduction is pilot-only. Manual startup is.30 unless explicitly changed.
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
