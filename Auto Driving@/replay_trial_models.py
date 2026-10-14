"""Compare unvalidated imitation models with vision on saved camera frames.

This offline report never opens a camera, network connection, or GPIO device.
"""

import argparse
from collections import Counter
import csv
from pathlib import Path

import cv2

from imitation_features import road_fraction
from imitation_runtime import ImitationModel
from road_vision import analyze


DEFAULT_MODELS = (
    "imitation_model_raw_sessions_20261012.npz",
    "imitation_model_all_20261012.npz",
)


def replay(frames_dir, model_paths, output):
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        raise ValueError(f"No JPEG frames found in {frames_dir}")
    models = [(path, ImitationModel(path, allow_unvalidated=True))
              for path in model_paths]
    counts = Counter()
    with output.open("x", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("frame", "model", "prediction", "confidence",
                         "road_fraction", "opencv_lane", "opencv_surface",
                         "opencv_center_error"))
        for image in frames:
            frame = cv2.imread(str(image))
            if frame is None:
                raise ValueError(f"Invalid frame: {image}")
            road = road_fraction(frame)
            reading = analyze(frame)
            for path, model in models:
                prediction, confidence = model.predict(frame)
                counts[path.name, prediction] += 1
                writer.writerow((image.name, path.name,
                                 "none" if prediction is None else prediction,
                                 round(confidence, 4), round(road, 4),
                                 reading.lane, round(reading.surface, 4),
                                 "" if reading.center_error is None
                                 else round(reading.center_error, 2)))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("--model", type=Path, action="append", dest="models")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    model_paths = args.models or [Path(__file__).parent / "manual_dataset" / name
                                   for name in DEFAULT_MODELS]
    output = args.output or args.frames_dir.parent / f"{args.frames_dir.name}_models.csv"
    counts = replay(args.frames_dir, model_paths, output)
    print(f"Saved {output}")
    for (model, prediction), count in sorted(counts.items(), key=lambda item: str(item[0])):
        print(f"{model}: prediction={prediction}, frames={count}")


if __name__ == "__main__":
    main()
