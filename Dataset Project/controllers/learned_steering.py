"""Runtime inference for the lightweight image steering model."""

from pathlib import Path

import numpy as np

from controllers.vision_preprocessing import extract_steering_features


class LearnedSteeringModel:
    def __init__(self, model_path):
        data = np.load(Path(model_path))
        self.weights = data["weights"]
        self.feature_mean = data["feature_mean"]
        self.feature_std = data["feature_std"]
        self.image_width = int(data["image_width"])
        self.image_height = int(data["image_height"])
        self.feature_mode = (
            str(data["feature_mode"].item())
            if "feature_mode" in data
            else "grayscale"
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
