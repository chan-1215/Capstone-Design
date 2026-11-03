"""The dashboard's OpenCV view works for both road color polarities."""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from road_drive_p_control import LaneDetector, load_vision_dependencies


class LaneDiagnosticTests(unittest.TestCase):
    def test_borders_must_straddle_camera_center(self):
        detector = LaneDetector("auto", 0.45, 0.98, 150, 50, 70, 55)
        candidates = [
            (193.5, 31.7, 0, 18),
            (170.0, 18.9, 0, 15),
            (116.0, 92.6, 80, 20),
            (81.0, 287.1, 275, 20),
        ]
        self.assertEqual(detector._two_separated_candidates(candidates, 160.0),
                         (31.7, 287.1))
        self.assertIsNone(detector._two_separated_candidates(candidates[:3], 160.0))

    def test_broken_left_border_does_not_displace_lane_center(self):
        load_vision_dependencies()
        detector = LaneDetector("auto", 0.45, 0.98, 150, 50, 70, 55)
        mask = np.zeros((127, 320), dtype=np.uint8)
        cv2.rectangle(mask, (20, 1), (50, 68), 255, -1)
        cv2.rectangle(mask, (95, 35), (115, 115), 255, -1)
        cv2.rectangle(mask, (280, 45), (300, 95), 255, -1)
        target, status = detector._find_target_x(mask, 160.0)
        self.assertEqual(status, "both_edges")
        self.assertAlmostEqual(target, 162.5, delta=2)

    def test_center_line_is_drawn_for_dark_and_bright_roads(self):
        load_vision_dependencies()
        detector = LaneDetector("auto", 0.45, 0.98, 150, 50, 70, 55)
        for background, line_color in ((0, 255), (255, 0)):
            with self.subTest(background=background):
                frame = np.full((240, 320, 3), background, dtype=np.uint8)
                cv2.line(frame, (160, 110), (160, 235), (line_color,) * 3, 8)
                result = detector.process(frame)
                self.assertTrue(result.visible)
                self.assertAlmostEqual(result.target_x, 160, delta=3)
                self.assertEqual(tuple(result.debug_frame[170, 160]), (0, 255, 0))


if __name__ == "__main__":
    unittest.main()
