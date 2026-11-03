"""Reusable motor control module for the Driving test folder.

This follows the textbook structure: GPIO pin setup and movement functions live
in this module, while test programs import and call these functions.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Sequence, Tuple


PinPair = Tuple[int, int]

DEFAULT_MOTOR_PINS: Dict[int, PinPair] = {
    1: (26, 19),
    2: (20, 21),
    3: (22, 27),
    4: (24, 23),
}
DEFAULT_MOTOR_TRIM: Dict[int, float] = {
    1: 0.75,
    2: 1.00,
    3: 1.00,
    4: 1.00,
}
DEFAULT_RIGHT_MOTORS = (1, 2)
DEFAULT_LEFT_MOTORS = (3, 4)

MIN_SPEED_RIGHT = 0.30
MIN_SPEED_LEFT = 0.30
MAX_SPEED = 1.0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def map_speed(logical_speed: float, min_speed: float, max_speed: float = MAX_SPEED) -> float:
    """Map 0.0-1.0 logical speed into the physical motor range."""
    logical_speed = clamp(logical_speed, 0.0, 1.0)
    if logical_speed == 0.0:
        return 0.0
    return min_speed + logical_speed * (max_speed - min_speed)


def _swap_pair(pair: PinPair) -> PinPair:
    return pair[1], pair[0]


class MotorController:
    def __init__(
        self,
        motor_pins: Optional[Dict[int, PinPair]] = None,
        motor_trim: Optional[Dict[int, float]] = None,
        left_motors: Sequence[int] = DEFAULT_LEFT_MOTORS,
        right_motors: Sequence[int] = DEFAULT_RIGHT_MOTORS,
        min_speed_left: float = MIN_SPEED_LEFT,
        min_speed_right: float = MIN_SPEED_RIGHT,
        max_speed: float = MAX_SPEED,
        dry_run: bool = False,
        dry_run_verbose: bool = False,
        invert_left_pins: bool = False,
        invert_right_pins: bool = False,
    ) -> None:
        self.left_motors = tuple(left_motors)
        self.right_motors = tuple(right_motors)
        self.min_speed_left = clamp(min_speed_left)
        self.min_speed_right = clamp(min_speed_right)
        self.max_speed = clamp(max_speed)
        self.dry_run = dry_run
        self.dry_run_verbose = dry_run_verbose
        self.motor_pins = dict(DEFAULT_MOTOR_PINS if motor_pins is None else motor_pins)
        self.motor_trim = dict(DEFAULT_MOTOR_TRIM if motor_trim is None else motor_trim)
        self.motors = {}

        for number in self.left_motors:
            if invert_left_pins:
                self.motor_pins[number] = _swap_pair(self.motor_pins[number])
        for number in self.right_motors:
            if invert_right_pins:
                self.motor_pins[number] = _swap_pair(self.motor_pins[number])

        if self.dry_run:
            return

        try:
            from gpiozero import Motor
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "gpiozero is not installed. Install it with:\n"
                "  sudo apt install -y python3-gpiozero python3-lgpio"
            ) from exc

        for number, pins in sorted(self.motor_pins.items()):
            self.motors[number] = Motor(pins[0], pins[1])

    def forward(
        self,
        numbers: Optional[Iterable[int]] = None,
        speed: float = 1.0,
        direct_pwm: bool = True,
    ) -> None:
        for number in self._numbers(numbers):
            self._apply(number, "forward", speed, direct_pwm)

    def backward(
        self,
        numbers: Optional[Iterable[int]] = None,
        speed: float = 1.0,
        direct_pwm: bool = True,
    ) -> None:
        for number in self._numbers(numbers):
            self._apply(number, "backward", speed, direct_pwm)

    def stop(self, numbers: Optional[Iterable[int]] = None) -> None:
        for number in self._numbers(numbers):
            self._apply(number, "stop", 0.0, direct_pwm=True)

    def set_side_pwm(self, left_pwm: float, right_pwm: float) -> None:
        """Drive left/right sides forward using direct PWM values."""
        self.forward(self.left_motors, left_pwm, direct_pwm=True)
        self.forward(self.right_motors, right_pwm, direct_pwm=True)

    def set(self, left_pwm: float, right_pwm: float) -> None:
        self.set_side_pwm(left_pwm, right_pwm)

    def set_side_logical(self, left_speed: float, right_speed: float) -> None:
        self.forward(self.left_motors, left_speed, direct_pwm=False)
        self.forward(self.right_motors, right_speed, direct_pwm=False)

    def move_forward(self, current_speed: float) -> None:
        self.set_side_logical(current_speed, current_speed)

    def move_backward(self, current_speed: float) -> None:
        self.backward(self.left_motors, current_speed, direct_pwm=False)
        self.backward(self.right_motors, current_speed, direct_pwm=False)

    def move_curve_left(self, current_speed: float) -> None:
        self.set_side_logical(current_speed * 0.5, current_speed)

    def move_curve_right(self, current_speed: float) -> None:
        self.set_side_logical(current_speed, current_speed * 0.5)

    def move_turn_left(self, current_speed: float) -> None:
        self.backward(self.left_motors, current_speed, direct_pwm=False)
        self.forward(self.right_motors, current_speed, direct_pwm=False)

    def move_turn_right(self, current_speed: float) -> None:
        self.forward(self.left_motors, current_speed, direct_pwm=False)
        self.backward(self.right_motors, current_speed, direct_pwm=False)

    def cleanup(self) -> None:
        self.stop()
        if not self.dry_run:
            for motor in self.motors.values():
                motor.close()

    def _numbers(self, numbers: Optional[Iterable[int]]) -> Iterable[int]:
        if numbers is None:
            return self.motor_pins.keys()
        return numbers

    def _mapped_speed(self, number: int, speed: float) -> float:
        if number in self.left_motors:
            return map_speed(speed, self.min_speed_left, self.max_speed)
        return map_speed(speed, self.min_speed_right, self.max_speed)

    def _apply(self, number: int, action: str, speed: float, direct_pwm: bool) -> None:
        speed = clamp(speed)
        if action != "stop" and not direct_pwm:
            speed = self._mapped_speed(number, speed)
        if action != "stop":
            speed = clamp(speed * self.motor_trim.get(number, 1.0))

        if self.dry_run:
            if self.dry_run_verbose:
                pins = self.motor_pins[number]
                mode = "pwm" if direct_pwm else "mapped"
                print(
                    f"dry-run motor{number} pins={pins} action={action} "
                    f"speed={speed:.2f} mode={mode}"
                )
            return

        motor = self.motors[number]
        if action == "forward":
            motor.forward(speed=speed)
        elif action == "backward":
            motor.backward(speed=speed)
        else:
            motor.stop()


_controller: Optional[MotorController] = None


def setup_motor(**kwargs) -> MotorController:
    global _controller
    if _controller is not None:
        _controller.cleanup()
    _controller = MotorController(**kwargs)
    return _controller


def get_motor_controller() -> MotorController:
    global _controller
    if _controller is None:
        _controller = MotorController()
    return _controller


def move_forward(current_speed: float) -> None:
    get_motor_controller().move_forward(current_speed)


def move_backward(current_speed: float) -> None:
    get_motor_controller().move_backward(current_speed)


def move_curve_left(current_speed: float) -> None:
    get_motor_controller().move_curve_left(current_speed)


def move_curve_right(current_speed: float) -> None:
    get_motor_controller().move_curve_right(current_speed)


def move_turn_left(current_speed: float) -> None:
    get_motor_controller().move_turn_left(current_speed)


def move_turn_right(current_speed: float) -> None:
    get_motor_controller().move_turn_right(current_speed)


def set_side_pwm(left_pwm: float, right_pwm: float) -> None:
    get_motor_controller().set_side_pwm(left_pwm, right_pwm)


def move_stop() -> None:
    get_motor_controller().stop()


def cleanup_motor() -> None:
    global _controller
    if _controller is not None:
        _controller.cleanup()
        _controller = None
