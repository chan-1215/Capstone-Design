"""Run both DC motors opposite to GO test.py for a short test."""

import time

from gpiozero import Motor


# BCM GPIO numbering. Increase only after checking the wheels are clear.
TEST_SECONDS = 2.0


def main():
    motor1 = Motor(20, 21)
    try:
        motor2 = Motor(23, 24)
    except Exception:
        motor1.close()
        raise

    try:
        print(f"Backward test for {TEST_SECONDS} seconds. Press Ctrl+C to stop early.")
        motor1.forward()
        motor2.backward()
        time.sleep(TEST_SECONDS)
    except KeyboardInterrupt:
        print("Stopped by Ctrl+C")
    finally:
        motor1.stop()
        motor2.stop()
        motor1.close()
        motor2.close()
        print("Motors stopped")


if __name__ == "__main__":
    main()
