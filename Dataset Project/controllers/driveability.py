"""Runtime inference for the drivable / non-drivable safety model."""

from pathlib import Path

import numpy as np

from controllers.vision_preprocessing import extract_steering_features


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
            str(data["feature_mode"].item())
            if "feature_mode" in data
            else "lane_edges"
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
