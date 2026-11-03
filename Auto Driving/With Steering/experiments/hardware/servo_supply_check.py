"""Brief steering-only pulse with Pi input voltage readings."""

import subprocess
import time

from gpiozero import AngularServo


def input_voltage():
    result = subprocess.run(
        ["vcgencmd", "pmic_read_adc", "EXT5V_V"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main():
    servo = AngularServo(
        18,
        initial_angle=None,
        min_angle=-90,
        max_angle=90,
        min_pulse_width=0.001,
        max_pulse_width=0.002,
    )
    try:
        print("before:", input_voltage(), flush=True)
        servo.angle = -30
        time.sleep(0.25)
        print("steering:", input_voltage(), flush=True)
        servo.angle = 0
        time.sleep(0.3)
        print("centered:", input_voltage(), flush=True)
    finally:
        servo.detach()
        servo.close()


if __name__ == "__main__":
    main()
