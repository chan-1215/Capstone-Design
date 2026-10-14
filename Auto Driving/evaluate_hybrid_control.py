"""Tune an OpenCV P-plus-heading rule on manual labels, with session holdout.

This evaluates steering direction only. It never accesses a Pi or commands motors.
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from road_drive_web import STEER_KP, plan
from road_vision import analyze


GAINS = np.arange(0.0, 0.51, 0.025)
THRESHOLDS = np.arange(2.0, 20.1, 2.0)
CLASSES = (-1, 0, 1)


def load_session(manifest):
    session_name = manifest.stem.removeprefix("manual_dataset_").removesuffix("_quality")
    session = manifest.parent / "raw_sessions" / session_name
    features = []
    labels = []
    with manifest.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            image = session / row["file"]
            frame = cv2.imread(str(image))
            if frame is None:
                raise ValueError(f"Missing frame: {image}")
            reading = analyze(frame)
            if plan(reading, 0, allow_single=True) is None:
                continue
            features.append((reading.center_error, reading.heading_error))
            labels.append(int(row["steer"]))
    return np.asarray(features, np.float32), np.asarray(labels, np.int8)


def predict(features, heading_gain, threshold):
    score = -STEER_KP * features[:, 0] + heading_gain * features[:, 1]
    return np.where(score > threshold, 1,
                    np.where(score < -threshold, -1, 0)).astype(np.int8)


def balanced_recall(labels, predictions):
    recalls = [np.mean(predictions[labels == label] == label)
               for label in CLASSES if np.any(labels == label)]
    return float(np.mean(recalls))


def select_parameters(features, labels):
    candidates = ((balanced_recall(labels, predict(features, gain, threshold)),
                   -gain, -threshold, float(gain), float(threshold))
                  for gain in GAINS for threshold in THRESHOLDS)
    _, _, _, gain, threshold = max(candidates)
    return gain, threshold


def report(labels, predictions):
    confusion = [[int(np.sum((labels == actual) & (predictions == predicted)))
                  for predicted in CLASSES] for actual in CLASSES]
    return confusion, balanced_recall(labels, predictions)


def evaluate(manifests):
    sessions = [load_session(path) for path in manifests]
    for index, manifest in enumerate(manifests):
        train_x = np.concatenate([sample[0] for other, sample in enumerate(sessions)
                                  if other != index])
        train_y = np.concatenate([sample[1] for other, sample in enumerate(sessions)
                                  if other != index])
        test_x, test_y = sessions[index]
        gain, threshold = select_parameters(train_x, train_y)
        predictions = predict(test_x, gain, threshold)
        baseline = predict(test_x, 0.0, threshold)
        matrix, score = report(test_y, predictions)
        _, base_score = report(test_y, baseline)
        straight_count = int(np.sum(test_y == 0))
        false_turns = int(np.sum((test_y == 0) & (predictions != 0)))
        print(f"held_out={manifest.name} samples={len(test_y)} "
              f"train_heading_gain={gain:.3f} train_threshold={threshold:.1f}")
        print(f"  hybrid_balanced_recall={score:.3f} "
              f"center_only_balanced_recall={base_score:.3f}")
        print(f"  false_turns_on_straight={false_turns}/{straight_count}")
        print(f"  confusion_rows_actual_left_straight_right={matrix}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", type=Path, nargs="+")
    args = parser.parse_args()
    if len(args.manifests) < 2:
        parser.error("at least two independent sessions are required")
    evaluate(args.manifests)


if __name__ == "__main__":
    main()
