from __future__ import annotations

import os
import sys
from contextlib import suppress

from gpiozero import Motor, Robot

if os.name != "nt":
    import select
    import termios
    import tty


RIGHT_MOTOR_PINS = ((26, 19), (22, 27))
LEFT_MOTOR_PINS = ((20, 21), (24, 23))

KEY_BINDINGS = {
    ord("w"): ("forward", "forward"),
    ord("a"): ("turn left", "left"),
    ord("s"): ("backward", "backward"),
    ord("d"): ("turn right", "right"),
    ord("x"): ("stop", "stop"),
    ord("q"): ("quit", "quit"),
}


class CarController:
    def __init__(self) -> None:
        right_front = Motor(*RIGHT_MOTOR_PINS[0])
        right_rear = Motor(*RIGHT_MOTOR_PINS[1])
        left_front = Motor(*LEFT_MOTOR_PINS[0])
        left_rear = Motor(*LEFT_MOTOR_PINS[1])

        self.right_wheel = Robot(right_front, right_rear)
        self.left_wheel = Robot(left_front, left_rear)

    def forward(self) -> None:
        self.right_wheel.forward()
        self.left_wheel.forward()

    def backward(self) -> None:
        self.right_wheel.backward()
        self.left_wheel.backward()

    def left(self) -> None:
        self.right_wheel.forward()
        self.left_wheel.backward()

    def right(self) -> None:
        self.right_wheel.backward()
        self.left_wheel.forward()

    def stop(self) -> None:
        self.right_wheel.stop()
        self.left_wheel.stop()


def read_key() -> int:
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


def handle_command(car: CarController, ascii_code: int) -> bool:
    command_info = KEY_BINDINGS.get(ascii_code)
    if command_info is None:
        printable = chr(ascii_code) if 32 <= ascii_code <= 126 else "unknown"
        print(f"Unsupported input: {printable} (ASCII {ascii_code})")
        return True

    label, command = command_info
    print(f"Command: {label} (ASCII {ascii_code})")

    if command == "forward":
        car.forward()
    elif command == "backward":
        car.backward()
    elif command == "left":
        car.left()
    elif command == "right":
        car.right()
    elif command == "stop":
        car.stop()
    elif command == "quit":
        car.stop()
        return False

    return True


def print_guide() -> None:
    print("Drive the car with W/A/S/D.")
    print("w: forward, a: turn left, s: backward, d: turn right")
    print("x: stop, q: quit")
    print("-" * 30)


def main() -> None:
    car = CarController()
    print_guide()

    try:
        while True:
            ascii_code = read_key()
            if ascii_code < 0:
                continue

            if not handle_command(car, ascii_code):
                break
    except KeyboardInterrupt:
        print("\nExit by Ctrl+C.")
    finally:
        with suppress(Exception):
            car.stop()


if __name__ == "__main__":
    main()
