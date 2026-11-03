# Auto Driving (steering-servo robot)

This folder preserves the post-steering-linkage autonomous-driving work from
the local `Steering robot test` workspace as of 2026-10-14. It is a **PC
snapshot**, not an automatically deployed Raspberry Pi image. Read
[`HANDOFF.md`](HANDOFF.md) before changing the controller or testing hardware.

## Project boundaries

- This robot uses two DC motor channels and a separate steering servo. Its
  GPIO mapping is defined in `road_drive_web.py`; do not assume it matches
  `Lee/motor_module.py`, `Driving test`, or `Dataset Project`.
- The camera/OpenCV/P-controller is the live autonomous-driving path.
  Manual-driving datasets and imitation models are experimental analysis
  material; `road_drive_web.py` does **not** load an imitation model.
- `--gesture` adds a display-only recognition tab. It does not command motors.
  The KNN artifact is not copied here; see `Lee/gesture/` for the separately
  maintained gesture model and its provenance.
- No uninterrupted autonomous lap has been established by the saved tests.
  Short physical trials reached curves but also stopped on uncertain vision,
  low road coverage, or course features. Do not describe this as validated
  full-course autonomous driving.

## Code map

| Area | Files | Purpose |
| --- | --- | --- |
| Runtime | `road_drive_web.py`, `road_camera_web.py`, `road_vision.py`, `camera_test.py` | Bounded motor/servo control, Flask UI, road detection, CSI camera. |
| Optional gesture UI | `gesture_recognition_module.py`, `hand_utils.py` | Show MediaPipe + KNN result when `--gesture` is enabled; requires an external model file. |
| Manual-data analysis | `collect_manual_raw.py`, `extract_manual_demo.py`, `build_manual_dataset.py`, `build_raw_session_dataset.py`, `imitation_features.py`, `imitation_runtime.py`, `train_manual_model.py` | Collect, derive, and evaluate manual-control examples; not live motor control. |
| Offline diagnostics | `analyze_label_alignment.py`, `evaluate_hybrid_control.py`, `extract_overhead_path.py`, `replay_road_vision.py`, `replay_trial_models.py`, `shadow_manual_model.py`, `study_curve_heading.py` | Compare predictions and inspect recorded trials without changing the Pi controller. |
| Test support | `overhead_guard.py`, `record_overhead_trial.py`, `capture_boundary_view.py`, `hardware_test.py` | Observed trials, data capture, and explicitly invoked hardware checks. |
| Verification | `test_*.py`, `test_fixtures/*.jpg` | PC-side regression tests and small track-image fixtures. |

## Running and testing

On a Raspberry Pi with the known steering-servo wiring, CSI camera, system
`rpicam-vid` or `libcamera-vid`, and a Python environment with NumPy, OpenCV,
Flask, Werkzeug, and GPIO Zero:

```bash
cd 'Auto Driving'
python road_drive_web.py --forward-speed 0.22 --run-seconds 5
```

The UI is at `http://<pi-ip>:5001/`. Starting the server does not itself
start a drive; a user action is required. The 5-second example is a bounded
test, not a recommended unattended run. Use `--collection-only` for manual
control/recording with autonomous start disabled. Optional `--gesture`
requires MediaPipe and `/home/pi/gesture_knn_model.npz`; its output is
display-only. Do not run two programs against the same CSI camera or GPIO.

For PC-only verification, install NumPy, OpenCV, Flask, and Werkzeug, then:

```bash
python -m unittest discover -s . -p 'test_*.py'
```

The tests mock GPIO or use saved images; a passing suite is **not** a
physical-driving safety certification. `hardware_test.py` is a separate
explicit hardware tool and must not be part of unattended automation.

## Data and publishing

The two small `manual_demo_20261011*.csv` files are extracted observations,
not synchronized motor-command ground truth. Raw camera frames, videos,
session datasets, trained imitation-model artifacts, browser profiles, and
presentation exports are deliberately excluded. The original local
`Steering robot test/manual_dataset/` remains on the PC. Rebuilding a
particular analysis result requires its separately retained source session.
Do not commit raw recordings or credentials without a team review.
