from gpiozero import Motor  
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

def move_turn_left():
    right_wheel.forward()
    left_wheel.backward()

def move_turn_right():
    right_wheel.backward()
    left_wheel.forward()

def move_stop():
    right_wheel.stop()
    left_wheel.stop()

print('Press Ctrl+C to stop')
print('-'*30)

while True:
    print('1. forward')
    move_forward()
    sleep(1)
    move_stop()
    sleep(0.5)

    print('2. left_turn')
    move_turn_left()
    sleep(1)
    move_stop()
    sleep(0.5)

    print('3. forward')
    move_forward()
    sleep(1)
    move_stop()
    sleep(0.5)

    print('4. backward')
    move_backward()
    sleep(1)
    move_stop()
    sleep(0.5)

    print('5. right_turn')
    move_turn_right()
    sleep(1)
    move_stop()
    sleep(0.5)

    print('6. backward')
    move_tbackward()
    sleep(1)
    move_stop()
    sleep(0.5)

    print('Motor restart...')
    sleep(1)