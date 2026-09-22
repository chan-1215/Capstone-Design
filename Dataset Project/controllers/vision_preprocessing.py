"""Shared image preprocessing for lane-following models."""

import cv2
import numpy as np


DARK_ROAD_MEDIAN_THRESHOLD = 127
STEERING_CROP_Y1 = 55
STEERING_CROP_Y2 = 230


def normalize_lane_polarity(gray_frame):
    """Return grayscale frame with bright lane markings on a dark road."""
    height, width = gray_frame.shape[:2]
    road_sample = gray_frame[
        (height * 2) // 3:height,
        width // 3:(width * 2) // 3,
    ]
    if float(np.median(road_sample)) > DARK_ROAD_MEDIAN_THRESHOLD:
        return cv2.bitwise_not(gray_frame)
    return gray_frame


def simulate_inverted_road_surface(frame):
    """Return a frame approximating white road with dark lane markings."""
    augmented = frame.copy()
    crop = augmented[STEERING_CROP_Y1:STEERING_CROP_Y2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    dark_road = gray < 110
    bright_marking = gray > 165
    crop[dark_road] = (225, 225, 225)
    crop[bright_marking] = (30, 30, 30)
    return augmented


def extract_steering_features(frame, image_width, image_height, feature_mode="grayscale"):
    crop = frame[STEERING_CROP_Y1:STEERING_CROP_Y2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    normalized = normalize_lane_polarity(gray)
    if feature_mode == "lane_edges":
        blur = cv2.GaussianBlur(normalized, (5, 5), 0)
        normalized = cv2.Canny(blur, 50, 150)
    elif feature_mode != "grayscale":
        raise ValueError(f"unsupported feature_mode: {feature_mode}")
    resized = cv2.resize(
        normalized,
        (image_width, image_height),
        interpolation=cv2.INTER_AREA,
    )
    return resized.astype(np.float32).reshape(-1) / 255.0
