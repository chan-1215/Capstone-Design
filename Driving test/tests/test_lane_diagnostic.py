"""The dashboard's OpenCV view works for both road color polarities."""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from road_drive_p_control import LaneDetector, load_vision_dependencies


class LaneDiagnosticTests(unittest.TestCase):
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
