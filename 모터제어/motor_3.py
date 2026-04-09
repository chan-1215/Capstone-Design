from gpiozero import Motor, Robot 
from time import sleep

motor1 = Motor(26, 19)
motor2 = Motor(22, 27)
motor3 = Motor(20, 21)
motor4 = Motor(24, 23)

right_wheel = Robot(motor1, motor2)
left_wheel = Robot(motor3, motor4)

def move_forward():
    right_wheel.forward()
    left_wheel.forward()

def move_backward():
    right_wheel.backward()
    left_wheel.backward()

def move_stop():
    right_wheel.stop()
    left_wheel.stop()

print('Press Ctrl+C to stop')
print('-'*30)

while True:
    move_forward()
    sleep(3)
    move_stop()
    sleep(1)
    move_backward()
    sleep(2)
    move_stop()
    sleep(1)