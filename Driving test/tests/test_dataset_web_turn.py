"""Autonomous turn state and four-motor command checks without GPIO."""

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import road_drive_dataset_web as web
from road_drive_dataset_web import DatasetWebRuntime, TurnDecision


class FakeMotors:
    left_motors = (3, 4)
    right_motors = (1, 2)

    def __init__(self):
        self.calls = []

    def stop(self, numbers=None):
        self.calls.append(("stop", tuple(numbers) if numbers is not None else None))

    def forward(self, numbers, speed, direct_pwm=True):
        self.calls.append(("forward", tuple(numbers), speed))

    def backward(self, numbers, speed, direct_pwm=True):
        self.calls.append(("backward", tuple(numbers), speed))

    def set_side_pwm(self, left, right):
        self.calls.append(("forward_both", left, right))

    def cleanup(self):
        self.stop()


class TurnDecisionTests(unittest.TestCase):
    def test_turn_requires_three_matching_frames(self):
        decision = TurnDecision(0.10, 0.04, 4, enter_frames=3)
        self.assertIsNone(decision.update(0.12))
        self.assertIsNone(decision.update(0.14))
        self.assertIsNone(decision.update(-0.14))
        self.assertIsNone(decision.update(-0.15))
        self.assertEqual(decision.update(-0.16), "right")

    def test_start_requires_centered_visible_line(self):
        runtime = DatasetWebRuntime(SimpleNamespace(dry_run=False, video_turn_assist=True))
        runtime.status.update(camera_online=True, safety_state="driveable")
        self.assertFalse(runtime.set_motor_enabled(True))
        runtime.status.update(opencv_lane_status="both_edges", opencv_lane_error=17.0)
        self.assertTrue(runtime.set_motor_enabled(True))

    def test_turn_keeps_direction_until_four_aligned_frames(self):
        decision = TurnDecision(0.10, 0.04, 4)
        self.assertIsNone(decision.update(0.08))
        self.assertEqual(decision.update(0.12), "left")
        self.assertEqual(decision.update(-0.14), "left")
        for error in (0.03, -0.02, 0.01):
            self.assertEqual(decision.update(error), "left")
        self.assertIsNone(decision.update(0.02))
        self.assertIsNone(decision.update(0.08))
        self.assertEqual(decision.update(-0.11), "right")

    def test_alignment_count_resets_on_large_error(self):
        decision = TurnDecision(0.10, 0.04, 2)
        self.assertEqual(decision.update(-0.12), "right")
        self.assertEqual(decision.update(0.01), "right")
        self.assertEqual(decision.update(0.06), "right")
        self.assertEqual(decision.update(0.01), "right")
        self.assertIsNone(decision.update(0.02))

    def test_sustained_overshoot_reverses_turn(self):
        decision = TurnDecision(0.10, 0.04, 4)
        self.assertEqual(decision.update(0.13), "left")
        self.assertEqual(decision.update(-0.12), "left")
        self.assertEqual(decision.update(-0.13), "left")
        self.assertEqual(decision.update(-0.14), "right")

    def test_autonomous_turn_and_straight_motor_commands(self):
        runtime = DatasetWebRuntime(SimpleNamespace(
            dry_run=False, manual_speed=0.30, left_motor_scale=1.0,
            right_motor_scale=0.90,
        ))
        motors = FakeMotors()
        self.assertEqual(runtime._apply_turn(motors, "right", 0.30), (0.30, -0.135))
        self.assertEqual(motors.calls, [
            ("forward", (3, 4), 0.30),
            ("stop", (1,)),
            ("backward", (2,), 0.27),
        ])
        motors.calls.clear()
        self.assertEqual(runtime._apply_turn(motors, "left", 0.30), (-0.15, 0.27))
        self.assertEqual(motors.calls, [
            ("stop", (3,)),
            ("backward", (4,), 0.30),
            ("forward", (1, 2), 0.27),
        ])
        motors.calls.clear()
        left, right = runtime._apply_forward(motors, 0.40, 0.20)
        self.assertAlmostEqual(left, 0.30)
        self.assertAlmostEqual(right, 0.27)
        self.assertEqual(motors.calls[0][0], "forward_both")

    def test_manual_turn_uses_turn_speed_only(self):
        runtime = DatasetWebRuntime(SimpleNamespace(
            dry_run=False, manual_speed=0.35, turn_speed=0.40,
            left_motor_scale=1.0, right_motor_scale=0.90,
        ))
        motors = FakeMotors()
        left, right = runtime._apply_manual(motors, "right")
        self.assertAlmostEqual(left, 0.40)
        self.assertAlmostEqual(right, -0.18)
        self.assertEqual(motors.calls[0], ("forward", (3, 4), 0.40))
        motors.calls.clear()
        left, right = runtime._apply_manual(motors, "forward")
        self.assertAlmostEqual(left, 0.35)
        self.assertAlmostEqual(right, 0.315)

    def test_slightly_faster_default_speeds(self):
        with patch.object(sys, "argv", ["road_drive_dataset_web.py"]):
            args = web.parse_args()
        self.assertEqual(args.manual_speed, 0.38)
        self.assertEqual(args.turn_speed, 0.48)
        self.assertEqual(args.speed_scale, 1.07)
        self.assertEqual(args.min_forward_pwm, 0.34)
        self.assertEqual(args.max_pwm, 0.58)
        self.assertEqual(args.right_motor_scale, 0.90)
        self.assertTrue(args.video_turn_assist)
        self.assertEqual(args.lane_loss_limit, 3)
        self.assertEqual(args.turn_enter_frames, 3)

    def test_autonomous_loop_stops_forward_during_turn(self):
        predictions = [(0.30, 0.30), (0.20, 0.40), (0.20, 0.40)]
        predictions += [(0.30, 0.30)] * 4
        runtime = DatasetWebRuntime(SimpleNamespace(
            dry_run=False, left_motor_scale=1.0, right_motor_scale=0.90,
            turn_enter_threshold=0.10, turn_exit_threshold=0.04,
            turn_straight_frames=4, turn_speed=0.30, max_turn_seconds=4.0,
            no_safety=True, model=Path("unused"), rotation=0,
            unsafe_frame_limit=8, pwm_alpha=1.0, pwm_step=1.0,
            speed_scale=1.0, steering_scale=1.0, invert_steering=False,
            min_forward_pwm=0.32, max_pwm=0.55, fps=1000,
            jpeg_quality=80, lane_mode="auto", lane_threshold=150, lane_fps=5,
            video_turn_assist=False, turn_enter_frames=1, lane_loss_limit=100,
        ))
        motors = FakeMotors()
        runtime.motor_enabled = True
        runtime.last_client_seen = time.monotonic()

        class Camera:
            def __init__(self):
                self.count = 0

            def read(self):
                self.count += 1
                if self.count == len(predictions):
                    runtime.stop_event.set()
                return np.zeros((240, 320, 3), dtype=np.uint8)

            def stop(self):
                pass

        class Model:
            def __init__(self, _path):
                self.index = 0

            def predict(self, _frame):
                result = predictions[self.index]
                self.index += 1
                return result

        with patch.object(web, "LearnedSteeringModel", Model), \
                patch.object(runtime, "_camera", return_value=Camera()), \
                patch.object(runtime, "_motors", return_value=motors), \
                patch.object(web, "draw_model_preview", side_effect=lambda frame, *_: frame):
            runtime._run()

        forwards = [i for i, call in enumerate(motors.calls) if call[0] == "forward_both"]
        turns = [i for i, call in enumerate(motors.calls) if call[:2] == ("backward", (4,))]
        self.assertEqual(len(forwards), 2)
        self.assertEqual(len(turns), 5)
        self.assertLess(forwards[0], turns[0])
        self.assertLess(turns[-1], forwards[-1])
        self.assertEqual(runtime.status["command"], "auto_forward")
        self.assertEqual(runtime.status["opencv_lane_status"], "lost")
        self.assertIsNotNone(runtime.latest_lane_jpeg)

    def test_video_assist_stops_when_model_disagrees(self):
        args = SimpleNamespace(
            dry_run=False, left_motor_scale=1.0, right_motor_scale=0.90,
            turn_enter_threshold=0.10, turn_exit_threshold=0.04,
            turn_straight_frames=4, turn_speed=0.30, max_turn_seconds=4.0,
            no_safety=True, model=Path("unused"), rotation=0,
            unsafe_frame_limit=8, pwm_alpha=1.0, pwm_step=1.0,
            speed_scale=1.0, steering_scale=1.0, invert_steering=False,
            min_forward_pwm=0.32, max_pwm=0.55, fps=1000,
            jpeg_quality=80, lane_mode="auto", lane_threshold=150, lane_fps=1000,
            video_turn_assist=True, turn_enter_frames=1, lane_loss_limit=100,
        )
        runtime = DatasetWebRuntime(args)
        runtime.motor_enabled = True
        runtime.last_client_seen = time.monotonic()
        motors = FakeMotors()
        frame = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.line(frame, (250, 100), (100, 190), (0, 0, 0), 8)

        class Camera:
            count = 0

            def read(self):
                time.sleep(0.003)
                self.count += 1
                if self.count == 3:
                    runtime.stop_event.set()
                return frame

            def stop(self):
                pass

        class Model:
            def __init__(self, _path):
                pass

            def predict(self, _frame):
                return 0.10, 0.50

        with patch.object(web, "LearnedSteeringModel", Model), \
                patch.object(runtime, "_camera", return_value=Camera()), \
                patch.object(runtime, "_motors", return_value=motors), \
                patch.object(web, "draw_model_preview", side_effect=lambda image, *_: image):
            runtime._run()

        self.assertEqual(runtime.status["command"], "vision_conflict")
        self.assertFalse(runtime.status["motor_enabled"])
        self.assertEqual(runtime.status["actual_left_pwm"], 0.0)
        self.assertEqual(runtime.status["actual_right_pwm"], 0.0)
        self.assertIn("disagree", runtime.status["error_message"])

    def test_centered_borders_prevent_model_only_pivot(self):
        args = SimpleNamespace(
            dry_run=False, left_motor_scale=1.0, right_motor_scale=0.90,
            turn_enter_threshold=0.10, turn_exit_threshold=0.04,
            turn_straight_frames=4, turn_enter_frames=1,
            turn_speed=0.30, max_turn_seconds=4.0,
            no_safety=True, model=Path("unused"), rotation=0,
            unsafe_frame_limit=8, pwm_alpha=1.0, pwm_step=1.0,
            speed_scale=1.0, steering_scale=1.0, invert_steering=False,
            min_forward_pwm=0.32, max_pwm=0.55, fps=1000,
            jpeg_quality=80, lane_mode="auto", lane_threshold=150, lane_fps=1000,
            video_turn_assist=False, lane_loss_limit=3,
        )
        runtime = DatasetWebRuntime(args)
        runtime.motor_enabled = True
        runtime.last_client_seen = time.monotonic()
        motors = FakeMotors()

        class Camera:
            count = 0

            def read(self):
                self.count += 1
                if self.count == 3:
                    runtime.stop_event.set()
                return np.zeros((240, 320, 3), dtype=np.uint8)

            def stop(self):
                pass

        class Model:
            def __init__(self, _path):
                pass

            def predict(self, _frame):
                return 0.10, 0.50

        class Detector:
            def __init__(self, *_args):
                pass

            def process(self, frame):
                return SimpleNamespace(visible=True, status="both_edges", error=0.0,
                                       debug_frame=frame)

        with patch.object(web, "LearnedSteeringModel", Model), \
                patch.object(web, "LaneDetector", Detector), \
                patch.object(runtime, "_camera", return_value=Camera()), \
                patch.object(runtime, "_motors", return_value=motors), \
                patch.object(web, "draw_model_preview", side_effect=lambda image, *_: image):
            runtime._run()

        self.assertEqual(runtime.status["command"], "auto_forward")
        self.assertFalse(any(call[0] == "backward" for call in motors.calls))

    def test_lost_lane_stops_motors_and_latches_fault(self):
        args = SimpleNamespace(
            dry_run=False, left_motor_scale=1.0, right_motor_scale=0.90,
            turn_enter_threshold=0.10, turn_exit_threshold=0.04,
            turn_straight_frames=4, turn_enter_frames=3,
            turn_speed=0.30, max_turn_seconds=4.0,
            no_safety=True, model=Path("unused"), rotation=0,
            unsafe_frame_limit=8, pwm_alpha=1.0, pwm_step=1.0,
            speed_scale=1.0, steering_scale=1.0, invert_steering=False,
            min_forward_pwm=0.32, max_pwm=0.55, fps=1000,
            jpeg_quality=80, lane_mode="auto", lane_threshold=150, lane_fps=1000,
            video_turn_assist=False, lane_loss_limit=3,
        )
        runtime = DatasetWebRuntime(args)
        runtime.motor_enabled = True
        runtime.last_client_seen = time.monotonic()
        motors = FakeMotors()

        class Camera:
            count = 0

            def read(self):
                self.count += 1
                if self.count == 4:
                    runtime.stop_event.set()
                return np.zeros((240, 320, 3), dtype=np.uint8)

            def stop(self):
                pass

        class Model:
            def __init__(self, _path):
                pass

            def predict(self, _frame):
                return 0.30, 0.30

        with patch.object(web, "LearnedSteeringModel", Model), \
                patch.object(runtime, "_camera", return_value=Camera()), \
                patch.object(runtime, "_motors", return_value=motors), \
                patch.object(web, "draw_model_preview", side_effect=lambda image, *_: image):
            runtime._run()

        self.assertEqual(runtime.status["command"], "lane_lost_stop")
        self.assertFalse(runtime.status["motor_enabled"])
        self.assertEqual(runtime.status["actual_left_pwm"], 0.0)
        self.assertEqual(runtime.status["actual_right_pwm"], 0.0)
        self.assertIn("lost", runtime.status["error_message"])


if __name__ == "__main__":
    unittest.main()
