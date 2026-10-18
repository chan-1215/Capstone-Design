"""Opt-in hardware commands shared by manual input and the bounded pilot."""

from contextlib import ExitStack
from dataclasses import dataclass
import math
import threading
import time


KEYS = ('w', 's', 'a', 'd')


@dataclass(frozen=True)
class DriveConfig:
    servo_pin: int = 18
    a_angle: float = -105
    d_angle: float = 85
    servo_seconds: float = 0.7
    timeout: float = 0.7
    max_speed: float = 0.5
    motors_confirmed: bool = False
    motor1_pins: tuple = (20, 21)
    motor2_pins: tuple = (23, 24)
    motor1_direction: int = 1  # User verified: motor1=left, forward()=vehicle forward.
    motor2_direction: int = 1

    def __post_init__(self):
        for value in (self.a_angle, self.d_angle, self.servo_seconds,
                      self.timeout, self.max_speed):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Control settings must be finite numbers')
        if not -120 <= self.a_angle <= 0 <= self.d_angle <= 120:
            raise ValueError('Steering commands must lie within -120..120')
        if not (0 < self.max_speed <= 1 and self.timeout > 0 and self.servo_seconds > 0):
            raise ValueError('Invalid speed or timeout')
        pins = (self.servo_pin, *self.motor1_pins, *self.motor2_pins)
        if (len(pins) != 5 or len(set(pins)) != 5 or
                any(type(pin) is not int or not 0 <= pin <= 27 for pin in pins)):
            raise ValueError('Use five distinct BCM GPIO numbers from 0..27')
        if self.motor1_direction not in (-1, 1) or self.motor2_direction not in (-1, 1):
            raise ValueError('Motor directions must be -1 or 1')

    def servo_parameters(self):
        # Preserve the tested calibration: -90=1ms, 0=1.5ms, +90=2ms.
        return dict(min_angle=-120, max_angle=120,
                    min_pulse_width=.0015 - 120 * .001 / 180,
                    max_pulse_width=.0015 + 120 * .001 / 180)


class ManualDrive:
    def __init__(self, servo, motors=None, config=None, cleanup=None):
        self.config = config or DriveConfig()
        self.servo = servo
        self.motors = motors
        if motors is not None and not self.config.motors_confirmed:
            raise ValueError('DC hardware requires confirmed wiring')
        self.cleanup = cleanup
        self.lock = threading.RLock()
        self.armed = False
        self.owner = None
        self.sequence = -1
        self.last_input = time.monotonic()
        self.angle = 0
        self.signal_until = None
        self.hold_servo = False
        self.motion_deadline = None
        self.command_started = False
        self.outputs = (0.0, 0.0)
        self.speed = .30
        self.trims = (1.0, 1.0)
        self.reason = 'disabled'
        self.error = None

    def arm(self, client):
        with self.lock:
            if self.armed and self.owner != client:
                raise PermissionError('Another browser controls the robot')
            if not self.armed:
                self.armed = True
                self.owner = client
                self.sequence = -1
                self.command_started = False
                self.last_input = time.monotonic()
                self.reason = 'ready'
                self.error = None

    def status(self):
        with self.lock:
            return dict(available=True, armed=self.armed, owner=self.owner,
                        motors_enabled=self.motors is not None,
                        reason=self.reason, error=self.error,
                        angle=self.angle, pwm_active=self.signal_until is not None,
                        hold_servo=self.hold_servo,
                        motor_outputs=list(self.outputs), speed=self.speed,
                        motor1_scale=self.trims[0], motor2_scale=self.trims[1],
                        a_angle=self.config.a_angle, d_angle=self.config.d_angle,
                        max_speed=self.config.max_speed)

    def _motor_output(self, values):
        if self.motors is None or values == self.outputs:
            return
        if any(old * new < 0 for old, new in zip(self.outputs, values)):
            for motor in self.motors:
                motor.stop()
            time.sleep(.05)
        for motor, value in zip(self.motors, values):
            if value:
                motor.value = value
            else:
                motor.stop()
        self.outputs = values

    def input(self, client, sequence, keys, speed, trim1, trim2):
        if (type(sequence) is not int or not 0 <= sequence <= 9007199254740991 or
                not isinstance(keys, dict) or set(keys) != set(KEYS) or
                any(type(keys[key]) is not bool for key in KEYS)):
            raise ValueError('Invalid keys or sequence')
        for value, maximum in ((speed, self.config.max_speed), (trim1, 1.5), (trim2, 1.5)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError('Speed or motor scale outside limits')
        angle = (0 if keys['a'] == keys['d'] else
                 self.config.a_angle if keys['a'] else self.config.d_angle)
        self._apply(client, sequence, angle, speed, trim1, trim2,
                    int(keys['w']) - int(keys['s']), any(keys.values()), False)

    def follow(self, client, sequence, angle, speed):
        if (type(sequence) is not int or sequence < 0 or
                type(angle) not in (int, float) or not math.isfinite(angle) or
                not self.config.a_angle <= angle <= self.config.d_angle or
                type(speed) not in (int, float) or not math.isfinite(speed) or
                not 0 < speed <= min(.30, self.config.max_speed)):
            raise ValueError('Invalid pilot command')
        self._apply(client, sequence, angle, speed, 1.0, 1.0, 1, True, True)

    def set_deadline(self, client, deadline):
        with self.lock:
            if not self.armed or self.owner != client:
                raise PermissionError('Control owner changed')
            self.motion_deadline = deadline

    def _apply(self, client, sequence, angle, speed, trim1, trim2, direction, active, hold):
        with self.lock:
            if not self.armed or self.owner != client:
                raise PermissionError('Manual control is not armed by this browser')
            if sequence <= self.sequence:
                return
            try:
                started = self.command_started or active
                if started and (angle != self.angle or not self.command_started):
                    self.servo.angle = angle
                    self.angle = angle
                    self.signal_until = time.monotonic() + self.config.servo_seconds
                self.command_started = started
                self.hold_servo = hold
                values = tuple(direction * polarity * min(speed * trim, self.config.max_speed)
                               for polarity, trim in zip(
                                   (self.config.motor1_direction, self.config.motor2_direction),
                                   (trim1, trim2)))
                self._motor_output(values)
                self.sequence = sequence
                self.last_input = time.monotonic()
                if not hold:
                    self.speed, self.trims = speed, (trim1, trim2)
                self.reason = 'pilot' if hold else 'manual' if active else 'ready'
            except Exception as error:
                self.stop('hardware_error')
                self.error = str(error)
                raise RuntimeError(str(error)) from error

    def stop(self, reason='stopped', client=None):
        with self.lock:
            if client is not None and client != self.owner:
                return
            self.armed = False
            self.owner = None
            self.command_started = False
            self.signal_until = None
            self.hold_servo = False
            self.motion_deadline = None
            self.reason = reason
            errors = []
            for device, operation in [(m, 'stop') for m in self.motors or ()] + [(self.servo, 'detach')]:
                try:
                    getattr(device, operation)()
                except Exception as error:
                    errors.append(str(error))
            self.outputs = (0.0, 0.0)
            if errors:
                self.error = '; '.join(errors)

    def tick(self):
        with self.lock:
            now = time.monotonic()
            if self.armed and self.motion_deadline is not None and now >= self.motion_deadline:
                self.stop('time_limit')
            elif self.armed and now - self.last_input > self.config.timeout:
                self.stop('connection_timeout')
            elif not self.hold_servo and self.signal_until is not None and now >= self.signal_until:
                try:
                    self.servo.detach()
                    self.signal_until = None
                except Exception as error:
                    self.stop('hardware_error')
                    self.error = str(error)

    def close(self):
        self.stop('shutdown')
        if self.cleanup:
            self.cleanup.close()


def open_hardware(config):
    from gpiozero import AngularServo, Motor
    from gpiozero.pins.lgpio import LGPIOFactory

    with ExitStack() as stack:
        factory = LGPIOFactory()
        stack.callback(factory.close)
        servo = AngularServo(config.servo_pin, initial_angle=None,
                             pin_factory=factory, **config.servo_parameters())
        stack.callback(servo.close)
        stack.callback(servo.detach)
        motors = None
        if config.motors_confirmed:
            devices = []
            for pins in (config.motor1_pins, config.motor2_pins):
                motor = Motor(*pins, pin_factory=factory)
                stack.callback(motor.close)
                stack.callback(motor.stop)
                devices.append(motor)
            motors = tuple(devices)
        return ManualDrive(servo, motors, config, cleanup=stack.pop_all())
