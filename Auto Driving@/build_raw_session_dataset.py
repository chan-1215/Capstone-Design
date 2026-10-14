"""Convert one synchronized laptop recording into a training dataset."""

import argparse
from bisect import bisect_left, bisect_right
import csv
from math import sqrt
from pathlib import Path

import cv2
import numpy as np

from build_manual_dataset import stable_actions
from imitation_features import features, road_fraction


def load_overhead_quality(path, margin_factor=0.45):
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows or "track_margin" not in rows[0]:
        raise ValueError("Overhead path needs track-margin measurements")
    times = [float(row["pc_unix_time"]) for row in rows]
    safe = [bool(row["track_margin"] and row["change_area"]
                 and float(row["track_margin"]) >=
                 margin_factor * sqrt(float(row["change_area"])))
            for row in rows]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("Overhead timestamps must increase")
    return times, safe


def overhead_safe(sample_time, quality, context=0.3):
    times, safe = quality
    start = bisect_left(times, sample_time - context)
    end = bisect_right(times, sample_time + context)
    return (end - start >= 2 and times[start] <= sample_time - context + 0.11
            and times[end - 1] >= sample_time + context - 0.11
            and all(safe[start:end]))


def build(session, output_dir, min_road=0.5, overhead_path=None):
    with (session / "frames.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError("Empty recording manifest")
    actions = []
    for row in rows:
        if row["manual_valid"] != "1" or int(row["throttle"]) != 1:
            actions.append(None)
        else:
            steer = float(row["steer"])
            actions.append(-1 if steer < -0.5 else (1 if steer > 0.5 else 0))
    stable = stable_actions(actions, radius=1)
    quality = load_overhead_quality(overhead_path) if overhead_path else None
    selected = []
    first_time = float(rows[0]["pi_frame_at"])
    for row, label in zip(rows, stable):
        if label is None:
            continue
        if quality is not None and not overhead_safe(float(row["pc_received_at"]),
                                                     quality):
            continue
        filename = session / row["file"]
        frame = cv2.imread(str(filename))
        if frame is None:
            raise ValueError(f"Missing or invalid frame: {filename}")
        coverage = road_fraction(frame)
        if coverage < min_road:
            continue
        selected.append((row["file"], float(row["pi_frame_at"]) - first_time,
                         label, coverage, features(frame)))
    if not selected:
        raise ValueError("No stable forward-driving samples found")
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_quality" if overhead_path else ""
    dataset = output_dir / f"manual_dataset_{session.name}{suffix}.npz"
    manifest = output_dir / f"manual_dataset_{session.name}{suffix}.csv"
    np.savez_compressed(dataset,
                        x=np.stack([row[4] for row in selected]),
                        y=np.array([row[2] for row in selected], np.int8),
                        seconds=np.array([row[1] for row in selected], np.float32),
                        source=session.name)
    with manifest.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("file", "seconds", "steer", "road_fraction"))
        writer.writerows((filename, round(seconds, 3), label, round(coverage, 3))
                         for filename, seconds, label, coverage, _ in selected)
    return dataset, manifest, {label: sum(row[2] == label for row in selected)
                               for label in (-1, 0, 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "manual_dataset")
    parser.add_argument("--overhead-path", type=Path,
                        help="Optional overhead path CSV; keep only clearly on-track frames")
    args = parser.parse_args()
    dataset, manifest, counts = build(args.session, args.output_dir,
                                      overhead_path=args.overhead_path)
    print(f"Dataset: {dataset}")
    print(f"Manifest: {manifest}")
    print(f"Forward labels (left/straight/right): {counts}")


if __name__ == "__main__":
    main()
