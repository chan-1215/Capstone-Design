"""Train a lightweight drivable / non-drivable image classifier.

Positive samples come from the compact expert-labeled dataset_v2. Negative
samples come from closed-loop runs where the car lost the lane or moved far
away from the target path. The saved model is small enough for Raspberry Pi
runtime safety gating.
"""

import argparse
import csv
import json
import sys
from collections import Counter
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


RUNS_DIR = PROJECT_ROOT / "dataset" / "runs"
DATASET_V2_DIR = PROJECT_ROOT / "dataset_v2"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_PATH = MODEL_DIR / "driveability_v1.npz"
METRICS_PATH = MODEL_DIR / "driveability_v1_metrics.json"

IMAGE_WIDTH = 32
IMAGE_HEIGHT = 18
FEATURE_MODE = "lane_edges"
RIDGE_ALPHA = 2.0
RANDOM_SEED = 2501
VALIDATION_FRACTION = 0.2
DEFAULT_MAX_PER_CLASS = 2500


def parse_float(row, key, default=0.0):
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def image_exists(path):
    return path.exists() and path.is_file()


def load_positive_rows():
    manifest_path = DATASET_V2_DIR / "manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing dataset_v2 manifest: {manifest_path}")

    records = []
    with manifest_path.open(encoding="utf-8", newline="") as manifest_file:
        for row in csv.DictReader(manifest_file):
            image_path = DATASET_V2_DIR / row.get("image_path", "")
            if not image_exists(image_path):
                continue
            records.append({
                "image_path": image_path,
                "label": 1.0,
                "source": row.get("source_run", "dataset_v2"),
                "reason": "expert_labeled",
            })
    return records


def is_negative_row(row):
    cte = abs(parse_float(row, "cross_track_error"))
    heading = abs(parse_float(row, "heading_error"))
    if cte >= 0.75:
        return True
    if row.get("lane_status") == "no_lane" and (cte >= 0.35 or heading >= 1.0):
        return True
    return False


def load_negative_rows():
    records = []
    for run_dir in sorted(RUNS_DIR.glob("run_*")):
        csv_path = run_dir / "driving.csv"
        if not csv_path.exists():
            continue
        with csv_path.open(encoding="utf-8", newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                if not is_negative_row(row):
                    continue
                image_path = run_dir / row.get("image_path", "")
                if not image_exists(image_path):
                    continue
                records.append({
                    "image_path": image_path,
                    "label": 0.0,
                    "source": run_dir.name,
                    "reason": "lane_lost_or_off_path",
                })
    return records


def choose_evenly(records, count):
    if count >= len(records):
        return list(records)
    if count <= 0:
        return []
    indices = np.linspace(0, len(records) - 1, count, dtype=int)
    return [records[index] for index in indices]


def split_records(records):
    rng = np.random.default_rng(RANDOM_SEED)
    order = rng.permutation(len(records))
    validation_count = max(1, int(round(len(records) * VALIDATION_FRACTION)))
    validation_indexes = set(order[:validation_count])

    train = []
    validation = []
    for index, record in enumerate(records):
        if index in validation_indexes:
            validation.append(record)
        else:
            train.append(record)
    return train, validation


def append_features(features, labels, record, augment):
    frame = cv2.imread(str(record["image_path"]))
    if frame is None:
        return

    features.append(extract_steering_features(
        frame,
        IMAGE_WIDTH,
        IMAGE_HEIGHT,
        feature_mode=FEATURE_MODE,
    ))
    labels.append(record["label"])

    if not augment:
        return

    flipped = cv2.flip(frame, 1)
    features.append(extract_steering_features(
        flipped,
        IMAGE_WIDTH,
        IMAGE_HEIGHT,
        feature_mode=FEATURE_MODE,
    ))
    labels.append(record["label"])

    inverted = simulate_inverted_road_surface(frame)
    features.append(extract_steering_features(
        inverted,
        IMAGE_WIDTH,
        IMAGE_HEIGHT,
        feature_mode=FEATURE_MODE,
    ))
    labels.append(record["label"])

    flipped_inverted = cv2.flip(inverted, 1)
    features.append(extract_steering_features(
        flipped_inverted,
        IMAGE_WIDTH,
        IMAGE_HEIGHT,
        feature_mode=FEATURE_MODE,
    ))
    labels.append(record["label"])


def load_features(records, augment):
    features = []
    labels = []
    for record in records:
        append_features(features, labels, record, augment)
    return (
        np.asarray(features, dtype=np.float32),
        np.asarray(labels, dtype=np.float32),
    )


def fit_ridge_classifier(x_train, y_train):
    feature_mean = x_train.mean(axis=0)
    feature_std = x_train.std(axis=0)
    feature_std[feature_std < 1e-5] = 1.0

    normalized = (x_train - feature_mean) / feature_std
    normalized = np.column_stack([normalized, np.ones(len(normalized), dtype=np.float32)])
    regularizer = np.eye(normalized.shape[1], dtype=np.float32) * RIDGE_ALPHA
    regularizer[-1, -1] = 0.0
    weights = np.linalg.solve(
        normalized.T @ normalized + regularizer,
        normalized.T @ y_train,
    )
    return weights, feature_mean, feature_std


def predict_probability(x, weights, feature_mean, feature_std):
    normalized = (x - feature_mean) / feature_std
    normalized = np.column_stack([normalized, np.ones(len(normalized), dtype=np.float32)])
    return np.clip(normalized @ weights, 0.0, 1.0)


def metrics(probability, target, threshold):
    predicted = probability >= threshold
    actual = target >= 0.5
    tp = int(np.sum(predicted & actual))
    tn = int(np.sum(~predicted & ~actual))
    fp = int(np.sum(predicted & ~actual))
    fn = int(np.sum(~predicted & actual))
    accuracy = (tp + tn) / max(1, len(actual))
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    negative_recall = tn / max(1, tn + fp)
    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "drivable_recall": float(recall),
        "negative_recall": float(negative_recall),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-per-class", type=int, default=DEFAULT_MAX_PER_CLASS)
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    positive = load_positive_rows()
    negative = load_negative_rows()
    if not positive:
        raise RuntimeError("no positive samples found")
    if not negative:
        raise RuntimeError("no negative samples found")

    selected_count = min(args.max_per_class, len(positive), len(negative))
    selected = (
        choose_evenly(positive, selected_count)
        + choose_evenly(negative, selected_count)
    )

    source_counts = Counter(record["source"] for record in selected)
    reason_counts = Counter(record["reason"] for record in selected)
    label_counts = Counter(int(record["label"]) for record in selected)
    summary = {
        "positive_candidates": len(positive),
        "negative_candidates": len(negative),
        "selected_per_class": selected_count,
        "selected_label_counts": dict(label_counts),
        "selected_reason_counts": dict(reason_counts),
        "selected_source_counts": dict(source_counts),
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return

    train_records, validation_records = split_records(selected)
    x_train, y_train = load_features(train_records, augment=True)
    x_validation, y_validation = load_features(validation_records, augment=True)

    weights, feature_mean, feature_std = fit_ridge_classifier(x_train, y_train)
    probability = predict_probability(x_validation, weights, feature_mean, feature_std)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MODEL_PATH,
        weights=weights,
        feature_mean=feature_mean,
        feature_std=feature_std,
        threshold=args.threshold,
        feature_mode=FEATURE_MODE,
        input_polarity="auto_dark_road",
        image_width=IMAGE_WIDTH,
        image_height=IMAGE_HEIGHT,
    )

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        **summary,
        "train_rows": len(train_records),
        "validation_rows": len(validation_records),
        "training_samples_augmented": int(len(x_train)),
        "validation_samples_augmented": int(len(x_validation)),
        "threshold": args.threshold,
        "feature_mode": FEATURE_MODE,
        "model_path": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        **metrics(probability, y_validation, args.threshold),
    }
    METRICS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
