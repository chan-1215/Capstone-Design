r"""Interactive motor test console for Raspberry Pi hardware calibration.

Run from the Raspberry Pi:
    cd ~/Capstone-Design/Dataset\ Project
    python3 -B hardware/test_motors_console.py --speed 0.30 --duration 1.0
"""

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

if str(LEE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LEE_DIRECTORY))

from motor_module import cleanup_motor, motor1, motor2, motor3, motor4  # noqa: E402


MOTOR_ORDER = ("1", "2", "3", "4")
MOTOR_LABELS = {
    "1": "motor1 current_label=left_front",
    "2": "motor2 current_label=left_rear",
    "3": "motor3 current_label=right_rear",
    "4": "motor4 current_label=right_front",
}
MOTORS = {
    "1": motor1,
    "2": motor2,
    "3": motor3,
    "4": motor4,
}
GROUPS = {
    "all": ("1", "2", "3", "4"),
    "left": ("1", "2"),
    "right": ("3", "4"),
    "front": ("1", "4"),
    "rear": ("2", "3"),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.30)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--pause", type=float, default=0.25)
    parser.add_argument("--inner-speed", type=float, default=0.05)
    return parser.parse_args()


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def stop_all():
    for motor in MOTORS.values():
        motor.stop()


def pin_text(motor):
    def read_pin(device_name):
        device = getattr(motor, device_name, None)
        pin = getattr(device, "pin", None)
        if pin is None:
            return "?"
        number = getattr(pin, "number", None)
        return str(number if number is not None else pin)

    return f"forward_pin={read_pin('forward_device')} backward_pin={read_pin('backward_device')}"


def print_map():
    print("Current code mapping:")
    for motor_id in MOTOR_ORDER:
        print(f"  {motor_id}: {MOTOR_LABELS[motor_id]} {pin_text(MOTORS[motor_id])}")
    print("Code groups:")
    for name, ids in GROUPS.items():
        labels = ", ".join(f"motor{motor_id}" for motor_id in ids)
        print(f"  {name}: {labels}")


def normalize_direction(token):
    token = token.lower()
    if token in {"f", "fw", "forward", "forwards"}:
        return "forward"
    if token in {"b", "bw", "back", "backward", "backwards", "reverse"}:
        return "backward"
    return None


def normalize_target(token):
    token = token.lower().replace("_", "-")
    if token.startswith("motor") and token[5:] in MOTORS:
        return token[5:]
    if token.startswith("m") and token[1:] in MOTORS:
        return token[1:]
    if token in MOTORS or token in GROUPS:
        return token
    return None


def resolve_target(target):
    if target in MOTORS:
        return (target,)
    if target in GROUPS:
        return GROUPS[target]
    raise ValueError(f"unknown target: {target}")


def run_selected(ids, directions, duration):
    stop_all()
    try:
        for motor_id, direction, speed in directions:
            motor = MOTORS[motor_id]
            if direction == "forward":
                motor.forward(speed=speed)
            elif direction == "backward":
                motor.backward(speed=speed)
            else:
                raise ValueError(f"unknown direction: {direction}")
        time.sleep(duration)
    finally:
        stop_all()


def pulse(target, direction, speed, duration):
    ids = resolve_target(target)
    directions = [(motor_id, direction, speed) for motor_id in ids]
    labels = ", ".join(MOTOR_LABELS[motor_id] for motor_id in ids)
    print(
        f"RUN target={target} direction={direction} speed={speed:.2f} "
        f"duration={duration:.2f}s motors=[{labels}]",
        flush=True,
    )
    run_selected(ids, directions, duration)


def arc(direction, speed, inner_speed, duration):
    if direction == "left":
        directions = [
            ("1", "forward", inner_speed),
            ("2", "forward", inner_speed),
            ("3", "forward", speed),
            ("4", "forward", speed),
        ]
    elif direction == "right":
        directions = [
            ("1", "forward", speed),
            ("2", "forward", speed),
            ("3", "forward", inner_speed),
            ("4", "forward", inner_speed),
        ]
    else:
        raise ValueError(f"unknown arc direction: {direction}")

    print(
        f"RUN arc-{direction} outer_speed={speed:.2f} "
        f"inner_speed={inner_speed:.2f} duration={duration:.2f}s",
        flush=True,
    )
    run_selected(MOTOR_ORDER, directions, duration)


def pivot(direction, speed, duration):
    if direction == "left":
        directions = [
            ("1", "backward", speed),
            ("2", "backward", speed),
            ("3", "forward", speed),
            ("4", "forward", speed),
        ]
    elif direction == "right":
        directions = [
            ("1", "forward", speed),
            ("2", "forward", speed),
            ("3", "backward", speed),
            ("4", "backward", speed),
        ]
    else:
        raise ValueError(f"unknown pivot direction: {direction}")

    print(f"RUN pivot-{direction} speed={speed:.2f} duration={duration:.2f}s", flush=True)
    run_selected(MOTOR_ORDER, directions, duration)


def print_help():
    print(
        """
Commands:
  help                 show this help
  map                  print current code labels and GPIO pins
  status               print current speed/duration settings
  stop                 stop all motors now
  q                    quit

  1f / 1b              pulse motor1 forward/backward
  2f / 2b              pulse motor2 forward/backward
  3f / 3b              pulse motor3 forward/backward
  4f / 4b              pulse motor4 forward/backward

  1 f                 same as 1f
  motor1 backward     same as 1b
  all f               pulse all motors forward
  all b               pulse all motors backward
  left f              pulse current-code left group forward
  right f             pulse current-code right group forward
  front f             pulse current-code front group forward
  rear f              pulse current-code rear group forward

  forward             pulse all motors forward
  backward            pulse all motors backward
  arc-left            left arc using current-code left/right groups
  arc-right           right arc using current-code left/right groups
  pivot-left          spin in place left using current-code groups
  pivot-right         spin in place right using current-code groups
  sequence            guided motor1..4 forward/backward test

  speed 0.30          set pulse speed
  duration 1.0        set pulse duration seconds
  pause 0.25          set pause between guided sequence steps
  inner 0.05          set inner wheel speed for arc-left/arc-right
""".strip()
    )


def guided_sequence(speed, duration, pause):
    for motor_id in MOTOR_ORDER:
        for direction in ("forward", "backward"):
            input(f"Press Enter for motor{motor_id} {direction}, or Ctrl+C to stop...")
            pulse(motor_id, direction, speed, duration)
            time.sleep(pause)


def handle_command(line, state):
    parts = line.strip().lower().split()
    if not parts:
        return True

    command = parts[0]
    if command in {"q", "quit", "exit"}:
        return False
    if command == "help":
        print_help()
        return True
    if command == "map":
        print_map()
        return True
    if command == "status":
        print(
            f"speed={state['speed']:.2f} duration={state['duration']:.2f}s "
            f"pause={state['pause']:.2f}s inner_speed={state['inner_speed']:.2f}"
        )
        return True
    if command == "stop":
        stop_all()
        print("STOP all motors")
        return True
    if command == "sequence":
        guided_sequence(state["speed"], state["duration"], state["pause"])
        return True

    if command in {"speed", "duration", "pause", "inner"} and len(parts) == 2:
        value = float(parts[1])
        if command == "speed":
            state["speed"] = clamp(value)
        elif command == "duration":
            state["duration"] = max(0.05, value)
        elif command == "pause":
            state["pause"] = max(0.0, value)
        elif command == "inner":
            state["inner_speed"] = clamp(value)
        print(
            f"speed={state['speed']:.2f} duration={state['duration']:.2f}s "
            f"pause={state['pause']:.2f}s inner_speed={state['inner_speed']:.2f}"
        )
        return True

    if command in {"forward", "fw"}:
        pulse("all", "forward", state["speed"], state["duration"])
        return True
    if command in {"backward", "back", "reverse"}:
        pulse("all", "backward", state["speed"], state["duration"])
        return True
    if command in {"arc-left", "left-arc"}:
        arc("left", state["speed"], state["inner_speed"], state["duration"])
        return True
    if command in {"arc-right", "right-arc"}:
        arc("right", state["speed"], state["inner_speed"], state["duration"])
        return True
    if command in {"pivot-left", "turn-left"}:
        pivot("left", state["speed"], state["duration"])
        return True
    if command in {"pivot-right", "turn-right"}:
        pivot("right", state["speed"], state["duration"])
        return True

    if len(command) == 2 and command[0] in MOTORS:
        direction = normalize_direction(command[1])
        if direction:
            pulse(command[0], direction, state["speed"], state["duration"])
            return True

    if len(parts) == 2:
        target = normalize_target(parts[0])
        direction = normalize_direction(parts[1])
        if target and direction:
            pulse(target, direction, state["speed"], state["duration"])
            return True

    print(f"Unknown command: {line.strip()}")
    print("Type 'help' for commands.")
    return True


def main():
    args = parse_args()
    state = {
        "speed": clamp(args.speed),
        "duration": max(0.05, args.duration),
        "pause": max(0.0, args.pause),
        "inner_speed": clamp(args.inner_speed),
    }

    print("Motor calibration console")
    print("Lift the wheels before testing. Every run is a timed pulse.")
    print_map()
    print_help()

    try:
        stop_all()
        while True:
            line = input("motor-test> ")
            if not handle_command(line, state):
                break
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        cleanup_motor()


if __name__ == "__main__":
    main()
