# file: camera_6.py

from picamera2 import Picamera2, Preview
from time import sleep
import os
from datetime import datetime

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

cam.start_preview(Preview.QTGL)
cam.start()
sleep(5)

INTERVAL = 5   # 5 seconds

print('Press Ctrl+C to exit')
print('-' * 30)

while True:
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = os.path.join(save_dir, f'{timestamp}.jpg')

    cam.capture_file(filename)
    print(f'Captured {filename}')

    sleep(INTERVAL)
