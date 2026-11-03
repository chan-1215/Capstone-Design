"""Identify rear motor side/direction from the Pi terminal. Never drives the servo."""

import argparse
from contextlib import ExitStack
import math
import signal
import time


MOTOR_1_PINS = (20, 21)  # BCM numbering; pin pairs confirmed unchanged by user.
MOTOR_2_PINS = (23, 24)
DEFAULT_SPEED = 0.25
DEFAULT_SECONDS = 0.4
COMMANDS = {'1f': (0, 'forward'), '1b': (0, 'backward'),
            '2f': (1, 'forward'), '2b': (1, 'backward')}


def stop_all(motors):
    error = None
    for motor in motors:
        try:
            motor.stop()
        except Exception as caught:
            error = caught
    if error is not None:
        raise error


def pulse(motors, command, speed, seconds):
    if command not in COMMANDS:
        raise ValueError('Use 1f, 1b, 2f or 2b')
    if not math.isfinite(speed) or not 0 < speed <= .5:
        raise ValueError('Speed must be greater than 0 and at most 0.5')
    if not math.isfinite(seconds) or not 0 < seconds <= 1:
        raise ValueError('Duration must be greater than 0 and at most 1 second')
    index, direction = COMMANDS[command]
    try:
        stop_all(motors)
        getattr(motors[index], direction)(speed)
        time.sleep(seconds)
    finally:
        stop_all(motors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speed', type=float, default=DEFAULT_SPEED)
    parser.add_argument('--seconds', type=float, default=DEFAULT_SECONDS)
    args = parser.parse_args()
    if not math.isfinite(args.speed) or not 0 < args.speed <= .5:
        parser.error('--speed must be greater than 0 and at most 0.5')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 1:
        parser.error('--seconds must be greater than 0 and at most 1')

    from gpiozero import Motor
    from gpiozero.pins.lgpio import LGPIOFactory

    def shutdown(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        with ExitStack() as cleanup:
            factory = LGPIOFactory()
            cleanup.callback(factory.close)
            motors = []
            for pins in (MOTOR_1_PINS, MOTOR_2_PINS):
                motor = Motor(*pins, pin_factory=factory)
                cleanup.callback(motor.close)
                cleanup.callback(motor.stop)
                motors.append(motor)
            print('Lift the wheels before testing. Servo is NOT controlled.')
            print('1f/1b: motor1 GPIO20/21 | 2f/2b: motor2 GPIO23/24')
            print('f/b mean GPIO polarity, NOT confirmed vehicle forward/reverse.')
            print(f'Each command: speed={args.speed:g}, {args.seconds:g}s, then stop.')
            print('Type a command and Enter. q: quit | Ctrl+C: interrupt/stop.')
            while True:
                try:
                    command = input('motor> ').strip().lower()
                except EOFError:
                    break
                if command == 'q':
                    break
                if command not in COMMANDS:
                    print('Use 1f, 1b, 2f, 2b or q. No movement.')
                    continue
                print(f'Testing {command}', flush=True)
                pulse(motors, command, args.speed, args.seconds)
                print('Stopped.', flush=True)
    except KeyboardInterrupt:
        print('\nInterrupted; motor cleanup requested.')


if __name__ == '__main__':
    main()
