# file: camera_5.py

from picamera2 import Picamera2, Preview
from time import sleep
import os

cam = Picamera2()                 # 카메라 객체 생성

config = cam.create_still_configuration(     # 환경 설정
    main={
        'size': (1920, 1080),
        'format': 'RGB888',
    }
)

cam.configure(config)

cam.start_preview(Preview.QTGL)   # 미리보기
cam.start()
sleep(5)

save_dir = '/home/pi/basic/images'          # 저장 디렉터리
os.makedirs(save_dir, exist_ok=True)        # 저장 디렉터리 없으면 생성

INTERVAL = 5                        # 5초 간격

counter = 1    # image counter

print('Press Ctrl+C to exit')
print('-' * 30)

while True:
    filename = os.path.join(save_dir, f'img_{counter:03d}.jpg')
    cam.capture_file(filename)
    print(f'Captured {filename}')
    counter += 1
    sleep(INTERVAL)
