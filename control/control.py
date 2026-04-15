from __future__ import annotations

import os
import sys
import time
from contextlib import suppress

from gpiozero import Motor

if os.name != "nt":
    import select
    import termios
    import tty

try:
    import keyboard as keyboard_lib
except Exception:
    keyboard_lib = None


RIGHT_MOTOR_PINS = ((26, 19), (22, 27))
LEFT_MOTOR_PINS = ((20, 21), (24, 23))

# Equal power for all 4 motors.
MOTOR_POWER = 1.0
DIRECTION_CHANGE_PAUSE = 0.06
POLL_INTERVAL = 0.02
# Used only in terminal fallback mode where key-up events are unavailable.
RELEASE_TIMEOUT = 0.70

MOTIONS = {
    "forward": (1, 1, 1, 1),
    # Keep all four motors active during backward.
    "backward": (-1, -1, -1, -1),
    "left": (1, 1, 0, 0),
    "right": (0, 0, 1, 1),
    "stop": (0, 0, 0, 0),
}

KEY_BINDINGS = {
    ord("w"): "forward",
    ord("a"): "left",
    ord("s"): "backward",
    ord("d"): "right",
    ord("x"): "stop",
    ord("q"): "quit",
}

HOLD_KEYS = (
    ("q", "quit"),
    ("x", "stop"),
    ("w", "forward"),
    ("s", "backward"),
    ("a", "left"),
    ("d", "right"),
)

MOVING_COMMANDS = {"forward", "backward", "left", "right"}


class CarController:
    def __init__(self) -> None:
        right_front = Motor(*RIGHT_MOTOR_PINS[0])
        right_rear = Motor(*RIGHT_MOTOR_PINS[1])
        left_front = Motor(*LEFT_MOTOR_PINS[0])
        left_rear = Motor(*LEFT_MOTOR_PINS[1])

        # Order: right_front, right_rear, left_front, left_rear
        self.motors = (right_front, right_rear, left_front, left_rear)
        self.current_motion = MOTIONS["stop"]

    def _drive_motor(self, motor: Motor, direction: int) -> None:
        if direction > 0:
            if MOTOR_POWER >= 0.99:
                motor.forward()
            else:
                motor.forward(MOTOR_POWER)
        elif direction < 0:
            if MOTOR_POWER >= 0.99:
                motor.backward()
            else:
                motor.backward(MOTOR_POWER)
        else:
            motor.stop()

    def apply(self, command: str) -> None:
        next_motion = MOTIONS[command]

        reverse_switch = any(
            prev != 0 and nxt != 0 and prev != nxt
            for prev, nxt in zip(self.current_motion, next_motion)
        )
        if reverse_switch:
            self.stop()
            time.sleep(DIRECTION_CHANGE_PAUSE)

        for motor, direction in zip(self.motors, next_motion):
            self._drive_motor(motor, direction)

        self.current_motion = next_motion

    def stop(self) -> None:
        for motor in self.motors:
            motor.stop()
        self.current_motion = MOTIONS["stop"]


class TerminalKeyReader:
    def __init__(self) -> None:
        self._fd = None
        self._original_settings = None

    def __enter__(self) -> "TerminalKeyReader":
        if os.name != "nt" and sys.stdin.isatty():
            self._fd = sys.stdin.fileno()
            self._original_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None and self._original_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_settings)

    def read_nonblocking(self) -> str | None:
        if not sys.stdin.isatty():
            return None

        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None

            key = msvcrt.getch()
            if key in {b"\x00", b"\xe0"}:
                if msvcrt.kbhit():
                    msvcrt.getch()
                return None

            decoded = key.decode("utf-8", errors="ignore")
            return decoded.lower() if decoded else None

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None

        key = sys.stdin.read(1)
        return key.lower() if key else None


def hold_mode_available() -> bool:
    if keyboard_lib is None:
        return False

    try:
        keyboard_lib.is_pressed("shift")
    except Exception:
        return False

    return True


def get_hold_command() -> str:
    for key_name, command in HOLD_KEYS:
        if keyboard_lib.is_pressed(key_name):
            return command
    return "stop"


def run_keyboard_hold_mode(car: CarController) -> None:
    print("Hold mode: keep W/A/S/D pressed to move.")
    print("Release key to stop. Press Q to quit.")
    print("-" * 30)

    last_reported = "stop"
    while True:
        command = get_hold_command()

        if command == "quit":
            break

        if command in MOVING_COMMANDS:
            # Re-apply continuously while key is held.
            car.apply(command)
        elif command != last_reported:
            car.apply("stop")

        if command != last_reported:
            print(f"Command: {command}")
            last_reported = command

        time.sleep(POLL_INTERVAL)

    car.stop()


def run_terminal_hold_like_mode(car: CarController) -> None:
    print("Hold-like mode: W/A/S/D to move, Q to quit.")
    print("Release auto-stop works with short timeout in this mode.")
    print("-" * 30)

    active_command = "stop"
    last_reported = "stop"
    last_motion_at = time.monotonic()

    with TerminalKeyReader() as reader:
        while True:
            key = reader.read_nonblocking()
            now = time.monotonic()

            if key:
                command = KEY_BINDINGS.get(ord(key))
                if command is None:
                    printable = key if 32 <= ord(key) <= 126 else "unknown"
                    print(f"Unsupported input: {printable} (ASCII {ord(key)})")
                elif command == "quit":
                    break
                elif command == "stop":
                    active_command = "stop"
                else:
                    active_command = command
                    last_motion_at = now

            if active_command in MOVING_COMMANDS:
                # Keep sending command so all motors stay engaged.
                car.apply(active_command)
                if now - last_motion_at >= RELEASE_TIMEOUT:
                    active_command = "stop"
            else:
                car.apply("stop")

            if active_command != last_reported:
                print(f"Command: {active_command}")
                last_reported = active_command

            time.sleep(POLL_INTERVAL)

    car.stop()


def main() -> None:
    car = CarController()

    try:
        if hold_mode_available():
            run_keyboard_hold_mode(car)
        else:
            print("[Info] keyboard hold mode unavailable (module/permission).")
            print("[Info] Using terminal hold-like fallback mode.")
            run_terminal_hold_like_mode(car)
    except KeyboardInterrupt:
        print("\nExit by Ctrl+C.")
    finally:
        with suppress(Exception):
            car.stop()


if __name__ == "__main__":
    main()
