# Pi Comparison Check: 2026-10-20

## Scope And Runtime

Owner explicitly selected DESK execution checks, not a track test or motion.
Pi: pi@192.168.137.60, Python3.11.17, OpenCV4.11.0, NumPy1.26.4.
Uploaded only hough_vision.py, compare_vision.py and their two test files.
Existing perception/controller, gesture, camera source and motor settings were
not modified. All304 Python tests passed on Pi after upload.

The old driving Flask and camera are OFF. No GPIO/motor commands were sent.
Only a static report server is running, PID2088, port5002:

http://192.168.137.60:5002/

This is a SAVED-SNAPSHOT comparison, not live video or a driving interface.
It serves only outputs/hough_desk_20261020T121810Z/, not the project/home folder.
Process details/log are in outputs/hough_desk_20261020T121810Z_server.json
and the corresponding _server.log. Verify the current PID/command before
stopping it; do not assume the recorded PID survives a reboot.

## Evidence

Used existing PiCameraSource under the same exclusive camera lock as Flask.
Captured960x720, requested30FPS, rotated180degrees to the existing orientation.
After2seconds of warmup, saved6 frames approximately0.5seconds apart, then
closed the camera and rpicam process. Observed delivery_fps=30.0 from rpicam.
This is delivery rate, not inference FPS or exposure-to-browser latency.

Raw oriented captures and metadata:

captures/comparison_20261020T121810Z/

PNG preserves the decoded BGR pixels, not sensor RAW. The rpicam bridge used
MJPEG before PNG saving. Current scene is a desk, not the track.

Compared current segmentation/path and6 Hough profiles (480/320, blur0/3/5)
on those identical6 inputs. Current baseline480, ROI top=.20; no reference or
heading calibration supplied; no BEV. OpenCV threads=2 for this comparison
process only. No valid current paths and no two-sided Hough groups appeared.
Some one-sided spurious segments exist: do not claim absence of false positives
or improved track accuracy from this negative desk scene.

Results, stages, timings and source/code hashes:

outputs/hough_desk_20261020T121810Z/index.html
outputs/hough_desk_20261020T121810Z/report.json

The page and an actual comparison image were checked; PC HTTP access returned
200. No track placement, corner following, lap or motor-stop test occurred.
The earlier manual-control stop fault is still unresolved.

## Repeat Offline Analysis

From this project directory, with a NEW output directory:

```bash
./.venv/bin/python -B compare_vision.py captures/comparison_20261020T121810Z/frame_000_raw.png --output outputs/hough_new_RUN
```

For later track checks, obtain fresh stationary raw frames first. Do not use
desk data, processed overlays or screen recordings as track validation.
Do not connect Hough midpoint outputs to the motor controller: one curved
boundary can produce both image-side groups, and missing groups yield no target.
Any future motion requires a separate supervised readiness confirmation.
