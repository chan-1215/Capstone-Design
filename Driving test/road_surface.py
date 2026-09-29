"""Independent road-surface gate for the fixed white-mat driving track."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SurfaceReading:
    state: str
    near_fraction: float
    far_fraction: float


def measure_surface(frame, profile: str = "white") -> SurfaceReading:
    height, width = frame.shape[:2]
    if height < 80 or width < 80:
        return SurfaceReading("off_track", 0.0, 0.0)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.int16)
    lightness, a, b = cv2.split(lab)
    if profile == "white":
        road = (lightness > 140) & ((a - b) <= 2)
    elif profile == "black":
        road = (lightness < 100) & (np.abs(a - b) <= 12)
    else:
        raise ValueError(f"unsupported road surface profile: {profile}")

    x1, x2 = int(width * 0.09), int(width * 0.91)
    near = road[int(height * 0.60):int(height * 0.94), x1:x2]
    far = road[int(height * 0.44):int(height * 0.67), x1:x2]
    near_fraction = float(np.mean(near))
    far_fraction = float(np.mean(far))
    if near_fraction < 0.35:
        state = "off_track"
    elif near_fraction >= 0.65 and far_fraction >= 0.55:
        state = "track"
    else:
        state = "uncertain"
    return SurfaceReading(state, near_fraction, far_fraction)


class RoadSurfaceGuard:
    def __init__(self, profile: str = "white", clear_samples: int = 3,
                 off_samples: int = 2, timeout_samples: int = 10) -> None:
        self.profile = profile
        self.clear_samples = clear_samples
        self.off_samples = off_samples
        self.timeout_samples = timeout_samples
        self.clear_count = 0
        self.off_count = 0
        self.uncertain_count = 0
        self.state = "waiting"
        self.reading = SurfaceReading("uncertain", 0.0, 0.0)

    def update(self, frame) -> str:
        self.reading = measure_surface(frame, self.profile)
        if self.reading.state == "track":
            self.clear_count += 1
            self.off_count = 0
            self.uncertain_count = 0
        else:
            self.clear_count = 0
            self.uncertain_count += 1
            self.off_count = self.off_count + 1 if self.reading.state == "off_track" else 0

        if self.off_count >= self.off_samples:
            self.state = "off_track"
        elif self.uncertain_count >= self.timeout_samples:
            self.state = "surface_timeout"
        elif self.clear_count >= self.clear_samples:
            self.state = "track"
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

    def update(self, frame, lane_visible: bool) -> str:
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
        elif surface_state == "track" and self.lane_clear_count >= self.clear_samples:
            self.state = "ready"
        else:
            self.state = "waiting"
        return self.state
