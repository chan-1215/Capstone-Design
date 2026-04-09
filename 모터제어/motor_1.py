from gpiozero import Motor  
from time import sleep

motor1 = Motor(26, 19)
motor2 = Motor(22, 27)
motor3 = Motor(20, 21)
motor4 = Motor(24, 23)

print('Press Ctrl+C to stop')
print('-'*30)

while True:
    print('Motor 1,2,3,4 Forward')
    motor1.forward()
    motor2.forward()
    motor3.forward()
    motor4.forward()
    sleep(3)

    print('Motor 1,2,3,4 Stop')
    motor1.stop()
    motor2.stop()
    motor3.stop()
    motor4.stop()
    sleep(1)

    print('Motor 1,2,3,4 Backward')
    motor1.backward()
    motor2.backward()
    motor3.backward()
    motor4.backward()
    sleep(2)

    print('Motor 1,2,3,4 Stop')
    motor1.stop()
    motor2.stop()
    motor3.stop()
    motor4.stop()
    sleep(1)