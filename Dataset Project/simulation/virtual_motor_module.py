"""In-memory replacement for the existing GPIO motor module."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MotorState:
    command: str
    speed: float


_state = MotorState("stop", 0.0)


def _set_state(command, speed=0.0):
    global _state
    if not 0.0 <= speed <= 1.0:
        raise ValueError("speed must be between 0 and 1")
    _state = MotorState(command, speed)
    return _state


def get_motor_state():
    return _state


def move_forward(current_speed):
    return _set_state("forward", current_speed)


def move_backward(current_speed):
    return _set_state("backward", current_speed)


def move_curve_left(current_speed, inner_ratio=0.3):
    del inner_ratio
    return _set_state("curve_left", current_speed)


def move_curve_right(current_speed, inner_ratio=0.3):
    del inner_ratio
    return _set_state("curve_right", current_speed)


def move_turn_left(current_speed):
    return _set_state("turn_left", current_speed)


def move_turn_right(current_speed):
    return _set_state("turn_right", current_speed)


def move_stop():
    return _set_state("stop", 0.0)


def cleanup_motor():
    move_stop()
