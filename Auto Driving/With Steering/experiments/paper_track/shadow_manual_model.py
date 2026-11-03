"""Run the experimental manual-driving model on a Pi camera stream, without GPIO."""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import time
from urllib.request import urlopen

import cv2
import numpy as np

from imitation_features import road_fraction
from imitation_runtime import ImitationModel


def mjpeg_frames(stream):
    while True:
        boundary = stream.readline()
        if not boundary:
            return
        if not boundary.startswith(b"--frame"):
            continue
        headers = {}
        while True:
            line = stream.readline()
            if not line:
                return
            if line in (b"\r\n", b"\n"):
                break
            key, separator, value = line.partition(b":")
            if separator:
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get(b"content-length", b"0"))
        if not 0 < length <= 5_000_000:
            raise ValueError("Invalid MJPEG frame length")
        jpeg = stream.read(length)
        if len(jpeg) != length:
            return
        yield jpeg


def run(pi_url, model_path, duration, fps, output_dir):
    model = ImitationModel(model_path, allow_unvalidated=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / f"shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    counts = {-1: 0, 0: 0, 1: 0, None: 0}
    deadline = time.monotonic() + duration
    next_sample = 0.0
    with urlopen(f"{pi_url.rstrip('/')}/stream/raw", timeout=5) as stream, \
            report.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("pc_time", "prediction", "confidence", "road_fraction"))
        for jpeg in mjpeg_frames(stream):
            now = time.monotonic()
            if now >= deadline:
                break
            if now < next_sample:
                continue
            next_sample = now + 1 / fps
            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            command, confidence = model.predict(frame)
            road = road_fraction(frame)
            counts[command] += 1
            writer.writerow((f"{time.time():.3f}", "none" if command is None else command,
                             f"{confidence:.3f}", f"{road:.3f}"))
            print(f"prediction={command} confidence={confidence:.3f} road={road:.3f}", flush=True)
    return report, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-url", required=True)
    parser.add_argument("--model", type=Path, default=Path(__file__).parent /
                        "manual_dataset/imitation_model_20261011.npz")
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--fps", type=float, default=5)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent /
                        "manual_dataset/shadow_runs")
    args = parser.parse_args()
    if not 1 <= args.duration <= 60 or not 1 <= args.fps <= 10:
        parser.error("duration must be 1..60 seconds and fps 1..10")
    report, counts = run(args.pi_url, args.model, args.duration, args.fps,
                         args.output_dir)
    print(f"Saved {report}; counts={counts}")


if __name__ == "__main__":
    main()
