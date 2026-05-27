import atexit
from gpiozero import LineSensor, Motor
from time import sleep

motor1 = Motor(26, 19)
motor2 = Motor(22, 27)
motor3 = Motor(20, 21)
motor4 = Motor(24, 23)

right_line = LineSensor(5)
left_line  = LineSensor(6)

SPEED = 0.8

def move_forward():
    motor1.forward(SPEED)
    motor2.forward(SPEED)
    motor3.forward(SPEED)
    motor4.forward(SPEED)

def move_left():
    motor1.forward(SPEED)
    motor2.forward(SPEED)
    motor3.forward(SPEED * 0.3)
    motor4.forward(SPEED * 0.3)

def move_right():
    motor1.forward(SPEED * 0.3)
    motor2.forward(SPEED * 0.3)
    motor3.forward(SPEED)
    motor4.forward(SPEED)

def move_stop():
    motor1.stop()
    motor2.stop()
    motor3.stop()
    motor4.stop()

atexit.register(move_stop)

try:
    while True:
        L = left_line.value
        R = right_line.value

        if L == 1 and R == 1:
            move_forward()
        elif L == 1 and R == 0:
            move_left()
        elif L == 0 and R == 1:
            move_right()
        else:
            move_right()

        sleep(0.05)

except KeyboardInterrupt:
    print('종료')
finally:
    move_stop()