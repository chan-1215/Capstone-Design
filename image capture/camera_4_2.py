from picamera2 import Picamera2, Preview
from time import sleep
import os

cam = Picamera2()

config = cam.create_still_configuration(
    main = {
        'size':(1920, 1080),
        'format':'RGB888'
    },
    lores={
        'size':(640, 480),
        'format':'BRG888'
    },
    controls={
        'ExposureTime': 10000,
        'AnalogueGain': 1.4,
    }
)

cam.configure(config)

save_dir = '/home/pi/basic/images'
os.makedirs(save_dir, exist_ok=True)

cam.start_preview(Preview.QTGL) #OpenGl preview window

cam.start()
sleep(5)

test.png = os.path.join(save_dir, 'test_image.png')
cam.capture_file(test.png)

cam.stop_preview()
cam.close()

print(f'Saved as {test.png}')