#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import numpy as np


SEQUENCE_LENGTH = 30
LABELS = ["stop", "go", "unknown"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train a simple KNN gesture classifier from npz samples."
    )
    parser.add_argument(
        "--dataset",
        default=str(Path.home() / "gesture_dataset"),
        help="Dataset directory that contains stop/go/unknown folders",
    )
    parser.add_argument(
        "--output",
        default=str(Path.home() / "gesture_knn_model.npz"),
        help="Output model path",
    )
    return parser.parse_args()


def resample_sequence(array, target_length):
    if len(array) == target_length:
        return array

    old_index = np.linspace(0, len(array) - 1, num=len(array))
    new_index = np.linspace(0, len(array) - 1, num=target_length)
    flat = array.reshape(len(array), -1)
    out = np.zeros((target_length, flat.shape[1]), dtype=np.float32)

    for column in range(flat.shape[1]):
        out[:, column] = np.interp(new_index, old_index, flat[:, column])

    return out.reshape((target_length,) + array.shape[1:])


def normalize_hand(hand):
    hand = hand.astype(np.float32).copy()

    for frame_index in range(hand.shape[0]):
        frame = hand[frame_index]
        wrist = frame[0].copy()
        frame -= wrist

        scale = np.linalg.norm(frame[9])
        if scale < 1e-6:
            scale = np.max(np.linalg.norm(frame, axis=1))
        if scale < 1e-6:
            scale = 1.0

        hand[frame_index] = frame / scale

    return hand


def normalize_pose(pose):
    pose = pose.astype(np.float32).copy()

    for frame_index in range(pose.shape[0]):
        frame = pose[frame_index]
        left_shoulder = frame[0, :3].copy()
        right_shoulder = frame[1, :3].copy()
        center = (left_shoulder + right_shoulder) / 2.0
        scale = np.linalg.norm(left_shoulder - right_shoulder)

        if scale < 1e-6:
            scale = 1.0

        frame[:, :3] = (frame[:, :3] - center) / scale
        pose[frame_index] = frame

    return pose


def make_feature(sample):
    hand = sample["hand"].astype(np.float32)
    pose = sample["pose"].astype(np.float32)

    hand = resample_sequence(hand, SEQUENCE_LENGTH)
    pose = resample_sequence(pose, SEQUENCE_LENGTH)

    hand = normalize_hand(hand)
    pose = normalize_pose(pose)

    return np.concatenate(
        [
            hand.reshape(-1),
            pose.reshape(-1),
        ]
    ).astype(np.float32)


def load_dataset(dataset_dir):
    features = []
    labels = []
    counts = {}

    for label_index, label in enumerate(LABELS):
        label_dir = dataset_dir / label
        files = sorted(label_dir.glob("*.npz"))
        counts[label] = len(files)

        for path in files:
            sample = np.load(path, allow_pickle=True)
            features.append(make_feature(sample))
            labels.append(label_index)

    if not features:
        raise RuntimeError("No npz samples found.")

    return np.asarray(features, dtype=np.float32), np.asarray(labels), counts


def leave_one_out_accuracy(features, labels):
    if len(features) < 2:
        return 0.0

    correct = 0

    for index in range(len(features)):
        train_features = np.delete(features, index, axis=0)
        train_labels = np.delete(labels, index, axis=0)
        test_feature = features[index]

        distances = np.linalg.norm(train_features - test_feature, axis=1)
        nearest_label = train_labels[np.argmin(distances)]

        if nearest_label == labels[index]:
            correct += 1

    return correct / len(features)


def main():
    args = parse_args()
    dataset_dir = Path(args.dataset).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    features, labels, counts = load_dataset(dataset_dir)
    accuracy = leave_one_out_accuracy(features, labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        features=features,
        labels=labels,
        label_names=np.asarray(LABELS),
        sequence_length=np.asarray(SEQUENCE_LENGTH),
    )

    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "labels": LABELS,
                "counts": counts,
                "total_samples": int(len(labels)),
                "leave_one_out_accuracy": float(accuracy),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Training finished.")
    print(f"Dataset: {dataset_dir}")
    print(f"Counts: {counts}")
    print(f"Leave-one-out accuracy: {accuracy:.1%}")
    print(f"Saved model: {output_path}")


if __name__ == "__main__":
    main()
