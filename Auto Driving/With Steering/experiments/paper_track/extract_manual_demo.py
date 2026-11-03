"""Extract this recording's highlighted manual keys and displayed road target.

The fixed screen coordinates are for the 1270x1314 Flask recording only.
The overhead red-object track is a review aid, not a driving ground truth.
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


BUTTONS = {"w": (1010, 955), "a": (900, 1045),
           "d": (1118, 1045), "s": (1010, 1135)}


def open_video(path):
    video = cv2.VideoCapture(str(path))
    if not video.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    return video


def highlighted(frame, x, y):
    return float(np.median(frame[y - 4:y + 4, x - 4:x + 4, 1])) > 90


def displayed_error(frame):
    strip = frame[680:720, 25:815]
    blue, green, red = cv2.split(strip)
    target = (green > 180) & (green > red * 1.5) & (green > blue * 1.5)
    center = (blue > 130) & (blue > red * 1.5) & (blue > green * 1.5)
    target_x = np.flatnonzero(target.sum(axis=0) > 12)
    center_x = np.flatnonzero(center.sum(axis=0) > 12)
    if not target_x.size or not center_x.size:
        return ""
    return round(float((np.median(center_x) - np.median(target_x)) / 1.25), 1)


def extract_first_person(path, output):
    video = open_video(path)
    if (round(video.get(cv2.CAP_PROP_FRAME_WIDTH)),
            round(video.get(cv2.CAP_PROP_FRAME_HEIGHT))) != (1270, 1314):
        video.release()
        raise ValueError("Expected the 1270x1314 Flask screen recording")
    fps = video.get(cv2.CAP_PROP_FPS)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("seconds", "w", "a", "s", "d", "display_error_px"))
        index = 0
        while True:
            ok, frame = video.read()
            if not ok:
                break
            keys = {key: int(highlighted(frame, *point))
                    for key, point in BUTTONS.items()}
            writer.writerow((round(index / fps, 3), keys["w"], keys["a"],
                             keys["s"], keys["d"], displayed_error(frame)))
            index += 1
    video.release()
    return index


def red_robot_center(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = (cv2.inRange(hsv, (0, 90, 50), (10, 255, 255)) |
            cv2.inRange(hsv, (170, 90, 50), (180, 255, 255)))
    mask[:115] = 0
    mask[650:] = 0
    count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return "", ""
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[component, cv2.CC_STAT_AREA] < 25:
        return "", ""
    return round(float(centers[component, 0]), 1), round(float(centers[component, 1]), 1)


def extract_overhead(path, output):
    video = open_video(path)
    if (round(video.get(cv2.CAP_PROP_FRAME_WIDTH)),
            round(video.get(cv2.CAP_PROP_FRAME_HEIGHT))) != (1280, 720):
        video.release()
        raise ValueError("Expected the 1280x720 fixed overhead recording")
    fps = video.get(cv2.CAP_PROP_FPS)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("seconds", "robot_x", "robot_y"))
        index = 0
        while True:
            ok, frame = video.read()
            if not ok:
                break
            if index % 3 == 0:
                writer.writerow((round(index / fps, 3), *red_robot_center(frame)))
            index += 1
    video.release()
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_person", type=Path)
    parser.add_argument("overhead", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    first = args.output_dir / "manual_demo_20261011.csv"
    overhead = args.output_dir / "manual_demo_20261011_overhead.csv"
    first_frames = extract_first_person(args.first_person, first)
    overhead_frames = extract_overhead(args.overhead, overhead)
    print(f"{first}: {first_frames} frames")
    print(f"{overhead}: {overhead_frames} frames")


if __name__ == "__main__":
    main()
