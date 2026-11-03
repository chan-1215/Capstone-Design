# Pi4 dataset file

Last updated: 2026-09-22

This document is the entry point for continuing the Raspberry Pi 4 autonomous-driving work.

## Included in Git

- `Driving test/`: Raspberry Pi 4 motor tests, OpenCV P-control driving, and dataset-model driving.
- `Driving test/models/`: deployable steering and driveability models.
- `Dataset Project/controllers/`: Webots collection and driving controllers.
- `Dataset Project/training/`: compact-dataset builders, training, and evaluation scripts.
- `Dataset Project/worlds/` and `protos/`: three-lane and polarity-test simulations.
- `Dataset Project/models/`: trained model files and metrics.
- `Dataset Project/dataset_v2/`: final compact dataset, 9,000 images, tracked with Git LFS.
- `Dataset Project/reports/`: final closed-loop evaluation reports.
- `Lee/lane_tracking_module.py`: normal/inverted lane-polarity support and pixel fallback.
- `Lee/motor_module.py`: verified motor grouping for the earlier robot.

## Dataset summary

- Final compact dataset: `Dataset Project/dataset_v2/`
- Total samples: 9,000
- Lane balance: lane 1 = 3,000, lane 2 = 3,000, lane 3 = 3,000
- Labels: `expert_command` = 8,500, `expert_reference` = 500
- Manifest: `Dataset Project/dataset_v2/manifest.csv`
- Dataset summary: `Dataset Project/dataset_v2/summary.json`

The full raw Webots captures are intentionally not committed. They contain more than 200,000 files and use about 1.5 GB. The local source is `Dataset Project/dataset/runs/`. Preserve that directory separately when retraining or rebuilding the compact dataset.

## Raspberry Pi 4 runtime

The current Pi 4 runtime is isolated in `Driving test/`. The dataset is used through the trained `.npz` models; raw images are not loaded while driving.

Motor-only check, with the robot lifted:

```bash
cd ~/Capstone-Design/Driving\ test
python3 motor_test_pdf.py each --speed 0.35 --duration 1.0
```

Camera/model dry run:

```bash
python3 road_drive_dataset.py --dry-run --camera rpicam --duration 10
```

Short real drive:

```bash
python3 road_drive_dataset.py --camera rpicam --duration 20 --max-pwm 0.45
```

Current Pi 4 motor calibration in `Driving test/motor_module.py`:

- motor 1, right front: trim 0.75
- motor 2, right rear: trim 1.00
- motor 3, left front: trim 1.00
- motor 4, left rear: trim 1.00

Confirm GPIO direction with the lifted motor test whenever the robot wiring changes.

## Models and results

- Steering model: `Dataset Project/models/steering_v2.npz`
- Driveability model: `Dataset Project/models/driveability_v1.npz`
- Steering validation MAE: 0.0439986661
- Driveability validation accuracy: 0.9595
- Normal-polarity Webots test: pass, mean absolute CTE 0.04073 m
- Inverted-polarity Webots test: pass, mean absolute CTE 0.04790 m

## Verification

From `Dataset Project/`:

```powershell
python -B -m unittest discover -s tests -v
python -B training/evaluate_drive_run.py run_20260901_172142 run_20260901_172316
```

Read `AGENTS.md`, `Dataset Project/HANDOFF.md`, and `Driving test/README.md` before changing GPIO or driving behavior. No password is stored in this repository.
