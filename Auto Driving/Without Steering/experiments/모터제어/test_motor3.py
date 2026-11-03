import atexit
from gpiozero import Motor

motor3 = Motor(20, 21)

print('Press Ctrl+C to stop')
print('-'*30)

def cleanup():
    print('Motor 3 stopped')
    motor3.stop()

atexit.register(cleanup)

while True:
    print('Motor 3 Forward')
    motor3.forward()