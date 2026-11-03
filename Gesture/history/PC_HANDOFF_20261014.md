# Gesture PC handoff

Current stage: YOLOv8n-seg person outlines alongside MediaPipe + KNN gestures,
using the owner's PC webcam. The robot is with another teammate.

- `gesture_recognition_module.py`, `hand_utils.py`, and the KNN NPZ are
  unchanged copies from `Lee/gesture/`.
- `run_webcam.py` opens the webcam once and sends the same acquired frame
  to the gesture recognizer and `LatestFrameDetector`.
- `person_detection.py` wraps YOLOv8n-seg, keeps only the COCO `person`
  class, and returns confidence, internal bounding coordinates, and an
  outline polygon per instance. The UI draws polygons, not rectangles.
  Bounded-frequency inference runs in one worker with one pending frame.
- `camera_guard.py` rejects a second Gesture PC process for the same Windows
  camera index. Stop the preview before running a headless camera check.
- `requirements.txt` pins the tested Python packages. Read the OpenCV
  exclusion instructions in `README.md` when recreating the environment.
- `models/`, `.venv/`, and runtime output directories are ignored by Git.
  No camera image, video, or gesture log is saved by the runner.

Person count and gesture label are separate observations. A detected hand
has not been associated with a particular person. Do not describe this as
recognizing a pedestrian's intent or issuing vehicle commands yet. Multiple
persons, partial views, distant people, and camera motion need evaluation.

The next agreed milestone is person detection testing. Crosswalk detection
belongs to later autonomous-driving integration. After person detection is
evaluated, define hand/person association and a temporal decision rule for
stop/go/unknown. The current gesture label hold is for display and should
not be treated as a fresh movement authorization.

Keep PC changes here while teammates work on the robot. Document any model
or landmark-processing change before proposing it for the shared robot code.

## Verification on 2026-10-14

Initial box-detector baseline:

- Worker tests cover latest pending input, rate limits, errors, result
  freshness, and shutdown. Camera tests cover duplicate-session rejection
  and releasing the session for restart.
- Ultralytics' bundled `bus.jpg` produced three person detections at the
  default 0.5 confidence threshold. A blank image produced none.
- Ten warmed-up sample-image inferences averaged 22.3 ms with two CPU
  threads and 320-pixel input on this i9-13980HX PC. This is a model timing,
  not camera FPS or a recognition-accuracy measurement.
- Initial webcam probes were invalid because the previous Gesture PC window
  still held the camera: second captures returned almost-black images at
  about 1 FPS. After closing that owned process, the combined 60-frame check
  passed at 24.3 FPS, detected one person, and reported 32.0 ms for the latest
  YOLO inference. Gesture output was unknown in that check; labeled gesture
  accuracy has not been measured. The added camera guard prevents that
  duplicate access between future Gesture PC runs.

Current segmentation version:

- Nine tests passed, including polygon rendering without a bounding box
  or background fill and hiding stale outlines.
- The bundled `bus.jpg` produced three person outlines with 613, 354, and
  348 vertices. The rendered sample was inspected visually. A blank image
  produced no persons.
- Ten warmed-up sample inferences averaged 40.2 ms with two CPU threads
  and 320-pixel input; this is slower than the box detector's sample timing.
- The combined webcam check processed 60 frames at 24.3 FPS, detected one
  person outline, and reported 31.0 ms for the latest segmentation call.
  Gesture output was unknown, so this is a pipeline/speed check, not a
  gesture classification accuracy test.
- Full-resolution mask postprocessing is enabled, but low-resolution model
  input limits fine boundaries. The mask describes visible person pixels,
  including clothes; it does not reconstruct an occluded body.
