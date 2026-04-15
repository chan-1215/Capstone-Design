import curses
from time import monotonic, sleep
from gpiozero import Motor

MOTOR1_PINS = (26, 19)
MOTOR2_PINS = (22, 27)
MOTOR3_PINS = (20, 21)
MOTOR4_PINS = (24, 23)

# All motors use the exact same power value.
MOTOR_POWER = 1.0
DIRECTION_CHANGE_PAUSE = 0.06
RELEASE_TIMEOUT = 0.2

KEY_TO_MOTION = {
  ord("w"): (1, 1, 1, 1),
  ord("W"): (1, 1, 1, 1),
  ord("s"): (-1, -1, -1, -1),
  ord("S"): (-1, -1, -1, -1),
  ord("a"): (1, 1, 0, 0),
  ord("A"): (1, 1, 0, 0),
  ord("d"): (0, 0, 1, 1),
  ord("D"): (0, 0, 1, 1),
  ord(" "): (0, 0, 0, 0),
}

MOTION_LABEL = {
  (1, 1, 1, 1): "Forward",
  (-1, -1, -1, -1): "Backward",
  (1, 1, 0, 0): "Left Turn",
  (0, 0, 1, 1): "Right Turn",
  (0, 0, 0, 0): "Stop",
}

motor1 = Motor(*MOTOR1_PINS)
motor2 = Motor(*MOTOR2_PINS)
motor3 = Motor(*MOTOR3_PINS)
motor4 = Motor(*MOTOR4_PINS)

motors = (motor1, motor2, motor3, motor4)
current_motion = (0, 0, 0, 0)


def drive_motor(motor, direction):
  if direction > 0:
    if MOTOR_POWER >= 0.99:
      motor.forward()
    else:
      motor.forward(MOTOR_POWER)
  elif direction < 0:
    if MOTOR_POWER >= 0.99:
      motor.backward()
    else:
      motor.backward(MOTOR_POWER)
  else:
    motor.stop()


def stop_all():
  for motor in motors:
    motor.stop()


def apply_motion(next_motion):
  global current_motion

  # Prevent weak starts when changing motor direction.
  is_reverse_switch = any(
    prev != 0 and nxt != 0 and prev != nxt
    for prev, nxt in zip(current_motion, next_motion)
  )
  if is_reverse_switch:
    stop_all()
    sleep(DIRECTION_CHANGE_PAUSE)

  for motor, direction in zip(motors, next_motion):
    drive_motor(motor, direction)

  current_motion = next_motion


def draw_screen(stdscr, msg):
  stdscr.clear()
  stdscr.addstr(0, 0, "Motor keyboard control (ESC to exit)")
  stdscr.addstr(1, 0, "w: forward | s: backward | a: left | d: right")
  stdscr.addstr(2, 0, "space: stop")
  stdscr.addstr(4, 0, f"Power: {MOTOR_POWER:.2f} (same for all 4 motors)")
  stdscr.addstr(5, 0, msg)
  stdscr.refresh()


def main(stdscr):
  curses.curs_set(0)
  stdscr.nodelay(True)
  msg = "Ready"
  last_input_time = monotonic()

  while True:
    draw_screen(stdscr, msg)
    key = stdscr.getch()

    if key == 27:
      break

    now = monotonic()

    if key != -1:
      last_input_time = now
      motion = KEY_TO_MOTION.get(key)
      if motion is None:
        if 32 <= key <= 126:
          msg = f"Unknown key: {chr(key)}"
        else:
          msg = f"Unknown key code: {key}"
      else:
        apply_motion(motion)
        msg = MOTION_LABEL[motion]
    elif current_motion != (0, 0, 0, 0) and now - last_input_time >= RELEASE_TIMEOUT:
      apply_motion((0, 0, 0, 0))
      msg = "Stop"

    sleep(0.01)

  stop_all()


try:
  curses.wrapper(main)
finally:
  stop_all()
