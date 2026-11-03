# file: camera_8.py

from picamera2 import Picamera2
from gpiozero import Button
from datetime import datetime
import os
from time import sleep
from signal import pause

cam = Picamera2()
config = cam.create_still_configuration(
    main={
        'size': (1920, 1080),
        'format': 'YUV420',        # 비디오용 포맷
    }
)
cam.configure(config)

save_dir = '/home/pi/basic/video'
os.makedirs(save_dir, exist_ok=True)

button = Button(23)
record_time = 5   # 5 seconds


def record_video():
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    filename = os.path.join(save_dir, f'video_{timestamp}.h264')

    cam.start_recording(filename)
    sleep(record_time)
    cam.stop_recording()
    print(f'Video saved as {filename}')


button.when_pressed = record_video         # 버튼을 누르면 촬영 시작

print('Press the button to start recording...')
print('Press Ctrl+C to exit')
print('-' * 30)

pause()
