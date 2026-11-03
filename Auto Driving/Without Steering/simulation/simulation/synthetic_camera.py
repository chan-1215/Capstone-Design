"""Generate deterministic road frames before the Webots world is available."""

import cv2
import numpy as np


def make_lane_frame(width=320, height=240, lane_offset=0,
                    left_visible=True, right_visible=True,
                    inverted=False):
    """Return a BGR road image compatible with the existing LaneTracker.

    ``lane_offset`` moves the apparent lane center horizontally in pixels.
    This is a test camera, not a replacement for the real Pi camera module.
    """
    road_color = 210 if inverted else 45
    line_color = (0, 0, 0) if inverted else (255, 255, 255)
    frame = np.full((height, width, 3), road_color, dtype=np.uint8)
    horizon_y = 80
    bottom_y = height - 1
    thickness = 6

    if left_visible:
        cv2.line(
            frame,
            (70 + lane_offset, bottom_y),
            (135 + lane_offset, horizon_y),
            line_color,
            thickness,
        )
    if right_visible:
        cv2.line(
            frame,
            (250 + lane_offset, bottom_y),
            (185 + lane_offset, horizon_y),
            line_color,
            thickness,
        )
    return frame
