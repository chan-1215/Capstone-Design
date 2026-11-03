import unittest

from controllers.learned_control import stabilize_learned_pwm


class LearnedControlTests(unittest.TestCase):
    def test_visible_lane_enforces_minimum_speed(self):
        left_pwm, right_pwm = stabilize_learned_pwm(0.08, 0.08, 0, True)

        self.assertAlmostEqual(left_pwm, 0.32, places=5)
        self.assertAlmostEqual(right_pwm, 0.32, places=5)

    def test_positive_lane_error_adds_left_turn_trim(self):
        left_pwm, right_pwm = stabilize_learned_pwm(0.4, 0.4, 50, True)

        self.assertLess(left_pwm, right_pwm)

    def test_invisible_lane_does_not_trim_pwm(self):
        self.assertEqual(
            stabilize_learned_pwm(0.1, 0.2, 50, False),
            (0.1, 0.2),
        )


if __name__ == "__main__":
    unittest.main()
