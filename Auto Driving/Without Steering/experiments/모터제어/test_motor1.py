import atexit
from gpiozero import Motor

motor1 = Motor(26, 19)

print('Press Ctrl+C to stop')
print('-'*30)

def cleanup():
    print('Motor 1 stopped')
    motor1.stop()

atexit.register(cleanup)

while True:
    print('Motor 1 Forward')
    motor1.forward()