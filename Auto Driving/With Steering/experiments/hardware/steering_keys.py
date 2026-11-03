"""Control a detached steering servo from a Raspberry Pi SSH terminal."""

import sys
import termios
import time
import tty

from gpiozero import AngularServo


SERVO_PIN = 18  # BCM numbering; physical header pin 12.
A_ANGLE = -80
D_ANGLE = 85
CENTER_ANGLE = 0
SIGNAL_SECONDS = 0.7  # Send PWM briefly, then release it to avoid idle jitter.


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run this in the VS Code SSH terminal, not the Debug Console.")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    servo = AngularServo(
        SERVO_PIN,
        initial_angle=None,
        min_angle=-90,
        max_angle=90,
        min_pulse_width=0.001,
        max_pulse_width=0.002,
    )
    try:
        tty.setcbreak(fd)
        print(
            f"a: {A_ANGLE:+d} | d: {D_ANGLE:+d} | space: center | q: quit",
            flush=True,
        )
        while True:
            key = sys.stdin.read(1).lower()
            if key == "a":
                angle = A_ANGLE
            elif key == "d":
                angle = D_ANGLE
            elif key == " ":
                angle = CENTER_ANGLE
            elif key == "q":
                break
            else:
                continue

            print(f"\rTarget: {angle:+d} degrees", flush=True)
            try:
                servo.angle = angle
                time.sleep(SIGNAL_SECONDS)
            finally:
                servo.detach()
            print("Signal off; press another key", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        finally:
            servo.detach()
            servo.close()
        print("\nServo signal released")


if __name__ == "__main__":
    main()
