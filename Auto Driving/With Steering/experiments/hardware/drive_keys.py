"""Keyboard driving test for the Pi robot, using BCM GPIO numbering.

Run in an SSH terminal. Motor output times out if key repeat or SSH stops.
"""

from contextlib import ExitStack
import select
import sys
import termios
import time
import tty

from gpiozero import AngularServo, Motor


MOTOR_1_PINS = (20, 21)
MOTOR_2_PINS = (23, 24)
SERVO_PIN = 18
RIGHT_ANGLE = -80
LEFT_ANGLE = 85
DRIVE_TIMEOUT = 0.6  # Maximum motor run time after the latest w/s key event.
SERVO_SIGNAL_SECONDS = 0.3  # Release PWM afterward to avoid idle jitter.


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run in the VS Code SSH terminal, not the Debug Console.")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    with ExitStack() as cleanup:
        motor1 = Motor(*MOTOR_1_PINS)
        cleanup.callback(motor1.close)
        cleanup.callback(motor1.stop)
        motor2 = Motor(*MOTOR_2_PINS)
        cleanup.callback(motor2.close)
        cleanup.callback(motor2.stop)
        servo = AngularServo(
            SERVO_PIN,
            initial_angle=None,
            min_angle=-90,
            max_angle=90,
            min_pulse_width=0.001,
            max_pulse_width=0.002,
        )
        cleanup.callback(servo.close)
        cleanup.callback(servo.detach)

        tty.setcbreak(fd)
        cleanup.callback(termios.tcsetattr, fd, termios.TCSADRAIN, old_settings)
        print("w: forward | s: backward | a: right | d: left | space: center/stop | q: quit")

        drive_deadline = None
        servo_deadline = None
        direction = None
        try:
            while True:
                now = time.monotonic()
                if drive_deadline is not None and now >= drive_deadline:
                    motor1.stop()
                    motor2.stop()
                    drive_deadline = None
                    direction = None
                if servo_deadline is not None and now >= servo_deadline:
                    servo.detach()
                    servo_deadline = None

                deadlines = [deadline for deadline in (drive_deadline, servo_deadline) if deadline]
                timeout = max(0, min(deadlines) - now) if deadlines else None
                if not select.select([sys.stdin], [], [], timeout)[0]:
                    continue

                key = sys.stdin.read(1).lower()
                if key in ("w", "s"):
                    if direction != key:
                        motor1.stop()
                        motor2.stop()
                        if direction is not None:
                            time.sleep(0.05)
                        if key == "w":
                            motor1.backward()
                            motor2.forward()
                        else:
                            motor1.forward()
                            motor2.backward()
                        direction = key
                        print("\rForward " if key == "w" else "\rBackward", flush=True)
                    drive_deadline = time.monotonic() + DRIVE_TIMEOUT
                elif key in ("a", "d", " "):
                    if key == " ":
                        motor1.stop()
                        motor2.stop()
                        drive_deadline = None
                        direction = None
                    angle = RIGHT_ANGLE if key == "a" else LEFT_ANGLE if key == "d" else 0
                    servo.angle = angle
                    servo_deadline = time.monotonic() + SERVO_SIGNAL_SECONDS
                    print(f"\rSteering: {angle:+d} degrees", flush=True)
                elif key == "x":
                    motor1.stop()
                    motor2.stop()
                    servo.detach()
                    drive_deadline = servo_deadline = direction = None
                    print("\rStopped", flush=True)
                elif key == "q":
                    break
        except KeyboardInterrupt:
            pass
        finally:
            motor1.stop()
            motor2.stop()
            servo.detach()
    print("\nMotor output stopped; servo signal released")


if __name__ == "__main__":
    main()
