"""One-action-at-a-time GPIO test for the borrowed steering robot.

BCM numbering. No motor or servo moves until a command is selected.
"""

from __future__ import annotations

import argparse
import time


# Edit these values after observing the hardware. Pins use BCM numbering.
MOTOR_PINS = {1: (20, 21), 2: (24, 23)}
SERVO_PIN = 18
DEFAULT_MOTOR_SPEED = 0.20
DEFAULT_MOTOR_SECONDS = 0.5
SERVO_CENTER = 0.0
SERVO_STEP = 0.08  # Change this first to reduce/increase steering travel.
SERVO_MAX_ABS = 0.15  # Hard limit for this test; keep small until linkage is checked.
SERVO_SECONDS = 0.35


def main() -> None:
    actions = [
        "motor1-forward", "motor1-reverse",
        "motor2-forward", "motor2-reverse",
        "servo-center", "servo-left", "servo-right",
    ]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=actions)
    parser.add_argument("--speed", type=float, default=DEFAULT_MOTOR_SPEED)
    parser.add_argument("--duration", type=float, default=DEFAULT_MOTOR_SECONDS)
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not access GPIO")
    args = parser.parse_args()

    if not 0 < args.speed <= 0.5:
        parser.error("--speed must be greater than 0 and at most 0.5")
    if not 0 < args.duration <= 2.0:
        parser.error("--duration must be greater than 0 and at most 2.0 seconds")
    if not 0 <= SERVO_STEP <= SERVO_MAX_ABS <= 0.15:
        parser.error("servo settings must satisfy 0 <= STEP <= MAX_ABS <= 0.15")

    if args.action.startswith("motor"):
        number = int(args.action[5])
        direction = args.action.split("-", 1)[1]
        pins = MOTOR_PINS[number]
        print(f"Motor {number}, pins {pins}, {direction}, speed {args.speed}, {args.duration}s")
        if args.dry_run:
            return

        try:
            from gpiozero import Motor
        except ImportError as exc:
            parser.exit(1, f"gpiozero is required: {exc}\n")
        motor = Motor(forward=pins[0], backward=pins[1], pwm=True)
        try:
            if direction == "forward":
                motor.forward(args.speed)
            else:
                motor.backward(args.speed)
            time.sleep(args.duration)
        finally:
            motor.stop()
            motor.close()
        return

    positions = {
        "servo-center": SERVO_CENTER,
        "servo-left": SERVO_CENTER + SERVO_STEP * 1.10,
        "servo-right": SERVO_CENTER - SERVO_STEP,
    }
    target = positions[args.action]
    if abs(target) > SERVO_MAX_ABS:
        parser.error("servo target exceeds SERVO_MAX_ABS")
    print(f"Servo pin {SERVO_PIN}, target value {target:+.3f}, {SERVO_SECONDS}s then detach")
    if args.dry_run:
        return

    try:
        from gpiozero import Servo
    except ImportError as exc:
        parser.exit(1, f"gpiozero is required: {exc}\n")
    servo = Servo(
        SERVO_PIN,
        initial_value=None,
        min_pulse_width=0.001,
        max_pulse_width=0.002,
    )
    try:
        servo.value = target
        time.sleep(SERVO_SECONDS)
    finally:
        servo.detach()
        servo.close()


if __name__ == "__main__":
    main()
