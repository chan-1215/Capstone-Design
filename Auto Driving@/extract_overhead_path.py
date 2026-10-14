"""Extract a robot path from a fixed overhead recording. Never controls hardware."""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from overhead_guard import track_margin


def background(video, count):
    indices = np.linspace(max(1, count // 10), count - 1,
                          min(15, max(2, count // 10)), dtype=int)
    frames = []
    for index in indices:
        video.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = video.read()
        if ok and frame.mean() > 30:
            frames.append(frame)
    if len(frames) < 3:
        raise ValueError("Not enough illuminated frames for a background")
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def locate(frame, reference, previous=None, gap=1):
    if frame.mean() < 30:
        return None
    diff = cv2.cvtColor(cv2.absdiff(frame, reference), cv2.COLOR_BGR2GRAY)
    mask = cv2.threshold(diff, 35, 255, cv2.THRESH_BINARY)[1]
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        if (area >= 200 and 25 <= width <= 180 and 25 <= height <= 180
                and 0.08 * frame.shape[1] <= x <= 0.95 * frame.shape[1]
                and 0.05 * frame.shape[0] <= y <= 0.91 * frame.shape[0]):
            candidates.append((area, x + width / 2, y + height / 2))
    if not candidates:
        return None
    if previous is not None:
        nearby = [candidate for candidate in candidates
                  if np.hypot(candidate[1] - previous[0],
                              candidate[2] - previous[1]) <= 35 * gap + 10]
        if not nearby:
            return None
        area, x, y = min(nearby, key=lambda candidate: np.hypot(
            candidate[1] - previous[0], candidate[2] - previous[1]))
    else:
        area, x, y = max(candidates)
    return x, y, area


def extract(video_path, output):
    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise ValueError(f"Cannot read {video_path}")
    timestamps = video_path.with_suffix(".csv")
    try:
        with timestamps.open(newline="", encoding="utf-8") as file:
            times = [float(row["pc_unix_time"]) for row in csv.DictReader(file)]
        reference = background(video, len(times))
        video.set(cv2.CAP_PROP_POS_FRAMES, 0)
        output.parent.mkdir(parents=True, exist_ok=True)
        detected = 0
        previous = None
        previous_index = None
        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("frame", "pc_unix_time", "x", "y", "change_area",
                             "track_margin"))
            for index, when in enumerate(times):
                ok, frame = video.read()
                if not ok:
                    raise ValueError(f"Video ended at frame {index}")
                gap = index - previous_index if previous_index is not None else 1
                point = locate(frame, reference, previous, gap)
                margin = track_margin(frame, point[:2]) if point else None
                writer.writerow((index, f"{when:.6f}", *point,
                                 f"{margin:.3f}" if margin is not None else "")
                                if point else (index, f"{when:.6f}", "", "", "", ""))
                detected += point is not None
                if point is not None:
                    previous = point[:2]
                    previous_index = index
        return detected, len(times)
    finally:
        video.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.video.with_name(args.video.stem + "_path.csv")
    detected, total = extract(args.video, output)
    print(f"Detected {detected}/{total} frames: {output}")


if __name__ == "__main__":
    main()
