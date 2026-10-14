"""Shared image features for laptop training and Pi inference."""

import cv2
import numpy as np


FEATURE_SIZE = (48, 24)
SCREEN_CROP = (20, 322, 820, 720)
CAMERA_CROP_FRACTIONS = (0.0, 122 / 480, 1.0, 440 / 480)


def road_crop(frame, screen_recording=False):
    height, width = frame.shape[:2]
    if screen_recording:
        if (width, height) not in {(1270, 1314), (1266, 1364)}:
            raise ValueError("Unsupported manual screen recording dimensions")
        x1, y1, x2, y2 = SCREEN_CROP
        crop = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (35, 95, 80), (140, 255, 255))
        crop = cv2.inpaint(crop, mask, 3, cv2.INPAINT_TELEA)
    else:
        x1, y1, x2, y2 = CAMERA_CROP_FRACTIONS
        crop = frame[round(height * y1):round(height * y2),
                     round(width * x1):round(width * x2)]
    if crop.size == 0:
        raise ValueError("Empty road crop")
    return crop


def features(frame, screen_recording=False):
    crop = road_crop(frame, screen_recording)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, FEATURE_SIZE, interpolation=cv2.INTER_AREA)
    return (small.astype(np.float32) / 255.0).reshape(-1)


def road_fraction(frame, screen_recording=False):
    crop = road_crop(frame, screen_recording)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    white = ((light > 150) & (np.abs(a.astype(np.int16) - 128) < 22)
             & (np.abs(b.astype(np.int16) - 128) < 22))
    return float(np.mean(white))
