"""Run the learned lane follower on the Raspberry Pi RC car.

This script reuses the existing Lee camera and motor modules without modifying
their wiring or polarity.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

for path in (PROJECT_ROOT, LEE_DIRECTORY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from camera_module import get_latest_frame, start_camera, stop_camera  # noqa: E402
from controllers.driveability import DriveabilityModel  # noqa: E402
from controllers.learned_control import stabilize_learned_pwm  # noqa: E402
from controllers.learned_steering import LearnedSteeringModel  # noqa: E402
from controllers.lee_lane_adapter import LeeLaneAdapter  # noqa: E402
from motor_module import cleanup_motor, left_wheels, move_stop, right_wheels  # noqa: E402


DEFAULT_MODEL = PROJECT_ROOT / "models" / "steering_v2.npz"
DEFAULT_DRIVEABILITY_MODEL = PROJECT_ROOT / "models" / "driveability_v1.npz"
UNSAFE_FRAME_LIMIT = 15


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def set_side_speeds(left_pwm, right_pwm):
    left_pwm = clamp(left_pwm)
    right_pwm = clamp(right_pwm)

    if left_pwm > 0.001:
        left_wheels.forward(speed=left_pwm)
    else:
        left_wheels.stop()

    if right_pwm > 0.001:
        right_wheels.forward(speed=right_pwm)
    else:
        right_wheels.stop()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--driveability-model",
        type=Path,
        default=DEFAULT_DRIVEABILITY_MODEL,
    )
    parser.add_argument("--no-safety", action="store_true")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    steering_model = LearnedSteeringModel(args.model)
    safety_model = None
    if not args.no_safety and args.driveability_model.exists():
        safety_model = DriveabilityModel(args.driveability_model)

    tracker = LeeLaneAdapter()
    unsafe_frames = 0
    start_time = time.monotonic()
    last_log = 0.0

    start_camera(
        width=args.width,
        height=args.height,
        fps=args.fps,
        show_preview=False,
    )
    print(f"steering model: {args.model}")
    print(f"driveability model: {args.driveability_model if safety_model else 'disabled'}")

    try:
        while True:
            if args.duration and time.monotonic() - start_time >= args.duration:
                break

            frame = get_latest_frame()
            if frame is None:
                move_stop()
                time.sleep(0.02)
                continue

            lane = tracker.process(frame)
            safety_state = "disabled"
            driveability_score = None
            if safety_model is not None:
                driveability_score = safety_model.predict_probability(frame)
                if driveability_score >= safety_model.threshold:
                    unsafe_frames = 0
                    safety_state = "driveable"
                elif lane["visible"]:
                    unsafe_frames = 0
                    safety_state = "uncertain"
                else:
                    unsafe_frames += 1
                    safety_state = (
                        "unsafe"
                        if unsafe_frames >= UNSAFE_FRAME_LIMIT
                        else "uncertain"
                    )

            if safety_state == "unsafe":
                left_pwm = 0.0
                right_pwm = 0.0
                command = "safety_stop"
            else:
                left_pwm, right_pwm = steering_model.predict(frame)
                left_pwm, right_pwm = stabilize_learned_pwm(
                    left_pwm,
                    right_pwm,
                    lane["error"],
                    lane["visible"],
                )
                command = "learned_model"

            set_side_speeds(left_pwm, right_pwm)

            now = time.monotonic()
            if now - last_log >= 1.0:
                score_text = (
                    f"{driveability_score:.3f}"
                    if driveability_score is not None
                    else "-"
                )
                print(
                    f"{command} lane={lane['status']} error={lane['error']} "
                    f"score={score_text} safety={safety_state} "
                    f"left={left_pwm:.3f} right={right_pwm:.3f}"
                )
                last_log = now

            if args.preview:
                cv2.imshow("Pi learned lane follower", lane["debug_frame"])
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(1.0 / max(args.fps, 1))

    except KeyboardInterrupt:
        print("stopped by user")
    finally:
        move_stop()
        cleanup_motor()
        stop_camera()
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
