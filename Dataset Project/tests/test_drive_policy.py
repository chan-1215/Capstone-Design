import unittest

from controllers.drive_policy import DriveCommand, LaneFollowPolicy
from controllers.motor_dispatcher import apply_decision
from simulation import virtual_motor_module as motor


class LaneFollowPolicyTests(unittest.TestCase):
    def setUp(self):
        motor.move_stop()
        self.policy = LaneFollowPolicy(max_missing_frames=2)

    def test_centered_lane_drives_forward(self):
        self.assertEqual(self.policy.decide(10, True).command,
                         DriveCommand.FORWARD)

    def test_lane_error_selects_curve_direction(self):
        self.assertEqual(self.policy.decide(40, True).command,
                         DriveCommand.CURVE_LEFT)
        self.assertEqual(self.policy.decide(-40, True).command,
                         DriveCommand.CURVE_RIGHT)

    def test_safety_stop_has_priority(self):
        self.assertEqual(self.policy.decide(0, True, True).command,
                         DriveCommand.STOP)

    def test_repeated_lane_loss_stops(self):
        self.policy.decide(0, True)
        self.policy.decide(0, False)
        self.policy.decide(0, False)
        decision = self.policy.decide(0, False)
        self.assertEqual(decision.command, DriveCommand.STOP)
        self.assertEqual(decision.reason, "lane_lost")

    def test_dispatcher_controls_virtual_motor(self):
        decision = self.policy.decide(-40, True)
        apply_decision(motor, decision)
        state = motor.get_motor_state()
        self.assertEqual(state.command, "curve_right")
        self.assertEqual(state.speed, decision.speed)


if __name__ == "__main__":
    unittest.main()
