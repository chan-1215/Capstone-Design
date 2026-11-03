"""Test one DC motor through an H-bridge, using BCM GPIO numbers.

This program never runs a motor without an explicit motor and direction.
The wheels must be lifted before a real test.
"""

from __future__ import annotations

import argparse
import time


# BCM GPIO numbers. Swap a pair only after confirming the physical direction.
MOTOR_PINS = {1: (20, 21), 2: (24, 23)}
DEFAULT_SECONDS = 1.0
MAX_SECONDS = 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("motor", type=int, choices=(1, 2), nargs="?")
    parser.add_argument("direction", choices=("forward", "backward"), nargs="?")
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.motor is None and args.direction is None:
        print("1: Motor 1 forward    2: Motor 1 backward")
        print("3: Motor 2 forward    4: Motor 2 backward    q: Quit")
        try:
            choice = input("Select one action: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled; no GPIO used")
            return
        actions = {
            "1": (1, "forward"),
            "2": (1, "backward"),
            "3": (2, "forward"),
            "4": (2, "backward"),
        }
        if choice not in actions:
            print("Cancelled; no GPIO used")
            return
        args.motor, args.direction = actions[choice]
    elif args.motor is None or args.direction is None:
        parser.error("provide both motor and direction, or neither for the menu")

    if not 0 < args.seconds <= MAX_SECONDS:
        parser.error(f"--seconds must be greater than 0 and at most {MAX_SECONDS}")

    forward_pin, backward_pin = MOTOR_PINS[args.motor]
    print(
        f"Motor {args.motor}: BCM {forward_pin}/{backward_pin}, "
        f"{args.direction}, full power for {args.seconds:.1f}s"
    )
    if args.dry_run:
        return

    try:
        from gpiozero import Motor
    except ImportError as exc:
        parser.exit(1, f"gpiozero is required: {exc}\n")

    motor = Motor(forward=forward_pin, backward=backward_pin, pwm=False)
    try:
        if args.direction == "forward":
            motor.forward()
        else:
            motor.backward()
        time.sleep(args.seconds)
    finally:
        motor.stop()
        motor.close()
        print("Motor stopped; GPIO released")


if __name__ == "__main__":
    main()
