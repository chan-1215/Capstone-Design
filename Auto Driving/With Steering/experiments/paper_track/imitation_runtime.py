"""NumPy/OpenCV-only inference; no training package is required on the Pi."""

from pathlib import Path

import numpy as np

from imitation_features import features


class ImitationModel:
    def __init__(self, path, allow_unvalidated=False):
        with np.load(Path(path), allow_pickle=False) as data:
            self.validated = bool(data["validated"])
            if not self.validated and not allow_unvalidated:
                raise ValueError("Model is not validated for driving")
            self.coef = data["coef"]
            self.intercept = data["intercept"]
            self.mean = data["mean"]
            self.scale = data["scale"]
            self.classes = data["classes"]
            self.min_probability = float(data["min_probability"])

    def predict(self, frame):
        vector = features(frame)
        logits = self.coef @ ((vector - self.mean) / self.scale) + self.intercept
        logits -= np.max(logits)
        probabilities = np.exp(logits)
        probabilities /= np.sum(probabilities)
        best = int(np.argmax(probabilities))
        confidence = float(probabilities[best])
        command = int(self.classes[best]) if confidence >= self.min_probability else None
        return command, confidence
