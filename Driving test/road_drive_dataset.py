"""Run the dataset-trained lane follower with the calibrated motor module."""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from dataset_model import DriveabilityModel, LearnedSteeringModel
from motor_module import DEFAULT_MOTOR_PINS, DEFAULT_MOTOR_TRIM, MotorController, PinPair, clamp


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STEERING_MODEL = SCRIPT_DIR / "models" / "steering_v2.npz"
DEFAULT_SAFETY_MODEL = SCRIPT_DIR / "models" / "driveability_v1.npz"


def parse_pin_pair(text: str) -> PinPair:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("pin pair must look like 26,19")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pins must be integers") from exc


class LowPass:
    def __init__(self, alpha: float) -> None:
        self.alpha = clamp(alpha, 0.0, 1.0)
        self.left: Optional[float] = None
        self.right: Optional[float] = None

    def update(self, left: float, right: float) -> Tuple[float, float]:
        if self.left is None or self.right is None:
            self.left = left
            self.right = right
        else:
            self.left = self.alpha * left + (1.0 - self.alpha) * self.left
            self.right = self.alpha * right + (1.0 - self.alpha) * self.right
        return self.left, self.right

    def reset(self) -> None:
        self.left = 0.0
        self.right = 0.0


class RateLimiter:
    def __init__(self, step: float) -> None:
        self.step = max(0.0, step)
        self.left = 0.0
        self.right = 0.0

    def update(self, left: float, right: float) -> Tuple[float, float]:
        self.left += clamp(left - self.left, -self.step, self.step)
        self.right += clamp(right - self.right, -self.step, self.step)
        return self.left, self.right

    def reset(self) -> None:
        self.left = 0.0
        self.right = 0.0


class OpenCvCamera:
    def __init__(self, index: int, width: int, height: int, fps: int) -> None:
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        if not self.cap.isOpened():
            raise SystemExit(f"OpenCV camera index {index} is not available")

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def stop(self) -> None:
        self.cap.release()


class RpicamMjpegCamera:
    def __init__(self, width: int, height: int, fps: int) -> None:
        command = [
            "rpicam-vid",
            "--codec",
            "mjpeg",
            "--inline",
            "--width",
            str(width),
            "--height",
            str(height),
            "--framerate",
            str(fps),
            "--timeout",
            "0",
            "--nopreview",
            "--output",
            "-",
        ]
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self) -> None:
        if self.process.stdout is None:
            return

        buffer = bytearray()
        while self.running:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                if self.process.poll() is not None:
                    break
                time.sleep(0.01)
                continue

            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9")
                if start < 0 or end < 0 or end <= start:
                    if start > 0:
                        del buffer[:start]
                    break

                jpeg = bytes(buffer[start : end + 2])
                del buffer[: end + 2]
                image = np.frombuffer(jpeg, dtype=np.uint8)
                frame = cv2.imdecode(image, cv2.IMREAD_COLOR)
                if frame is not None:
                    with self.lock:
                        self.latest_frame = frame

    def read(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def stop(self) -> None:
        self.running = False
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.thread.join(timeout=1.0)


def build_camera(args):
    if args.camera == "opencv":
        return OpenCvCamera(args.camera_index, args.width, args.height, args.fps)
    return RpicamMjpegCamera(args.width, args.height, args.fps)


def build_motors(args):
    motor_trim = {
        1: args.motor1_trim,
        2: args.motor2_trim,
        3: args.motor3_trim,
        4: args.motor4_trim,
    }
    return MotorController(
        motor_pins={
            1: args.motor1_pins,
            2: args.motor2_pins,
            3: args.motor3_pins,
            4: args.motor4_pins,
        },
        motor_trim=motor_trim,
        left_motors=(3, 4),
        right_motors=(1, 2),
        dry_run=args.dry_run,
        dry_run_verbose=False,
        invert_left_pins=args.invert_left_pins,
        invert_right_pins=args.invert_right_pins,
    )


def postprocess_pwm(left_pwm: float, right_pwm: float, args) -> Tuple[float, float]:
    average = ((left_pwm + right_pwm) / 2.0) * args.speed_scale
    steering = (right_pwm - left_pwm) * args.steering_scale
    if args.invert_steering:
        steering = -steering

    if average > 0.001:
        average = max(args.min_forward_pwm, average)

    left = average - steering / 2.0
    right = average + steering / 2.0
    return clamp(left, 0.0, args.max_pwm), clamp(right, 0.0, args.max_pwm)


def draw_preview(frame, left_pwm: float, right_pwm: float, score, safety_state: str):
    preview = frame.copy()
    text = f"L={left_pwm:.3f} R={right_pwm:.3f} safety={safety_state}"
    if score is not None:
        text += f" score={score:.3f}"
    cv2.putText(
        preview,
        text,
        (8, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return preview


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_STEERING_MODEL)
    parser.add_argument("--safety-model", type=Path, default=DEFAULT_SAFETY_MODEL)
    parser.add_argument("--no-safety", action="store_true")
    parser.add_argument("--unsafe-frame-limit", type=int, default=8)

    parser.add_argument("--camera", choices=["rpicam", "opencv"], default="rpicam")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-every", type=int, default=5)

    parser.add_argument("--speed-scale", type=float, default=1.0)
    parser.add_argument("--steering-scale", type=float, default=1.0)
    parser.add_argument("--min-forward-pwm", type=float, default=0.0)
    parser.add_argument("--max-pwm", type=float, default=0.85)
    parser.add_argument("--pwm-alpha", type=float, default=0.65)
    parser.add_argument("--pwm-step", type=float, default=0.08)
    parser.add_argument("--invert-steering", action="store_true")

    parser.add_argument("--motor1-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[1])
    parser.add_argument("--motor2-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[2])
    parser.add_argument("--motor3-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[3])
    parser.add_argument("--motor4-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[4])
    parser.add_argument("--motor1-trim", type=float, default=DEFAULT_MOTOR_TRIM[1])
    parser.add_argument("--motor2-trim", type=float, default=DEFAULT_MOTOR_TRIM[2])
    parser.add_argument("--motor3-trim", type=float, default=DEFAULT_MOTOR_TRIM[3])
    parser.add_argument("--motor4-trim", type=float, default=DEFAULT_MOTOR_TRIM[4])
    parser.add_argument("--invert-left-pins", action="store_true")
    parser.add_argument("--invert-right-pins", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.model.exists():
        raise SystemExit(f"steering model not found: {args.model}")

    steering_model = LearnedSteeringModel(args.model)
    safety_model = None
    if not args.no_safety and args.safety_model.exists():
        safety_model = DriveabilityModel(args.safety_model)

    camera = build_camera(args)
    motors = build_motors(args)
    pwm_filter = LowPass(args.pwm_alpha)
    pwm_limiter = RateLimiter(args.pwm_step)
    unsafe_frames = 0
    frame_index = 0
    start_time = time.monotonic()

    print("dataset-trained road driver started")
    print(f"model={args.model}")
    print(f"safety={args.safety_model if safety_model is not None else 'disabled'}")
    print(
        "motor trim="
        f"m1:{args.motor1_trim:.2f} m2:{args.motor2_trim:.2f} "
        f"m3:{args.motor3_trim:.2f} m4:{args.motor4_trim:.2f}"
    )
    if args.dry_run:
        print("dry-run: motor GPIO output is disabled")

    try:
        while True:
            if args.duration > 0 and time.monotonic() - start_time >= args.duration:
                break

            frame = camera.read()
            if frame is None:
                motors.stop()
                time.sleep(0.02)
                continue

            score = None
            safety_state = "disabled"
            if safety_model is not None:
                score = safety_model.predict_probability(frame)
                if score >= safety_model.threshold:
                    unsafe_frames = 0
                    safety_state = "driveable"
                else:
                    unsafe_frames += 1
                    safety_state = "unsafe" if unsafe_frames >= args.unsafe_frame_limit else "uncertain"

            if safety_state == "unsafe":
                pwm_filter.reset()
                pwm_limiter.reset()
                left_pwm = 0.0
                right_pwm = 0.0
                command = "safety_stop"
            else:
                model_left, model_right = steering_model.predict(frame)
                left_pwm, right_pwm = postprocess_pwm(model_left, model_right, args)
                left_pwm, right_pwm = pwm_filter.update(left_pwm, right_pwm)
                left_pwm, right_pwm = pwm_limiter.update(left_pwm, right_pwm)
                command = "dataset_model"

            motors.set_side_pwm(left_pwm, right_pwm)

            if frame_index % max(1, args.print_every) == 0:
                score_text = "-" if score is None else f"{score:.3f}"
                elapsed = time.monotonic() - start_time
                print(
                    f"t={elapsed:6.2f}s frame={frame_index:05d} {command} "
                    f"safety={safety_state} score={score_text} "
                    f"left={left_pwm:.3f} right={right_pwm:.3f}"
                )

            if args.preview:
                cv2.imshow(
                    "Driving test - dataset model",
                    draw_preview(frame, left_pwm, right_pwm, score, safety_state),
                )
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            frame_index += 1
            time.sleep(1.0 / max(1, args.fps))

    except KeyboardInterrupt:
        print("stopped by user")
    finally:
        motors.stop()
        motors.cleanup()
        camera.stop()
        if args.preview:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
