import atexit
from gpiozero import Motor

motor4 = Motor(24, 23)

print('Press Ctrl+C to stop')
print('-'*30)

def cleanup():
    print('Motor 4 stopped')
    motor4.stop()

atexit.register(cleanup)

while True:
    print('Motor 4 Forward')
    motor4.forward()