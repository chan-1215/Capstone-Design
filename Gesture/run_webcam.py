"""Show MediaPipe/KNN gestures and YOLOv8n-seg person outlines from one webcam."""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from gesture_recognition_module import GestureRecognizer
from camera_guard import webcam_guard
from person_detection import DEFAULT_PERSON_MODEL, LatestFrameDetector, YoloPersonModel


MODEL_PATH = Path(__file__).with_name("models") / "gesture_knn_model.npz"
WINDOW_NAME = "Gesture PC"


def open_camera(index):
    backends = (cv2.CAP_DSHOW, cv2.CAP_ANY) if sys.platform == "win32" else (cv2.CAP_ANY,)
    for backend in backends:
        camera = cv2.VideoCapture(index, backend)
        if camera.isOpened():
            return camera
        camera.release()
    raise RuntimeError(f"Cannot open webcam {index}. Try --camera 1 or close other camera apps.")


def draw_person_result(frame, result, now):
    color = (60, 220, 80)
    if result is None:
        status = "Persons: starting"
    elif not result.is_fresh(now):
        status = "Persons: stale"
    else:
        status = f"Persons: {len(result.persons)}"
        for person in result.persons:
            left, top, right, bottom = person.xyxy
            contour = np.asarray(person.outline, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(frame, [contour], True, color, 2, cv2.LINE_AA)
            label = f"person {person.confidence:.2f}"
            text_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
            label_x = max(4, min(left, frame.shape[1] - text_width - 4))
            label_y = max(16, top - 6)
            cv2.putText(frame, label,
                        (label_x, min(frame.shape[0] - 6, label_y)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, color, 1)
        cv2.putText(frame, f"YOLO {result.inference_ms:.0f} ms | age {(now - result.captured_at) * 1000:.0f} ms",
                    (10, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.putText(frame, status, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--mirror", action="store_true", help="Mirror the input like a selfie preview")
    parser.add_argument("--check", action="store_true", help="Check 60 frames and YOLO without opening a window")
    parser.add_argument("--gesture-only", action="store_true", help="Run the original gesture-only baseline")
    parser.add_argument("--person-model", type=Path, default=DEFAULT_PERSON_MODEL)
    parser.add_argument("--person-confidence", type=float, default=0.5)
    parser.add_argument("--person-interval", type=float, default=0.2,
                        help="Minimum seconds between YOLO inference starts")
    parser.add_argument("--person-imgsz", type=int, default=320)
    parser.add_argument("--person-threads", type=int, default=2)
    args = parser.parse_args()

    if not args.model.is_file():
        parser.error(f"Model file not found: {args.model}")
    if not 0 < args.person_confidence <= 1:
        parser.error("Person confidence must be in (0, 1].")
    if args.person_interval <= 0 or args.person_threads < 1:
        parser.error("Person interval and CPU thread count must be positive.")
    if args.person_imgsz < 32 or args.person_imgsz % 32:
        parser.error("Person image size must be a positive multiple of 32.")

    try:
        with webcam_guard(args.camera):
            run(args)
    except (RuntimeError, OSError, ValueError) as exc:
        parser.exit(1, f"Gesture PC: {exc}\n")


def run(args):
    camera = None
    recognizer = None
    detector = None
    try:
        if not args.gesture_only:
            person_model = YoloPersonModel(args.person_model, args.person_confidence,
                                          args.person_imgsz, args.person_threads)
            detector = LatestFrameDetector(person_model, args.person_interval)
        recognizer = GestureRecognizer(model_path=str(args.model))
        camera = open_camera(args.camera)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
        if detector is not None:
            detector.start()
        frame_count = 0
        started = time.monotonic()

        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("Webcam stopped returning frames.")
            if args.mirror:
                frame = cv2.flip(frame, 1)
            captured_at = time.monotonic()
            if detector is not None:
                detector.submit(frame, captured_at)

            result = recognizer.process(frame)
            frame_count += 1
            now = time.monotonic()
            person_result, person_error, yolo_calls = (
                detector.snapshot() if detector is not None else (None, None, 0)
            )
            if person_error is not None:
                raise RuntimeError(f"YOLO inference failed: {person_error}")
            preview_fps = frame_count / max(now - started, 1e-6)

            if args.check:
                if now - started > 15:
                    raise RuntimeError(
                        f"Camera/model check timed out: frames={frame_count}, "
                        f"FPS={preview_fps:.1f}, YOLO calls={yolo_calls}. "
                        "Check the webcam shutter, lighting, or camera index."
                    )
                yolo_ready = detector is None or (
                    yolo_calls >= 3 and person_result.is_fresh(now)
                )
                if frame_count >= 60 and yolo_ready:
                    print(
                        f"Camera OK: {frame.shape[1]}x{frame.shape[0]}, "
                        f"frames={frame_count}, label={result['label']}, "
                        f"distance={result['distance']:.1f}, FPS={preview_fps:.1f}"
                    )
                    if person_result is not None:
                        print(f"YOLO outlines OK: persons={len(person_result.persons)}, "
                              f"calls={yolo_calls}, inference={person_result.inference_ms:.1f} ms")
                    break
            else:
                debug_frame = result["debug_frame"]
                if detector is not None:
                    draw_person_result(debug_frame, person_result, now)
                cv2.putText(debug_frame, f"FPS {preview_fps:.1f}",
                            (10, debug_frame.shape[0] - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.imshow(WINDOW_NAME, debug_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
    finally:
        try:
            if detector is not None:
                detector.close()
        finally:
            if recognizer is not None:
                recognizer.close()
            if camera is not None:
                camera.release()
            if not args.check:
                cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
