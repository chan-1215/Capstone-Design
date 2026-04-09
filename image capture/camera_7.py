# file: camera_7.py

from picamera2 import Picamera2, Preview
from time import sleep
import os
from datetime import datetime
from gpiozero import Button
from signal import pause

cam = Picamera2()
config = cam.create_still_configuration(
    main={
        'size': (1920, 1080),
        'format': 'RGB888',
    }
)
cam.configure(config)

save_dir = '/home/pi/basic/img'
os.makedirs(save_dir, exist_ok=True)

button = Button(23)


def capture_image():
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = os.path.join(save_dir, f'{timestamp}.jpg')

    cam.start_preview(Preview.QTGL)
    cam.start()
    sleep(3)

    cam.capture_file(filename)
    print(f'Captured {filename}')
    cam.stop_preview()
    cam.stop()
    print('Camera stopped')


button.when_pressed = capture_image      # 버튼 누르면 caputer_image() 함수 실행

print('Press the button to capture an image.')
print('Press Ctrl+C to exit')
print('-' * 30)

pause()
