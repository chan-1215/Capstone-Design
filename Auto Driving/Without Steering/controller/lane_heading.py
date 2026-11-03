"""Conservative turn cue from the direction of visible road markings."""

from collections import deque
from typing import Optional, Tuple

import cv2
import numpy as np


def estimate_lane_heading(frame) -> Optional[float]:
    """Return a signed line slope: positive bends right, negative bends left."""
    height, width = frame.shape[:2]
    y1, y2 = int(height * 0.40), int(height * 0.82)
    if y2 - y1 < 30 or width < 80:
        return None

    gray = cv2.cvtColor(frame[y1:y2], cv2.COLOR_BGR2GRAY)
    sample = gray[int(gray.shape[0] * 0.65):, int(width * 0.35):int(width * 0.65)]
    if sample.size and float(np.median(sample)) > 127:
        gray = 255 - gray
    mask = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 150, 255, cv2.THRESH_BINARY)[1]
    segments = cv2.HoughLinesP(
        mask, 1, np.pi / 180, 25,
        minLineLength=max(24, width // 13), maxLineGap=max(14, width // 23),
    )
    if segments is None:
        return None

    slopes = []
    lengths = []
    for x1, sy1, x2, sy2 in segments.reshape(-1, 4):
        dx, dy = int(x2 - x1), int(sy2 - sy1)
        if abs(dy) < 18 or abs(dx) > abs(dy) * 2:
            continue
        slopes.append(-dx / dy)
        lengths.append(float(np.hypot(dx, dy)))
    if len(slopes) < 2 or sum(lengths) < width * 0.3:
        return None
    positive = sum(length for slope, length in zip(slopes, lengths) if slope > 0.3)
    negative = sum(length for slope, length in zip(slopes, lengths) if slope < -0.3)
    if positive and negative and max(positive, negative) / (positive + negative) < 0.9:
        return None
    return float(np.average(slopes, weights=lengths))


class VideoTurnAssist:
    """Require repeated visual cues before supplementing the steering model."""

    def __init__(self, enter_slope: float = 1.25, required_samples: int = 3) -> None:
        self.enter_slope = enter_slope
        self.required_samples = required_samples
        self.samples = deque(maxlen=required_samples)
        self.direction: Optional[str] = None

    def reset(self) -> None:
        self.samples.clear()
        self.direction = None

    def observe(self, heading: Optional[float]) -> None:
        candidate = None
        if heading is not None and abs(heading) >= self.enter_slope:
            candidate = "right" if heading > 0 else "left"
        self.samples.append(candidate)
        if len(self.samples) == self.required_samples and all(
            sample == candidate for sample in self.samples
        ) and candidate is not None:
            self.direction = candidate
        elif candidate is None and self.samples.count(None) >= 2:
            self.direction = None
        elif candidate is not None and self.direction != candidate:
            self.direction = None

    def control_error(self, model_error: float, enter_threshold: float) -> Tuple[float, bool]:
        if self.direction is None:
            return model_error, False
        desired_sign = 1 if self.direction == "left" else -1
        if model_error * desired_sign <= -enter_threshold:
            return 0.0, True
        return desired_sign * max(abs(model_error), enter_threshold + 0.01), False
