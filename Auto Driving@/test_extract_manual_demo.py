import unittest

import cv2
import numpy as np

from extract_manual_demo import displayed_error, highlighted, red_robot_center


class ManualDemoExtractionTest(unittest.TestCase):
    def test_highlighted_button(self):
        frame = np.zeros((1314, 1270, 3), np.uint8)
        frame[951:959, 1006:1014] = (77, 120, 68)
        self.assertTrue(highlighted(frame, 1010, 955))
        self.assertFalse(highlighted(frame, 900, 1045))

    def test_displayed_center_error(self):
        frame = np.zeros((1314, 1270, 3), np.uint8)
        cv2.line(frame, (420, 680), (420, 719), (255, 0, 0), 3)
        cv2.line(frame, (520, 680), (520, 719), (0, 255, 0), 3)
        self.assertAlmostEqual(displayed_error(frame), -80, delta=2)
        frame[680:720, 518:523] = 0
        self.assertEqual(displayed_error(frame), "")

    def test_overhead_red_target(self):
        frame = np.zeros((720, 1280, 3), np.uint8)
        cv2.rectangle(frame, (296, 396), (304, 404), (0, 0, 255), -1)
        x, y = red_robot_center(frame)
        self.assertAlmostEqual(x, 300, delta=1)
        self.assertAlmostEqual(y, 400, delta=1)


if __name__ == "__main__":
    unittest.main()
