from picamera2 import Picamera2, Preview
from time import sleep
cam = Picamera2()

cam.start_preview(Preview.QTGL) #OpenGl preview window
cam.start()
sleep(5)

cam.stop_preview()
cam.capture_file('camera_preview_test.jpg')

cam.close()
