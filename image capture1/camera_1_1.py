from picamera2 import Picamera2
from time import sleep
cam = Picamera2()

cam.start()
sleep(5)

cam.capture_file('camera_test.jpg')

cam.close()



