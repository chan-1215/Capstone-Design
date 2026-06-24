import cv2
import numpy as np
from picamera2 import Picamera2
from RPLCD.i2c import CharLCD

lcd = CharLCD('PCF8574', 0x27)
picam2 = Picamera2()
picam2.start()

last_msg = ""

while True:
    frame = picam2.capture_array()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower_orange = np.array([85, 50, 150])
    upper_orange = np.array([105, 200, 255])
    mask_orange = cv2.inRange(hsv, lower_orange, upper_orange)

    contours, _ = cv2.findContours(mask_orange, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = [c for c in contours if cv2.contourArea(c) > 500]

    if len(big) == 0:
        msg = "GO"
    else:
        msg = "Detection:\r\nPerson"

    if msg != last_msg:
        lcd.clear()
        lcd.write_string(msg)
        last_msg = msg
        print(msg)

picam2.stop()