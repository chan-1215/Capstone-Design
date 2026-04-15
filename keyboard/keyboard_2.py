import curses
from time import sleep
from gpiozero import Motor

MOTOR1_PINS = (26, 19)
MOTOR2_PINS = (22, 27)
MOTOR3_PINS = (20, 21)
MOTOR4_PINS = (24, 23)

MIN_SPEED = 0.3
MAX_SPEED = 1.0
SPEED_STEP = 0.05
CURVE_RATIO = 0.75
DEFAULT_SPEED = 1.0
FULL_POWER_THRESHOLD = 0.99
REVERSE_BOOST_TIME = 0.12

# Per-motor trim for matching wheel force (1.0 means no adjustment).
MOTOR_TRIM = {
  "m1": 1.00,
  "m2": 1.00,
  "m3": 1.00,
  "m4": 1.00,
}

motor1 = Motor(*MOTOR1_PINS)
motor2 = Motor(*MOTOR2_PINS)
motor3 = Motor(*MOTOR3_PINS)
motor4 = Motor(*MOTOR4_PINS)

motor_map = {
  "m1": motor1,
  "m2": motor2,
  "m3": motor3,
  "m4": motor4,
}

right_motor_keys = ("m1", "m2")
left_motor_keys = ("m3", "m4")
last_motion = "stop"


def clamp_speed(value):
  return max(MIN_SPEED, min(MAX_SPEED, value))


def scaled_speed(base_speed, trim):
  return clamp_speed(base_speed * trim)


def drive_forward(motor_keys, speed):
  for key in motor_keys:
    motor = motor_map[key]
    speed_with_trim = scaled_speed(speed, MOTOR_TRIM[key])
    # At full speed, avoid PWM and drive fully ON for maximum torque.
    if speed_with_trim >= FULL_POWER_THRESHOLD:
      motor.forward()
    else:
      motor.forward(speed_with_trim)


def drive_backward(motor_keys, speed):
  for key in motor_keys:
    motor = motor_map[key]
    speed_with_trim = scaled_speed(speed, MOTOR_TRIM[key])
    # At full speed, avoid PWM and drive fully ON for maximum torque.
    if speed_with_trim >= FULL_POWER_THRESHOLD:
      motor.backward()
    else:
      motor.backward(speed_with_trim)


def move_forward(speed):
  drive_forward(right_motor_keys, speed)
  drive_forward(left_motor_keys, speed)


def move_backward(speed):
  drive_backward(right_motor_keys, speed)
  drive_backward(left_motor_keys, speed)


def move_turn_left(speed):
  # Pivot turn: avoids reverse torque loss on one side.
  drive_forward(right_motor_keys, speed)
  stop_group(left_motor_keys)


def move_turn_right(speed):
  # Pivot turn: avoids reverse torque loss on one side.
  stop_group(right_motor_keys)
  drive_forward(left_motor_keys, speed)


def move_curve_left(speed):
  drive_forward(right_motor_keys, speed)
  drive_forward(left_motor_keys, max(MIN_SPEED, speed * CURVE_RATIO))


def move_curve_right(speed):
  drive_forward(right_motor_keys, max(MIN_SPEED, speed * CURVE_RATIO))
  drive_forward(left_motor_keys, speed)


def stop_group(motor_keys):
  for key in motor_keys:
    motor_map[key].stop()


def move_stop():
  for motor in (motor1, motor2, motor3, motor4):
    motor.stop()


def prepare_reverse():
  move_stop()
  sleep(0.05)
  drive_backward(right_motor_keys, MAX_SPEED)
  drive_backward(left_motor_keys, MAX_SPEED)
  sleep(REVERSE_BOOST_TIME)


def draw_screen(stdscr, speed, msg):
  stdscr.clear()
  stdscr.addstr(0, 0, "Motor keyboard control (ESC to exit)")
  stdscr.addstr(1, 0, "w/s: forward/backward | a/d: turn | q/e: curve")
  stdscr.addstr(2, 0, "+/-: speed up/down | space: stop")
  stdscr.addstr(4, 0, f"Speed: {speed:.2f} (max: 1.00)")
  stdscr.addstr(5, 0, msg)
  stdscr.refresh()


def main(stdscr):
  global last_motion
  curses.curs_set(0)
  speed = DEFAULT_SPEED
  msg = "Ready (full-power default)"

  while True:
    draw_screen(stdscr, speed, msg)
    key = stdscr.getch()

    if key in (ord("w"), ord("W")):
      if last_motion == "backward":
        move_stop()
        sleep(0.05)
      move_forward(speed)
      msg = f"Forward ({speed:.2f})"
      last_motion = "forward"
    elif key in (ord("s"), ord("S")):
      if last_motion != "backward":
        prepare_reverse()
      move_backward(speed)
      msg = f"Backward ({speed:.2f})"
      last_motion = "backward"
    elif key in (ord("a"), ord("A")):
      move_turn_left(speed)
      msg = f"Turn Left ({speed:.2f})"
      last_motion = "turn_left"
    elif key in (ord("d"), ord("D")):
      move_turn_right(speed)
      msg = f"Turn Right ({speed:.2f})"
      last_motion = "turn_right"
    elif key in (ord("q"), ord("Q")):
      move_curve_left(speed)
      msg = f"Curve Left ({speed:.2f})"
      last_motion = "curve_left"
    elif key in (ord("e"), ord("E")):
      move_curve_right(speed)
      msg = f"Curve Right ({speed:.2f})"
      last_motion = "curve_right"
    elif key in (ord("+"), ord("=")):
      speed = min(MAX_SPEED, speed + SPEED_STEP)
      msg = f"Speed Up -> {speed:.2f}"
    elif key == ord("-"):
      speed = max(MIN_SPEED, speed - SPEED_STEP)
      msg = f"Speed Down -> {speed:.2f}"
    elif key == ord(" "):
      move_stop()
      msg = "Stop"
      last_motion = "stop"
    elif key == 27:
      break
    elif 32 <= key <= 126:
      msg = f"Unknown key: {chr(key)}"
    else:
      msg = f"Unknown key code: {key}"

  move_stop()


try:
  curses.wrapper(main)
finally:
  move_stop()
