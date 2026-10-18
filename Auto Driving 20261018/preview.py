"""Run the new vision prototype on a saved video or an explicitly selected webcam."""

import argparse
import json
from pathlib import Path
import time

import cv2

from track_vision import VisionConfig, analyze, overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path)
    source.add_argument("--camera", type=int)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frames", type=int, help="Stop after this many frames")
    parser.add_argument("--roi-top", type=float, default=0.0)
    parser.add_argument("--max-side", type=int, default=960)
    parser.add_argument("--view", choices=("overlay", "road", "yellow", "white", "dashes"),
                        default="overlay")
    args = parser.parse_args()
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive.")
    if args.video is not None and not args.video.is_file():
        parser.error(f"Video not found: {args.video}")
    try:
        config = VisionConfig(max_side=args.max_side, roi_top=args.roi_top)
    except ValueError as error:
        parser.error(str(error))
    capture = cv2.VideoCapture(str(args.video) if args.video is not None else args.camera)
    count = 0
    detections = 0
    started = time.perf_counter()
    try:
        if not capture.isOpened():
            raise RuntimeError("Cannot open source. For a webcam, close other camera apps first.")
        fps = capture.get(cv2.CAP_PROP_FPS)
        delay = max(1, round(1000 / fps)) if args.video is not None and fps > 0 else 1
        while True:
            ok, frame = capture.read()
            if not ok:
                if count == 0 or args.camera is not None:
                    raise RuntimeError("Source did not return a frame.")
                break
            result = analyze(frame, config)
            count += 1
            detections += result.metrics["status"] == "markings_detected"
            if not args.headless:
                displayed = overlay(result) if args.view == "overlay" else getattr(result, args.view)
                cv2.imshow("Track Vision - analysis only", displayed)
                if cv2.waitKey(delay) & 0xFF in (27, ord("q")):
                    break
                if cv2.getWindowProperty("Track Vision - analysis only", cv2.WND_PROP_VISIBLE) < 1:
                    break
            if args.frames is not None and count >= args.frames:
                break
        elapsed = time.perf_counter() - started
        print(json.dumps({"frames": count, "frames_with_candidates": detections,
                          "elapsed_seconds": round(elapsed, 3),
                          "processing_fps": round(count / max(elapsed, 1e-6), 1),
                          "control_enabled": False}))
    except RuntimeError as error:
        parser.exit(1, f"Track Vision: {error}\n")
    finally:
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
