"""Train a small image-to-wheel-PWM model from recorded Webots runs."""

import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from controllers.vision_preprocessing import (  # noqa: E402
    extract_steering_features,
    simulate_inverted_road_surface,
)

RUNS_DIR = PROJECT_ROOT / "dataset" / "runs"
MODEL_DIR = PROJECT_ROOT / "models"
IMAGE_WIDTH = 32
IMAGE_HEIGHT = 18
MAX_SOURCE_SAMPLES = 3500
RIDGE_ALPHA = 3.0
RANDOM_SEED = 1215


def find_latest_expert_run():
    candidates = sorted(RUNS_DIR.glob("run_*"), reverse=True)
    for run_dir in candidates:
        csv_path = run_dir / "driving.csv"
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as file:
                rows = [row for row in csv.DictReader(file)
                        if row.get("control_mode") == "expert"]
            if rows:
                return run_dir, rows
    raise RuntimeError("No expert dataset run found")


def extract_features(frame):
    return extract_steering_features(frame, IMAGE_WIDTH, IMAGE_HEIGHT)


def load_samples(run_dir, rows):
    if len(rows) > MAX_SOURCE_SAMPLES:
        indices = np.linspace(0, len(rows) - 1, MAX_SOURCE_SAMPLES, dtype=int)
        rows = [rows[index] for index in indices]

    features = []
    targets = []
    for row in rows:
        frame = cv2.imread(str(run_dir / row["image_path"]))
        if frame is None:
            continue

        left_pwm = float(row["left_pwm"])
        right_pwm = float(row["right_pwm"])
        features.append(extract_features(frame))
        targets.append([left_pwm, right_pwm])

        # The source track turns left only. Horizontal mirroring supplies the
        # corresponding right-turn image while swapping wheel targets.
        flipped = cv2.flip(frame, 1)
        features.append(extract_features(flipped))
        targets.append([right_pwm, left_pwm])

        inverted = simulate_inverted_road_surface(frame)
        features.append(extract_features(inverted))
        targets.append([left_pwm, right_pwm])

        flipped_inverted = cv2.flip(inverted, 1)
        features.append(extract_features(flipped_inverted))
        targets.append([right_pwm, left_pwm])

    return np.asarray(features, dtype=np.float32), np.asarray(targets, dtype=np.float32)


def main():
    run_dir, rows = find_latest_expert_run()
    x, y = load_samples(run_dir, rows)

    rng = np.random.default_rng(RANDOM_SEED)
    order = rng.permutation(len(x))
    split = int(len(x) * 0.8)
    train_indices = order[:split]
    validation_indices = order[split:]
    x_train, y_train = x[train_indices], y[train_indices]
    x_validation, y_validation = x[validation_indices], y[validation_indices]

    feature_mean = x_train.mean(axis=0)
    feature_std = x_train.std(axis=0)
    feature_std[feature_std < 1e-5] = 1.0
    x_train = (x_train - feature_mean) / feature_std
    x_validation = (x_validation - feature_mean) / feature_std

    x_train = np.column_stack([x_train, np.ones(len(x_train), dtype=np.float32)])
    x_validation = np.column_stack([x_validation, np.ones(len(x_validation), dtype=np.float32)])

    regularizer = np.eye(x_train.shape[1], dtype=np.float32) * RIDGE_ALPHA
    regularizer[-1, -1] = 0.0
    weights = np.linalg.solve(
        x_train.T @ x_train + regularizer,
        x_train.T @ y_train,
    )

    prediction = np.clip(x_validation @ weights, 0.0, 1.0)
    wheel_mae = np.mean(np.abs(prediction - y_validation), axis=0)
    steering_prediction = prediction[:, 1] - prediction[:, 0]
    steering_target = y_validation[:, 1] - y_validation[:, 0]
    steering_mae = float(np.mean(np.abs(steering_prediction - steering_target)))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "steering_v1.npz"
    np.savez_compressed(
        model_path,
        weights=weights,
        feature_mean=feature_mean,
        feature_std=feature_std,
        image_width=IMAGE_WIDTH,
        image_height=IMAGE_HEIGHT,
    )

    metrics = {
        "source_run": run_dir.name,
        "source_rows": len(rows),
        "training_samples_augmented": int(len(x_train)),
        "validation_samples": int(len(x_validation)),
        "polarity_augmentation": True,
        "left_pwm_mae": float(wheel_mae[0]),
        "right_pwm_mae": float(wheel_mae[1]),
        "steering_mae": steering_mae,
        "model_path": str(model_path.relative_to(PROJECT_ROOT)),
    }
    (MODEL_DIR / "steering_v1_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
