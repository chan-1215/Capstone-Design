from picamera2 import Picamera2
from time import sleep

cam = Picamera2()
cam.start_recording('video_test.h264')
sleep(10)

cam.stop_recording()

cam.close()