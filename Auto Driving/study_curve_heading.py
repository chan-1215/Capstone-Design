"""Summarize heading evidence in labeled manual sessions without controlling the Pi."""

import argparse
from collections import defaultdict
import csv
from pathlib import Path
from statistics import median

import cv2

from road_drive_web import plan
from road_vision import analyze


def summarize(manifests):
    samples = defaultdict(list)
    straight_examples = defaultdict(list)
    for manifest in manifests:
        session = manifest.parent / "raw_sessions" / manifest.stem.removeprefix(
            "manual_dataset_")
        with manifest.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                frame = cv2.imread(str(session / row["file"]))
                if frame is None:
                    raise ValueError(f"Missing frame: {session / row['file']}")
                reading = analyze(frame)
                label = int(row["steer"])
                eligible = plan(reading, 0, allow_single=True) is not None
                samples[(manifest.name, label, eligible)].append(reading.heading_error)
                if label == 0 and eligible:
                    straight_examples[manifest.name].append(
                        (abs(reading.heading_error), row["file"], reading.center_error,
                         reading.heading_error, reading.lane))
    for (name, label, eligible), headings in sorted(samples.items()):
        positive = sum(value > 10 for value in headings)
        negative = sum(value < -10 for value in headings)
        print(f"{name} label={label:+d} eligible={eligible} n={len(headings)} "
              f"median={median(headings):+.1f} right_gt10={positive} "
              f"left_lt-10={negative}")
    for name, examples in straight_examples.items():
        print(f"{name} straight_high_heading_examples:")
        for _, filename, center, heading, lane in sorted(examples, reverse=True)[:5]:
            print(f"  {filename} center={center:+.1f} heading={heading:+.1f} lane={lane}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", type=Path, nargs="+")
    args = parser.parse_args()
    summarize(args.manifests)


if __name__ == "__main__":
    main()
