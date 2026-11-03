"""Dataset-trained model inference for Driving test.

The models are small NumPy `.npz` files trained from the dataset project. This
module is standalone so the Raspberry Pi only needs this folder plus the model
files, not the full dataset.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


DARK_ROAD_MEDIAN_THRESHOLD = 127
STEERING_CROP_Y1 = 55
STEERING_CROP_Y2 = 230


def normalize_lane_polarity(gray_frame):
    """Return grayscale input as dark road with bright lane markings."""
    height, width = gray_frame.shape[:2]
    road_sample = gray_frame[
        (height * 2) // 3 : height,
        width // 3 : (width * 2) // 3,
    ]
    if road_sample.size and float(np.median(road_sample)) > DARK_ROAD_MEDIAN_THRESHOLD:
        return cv2.bitwise_not(gray_frame)
    return gray_frame


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


class LearnedSteeringModel:
    def __init__(self, model_path):
        data = np.load(Path(model_path))
        self.weights = data["weights"]
        self.feature_mean = data["feature_mean"]
        self.feature_std = data["feature_std"]
        self.image_width = int(data["image_width"])
        self.image_height = int(data["image_height"])
        self.feature_mode = (
            str(data["feature_mode"].item()) if "feature_mode" in data else "grayscale"
        )
        self.output_min = data["output_min"] if "output_min" in data else np.array([0.0, 0.0])
        self.output_max = data["output_max"] if "output_max" in data else np.array([0.85, 0.85])
        self.steering_min = float(data["steering_min"]) if "steering_min" in data else -0.85
        self.steering_max = float(data["steering_max"]) if "steering_max" in data else 0.85

    def _features(self, frame):
        features = extract_steering_features(
            frame,
            self.image_width,
            self.image_height,
            feature_mode=self.feature_mode,
        )
        normalized = (features - self.feature_mean) / self.feature_std
        return np.append(normalized, 1.0)

    def predict(self, frame):
        left_pwm, right_pwm = self._features(frame) @ self.weights
        left_pwm, right_pwm = np.clip(
            [left_pwm, right_pwm],
            self.output_min,
            self.output_max,
        )
        average_pwm = (left_pwm + right_pwm) / 2.0
        steering = float(np.clip(right_pwm - left_pwm, self.steering_min, self.steering_max))
        limited = np.clip(
            [average_pwm - steering / 2.0, average_pwm + steering / 2.0],
            self.output_min,
            self.output_max,
        )
        return float(limited[0]), float(limited[1])


class DriveabilityModel:
    def __init__(self, model_path):
        data = np.load(Path(model_path))
        self.weights = data["weights"]
        self.feature_mean = data["feature_mean"]
        self.feature_std = data["feature_std"]
        self.image_width = int(data["image_width"])
        self.image_height = int(data["image_height"])
        self.threshold = float(data["threshold"])
        self.feature_mode = (
            str(data["feature_mode"].item()) if "feature_mode" in data else "lane_edges"
        )

    def predict_probability(self, frame):
        features = extract_steering_features(
            frame,
            self.image_width,
            self.image_height,
            feature_mode=self.feature_mode,
        )
        normalized = (features - self.feature_mean) / self.feature_std
        normalized = np.append(normalized, 1.0)
        score = float(normalized @ self.weights)
        return float(np.clip(score, 0.0, 1.0))

    def is_drivable(self, frame):
        return self.predict_probability(frame) >= self.threshold
