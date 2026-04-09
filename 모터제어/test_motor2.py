import atexit
from gpiozero import Motor

motor2 = Motor(22, 27)

print('Press Ctrl+C to stop')
print('-'*30)

def cleanup():
    print('Motor 2 stopped')
    motor2.stop()

atexit.register(cleanup)

while True:
    print('Motor 2 Forward')
    motor2.forward()