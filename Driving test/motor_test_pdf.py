"""Motor test runner based on the professor PDF examples.

GPIO pin setup and movement functions are in motor_module.py. This file only
chooses which test routine to run.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from motor_module import DEFAULT_MOTOR_PINS, MotorController, PinPair, clamp


def parse_pin_pair(text: str) -> PinPair:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("pin pair must look like 26,19")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pins must be integers") from exc


@dataclass
class TestConfig:
    speed: float
    duration: float
    pause: float
    motor_pins: Dict[int, Tuple[int, int]]


def wait_seconds(seconds: float) -> None:
    end_time = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < end_time:
        time.sleep(min(0.05, end_time - time.monotonic()))


def test_each_motor(motors: MotorController, config: TestConfig) -> None:
    for number in [1, 2, 3, 4]:
        print(f"motor{number} forward speed={config.speed:.2f}")
        motors.forward([number], config.speed, direct_pwm=True)
        wait_seconds(config.duration)
        motors.stop([number])
        wait_seconds(config.pause)

        print(f"motor{number} backward speed={config.speed:.2f}")
        motors.backward([number], config.speed, direct_pwm=True)
        wait_seconds(config.duration)
        motors.stop([number])
        wait_seconds(config.pause)


def test_all_forward(motors: MotorController, config: TestConfig) -> None:
    print(f"all motors forward speed={config.speed:.2f}")
    motors.forward([1, 2, 3, 4], config.speed, direct_pwm=True)
    wait_seconds(config.duration)
    motors.stop()


def test_speed_ramp(
    motors: MotorController,
    config: TestConfig,
    step: float,
    max_speed: float,
) -> None:
    speed = 0.0
    increasing = True

    print("speed ramp started")
    while True:
        speed = round(speed, 2)
        print(f"all motors forward speed={speed:.2f}")
        motors.forward([1, 2, 3, 4], speed, direct_pwm=True)
        wait_seconds(config.duration)

        if increasing:
            speed += step
            if speed >= max_speed:
                speed = max_speed
                increasing = False
        else:
            speed -= step
            if speed <= 0.0:
                motors.stop()
                break


def run_warmup(motors: MotorController, config: TestConfig) -> None:
    steps = [
        ("Forward", motors.move_forward),
        ("Turn Left", motors.move_turn_left),
        ("Forward", motors.move_forward),
        ("Backward", motors.move_backward),
        ("Turn Right", motors.move_turn_right),
        ("Backward", motors.move_backward),
    ]

    print("warmup started")
    for label, command in steps:
        print(f"{label} speed={config.speed:.2f}")
        command(config.speed)
        wait_seconds(config.duration)
        motors.stop()
        wait_seconds(config.pause)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "test",
        choices=["each", "all-forward", "ramp", "warmup"],
        help="motor test to run",
    )
    parser.add_argument("--speed", type=float, default=0.35)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--pause", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--motor1-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[1])
    parser.add_argument("--motor2-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[2])
    parser.add_argument("--motor3-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[3])
    parser.add_argument("--motor4-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[4])
    parser.add_argument("--invert-left-pins", action="store_true")
    parser.add_argument("--invert-right-pins", action="store_true")
    parser.add_argument("--min-speed-left", type=float, default=0.30)
    parser.add_argument("--min-speed-right", type=float, default=0.30)
    parser.add_argument("--ramp-step", type=float, default=0.1)
    parser.add_argument("--ramp-max-speed", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = TestConfig(
        speed=clamp(args.speed),
        duration=max(0.0, args.duration),
        pause=max(0.0, args.pause),
        motor_pins={
            1: args.motor1_pins,
            2: args.motor2_pins,
            3: args.motor3_pins,
            4: args.motor4_pins,
        },
    )

    print("PDF-style motor test")
    print("Keep the robot lifted before running real motor output.")
    for number, pins in sorted(config.motor_pins.items()):
        print(f"motor{number}: GPIO {pins[0]}, {pins[1]}")

    motors = MotorController(
        motor_pins=config.motor_pins,
        min_speed_left=args.min_speed_left,
        min_speed_right=args.min_speed_right,
        dry_run=args.dry_run,
        dry_run_verbose=args.dry_run,
        invert_left_pins=args.invert_left_pins,
        invert_right_pins=args.invert_right_pins,
    )

    try:
        if args.test == "each":
            test_each_motor(motors, config)
        elif args.test == "all-forward":
            test_all_forward(motors, config)
        elif args.test == "ramp":
            test_speed_ramp(
                motors,
                config,
                step=max(0.01, args.ramp_step),
                max_speed=clamp(args.ramp_max_speed),
            )
        elif args.test == "warmup":
            run_warmup(motors, config)
    except KeyboardInterrupt:
        print("stopped by user")
    finally:
        motors.cleanup()
        print("motors stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
