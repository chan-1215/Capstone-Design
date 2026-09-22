"""Train steering_v2 from the compact balanced dataset_v2 manifest."""

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
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

DATASET_DIR = PROJECT_ROOT / "dataset_v2"
MANIFEST_PATH = DATASET_DIR / "manifest.csv"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_PATH = MODEL_DIR / "steering_v2.npz"
METRICS_PATH = MODEL_DIR / "steering_v2_metrics.json"

IMAGE_WIDTH = 32
IMAGE_HEIGHT = 18
FEATURE_MODE = "grayscale"
RIDGE_ALPHA = 3.0
VALIDATION_FRACTION = 0.2
RANDOM_SEED = 2402
OUTPUT_CLIP_MARGIN = 0.02


def extract_features(frame):
    return extract_steering_features(
        frame,
        IMAGE_WIDTH,
        IMAGE_HEIGHT,
        feature_mode=FEATURE_MODE,
    )


def load_manifest():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"missing dataset manifest: {MANIFEST_PATH}")

    rows = []
    with MANIFEST_PATH.open(encoding="utf-8", newline="") as manifest_file:
        for row in csv.DictReader(manifest_file):
            image_path = DATASET_DIR / row["image_path"]
            if not image_path.exists():
                continue
            rows.append(row)
    if not rows:
        raise RuntimeError("dataset_v2 manifest has no usable rows")
    return rows


def stratified_split(rows):
    rng = np.random.default_rng(RANDOM_SEED)
    by_lane = defaultdict(list)
    for row in rows:
        by_lane[row.get("target_lane", "")].append(row)

    train_rows = []
    validation_rows = []
    for lane_rows in by_lane.values():
        order = rng.permutation(len(lane_rows))
        validation_count = max(1, int(round(len(lane_rows) * VALIDATION_FRACTION)))
        validation_indexes = set(order[:validation_count])
        for index, row in enumerate(lane_rows):
            if index in validation_indexes:
                validation_rows.append(row)
            else:
                train_rows.append(row)

    return train_rows, validation_rows


def append_sample(features, targets, lanes, frame, left_pwm, right_pwm, lane):
    features.append(extract_features(frame))
    targets.append([left_pwm, right_pwm])
    lanes.append(lane)


def load_features(rows, augment_mirror, augment_polarity):
    features = []
    targets = []
    lanes = []

    for row in rows:
        frame = cv2.imread(str(DATASET_DIR / row["image_path"]))
        if frame is None:
            continue

        left_pwm = float(row["left_pwm"])
        right_pwm = float(row["right_pwm"])
        lane = row.get("target_lane", "")

        append_sample(features, targets, lanes, frame, left_pwm, right_pwm, lane)

        if augment_mirror:
            flipped = cv2.flip(frame, 1)
            append_sample(features, targets, lanes, flipped, right_pwm, left_pwm, lane)

        if augment_polarity:
            inverted = simulate_inverted_road_surface(frame)
            append_sample(features, targets, lanes, inverted, left_pwm, right_pwm, lane)

            if augment_mirror:
                flipped_inverted = cv2.flip(inverted, 1)
                append_sample(
                    features,
                    targets,
                    lanes,
                    flipped_inverted,
                    right_pwm,
                    left_pwm,
                    lane,
                )

    return (
        np.asarray(features, dtype=np.float32),
        np.asarray(targets, dtype=np.float32),
        np.asarray(lanes),
    )


def fit_ridge(x_train, y_train):
    feature_mean = x_train.mean(axis=0)
    feature_std = x_train.std(axis=0)
    feature_std[feature_std < 1e-5] = 1.0

    x_train_normalized = (x_train - feature_mean) / feature_std
    x_train_normalized = np.column_stack(
        [x_train_normalized, np.ones(len(x_train_normalized), dtype=np.float32)]
    )

    regularizer = np.eye(x_train_normalized.shape[1], dtype=np.float32) * RIDGE_ALPHA
    regularizer[-1, -1] = 0.0
    weights = np.linalg.solve(
        x_train_normalized.T @ x_train_normalized + regularizer,
        x_train_normalized.T @ y_train,
    )
    return weights, feature_mean, feature_std


def output_limits(targets):
    output_min = np.maximum(targets.min(axis=0) - OUTPUT_CLIP_MARGIN, 0.0)
    output_max = np.minimum(targets.max(axis=0) + OUTPUT_CLIP_MARGIN, 0.85)

    steering = targets[:, 1] - targets[:, 0]
    steering_min = max(float(steering.min()) - OUTPUT_CLIP_MARGIN, -0.85)
    steering_max = min(float(steering.max()) + OUTPUT_CLIP_MARGIN, 0.85)
    return output_min, output_max, steering_min, steering_max


def apply_output_limits(prediction, output_min, output_max, steering_min, steering_max):
    limited = np.clip(prediction, output_min, output_max)
    average_pwm = np.mean(limited, axis=1)
    steering = np.clip(limited[:, 1] - limited[:, 0], steering_min, steering_max)
    limited[:, 0] = average_pwm - steering / 2.0
    limited[:, 1] = average_pwm + steering / 2.0
    return np.clip(limited, output_min, output_max)


def predict(x, weights, feature_mean, feature_std):
    normalized = (x - feature_mean) / feature_std
    normalized = np.column_stack(
        [normalized, np.ones(len(normalized), dtype=np.float32)]
    )
    return normalized @ weights


def error_metrics(prediction, target):
    wheel_mae = np.mean(np.abs(prediction - target), axis=0)
    steering_prediction = prediction[:, 1] - prediction[:, 0]
    steering_target = target[:, 1] - target[:, 0]
    steering_mae = float(np.mean(np.abs(steering_prediction - steering_target)))
    return {
        "left_pwm_mae": float(wheel_mae[0]),
        "right_pwm_mae": float(wheel_mae[1]),
        "steering_mae": steering_mae,
    }


def lane_metrics(prediction, target, lanes):
    results = {}
    for lane in sorted(set(lanes)):
        mask = lanes == lane
        if not np.any(mask):
            continue
        results[lane] = error_metrics(prediction[mask], target[mask])
        results[lane]["samples"] = int(np.sum(mask))
    return results


def main():
    rows = load_manifest()
    train_rows, validation_rows = stratified_split(rows)

    x_train, y_train, train_lanes = load_features(
        train_rows,
        augment_mirror=True,
        augment_polarity=True,
    )
    x_validation, y_validation, validation_lanes = load_features(
        validation_rows,
        augment_mirror=True,
        augment_polarity=True,
    )

    weights, feature_mean, feature_std = fit_ridge(x_train, y_train)
    output_min, output_max, steering_min, steering_max = output_limits(y_train)
    prediction = apply_output_limits(
        predict(x_validation, weights, feature_mean, feature_std),
        output_min,
        output_max,
        steering_min,
        steering_max,
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MODEL_PATH,
        weights=weights,
        feature_mean=feature_mean,
        feature_std=feature_std,
        output_min=output_min,
        output_max=output_max,
        steering_min=steering_min,
        steering_max=steering_max,
        feature_mode=FEATURE_MODE,
        input_polarity="auto_dark_road",
        image_width=IMAGE_WIDTH,
        image_height=IMAGE_HEIGHT,
    )

    metrics = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_manifest": str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
        "source_rows": len(rows),
        "source_rows_by_lane": dict(Counter(row.get("target_lane", "") for row in rows)),
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "training_samples_augmented": int(len(x_train)),
        "validation_samples_augmented": int(len(x_validation)),
        "polarity_augmentation": True,
        "input_polarity": "auto_dark_road",
        "feature_mode": FEATURE_MODE,
        "model_path": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        "output_min": output_min.tolist(),
        "output_max": output_max.tolist(),
        "steering_min": steering_min,
        "steering_max": steering_max,
        **error_metrics(prediction, y_validation),
        "lane_metrics": lane_metrics(prediction, y_validation, validation_lanes),
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
