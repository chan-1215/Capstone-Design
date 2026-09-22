"""Spin each RC car motor forward and backward once on the Raspberry Pi."""

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

if str(LEE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LEE_DIRECTORY))

from motor_module import cleanup_motor, motor1, motor2, motor3, motor4, move_stop  # noqa: E402


MOTORS = [
    ("motor1", "left_front", motor1),
    ("motor2", "left_rear", motor2),
    ("motor3", "right_rear", motor3),
    ("motor4", "right_front", motor4),
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.35)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--pause", type=float, default=0.4)
    return parser.parse_args()


def main():
    args = parse_args()
    speed = max(0.0, min(1.0, args.speed))
    duration = max(0.05, args.duration)
    pause = max(0.0, args.pause)

    try:
        move_stop()
        for name, position, motor in MOTORS:
            print(f"{name} {position} forward speed={speed:.2f} duration={duration:.2f}s", flush=True)
            motor.forward(speed=speed)
            time.sleep(duration)
            motor.stop()
            time.sleep(pause)

            print(f"{name} {position} backward speed={speed:.2f} duration={duration:.2f}s", flush=True)
            motor.backward(speed=speed)
            time.sleep(duration)
            motor.stop()
            time.sleep(pause)
    finally:
        cleanup_motor()


if __name__ == "__main__":
    main()
