"""Record the PC overhead camera for a bounded robot trial; never control GPIO."""

import argparse
import csv
from pathlib import Path
import time

import cv2


def record(camera_index, seconds, output):
    camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not camera.isOpened():
        raise RuntimeError("Overhead camera unavailable")
    writer = None
    timestamps = output.with_suffix(".csv")
    try:
        ok, frame = camera.read()
        if not ok:
            raise RuntimeError("Overhead camera returned no frame")
        height, width = frame.shape[:2]
        output.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"MJPG"),
                                 10, (width, height))
        if not writer.isOpened():
            raise RuntimeError("Cannot open overhead video output")
        deadline = time.monotonic() + seconds
        count = 0
        with timestamps.open("x", newline="", encoding="utf-8") as file:
            rows = csv.writer(file)
            rows.writerow(("frame", "pc_unix_time"))
            while ok and time.monotonic() < deadline:
                writer.write(frame)
                rows.writerow((count, f"{time.time():.6f}"))
                count += 1
                ok, frame = camera.read()
        print(f"Recorded {count} frames at {width}x{height}: {output}")
    finally:
        camera.release()
        if writer is not None:
            writer.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    if not 0 < args.seconds <= 30:
        parser.error("seconds must be in (0, 30]")
    record(args.camera, args.seconds, args.output)


if __name__ == "__main__":
    main()
