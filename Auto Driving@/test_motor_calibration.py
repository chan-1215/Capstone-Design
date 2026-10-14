"""Rear-wheel motor calibration checks using mocked GPIO only."""

import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from road_drive_web import DriveController, apply_forward, apply_reverse


class MotorCalibrationTests(unittest.TestCase):
    def make_driver(self, center=0):
        monitor = SimpleNamespace(
            lock=threading.Lock(), last_frame_at=time.monotonic(),
            begin_capture=lambda: None, end_capture=lambda: None)
        driver = DriveController(monitor, motor1_scale=1.08, motor2_scale=0.89,
                                 servo_center=center)
        driver.motor1, driver.motor2, driver.servo = Mock(), Mock(), Mock()
        return driver

    def test_manual_left_stops_left_rear_and_boosts_right(self):
        driver = self.make_driver()
        self.assertIsNone(driver.manual_command(1, -1))
        driver.motor1.stop.assert_called_once()
        driver.motor1.forward.assert_not_called()
        driver.motor2.backward.assert_called_once_with(0.22 * 0.89 * 1.60)
        self.assertEqual(driver.status()['motor1_pwm_command'], 0)
        self.assertAlmostEqual(driver.status()['motor2_pwm_command'], -0.31328)
        self.assertEqual(driver.servo.angle, -80)

    def test_manual_right_stops_right_rear_and_boosts_left(self):
        driver = self.make_driver()
        self.assertIsNone(driver.manual_command(1, 1))
        driver.motor2.stop.assert_called_once()
        driver.motor2.backward.assert_not_called()
        driver.motor1.forward.assert_called_once_with(0.22 * 1.08 * 1.35)
        self.assertAlmostEqual(driver.status()['motor1_pwm_command'], 0.32076)
        self.assertEqual(driver.status()['motor2_pwm_command'], 0)
        self.assertEqual(driver.servo.angle, 85)

    def test_manual_motor_side_does_not_depend_on_servo_center(self):
        driver = self.make_driver(center=10)
        self.assertIsNone(driver.manual_command(1, -0.1))
        driver.motor1.stop.assert_called_once()
        driver.motor2.backward.assert_called_once_with(0.22 * 0.89 * 1.60)
        self.assertEqual(driver.servo.angle, 1)
        self.assertEqual(driver.status()['servo_target'], driver.servo.angle)

    def test_straight_trim_does_not_apply_to_reverse(self):
        left, right = Mock(), Mock()
        forward = apply_forward(left, right, 0.22, 1.08, 0.89)
        self.assertAlmostEqual(forward[0], 0.26136)
        self.assertAlmostEqual(forward[1], -0.1958)
        reverse = apply_reverse(left, right, 0.22, 1.08, 0.89)
        self.assertAlmostEqual(reverse[0], -0.2376)
        self.assertAlmostEqual(reverse[1], 0.1958)

    def test_forward_pwm_is_clamped_for_both_curves_and_straight(self):
        for direction in (-1, 0, 1):
            with self.subTest(direction=direction):
                commands = apply_forward(Mock(), Mock(), 1.0, 1.2, 1.2, direction)
                self.assertTrue(all(abs(value) <= 1 for value in commands))
                self.assertIn(1.0, [abs(value) for value in commands])

    def test_zero_throttle_moves_only_servo(self):
        driver = self.make_driver()
        self.assertIsNone(driver.manual_command(0, -1))
        driver.motor1.stop.assert_called_once()
        driver.motor2.stop.assert_called_once()
        driver.motor1.forward.assert_not_called()
        driver.motor2.backward.assert_not_called()
        self.assertEqual(driver.motor_pwm_commands, (0, 0))

    def test_release_and_stale_camera_clear_command_pwm(self):
        driver = self.make_driver()
        self.assertIsNone(driver.manual_command(1, 1))
        self.assertIsNone(driver.manual_command(0, 0))
        self.assertEqual(driver.motor_pwm_commands, (0, 0))
        driver.monitor.last_frame_at = time.monotonic()
        self.assertIsNone(driver.manual_command(1, -1))
        driver.monitor.last_frame_at = time.monotonic() - 1
        self.assertIsNotNone(driver.manual_command(1, -1))
        self.assertEqual(driver.motor_pwm_commands, (0, 0))

    def test_auto_servo_transform_is_not_changed_by_manual_fix(self):
        driver = self.make_driver()
        driver.mode, driver.angle = 'auto', 20
        self.assertEqual(driver.status()['servo_target'], -20)
        driver.mode = 'manual'
        self.assertEqual(driver.status()['servo_target'], 22)


if __name__ == '__main__':
    unittest.main()
