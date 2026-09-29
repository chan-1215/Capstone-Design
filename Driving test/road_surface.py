"""Independent road-surface gate for the fixed white-mat driving track."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SurfaceReading:
    state: str
    near_fraction: float
    far_fraction: float
    far_left: float = 0.0
    far_right: float = 0.0


def measure_surface(frame, profile: str = "white") -> SurfaceReading:
    height, width = frame.shape[:2]
    if height < 80 or width < 80:
        return SurfaceReading("off_track", 0.0, 0.0)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.int16)
    lightness, a, b = cv2.split(lab)
    if profile == "white":
        road = ((lightness > 140) & (np.abs(a - 128) <= 10)
                & (np.abs(b - 128) <= 10) & ((a - b) <= 3))
    elif profile == "black":
        road = (lightness < 100) & (np.abs(a - b) <= 12)
    else:
        raise ValueError(f"unsupported road surface profile: {profile}")

    x1, x2 = int(width * 0.09), int(width * 0.91)
    near = road[int(height * 0.60):int(height * 0.94), x1:x2]
    far = road[int(height * 0.44):int(height * 0.67), x1:x2]
    near_fraction = float(np.mean(near))
    far_fraction = float(np.mean(far))
    middle = far.shape[1] // 2
    far_left = float(np.mean(far[:, :middle]))
    far_right = float(np.mean(far[:, middle:]))
    if near_fraction < 0.35:
        state = "off_track"
    elif near_fraction >= 0.75 and 0.35 <= far_fraction < 0.75 and far_right - far_left >= 0.30:
        state = "corner_right"
    elif near_fraction >= 0.75 and 0.35 <= far_fraction < 0.75 and far_left - far_right >= 0.30:
        state = "corner_left"
    elif near_fraction >= 0.65 and far_fraction >= 0.60:
        state = "track"
    else:
        state = "uncertain"
    return SurfaceReading(state, near_fraction, far_fraction, far_left, far_right)


class RoadSurfaceGuard:
    def __init__(self, profile: str = "white", clear_samples: int = 3,
                 off_samples: int = 2, timeout_samples: int = 10) -> None:
        self.profile = profile
        self.clear_samples = clear_samples
        self.off_samples = off_samples
        self.timeout_samples = timeout_samples
        self.clear_count = 0
        self.corner_count = 0
        self.corner_direction = None
        self.off_count = 0
        self.uncertain_count = 0
        self.state = "waiting"
        self.reading = SurfaceReading("uncertain", 0.0, 0.0)

    def update(self, frame) -> str:
        self.reading = measure_surface(frame, self.profile)
        if self.reading.state == "track":
            self.clear_count += 1
            self.corner_count = 0
            self.corner_direction = None
            self.off_count = 0
            self.uncertain_count = 0
        elif self.reading.state in {"corner_left", "corner_right"}:
            self.corner_count = (self.corner_count + 1 if self.reading.state == self.corner_direction else 1)
            self.corner_direction = self.reading.state
            self.clear_count = 0
            self.off_count = 0
            self.uncertain_count = 0
        else:
            self.clear_count = 0
            self.corner_count = 0
            self.corner_direction = None
            self.uncertain_count += 1
            self.off_count = self.off_count + 1 if self.reading.state == "off_track" else 0

        if self.off_count >= self.off_samples:
            self.state = "off_track"
        elif self.uncertain_count >= self.timeout_samples:
            self.state = "surface_timeout"
        elif self.clear_count >= self.clear_samples:
            self.state = "track"
        elif self.corner_count >= self.clear_samples:
            self.state = self.corner_direction
        else:
            self.state = "waiting"
        return self.state


class VisionGate:
    """Pause on brief uncertainty and expose sustained failures as hard stops."""

    def __init__(self, profile: str = "white", lane_loss_limit: int = 10,
                 clear_samples: int = 3) -> None:
        self.surface = RoadSurfaceGuard(profile, clear_samples=clear_samples)
        self.lane_loss_limit = lane_loss_limit
        self.clear_samples = clear_samples
        self.lane_lost_count = 0
        self.lane_clear_count = 0
        self.state = "waiting"

    def update(self, frame, lane_visible: bool, lane_error=None) -> str:
        surface_state = self.surface.update(frame)
        if lane_visible:
            self.lane_clear_count += 1
            self.lane_lost_count = 0
        else:
            self.lane_clear_count = 0
            self.lane_lost_count += 1

        if surface_state in {"off_track", "surface_timeout"}:
            self.state = surface_state
        elif self.lane_lost_count >= self.lane_loss_limit:
            self.state = "lane_timeout"
        elif surface_state in {"corner_left", "corner_right"} and self.lane_clear_count >= self.clear_samples:
            self.state = surface_state
        elif (surface_state == "track" and self.lane_clear_count >= self.clear_samples
              and (lane_error is None or abs(lane_error) <= 40)):
            self.state = "ready"
        else:
            self.state = "waiting"
        return self.state
