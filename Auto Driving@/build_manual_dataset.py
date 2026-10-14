"""Build a compact, forward-only imitation dataset from the manual recording."""

import argparse
import csv
import hashlib
from pathlib import Path

import cv2
import numpy as np

from extract_manual_demo import BUTTONS, highlighted, open_video
from imitation_features import features, road_fraction


DEFAULT_VIDEO = Path.home() / "Downloads" / "녹음 2026-10-11 211631.mp4"


def action(keys):
    if not keys["w"] or keys["s"] or (keys["a"] and keys["d"]):
        return None
    return -1 if keys["a"] else (1 if keys["d"] else 0)


def stable_actions(actions, radius=3):
    result = []
    for index, label in enumerate(actions):
        lo, hi = max(0, index - radius), min(len(actions), index + radius + 1)
        result.append(label if label is not None and all(
            value == label for value in actions[lo:hi]) else None)
    return result


def build(video_path, output_dir, sample_every=2, min_road=0.5,
          dataset_id="20261011"):
    video = open_video(video_path)
    shape = (round(video.get(cv2.CAP_PROP_FRAME_WIDTH)),
             round(video.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if shape not in {(1270, 1314), (1266, 1364)}:
        video.release()
        raise ValueError("Unsupported manual screen recording dimensions")
    fps = video.get(cv2.CAP_PROP_FPS)
    if not 20 <= fps <= 60:
        video.release()
        raise ValueError(f"Unexpected recording frame rate: {fps}")
    samples = []
    actions = []
    while True:
        ok, frame = video.read()
        if not ok:
            break
        keys = {key: highlighted(frame, *point) for key, point in BUTTONS.items()}
        label = action(keys)
        actions.append(label)
        if label is not None and (len(actions) - 1) % sample_every == 0:
            samples.append((len(actions) - 1, road_fraction(frame, True),
                            features(frame, True)))
    video.release()
    stable = stable_actions(actions)
    selected = []
    for index, coverage, vector in samples:
        if stable[index] is None:
            continue
        if coverage < min_road:
            continue
        selected.append((index, stable[index], coverage, vector))
    if not selected:
        raise ValueError("No stable forward-driving samples found")
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = output_dir / f"manual_dataset_{dataset_id}.npz"
    manifest = output_dir / f"manual_dataset_{dataset_id}.csv"
    hasher = hashlib.sha256()
    with video_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    np.savez_compressed(dataset,
                        x=np.stack([row[3] for row in selected]),
                        y=np.array([row[1] for row in selected], np.int8),
                        seconds=np.array([row[0] / fps for row in selected], np.float32),
                        source_sha256=digest)
    with manifest.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("frame", "seconds", "steer", "road_fraction"))
        writer.writerows((index, round(index / fps, 3), label, round(coverage, 3))
                         for index, label, coverage, _ in selected)
    return dataset, manifest, {label: sum(row[1] == label for row in selected)
                               for label in (-1, 0, 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "manual_dataset")
    parser.add_argument("--dataset-id", default="20261011")
    parser.add_argument("--min-road", type=float, default=0.5)
    args = parser.parse_args()
    if not args.dataset_id.isdigit() or not 0 <= args.min_road <= 1:
        parser.error("dataset-id must be numeric and min-road must be 0..1")
    dataset, manifest, counts = build(args.video, args.output_dir,
                                      min_road=args.min_road,
                                      dataset_id=args.dataset_id)
    print(f"Dataset: {dataset}")
    print(f"Manifest: {manifest}")
    print(f"Forward labels (left/straight/right): {counts}")


if __name__ == "__main__":
    main()
