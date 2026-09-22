"""Check left/right differential steering on the Raspberry Pi RC car."""

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

if str(LEE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LEE_DIRECTORY))

from motor_module import cleanup_motor, left_wheels, move_stop, right_wheels  # noqa: E402


def clamp(value):
    return max(0.0, min(1.0, value))


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


def pivot_left(speed):
    right_wheels.forward(speed=clamp(speed))
    left_wheels.backward(speed=clamp(speed))


def pivot_right(speed):
    left_wheels.forward(speed=clamp(speed))
    right_wheels.backward(speed=clamp(speed))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("right-arc", "left-arc", "pivot-right", "pivot-left"),
        default="right-arc",
    )
    parser.add_argument("--speed", type=float, default=0.30)
    parser.add_argument("--inner-speed", type=float, default=0.05)
    parser.add_argument("--duration", type=float, default=3.0)
    return parser.parse_args()


def main():
    args = parse_args()
    speed = clamp(args.speed)
    inner_speed = clamp(args.inner_speed)
    duration = max(0.1, args.duration)

    try:
        move_stop()
        if args.mode == "right-arc":
            print(
                f"right_arc left={speed:.2f} right={inner_speed:.2f} duration={duration:.2f}s",
                flush=True,
            )
            set_side_speeds(speed, inner_speed)
        elif args.mode == "left-arc":
            print(
                f"left_arc left={inner_speed:.2f} right={speed:.2f} duration={duration:.2f}s",
                flush=True,
            )
            set_side_speeds(inner_speed, speed)
        elif args.mode == "pivot-right":
            print(f"pivot_right speed={speed:.2f} duration={duration:.2f}s", flush=True)
            pivot_right(speed)
        else:
            print(f"pivot_left speed={speed:.2f} duration={duration:.2f}s", flush=True)
            pivot_left(speed)

        time.sleep(duration)
        move_stop()
    finally:
        cleanup_motor()


if __name__ == "__main__":
    main()
