import curses
from gpiozero import Motor

MOTOR1_PINS = (26, 19)
MOTOR2_PINS = (22, 27)
MOTOR3_PINS = (20, 21)
MOTOR4_PINS = (24, 23)

MIN_SPEED = 0.2
MAX_SPEED = 1.0
SPEED_STEP = 0.1
CURVE_RATIO = 0.45
DEFAULT_SPEED = 1.0
FULL_POWER_THRESHOLD = 0.99

motor1 = Motor(*MOTOR1_PINS)
motor2 = Motor(*MOTOR2_PINS)
motor3 = Motor(*MOTOR3_PINS)
motor4 = Motor(*MOTOR4_PINS)

right_motors = (motor1, motor2)
left_motors = (motor3, motor4)


def drive_forward(motors, speed):
  for motor in motors:
    if speed >= FULL_POWER_THRESHOLD:
      motor.forward()
    else:
      motor.forward(speed)


def drive_backward(motors, speed):
  for motor in motors:
    if speed >= FULL_POWER_THRESHOLD:
      motor.backward()
    else:
      motor.backward(speed)


def stop_all():
  for motor in (motor1, motor2, motor3, motor4):
    motor.stop()


def move_forward(speed):
  drive_forward(right_motors, speed)
  drive_forward(left_motors, speed)


def move_backward(speed):
  drive_backward(right_motors, speed)
  drive_backward(left_motors, speed)


def move_turn_left(speed):
  drive_forward(right_motors, speed)
  drive_backward(left_motors, speed)


def move_turn_right(speed):
  drive_backward(right_motors, speed)
  drive_forward(left_motors, speed)


def move_curve_left(speed):
  drive_forward(right_motors, speed)
  drive_forward(left_motors, max(MIN_SPEED, speed * CURVE_RATIO))


def move_curve_right(speed):
  drive_forward(right_motors, max(MIN_SPEED, speed * CURVE_RATIO))
  drive_forward(left_motors, speed)


def draw_screen(stdscr, speed, msg):
  stdscr.clear()
  stdscr.addstr(0, 0, "Motor keyboard control (ESC to exit)")
  stdscr.addstr(1, 0, "w/s: forward/backward | a/d: turn | q/e: curve")
  stdscr.addstr(2, 0, "+/-: speed up/down | space: stop")
  stdscr.addstr(4, 0, f"Speed: {speed:.2f}")
  stdscr.addstr(5, 0, msg)
  stdscr.refresh()


def main(stdscr):
  curses.curs_set(0)
  speed = DEFAULT_SPEED
  msg = "Ready (full-power default)"

  while True:
    draw_screen(stdscr, speed, msg)
    key = stdscr.getch()

    if key in (ord("w"), ord("W")):
      move_forward(speed)
      msg = "Forward"
    elif key in (ord("s"), ord("S")):
      move_backward(speed)
      msg = "Backward"
    elif key in (ord("a"), ord("A")):
      move_turn_left(speed)
      msg = "Turn Left"
    elif key in (ord("d"), ord("D")):
      move_turn_right(speed)
      msg = "Turn Right"
    elif key in (ord("q"), ord("Q")):
      move_curve_left(speed)
      msg = "Curve Left"
    elif key in (ord("e"), ord("E")):
      move_curve_right(speed)
      msg = "Curve Right"
    elif key in (ord("+"), ord("=")):
      speed = min(MAX_SPEED, speed + SPEED_STEP)
      msg = f"Speed Up -> {speed:.2f}"
    elif key == ord("-"):
      speed = max(MIN_SPEED, speed - SPEED_STEP)
      msg = f"Speed Down -> {speed:.2f}"
    elif key == ord(" "):
      stop_all()
      msg = "Stop"
    elif key == 27:
      break
    elif 32 <= key <= 126:
      msg = f"Unknown key: {chr(key)}"
    else:
      msg = f"Unknown key code: {key}"

  stop_all()


try:
  curses.wrapper(main)
finally:
  stop_all()
