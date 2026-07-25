# file name: motor_module.py

from gpiozero import Motor, Robot
import time

motor1 = Motor(22, 27)
motor2 = Motor(24, 23)
motor3 = Motor(21, 16)
motor4 = Motor(19, 26)


front_wheels = Robot(motor1, motor2)
rear_wheels = Robot(motor3, motor4)
right_wheels = Robot(motor1, motor2)
left_wheels = Robot(motor3, motor4)

_last_curve_direction = None

# move forward
def move_forward(current_speed):
    global _last_curve_direction
    _last_curve_direction = "forward"

    front_wheels.forward(speed=current_speed)
    rear_wheels.forward(speed=current_speed)

# move backward
def move_backward(current_speed):
    front_wheels.backward(speed=current_speed)
    rear_wheels.backward(speed=current_speed)

def move_curve_left(current_speed, inner_ratio = 0.3):

    right_wheels.forward(speed=current_speed)
    left_wheels.forward(speed=current_speed * inner_ratio)


def move_curve_right(current_speed, inner_ratio = 0.3):
    
    right_wheels.forward(speed=current_speed * inner_ratio)
    left_wheels.forward(speed=current_speed)

def move_turn_left(current_speed):
    right_wheels.forward(speed=current_speed)
    left_wheels.backward(speed=current_speed)

def move_turn_right(current_speed):
    right_wheels.backward(speed=current_speed)
    left_wheels.forward(speed=current_speed)

def move_stop():
    global _last_curve_direction
    _last_curve_direction = None

    right_wheels.stop()
    left_wheels.stop()

def move_speed_up(current_speed):
    current_speed = min(1.0, current_speed + 0.1)
    return current_speed

def move_speed_down(current_speed):
    current_speed = max(0.0, current_speed - 0.1)
    return current_speed

def cleanup_motor():
    move_stop()
    print('Motors cleaned up')