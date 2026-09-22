"""Check whole-car forward/backward motor polarity on the Raspberry Pi."""

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

if str(LEE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LEE_DIRECTORY))

from motor_module import cleanup_motor, move_backward, move_forward, move_stop  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.25)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument(
        "--direction",
        choices=("forward", "backward", "both"),
        default="both",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    speed = max(0.0, min(1.0, args.speed))
    duration = max(0.1, args.duration)
    pause = max(0.0, args.pause)

    try:
        move_stop()
        if args.direction in ("forward", "both"):
            print(f"all_wheels forward speed={speed:.2f} duration={duration:.2f}s", flush=True)
            move_forward(speed)
            time.sleep(duration)
            move_stop()
            time.sleep(pause)

        if args.direction in ("backward", "both"):
            print(f"all_wheels backward speed={speed:.2f} duration={duration:.2f}s", flush=True)
            move_backward(speed)
            time.sleep(duration)
            move_stop()
    finally:
        cleanup_motor()


if __name__ == "__main__":
    main()
