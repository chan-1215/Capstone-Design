import math
import unittest

from controllers.oval_track_expert import (
    OvalTrackExpert,
    RoundedRectangleExpert,
    wrap_angle,
)


class OvalTrackExpertTests(unittest.TestCase):
    def setUp(self):
        self.expert = OvalTrackExpert()

    def test_bottom_straight_drives_nearly_straight(self):
        decision = self.expert.decide(0.0, -1.9, 0.0)
        self.assertAlmostEqual(decision.left_pwm, decision.right_pwm, delta=0.05)
        self.assertLess(decision.cross_track_error, 0.03)

    def test_right_curve_requests_left_turn(self):
        decision = self.expert.decide(3.7, 0.0, math.pi / 2)
        self.assertLess(decision.left_pwm, decision.right_pwm)

    def test_wrap_angle(self):
        self.assertAlmostEqual(wrap_angle(3 * math.pi), -math.pi)
        self.assertAlmostEqual(wrap_angle(-3 * math.pi), -math.pi)

    def test_clockwise_rectangle_top_straight(self):
        expert = RoundedRectangleExpert()
        decision = expert.decide(0.0, 2.0, 0.0)
        self.assertAlmostEqual(decision.left_pwm, decision.right_pwm, delta=0.06)
        self.assertLess(decision.cross_track_error, 0.04)

    def test_three_lane_corner_geometry(self):
        lanes = [RoundedRectangleExpert.for_lane(number) for number in (1, 2, 3)]
        self.assertEqual([lane.corner_radius for lane in lanes], [0.8, 1.4, 2.0])
        self.assertGreater(lanes[0].corner_curvature, lanes[1].corner_curvature)
        self.assertGreater(lanes[1].corner_curvature, lanes[2].corner_curvature)


if __name__ == "__main__":
    unittest.main()
