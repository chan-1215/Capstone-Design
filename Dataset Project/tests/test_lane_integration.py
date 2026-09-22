import unittest

from controllers.drive_policy import DriveCommand, LaneFollowPolicy
from controllers.lee_lane_adapter import LeeLaneAdapter
from controllers.motor_dispatcher import apply_decision
from simulation.synthetic_camera import make_lane_frame
from simulation import virtual_motor_module as motor


class LaneIntegrationTests(unittest.TestCase):
    def setUp(self):
        motor.move_stop()
        self.tracker = LeeLaneAdapter()
        self.policy = LaneFollowPolicy()

    def test_centered_synthetic_lane_drives_forward(self):
        lane = self.tracker.process(make_lane_frame())
        decision = self.policy.decide(lane["error"], lane["visible"])
        apply_decision(motor, decision)

        self.assertEqual(lane["status"], "both_lanes")
        self.assertEqual(decision.command, DriveCommand.FORWARD)
        self.assertEqual(motor.get_motor_state().command, "forward")

    def test_inverted_lane_colors_drive_forward(self):
        lane = self.tracker.process(make_lane_frame(inverted=True))
        decision = self.policy.decide(lane["error"], lane["visible"])

        self.assertEqual(lane["status"], "both_lanes")
        self.assertEqual(decision.command, DriveCommand.FORWARD)

    def test_blank_frames_eventually_stop(self):
        blank = make_lane_frame(left_visible=False, right_visible=False)
        decision = None
        for _ in range(4):
            lane = self.tracker.process(blank)
            decision = self.policy.decide(lane["error"], lane["visible"])

        self.assertIsNotNone(decision)
        self.assertEqual(decision.command, DriveCommand.STOP)
        self.assertEqual(decision.reason, "lane_lost")


if __name__ == "__main__":
    unittest.main()
