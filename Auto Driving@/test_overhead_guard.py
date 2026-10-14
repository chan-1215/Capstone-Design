import unittest

import cv2
import numpy as np

from overhead_guard import (lane_offset, locate_robot, should_stop,
                            should_stop_surface, track_margin)


class OverheadGuardTest(unittest.TestCase):
    def test_detects_red_chassis(self):
        image = np.full((720, 1280, 3), 230, np.uint8)
        cv2.rectangle(image, (360, 315), (395, 327), (0, 0, 200), -1)
        point = locate_robot(image)
        self.assertAlmostEqual(point[0], 378, delta=2)
        self.assertAlmostEqual(point[1], 321, delta=2)

    def test_lane_offset_and_lost_robot_stop(self):
        self.assertAlmostEqual(lane_offset((378, 320)), 0)
        self.assertLess(lane_offset((345, 320)), 0)
        self.assertEqual(should_stop(0.1, [], None), "track_edge_or_camera_lost")
        self.assertEqual(should_stop(0.1, [], -0.6), "track_edge_or_camera_lost")

    def test_no_visual_motion(self):
        self.assertEqual(should_stop(1.3, [(382, 320), (384, 321)], 0),
                         "no_visual_motion")
        self.assertIsNone(should_stop(1.3, [(382, 320), (390, 300)], 0))

    def test_surface_margin_and_boundary_stop(self):
        image = np.full((200, 200, 3), 60, np.uint8)
        cv2.rectangle(image, (30, 30), (170, 170), (230, 230, 230), -1)
        self.assertGreater(track_margin(image, (100, 100)), 50)
        self.assertLess(track_margin(image, (31, 100)), 4)
        self.assertIsNone(should_stop_surface(0, [], 14, 640))
        self.assertEqual(should_stop_surface(0, [], 10, 640),
                         "track_edge_or_camera_lost")

    def test_surface_margin_needs_visible_road(self):
        image = np.full((200, 200, 3), 60, np.uint8)
        self.assertIsNone(track_margin(image, (100, 100)))


if __name__ == "__main__":
    unittest.main()
