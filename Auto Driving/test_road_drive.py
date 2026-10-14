import unittest
import csv
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from flask import Flask
from werkzeug.serving import make_server

from road_camera_web import Monitor, build_app
from road_vision import analyze
from road_drive_web import (CornerEvidence, DriveController, MAX_STEER_DEGREES, SteeringErrorFilter,
                            apply_forward, apply_reverse, corner_motion, corner_plan, inward_edge_plan, plan, recovery_plan,
                            read_cpu_temp, servo_target, straight_plan, watch_temperature)


def reading(error=0, lane="양쪽 선", confidence=0.8, surface=0.8, heading=0.0):
    return SimpleNamespace(center_error=error, lane=lane,
                           confidence=confidence, surface=surface,
                           heading_error=heading)


class PlanTest(unittest.TestCase):
    def test_recorded_false_pair_recovers_toward_actual_lane(self):
        image = Path(__file__).with_name("test_fixtures") / "next_curve_false_pair_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        line = analyze(frame)
        self.assertEqual(line.lane, "양쪽 선")
        self.assertEqual(line.edge_inward, "right")
        self.assertEqual(inward_edge_plan(line, 0), (0.22, 6))

    def test_mid_corner_single_line_plan_uses_matching_outer_boundary(self):
        line = reading(error=46, lane="한쪽 선", confidence=0.595,
                       surface=0.456, heading=160)
        line.near_surface = 0.927
        line.edge_inward = "right"
        self.assertEqual(plan(line, 0, allow_single=True), (0.22, 6))
        line.edge_inward = "left"
        self.assertIsNone(plan(line, 0, allow_single=True))

    def test_inward_edge_plan_is_directional_and_requires_road(self):
        line = reading(error=-187, lane="한쪽 선", confidence=0.68, surface=0.65)
        line.near_surface = 0.86
        line.edge_inward = "right"
        self.assertEqual(inward_edge_plan(line, 0), (0.22, 6))
        self.assertEqual(inward_edge_plan(line, 49), (0.22, 50))
        line.edge_inward = "left"
        self.assertIsNone(inward_edge_plan(line, 0))
        line.center_error = 187
        self.assertEqual(inward_edge_plan(line, 0), (0.22, -6))
        line.edge_inward = None
        self.assertIsNone(inward_edge_plan(line, 0))
        line.edge_inward = "left"
        line.confidence = 0.5
        self.assertIsNone(inward_edge_plan(line, 0))
        line.confidence = 0.68
        line.surface = 0.57
        self.assertIsNone(inward_edge_plan(line, 0))

    def test_automatic_edge_recovery_is_bounded_and_logged(self):
        line = reading(error=-187, lane="한쪽 선", confidence=0.7, surface=0.78)
        line.near_surface = 0.86
        line.edge_inward = "right"
        line.corner = None
        monitor = SimpleNamespace(lock=threading.Lock(), last_reading=line,
                                  last_frame_at=time.monotonic(),
                                  begin_capture=lambda: None, end_capture=lambda: None)
        driver = DriveController(monitor)
        driver.motor1 = MagicMock()
        driver.motor2 = MagicMock()
        driver.servo = MagicMock()
        with patch("road_drive_web.EDGE_RECOVERY_SECONDS", 0.06):
            self.assertIsNone(driver.start())
            driver.start_thread()
            try:
                time.sleep(0.19)
                history = driver.history()
                self.assertTrue(any(sample["edge_recovering"] and sample["speed"] > 0
                                    for sample in history))
                self.assertFalse(driver.active)
                self.assertEqual(history[0]["run"], 1)
            finally:
                driver.close()

    def test_auto_starts_without_a_vision_precondition(self):
        monitor = SimpleNamespace(lock=threading.Lock(),
                                  last_reading=None,
                                  last_frame_at=0.0,
                                  begin_capture=lambda: None,
                                  end_capture=lambda: None)
        driver = DriveController(monitor)
        driver.motor1 = SimpleNamespace(stop=lambda: None)
        driver.motor2 = SimpleNamespace(stop=lambda: None)
        driver.servo = SimpleNamespace(angle=None)
        self.assertIsNone(driver.start())
        self.assertEqual(driver.state, "주행 중")
        self.assertEqual(driver.status()["auto_start_requests"], 1)
        driver.stop()

    def test_web_start_button_shows_request_feedback(self):
        app = build_app(SimpleNamespace(), driver=SimpleNamespace())
        page = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('onclick="sendDriveCommand(\'start\')"', page)
        self.assertIn('id="startRequests"', page)
        self.assertIn('id="speedInput"', page)
        self.assertIn('id="motor1Scale"', page)
        self.assertIn('id="motor2Scale"', page)
        self.assertIn('id="curveDirection"', page)
        self.assertIn('id="nearSurface"', page)

    def test_gesture_display_is_opt_in_and_does_not_control_motors(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        ok, jpeg = cv2.imencode(".jpg", frame)
        self.assertTrue(ok)
        camera = SimpleNamespace(condition=threading.Condition(), frame=jpeg.tobytes(),
                                 running=True, capture_fps=30.0)
        recognizer = MagicMock()
        recognizer.process.side_effect = lambda image: {
            "debug_frame": image, "label": "stop"}
        module = ModuleType("gesture_recognition_module")
        module.GestureRecognizer = lambda: recognizer
        with patch.dict(sys.modules, {"gesture_recognition_module": module}):
            monitor = Monitor(camera, enable_gesture=True)
        client = build_app(monitor).test_client()
        self.assertIn('id="gesture"', client.get("/").get_data(as_text=True))
        monitor.start()
        try:
            deadline = time.monotonic() + 1
            while monitor.gesture_processed is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNotNone(monitor.gesture_processed)
            self.assertEqual(client.get("/status").get_json()["gesture_label"], "stop")
        finally:
            camera.running = False
            with camera.condition:
                camera.condition.notify_all()
            monitor.stop()
        recognizer.close.assert_called_once()

    def test_web_speed_change_validates_and_updates_controller(self):
        driver = DriveController(SimpleNamespace())
        client = build_app(SimpleNamespace(), driver=driver).test_client()
        self.assertEqual(client.post("/drive/speed", json={"speed": 0.27}).status_code, 200)
        self.assertEqual(driver.status()["forward_speed"], 0.27)
        for speed in (None, True, 0.17, 0.31, "0.25"):
            self.assertEqual(client.post("/drive/speed", json={"speed": speed}).status_code, 400)
            self.assertEqual(driver.status()["forward_speed"], 0.27)

    def test_web_motor_scales_validate_and_update_independently(self):
        driver = DriveController(SimpleNamespace())
        client = build_app(SimpleNamespace(), driver=driver).test_client()
        self.assertEqual(client.post("/drive/motor-scales", json={
            "motor1_scale": 1.05, "motor2_scale": 0.97}).status_code, 200)
        self.assertEqual(driver.status()["motor1_scale"], 1.05)
        self.assertEqual(driver.status()["motor2_scale"], 0.97)
        for invalid in (None, True, 0.79, 1.21, "1.0", float("nan")):
            self.assertEqual(client.post("/drive/motor-scales", json={
                "motor1_scale": invalid, "motor2_scale": 1.0}).status_code, 400)
            self.assertEqual(driver.status()["motor1_scale"], 1.05)
            self.assertEqual(driver.status()["motor2_scale"], 0.97)

    def test_speed_setting_reaches_lane_and_corner_plans(self):
        self.assertEqual(plan(reading(), 0, forward_speed=0.27)[0], 0.27)
        self.assertEqual(plan(reading(lane="한쪽 선", confidence=0.7), 0,
                              allow_single=True, forward_speed=0.27)[0], 0.22)
        self.assertEqual(corner_motion("right", 0, forward_speed=0.27)[0], 0.27)

    def test_auto_uses_vision_control_from_first_command(self):
        class FakeMotor:
            def __init__(self):
                self.command = None

            def forward(self, speed):
                self.command = ("forward", speed)

            def backward(self, speed):
                self.command = ("backward", speed)

            def stop(self):
                self.command = ("stop", 0)

            def close(self):
                pass

        monitor = SimpleNamespace(lock=threading.Lock(), last_reading=reading(error=60),
                                  last_frame_at=time.monotonic(), begin_capture=lambda: None,
                                  end_capture=lambda: None)
        driver = DriveController(monitor)
        driver.motor1, driver.motor2 = FakeMotor(), FakeMotor()
        driver.servo = SimpleNamespace(angle=None, detach=lambda: None,
                                       close=lambda: None)
        self.assertIsNone(driver.start())
        driver.start_thread()
        try:
            time.sleep(0.08)
            self.assertEqual(driver.motor1.command, ("forward", 0.22))
            self.assertEqual(driver.motor2.command, ("backward", 0.22))
            self.assertLess(driver.angle, 0.0)
        finally:
            driver.close()

    def test_corner_requires_three_fresh_consistent_frames(self):
        evidence = CornerEvidence()
        self.assertIsNone(evidence.update("right", 1.00))
        self.assertIsNone(evidence.update("right", 1.00))
        self.assertIsNone(evidence.update("right", 1.04))
        self.assertEqual(evidence.update("right", 1.08), "right")
        self.assertIsNone(evidence.update("left", 1.12))
        self.assertIsNone(evidence.update(None, 1.16))
        self.assertIsNone(evidence.update("right", 1.40))
        self.assertIsNone(evidence.update("right", 1.70))

    def test_reversed_servo_target_keeps_center_and_limits_travel(self):
        self.assertEqual(servo_target(10, 0), 10)
        self.assertEqual(servo_target(10, 20), -10)
        self.assertEqual(servo_target(10, -20), 32)
        self.assertEqual(servo_target(10, -90), 85)
        self.assertEqual(servo_target(0, 85), -85)

    def test_pi_temperature_sensor_uses_millidegrees(self):
        with patch("road_drive_web.THERMAL_SENSOR") as sensor:
            sensor.read_text.return_value = "74950\n"
            self.assertAlmostEqual(read_cpu_temp(), 74.95)

    def test_thermal_guard_stops_drive_and_server(self):
        calls = []
        server = SimpleNamespace(shutdown=lambda: calls.append("server"))
        driver = SimpleNamespace(stop=lambda: calls.append("motor"))
        stop_event = SimpleNamespace(wait=lambda timeout: False)
        watch_temperature(server, driver, stop_event, lambda: 75.1)
        self.assertEqual(calls, ["motor", "server"])

    def test_thermal_guard_shuts_down_live_web_server(self):
        server = make_server("127.0.0.1", 0, Flask(__name__), threaded=True)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        calls = []
        driver = SimpleNamespace(stop=lambda: calls.append("motor"))
        stop_event = SimpleNamespace(wait=lambda timeout: False)
        try:
            watch_temperature(server, driver, stop_event, lambda: 75.1)
            serving.join(timeout=2)
            self.assertFalse(serving.is_alive())
            self.assertEqual(calls, ["motor"])
        finally:
            server.server_close()

    def test_corner_turn_is_bounded_and_requires_vision(self):
        corner = reading(error=None, lane="오른쪽 코너", confidence=0.75, surface=0.88)
        corner.corner = "right"
        self.assertEqual(corner_plan(corner, 0), (0.22, 10))
        self.assertEqual(corner_plan(corner, 80), (0.22, 80))
        self.assertEqual(corner_motion("right", 80), (0.22, 80))
        self.assertEqual(corner_motion("left", 0), (0.22, -10))
        corner.surface = 0.3
        self.assertIsNone(corner_plan(corner, 0))

    def test_recorded_target_jumps_are_reduced(self):
        path = Path(__file__).with_name("manual_demo_20261011.csv")
        steering = SteeringErrorFilter()
        raw_jumps = filtered_jumps = 0
        previous_raw = previous_filtered = None
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                raw = float(row["display_error_px"]) if row["display_error_px"] else None
                filtered = steering.update(raw, float(row["seconds"]))
                if raw is not None and previous_raw is not None:
                    raw_jumps += abs(raw - previous_raw) > 40
                    filtered_jumps += abs(filtered - previous_filtered) > 40
                previous_raw, previous_filtered = raw, filtered
        self.assertEqual(raw_jumps, 90)
        self.assertLess(filtered_jumps, raw_jumps)

    def test_steering_filter_suppresses_single_jump_without_reusing_old_frames(self):
        steering = SteeringErrorFilter()
        self.assertEqual(steering.update(0, 1.00), 0)
        self.assertEqual(steering.update(100, 1.03), 50)
        self.assertEqual(steering.update(0, 1.06), 0)
        self.assertEqual(steering.update(0, 1.06), 0)
        self.assertEqual(len(steering.errors), 3)
        self.assertEqual(steering.update(80, 1.40), 80)
        self.assertIsNone(steering.update(None, 1.43))
        self.assertEqual(steering.update(-30, 1.46), -30)

    def test_filtered_steering_keeps_raw_vision_safety_limit(self):
        self.assertEqual(plan(reading(error=100), 0, filtered_error=0)[1], 0)
        self.assertIsNone(plan(reading(error=230), 0, filtered_error=0))
        self.assertIsNone(plan(reading(error=140), 0, filtered_error=0))

    def test_raw_stream_waits_for_new_frame(self):
        camera = SimpleNamespace(condition=threading.Condition(), frame=b"first",
                                 running=True)
        monitor = SimpleNamespace(camera=camera, running=True)
        response = build_app(monitor).test_client().get("/stream/raw", buffered=False)
        self.assertIn(b"first", next(response.response))
        self.assertIn("no-store", response.headers["Cache-Control"])
        chunks = []
        reader = threading.Thread(target=lambda: chunks.append(next(response.response)))
        reader.start()
        time.sleep(0.05)
        self.assertTrue(reader.is_alive())
        with camera.condition:
            camera.frame = b"second"
            camera.condition.notify_all()
        reader.join(timeout=1)
        self.assertFalse(reader.is_alive())
        self.assertIn(b"second", chunks[0])
        response.close()

    def test_capture_keeps_only_trial_frames(self):
        monitor = Monitor(SimpleNamespace())
        monitor.begin_capture()
        monitor.recorded_frames.append((1.0, b"jpeg"))
        self.assertEqual(monitor.capture(), [(1.0, b"jpeg")])
        monitor.end_capture()
        monitor.begin_capture()
        self.assertEqual(monitor.capture(), [])

    def test_forward_motor_polarity(self):
        class FakeMotor:
            def __init__(self):
                self.command = None

            def forward(self, speed):
                self.command = ("forward", speed)

            def backward(self, speed):
                self.command = ("backward", speed)

        motor1, motor2 = FakeMotor(), FakeMotor()
        apply_forward(motor1, motor2, 0.22)
        self.assertEqual(motor1.command, ("forward", 0.22))
        self.assertEqual(motor2.command, ("backward", 0.22))

        apply_forward(motor1, motor2, 0.22, motor1_scale=0.9)
        self.assertAlmostEqual(motor1.command[1], 0.198)
        self.assertEqual(motor2.command, ("backward", 0.22))

        apply_forward(motor1, motor2, 0.22, motor2_scale=1.1)
        self.assertEqual(motor1.command, ("forward", 0.22))
        self.assertAlmostEqual(motor2.command[1], 0.242)

        apply_reverse(motor1, motor2, 0.22)
        self.assertEqual(motor1.command, ("backward", 0.22))
        self.assertEqual(motor2.command, ("forward", 0.22))

    def test_straight_mode_keeps_steering_centered_and_checks_surface(self):
        self.assertEqual(straight_plan(reading(error=100), True)[1], 0)
        self.assertEqual(straight_plan(reading(), True, 0.28)[0], 0.28)
        self.assertIsNone(straight_plan(reading(error=140), True))
        self.assertIsNone(straight_plan(reading(lane="한쪽 선"), True))
        self.assertIsNone(straight_plan(reading(surface=0.2), True))
        self.assertIsNone(straight_plan(reading(), False))

    def test_steers_toward_target(self):
        self.assertLess(plan(reading(60), 0)[1], 0)
        self.assertGreater(plan(reading(-60), 0)[1], 0)
        self.assertEqual(plan(reading(), 0, forward_speed=0.28)[0], 0.28)

    def test_camera_bias_corrects_steering_without_hiding_large_raw_error(self):
        self.assertLess(plan(reading(140), 0, camera_center_bias=100)[1], 0)
        self.assertGreater(plan(reading(60), 0, camera_center_bias=100)[1], 0)
        self.assertIsNone(plan(reading(230), 0, camera_center_bias=130))
        self.assertIsNotNone(straight_plan(reading(140), True,
                                           camera_center_bias=100))

    def test_rejects_unreliable_vision(self):
        self.assertIsNone(plan(None, 0))
        self.assertIsNone(plan(reading(lane="한쪽 선"), 0))
        self.assertIsNone(plan(reading(confidence=0.1), 0))
        self.assertIsNone(plan(reading(surface=0.1), 0))
        self.assertIsNone(plan(reading(error=200), 0))

    def test_short_single_line_assist_is_slower_and_rate_limited(self):
        speed, angle = plan(reading(error=-100, lane="한쪽 선", confidence=0.7),
                            -10, allow_single=True, forward_speed=0.27)
        self.assertEqual(speed, 0.22)
        self.assertLess(speed, plan(reading(), 0, forward_speed=0.27)[0])
        self.assertLessEqual(angle - (-10), 6)

    def test_single_line_curve_heading_can_override_near_center_error(self):
        curve = reading(error=54, lane="한쪽 선", confidence=0.68,
                        surface=0.85, heading=40.5)
        self.assertEqual(plan(curve, 0, allow_single=True)[0], 0.22)
        self.assertGreater(plan(curve, 0, allow_single=True)[1], 0)
        self.assertLess(plan(reading(error=54, lane="한쪽 선"), 0,
                             allow_single=True)[1], 0)
        self.assertIsNone(plan(curve, 0))
        curve.confidence = 0.5
        self.assertIsNone(plan(curve, 0, allow_single=True))

    def test_strong_single_line_curve_allows_bounded_extra_steering(self):
        curve = reading(error=-138, lane="한쪽 선", confidence=0.69,
                        surface=0.68, heading=160)
        self.assertEqual(plan(curve, 70, allow_single=True), (0.22, 70))
        self.assertEqual(plan(curve, 0, allow_single=True), (0.22, 6))
        curve.center_error = 54
        self.assertEqual(plan(curve, 70, allow_single=True), (0.22, 70))
        curve.center_error = 138
        self.assertIsNone(plan(curve, 0, allow_single=True))
        curve.center_error = -138
        self.assertIsNone(plan(reading(error=-138, lane="한쪽 선",
                                       confidence=0.69, surface=0.68), 0,
                                allow_single=True))
        self.assertIsNone(plan(reading(error=-138, lane="한쪽 선",
                                       confidence=0.69, surface=0.68,
                                       heading=-160), 0, allow_single=True))
        self.assertIsNone(plan(reading(error=-181, lane="한쪽 선",
                                       confidence=0.69, surface=0.68,
                                       heading=160), 0, allow_single=True))
        curve.surface = 0.64
        self.assertIsNone(plan(curve, 0, allow_single=True))

    def test_late_curve_needs_visible_near_road(self):
        curve = reading(error=-11, lane="한쪽 선", confidence=0.61,
                        surface=0.5, heading=160)
        curve.near_surface = 0.92
        self.assertEqual(plan(curve, 70, allow_single=True), (0.22, 70))
        self.assertIsNone(plan(curve, 0))
        curve.near_surface = 0.7
        self.assertIsNone(plan(curve, 0, allow_single=True))

    def test_high_quality_single_line_can_recenter_but_not_leave_road(self):
        line = reading(error=157, lane="한쪽 선", confidence=0.7,
                       surface=0.93, heading=-16)
        line.near_surface = 0.97
        self.assertEqual(plan(line, 0, allow_single=True), (0.22, -6))
        self.assertIsNone(plan(line, 0))
        line.near_surface = 0.7
        self.assertIsNone(plan(line, 0, allow_single=True))
        line.near_surface = 0.97
        line.center_error = 200
        self.assertIsNone(plan(line, 0, allow_single=True))

    def test_single_line_assist_continues_past_old_timeout(self):
        monitor = SimpleNamespace(lock=threading.Lock(),
                                  last_reading=reading(error=54, lane="한쪽 선",
                                                       confidence=0.68, surface=0.85,
                                                       heading=40.5),
                                  last_frame_at=time.monotonic(),
                                  begin_capture=lambda: None,
                                  end_capture=lambda: None)
        driver = DriveController(monitor)
        driver.motor1, driver.motor2, driver.servo = MagicMock(), MagicMock(), MagicMock()
        self.assertIsNone(driver.start())
        driver.last_both_at = time.monotonic() - 0.6
        driver.start_thread()
        try:
            time.sleep(0.08)
            self.assertTrue(driver.active)
            driver.motor1.forward.assert_called()
            self.assertGreater(driver.angle, 0)
            with driver.lock:
                driver.last_both_at = time.monotonic() - 2.1
            time.sleep(0.08)
            self.assertTrue(driver.active)
            with driver.lock:
                driver.last_both_at = time.monotonic() - 5.1
            time.sleep(0.08)
            self.assertFalse(driver.active)
            driver.motor1.stop.assert_called()
        finally:
            driver.close()

    def test_limits_steering(self):
        self.assertLessEqual(abs(plan(reading(120), -MAX_STEER_DEGREES)[1]),
                             MAX_STEER_DEGREES)

    def test_recovery_is_bounded_and_requires_visible_road(self):
        self.assertEqual(recovery_plan(reading(lane="한쪽 선"), True, "left"),
                         (0.22, -MAX_STEER_DEGREES))
        self.assertEqual(recovery_plan(reading(), True, "right"),
                         (0.22, MAX_STEER_DEGREES))
        self.assertIsNone(recovery_plan(reading(surface=0.2), True, "left"))
        self.assertIsNone(recovery_plan(reading(), False, "right"))

    def test_servo_hold_stays_active_until_stop(self):
        class FakeServo:
            def __init__(self):
                self.angle = None
                self.detach_count = 0

            def detach(self):
                self.detach_count += 1

        monitor = SimpleNamespace(lock=threading.Lock(),
                                  last_reading=reading(),
                                  last_frame_at=time.monotonic(),
                                  begin_capture=lambda: None,
                                  end_capture=lambda: None)
        driver = DriveController(monitor, hold_steering=True)
        driver.motor1 = SimpleNamespace(stop=lambda: None)
        driver.motor2 = SimpleNamespace(stop=lambda: None)
        driver.servo = FakeServo()
        self.assertIsNone(driver.start())
        self.assertEqual(driver.servo.angle, 0)
        self.assertEqual(driver.servo.detach_count, 0)
        driver.stop()
        self.assertEqual(driver.servo.detach_count, 0)
        self.assertIsNotNone(driver.center_detach_at)

    def test_auto_stop_centers_steering_before_detach(self):
        calls = []

        class FakeServo:
            @property
            def angle(self):
                return None

            @angle.setter
            def angle(self, value):
                calls.append(("angle", value))

            def detach(self):
                calls.append(("detach",))

        monitor = SimpleNamespace(lock=threading.Lock(),
                                  last_reading=reading(),
                                  last_frame_at=time.monotonic(),
                                  begin_capture=lambda: None,
                                  end_capture=lambda: None)
        driver = DriveController(monitor)
        self.assertTrue(driver.hold_steering)
        driver.motor1 = SimpleNamespace(stop=lambda: calls.append(("motor1_stop",)))
        driver.motor2 = SimpleNamespace(stop=lambda: calls.append(("motor2_stop",)))
        driver.servo = FakeServo()
        self.assertIsNone(driver.start())
        driver.last_angle = 20
        driver.stop()
        self.assertEqual(calls[-3:], [("motor1_stop",), ("motor2_stop",),
                                      ("angle", 0.0)])
        self.assertNotIn(("detach",), calls)
        self.assertIsNotNone(driver.center_detach_at)
        center_detach_at = driver.center_detach_at
        driver.stop()
        self.assertEqual(driver.center_detach_at, center_detach_at)
        self.assertEqual(calls[-2:], [("motor1_stop",), ("motor2_stop",)])

    def test_manual_extreme_detaches_but_center_stays_attached(self):
        class FakeServo:
            def __init__(self):
                self.angle = None
                self.detach_count = 0

            def detach(self):
                self.detach_count += 1

            def close(self):
                pass

        motor = SimpleNamespace(stop=lambda: None, forward=lambda speed: None,
                                backward=lambda speed: None, close=lambda: None)
        monitor = SimpleNamespace(lock=threading.Lock(),
                                  last_reading=reading(),
                                  last_frame_at=time.monotonic() + 5,
                                  begin_capture=lambda: None,
                                  end_capture=lambda: None)
        driver = DriveController(monitor)
        driver.motor1 = motor
        driver.motor2 = motor
        driver.servo = FakeServo()
        driver.start_thread()
        try:
            self.assertIsNone(driver.manual_command(0, 1))
            driver.detach_at = 0
            time.sleep(0.08)
            self.assertEqual(driver.servo.detach_count, 1)
            self.assertIsNone(driver.manual_command(1, 0))
            with driver.lock:
                driver.deadline = time.monotonic() + 3
            self.assertEqual(driver.servo.angle, 0)
            time.sleep(0.08)
            self.assertEqual(driver.servo.detach_count, 1)
            driver.stop()
            time.sleep(0.08)
            self.assertGreaterEqual(driver.servo.detach_count, 2)
        finally:
            driver.close()

    def test_manual_input_controls_motors_and_stops_on_release(self):
        class FakeMotor:
            def __init__(self):
                self.command = None

            def forward(self, speed):
                self.command = ("forward", speed)

            def backward(self, speed):
                self.command = ("backward", speed)

            def stop(self):
                self.command = ("stop", 0)

        class FakeServo:
            def __init__(self):
                self.angle = None

            def detach(self):
                pass

        monitor = SimpleNamespace(lock=threading.Lock(), last_frame_at=time.monotonic(),
                                  begin_capture=lambda: None, end_capture=lambda: None)
        driver = DriveController(monitor, servo_center=10)
        driver.motor1, driver.motor2, driver.servo = FakeMotor(), FakeMotor(), FakeServo()
        self.assertIsNone(driver.manual_command(1, -1))
        self.assertEqual(driver.servo.angle, 85)
        self.assertEqual(driver.motor1.command, ("forward", 0.22))
        self.assertEqual(driver.motor2.command, ("backward", 0.22))
        self.assertIsNone(driver.set_motor_scales(1.05, 0.95))
        self.assertIsNone(driver.manual_command(1, -1))
        self.assertAlmostEqual(driver.motor1.command[1], 0.231)
        self.assertAlmostEqual(driver.motor2.command[1], 0.209)
        self.assertIsNone(driver.set_motor_scales(1.0, 1.0))
        self.assertLess(driver.deadline - time.monotonic(), 0.5)
        self.assertIsNone(driver.manual_command(-1, 1))
        self.assertEqual(driver.servo.angle, -65)
        self.assertEqual(driver.motor1.command, ("backward", 0.22))
        self.assertEqual(driver.motor2.command, ("forward", 0.22))
        self.assertIsNone(driver.manual_command(1, 0.2))
        self.assertAlmostEqual(driver.servo.angle, -5)
        self.assertEqual(driver.motor1.command, ("forward", 0.22))
        self.assertIsNone(driver.manual_command(0, 0))
        self.assertEqual(driver.motor1.command, ("stop", 0))
        self.assertEqual(driver.servo.angle, 10)
        self.assertFalse(driver.active)
        self.assertEqual(driver.angle, 0)
        self.assertIsNotNone(driver.manual_command(True, 0))
        self.assertIsNotNone(driver.manual_command(0, float("nan")))


if __name__ == "__main__":
    unittest.main()
