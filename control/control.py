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

MOTOR_POWER = 1.0
DIRECTION_CHANGE_PAUSE = 0.06
POLL_INTERVAL = 0.02

MOTIONS = {
    "forward": (1, 1, 1, 1),
    "backward": (-1, -1, -1, -1),
    # Pivot turns: one side moves, the other side stops.
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


class CarController:
    def __init__(self) -> None:
        right_front = Motor(*RIGHT_MOTOR_PINS[0])
        right_rear = Motor(*RIGHT_MOTOR_PINS[1])
        left_front = Motor(*LEFT_MOTOR_PINS[0])
        left_rear = Motor(*LEFT_MOTOR_PINS[1])

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

        # Brief neutral pause when direction flips, to reduce weak starts.
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
    def read_key(self) -> int:
        if not sys.stdin.isatty():
            user_input = input("Input command (w/a/s/d/x/q): ").strip().lower()
            return ord(user_input[0]) if user_input else -1

        if os.name == "nt":
            import msvcrt

            key = msvcrt.getch()
            if key in {b"\x00", b"\xe0"}:
                msvcrt.getch()
                return -1

            return ord(key.decode("utf-8", errors="ignore").lower() or "\x00")

        file_descriptor = sys.stdin.fileno()
        original_settings = termios.tcgetattr(file_descriptor)

        try:
            tty.setraw(file_descriptor)
            _, _, _ = select.select([sys.stdin], [], [])
            key = sys.stdin.read(1)
        finally:
            termios.tcsetattr(file_descriptor, termios.TCSADRAIN, original_settings)

        return ord(key.lower())


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


def run_hold_mode(car: CarController) -> None:
    print("Hold mode: keep W/A/S/D pressed to move.")
    print("Release key to stop. Press Q to quit.")
    print("-" * 30)

    last_command = "stop"
    while True:
        command = get_hold_command()

        if command == "quit":
            break

        if command != last_command:
            car.apply(command)
            print(f"Command: {command}")
            last_command = command

        time.sleep(POLL_INTERVAL)

    car.stop()


def run_fallback_mode(car: CarController) -> None:
    reader = TerminalKeyReader()

    print("Drive the car with W/A/S/D.")
    print("w: forward, a: turn left, s: backward, d: turn right")
    print("x: stop, q: quit")
    print("-" * 30)

    while True:
        ascii_code = reader.read_key()
        if ascii_code < 0:
            continue

        command = KEY_BINDINGS.get(ascii_code)
        if command is None:
            printable = chr(ascii_code) if 32 <= ascii_code <= 126 else "unknown"
            print(f"Unsupported input: {printable} (ASCII {ascii_code})")
            continue

        print(f"Command: {command} (ASCII {ascii_code})")

        if command == "quit":
            break

        car.apply(command)

    car.stop()


def main() -> None:
    car = CarController()

    try:
        if hold_mode_available():
            run_hold_mode(car)
        else:
            print("[Info] Hold mode unavailable (keyboard module/permission).")
            print("[Info] Fallback mode enabled. Use x to stop.")
            run_fallback_mode(car)
    except KeyboardInterrupt:
        print("\nExit by Ctrl+C.")
    finally:
        with suppress(Exception):
            car.stop()


if __name__ == "__main__":
    main()
