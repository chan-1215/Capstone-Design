from gpiozero import Motor  
from time import sleep

motor1 = Motor(26, 19)
motor2 = Motor(22, 27)
motor3 = Motor(20, 21)
motor4 = Motor(24, 23)

def move_forward():
    motor1.forward()
    motor2.forward()
    motor3.forward()
    motor4.forward()

def move_backward():
    motor1.backward()
    motor2.backward()
    motor3.backward()
    motor4.backward()

def move_stop():
    motor1.stop()
    motor2.stop()
    motor3.stop()
    motor4.stop()

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