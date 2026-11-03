"""Hardware-independent lane-following decision policy."""

from dataclasses import dataclass
from enum import Enum


class DriveCommand(str, Enum):
    STOP = "stop"
    FORWARD = "forward"
    CURVE_LEFT = "curve_left"
    CURVE_RIGHT = "curve_right"


@dataclass(frozen=True)
class DriveDecision:
    command: DriveCommand
    speed: float
    reason: str


class LaneFollowPolicy:
    """Convert the existing LaneTracker error into a safe motor command."""

    def __init__(self, base_speed=0.35, curve_speed=0.28,
                 center_tolerance=25, max_missing_frames=3):
        if not 0.0 <= curve_speed <= 1.0 or not 0.0 <= base_speed <= 1.0:
            raise ValueError("speeds must be between 0 and 1")
        if center_tolerance < 0 or max_missing_frames < 0:
            raise ValueError("limits must be non-negative")
        self.base_speed = base_speed
        self.curve_speed = curve_speed
        self.center_tolerance = center_tolerance
        self.max_missing_frames = max_missing_frames
        self._missing_frames = 0
        self._last_command = DriveCommand.STOP

    def decide(self, lane_error, lane_visible, safety_stop=False):
        if safety_stop:
            self._last_command = DriveCommand.STOP
            return DriveDecision(DriveCommand.STOP, 0.0, "safety_stop")

        if not lane_visible:
            self._missing_frames += 1
            if self._missing_frames > self.max_missing_frames:
                self._last_command = DriveCommand.STOP
                return DriveDecision(DriveCommand.STOP, 0.0, "lane_lost")
            if self._last_command is DriveCommand.STOP:
                return DriveDecision(DriveCommand.STOP, 0.0, "lane_not_acquired")
            return DriveDecision(self._last_command, self.curve_speed,
                                 "temporary_lane_loss")

        self._missing_frames = 0
        if abs(lane_error) <= self.center_tolerance:
            decision = DriveDecision(DriveCommand.FORWARD, self.base_speed,
                                     "lane_centered")
        elif lane_error > 0:
            decision = DriveDecision(DriveCommand.CURVE_LEFT, self.curve_speed,
                                     "lane_left_of_camera")
        else:
            decision = DriveDecision(DriveCommand.CURVE_RIGHT, self.curve_speed,
                                     "lane_right_of_camera")
        self._last_command = decision.command
        return decision
