"""Small, brief steering-servo test on BCM GPIO18."""

import time

from gpiozero import Servo


SERVO_PIN = 18
SERVO_STEP = 0.1  # Keep this at or below 0.15 to protect the steering linkage.
MOVE_STEPS = 5  # More steps make each position change smaller.
STEP_SECONDS = 0.2  # Increase this to move more slowly.


def main():
    if not 0 < SERVO_STEP <= 0.15:
        raise ValueError("SERVO_STEP must be greater than 0 and at most 0.15")
    if MOVE_STEPS < 1 or STEP_SECONDS <= 0:
        raise ValueError("MOVE_STEPS and STEP_SECONDS must be positive")

    servo = Servo(
        SERVO_PIN,
        initial_value=None,
        min_pulse_width=0.001,
        max_pulse_width=0.002,
    )
    try:
        current = 0.0
        servo.value = current
        time.sleep(STEP_SECONDS)
        for label, target in (
            ("side 1", SERVO_STEP),
            ("center", 0.0),
            ("side 2", -SERVO_STEP),
            ("center", 0.0),
        ):
            print(f"{label}: {target:+.2f}")
            for step in range(1, MOVE_STEPS + 1):
                servo.value = current + (target - current) * step / MOVE_STEPS
                time.sleep(STEP_SECONDS)
            current = target
    except KeyboardInterrupt:
        print("Stopped by Ctrl+C")
    finally:
        servo.detach()
        servo.close()
        print("Servo signal released")


if __name__ == "__main__":
    main()
