"""Read lane results from Lee's existing tracker without modifying it."""

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

if str(LEE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(LEE_DIRECTORY))

from lane_tracking_module import LaneTracker  # noqa: E402


class LeeLaneAdapter:
    def __init__(self):
        self._tracker = LaneTracker(
            frame_width=320,
            crop_y1=60,
            crop_y2=220,
            center_tolerance=25,
            smooth_window=5,
        )

    def process(self, frame):
        result = self._tracker.process(frame)
        return {
            "error": result["smoothed_error"],
            "visible": result["status"] != "no_lane",
            "status": result["status"],
            "direction": result["direction"],
            "debug_frame": result["debug_frame"],
        }
