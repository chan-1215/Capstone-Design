"""Train on the laptop, validate by time blocks, and export Pi inference weights."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler


CLASSES = np.array([-1, 0, 1], np.int8)
MIN_PROBABILITY = 0.75


def fit(x, y):
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=0.1, class_weight="balanced", max_iter=1000)
    model.fit(scaler.transform(x), y)
    return scaler, model


def evaluate(x, y, groups, seconds=None):
    folds = min(5, len(np.unique(groups)))
    if folds < 2:
        raise ValueError("Need at least two distinct 4-second time blocks")
    predictions = np.full(len(y), 9, np.int8)
    probabilities = np.zeros(len(y), np.float32)
    for train, test in GroupKFold(n_splits=folds).split(x, y, groups):
        if seconds is not None:
            start, end = seconds[test].min(), seconds[test].max()
            train = train[(seconds[train] < start - 0.5)
                          | (seconds[train] > end + 0.5)]
        if len(np.unique(y[train])) != len(CLASSES):
            continue
        scaler, model = fit(x[train], y[train])
        scores = model.predict_proba(scaler.transform(x[test]))
        predictions[test] = model.classes_[scores.argmax(axis=1)]
        probabilities[test] = scores.max(axis=1)
    evaluated = predictions != 9
    confusion = np.array([[np.sum(evaluated & (y == actual) & (predictions == predicted))
                           for predicted in CLASSES] for actual in CLASSES])
    recall = np.divide(np.diag(confusion), confusion.sum(axis=1),
                       out=np.full(len(CLASSES), np.nan),
                       where=confusion.sum(axis=1) > 0)
    accepted = evaluated & (probabilities >= MIN_PROBABILITY)
    accuracy = (np.mean(predictions[accepted] == y[accepted])
                if accepted.any() else np.nan)
    return confusion, recall, evaluated.mean(), accepted.mean(), accuracy


def train(dataset_paths, output_path):
    samples = []
    for path in dataset_paths:
        with np.load(path, allow_pickle=False) as data:
            samples.append((data["x"].astype(np.float32),
                            data["y"].astype(np.int8), data["seconds"].copy()))
    x = np.concatenate([sample[0] for sample in samples])
    y = np.concatenate([sample[1] for sample in samples])
    if len(np.unique(y)) != len(CLASSES):
        raise ValueError("Training data must contain left, straight, and right")
    groups = (np.concatenate([np.full(len(sample[1]), index, int)
                              for index, sample in enumerate(samples)])
              if len(samples) > 1 else (samples[0][2] // 4).astype(int))
    confusion, recall, evaluated, coverage, accepted_accuracy = evaluate(
        x, y, groups, samples[0][2] if len(samples) == 1 else None)
    scaler, model = fit(x, y)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validated = (evaluated >= 0.95 and np.all(recall >= 0.85)
                 and coverage >= 0.7 and accepted_accuracy >= 0.9)
    np.savez_compressed(output_path,
                        coef=model.coef_.astype(np.float32),
                        intercept=model.intercept_.astype(np.float32),
                        mean=scaler.mean_.astype(np.float32),
                        scale=scaler.scale_.astype(np.float32),
                        classes=model.classes_.astype(np.int8),
                        min_probability=np.float32(MIN_PROBABILITY),
                        validated=np.bool_(validated))
    report = {
        "datasets": [str(path.resolve()) for path in dataset_paths],
        "samples": int(len(y)),
        "labels_left_straight_right": [int(np.sum(y == label)) for label in CLASSES],
        "confusion_actual_rows_predicted_columns": confusion.tolist(),
        "recall_left_straight_right": [None if np.isnan(value) else float(value)
                                        for value in recall],
        "independently_evaluated_fraction": float(evaluated),
        "accepted_coverage": float(coverage),
        "accepted_accuracy": None if np.isnan(accepted_accuracy) else float(accepted_accuracy),
        "validated_for_driving": bool(validated),
        "validation_method": ("held-out sessions" if len(samples) > 1
                              else "held-out 4-second blocks with 0.5-second embargo"),
    }
    output_path.with_suffix(".report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return confusion, recall, evaluated, coverage, accepted_accuracy, validated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path(__file__).parent / "manual_dataset"
    parser.add_argument("--dataset", type=Path, nargs="+",
                        default=[base / "manual_dataset_20261011.npz"])
    parser.add_argument("--output", type=Path, default=base / "imitation_model_20261011.npz")
    args = parser.parse_args()
    confusion, recall, evaluated, coverage, accuracy, validated = train(args.dataset, args.output)
    print("Held-out time block/session confusion (actual rows / predicted columns: left, straight, right):")
    print(confusion)
    print(f"Recall (NaN = not independently testable): {np.round(recall, 3)}")
    print(f"Independently evaluated fraction: {evaluated:.3f}")
    print(f"At confidence >= {MIN_PROBABILITY:.2f}: coverage={coverage:.3f}, accuracy={accuracy:.3f}")
    if not validated:
        print("NOT VALIDATED: more independent examples are required before driving")
    print(f"Model: {args.output}")


if __name__ == "__main__":
    main()
