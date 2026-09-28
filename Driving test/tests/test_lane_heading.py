"""Video-derived turn cues and their fail-closed behavior."""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lane_heading import VideoTurnAssist, estimate_lane_heading


class LaneHeadingTests(unittest.TestCase):
    def test_turn_direction_on_white_and_black_roads(self):
        for road, mark in ((255, 0), (0, 255)):
            for direction, top_x, bottom_x in (("right", 250, 100), ("left", 70, 220)):
                with self.subTest(road=road, direction=direction):
                    frame = np.full((240, 320, 3), road, dtype=np.uint8)
                    cv2.line(frame, (top_x, 100), (bottom_x, 190), (mark,) * 3, 8)
                    heading = estimate_lane_heading(frame)
                    self.assertIsNotNone(heading)
                    self.assertGreater(heading if direction == "right" else -heading, 1.25)

    def test_requires_three_matching_observations(self):
        assist = VideoTurnAssist()
        for heading in (1.3, 1.4):
            assist.observe(heading)
            self.assertIsNone(assist.direction)
        assist.observe(1.5)
        self.assertEqual(assist.direction, "right")
        error, conflict = assist.control_error(0.01, 0.10)
        self.assertLess(error, -0.10)
        self.assertFalse(conflict)
        assist.observe(None)
        self.assertEqual(assist.direction, "right")
        assist.observe(None)
        self.assertIsNone(assist.direction)

    def test_opposed_model_requests_stop(self):
        assist = VideoTurnAssist()
        for _ in range(3):
            assist.observe(-1.4)
        self.assertEqual(assist.direction, "left")
        self.assertEqual(assist.control_error(-0.12, 0.10), (0.0, True))

    def test_balanced_borders_are_not_a_turn_cue(self):
        frame = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.line(frame, (130, 100), (40, 190), (0, 0, 0), 8)
        cv2.line(frame, (190, 100), (280, 190), (0, 0, 0), 8)
        self.assertIsNone(estimate_lane_heading(frame))


if __name__ == "__main__":
    unittest.main()
