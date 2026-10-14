"""Bounded first autonomous-driving test for the borrowed steering robot."""

import argparse
from collections import deque
import math
from pathlib import Path
from statistics import median
import threading
import time

from werkzeug.serving import make_server

from camera_test import Camera
from road_camera_web import Monitor, build_app
from road_vision import curve_direction


MOTOR_1_PINS = (20, 21)
MOTOR_2_PINS = (23, 24)
SERVO_PIN = 18
FORWARD_SPEED = 0.22
MIN_FORWARD_SPEED = 0.18
MAX_FORWARD_SPEED = 0.30
MAX_STEER_DEGREES = 60
MAX_CORNER_ANGLE = 80
MAX_CORNER_SECONDS = 1.2
CORNER_HOLD_SECONDS = 0.25
THERMAL_LIMIT_C = 75.0
THERMAL_SENSOR = Path("/sys/class/thermal/thermal_zone0/temp")
STEER_KP = 0.35
RUN_SECONDS = 12.0
RECOVERY_SECONDS = 0.4
MANUAL_TIMEOUT = 0.45
MANUAL_LEFT_ANGLE = -80
MANUAL_RIGHT_ANGLE = 85
MANUAL_CENTER_SECONDS = 0.6
MIN_CONFIDENCE = 0.60
MIN_SURFACE = 0.35
MAX_CENTER_ERROR = 130
MAX_RAW_CENTER_ERROR = 220
LEFT_STEER_GAIN = 1.10
SINGLE_LINE_SECONDS = 2.0
SINGLE_CURVE_SECONDS = 5.0
SINGLE_HEADING_GAIN = 1.0
STRONG_CURVE_STEER_DEGREES = 70
EDGE_RECOVERY_SECONDS = 1.0
EDGE_RECOVERY_ANGLE = 50


def servo_target(center, logical_angle):
    # The replacement steering linkage turns opposite to the previous one.
    gain = LEFT_STEER_GAIN if logical_angle < 0 else 1.0
    return max(-85, min(85, center - logical_angle * gain))


class SteeringErrorFilter:
    """Suppress isolated lane-target jumps without relaxing vision stops."""

    def __init__(self):
        self.errors = deque(maxlen=3)
        self.last_frame_at = None

    def reset(self):
        self.errors.clear()
        self.last_frame_at = None

    def update(self, error, frame_at):
        if error is None:
            self.reset()
            return None
        if self.last_frame_at != frame_at:
            if self.last_frame_at is not None and frame_at - self.last_frame_at > 0.2:
                self.errors.clear()
            self.errors.append(error)
            self.last_frame_at = frame_at
        return median(self.errors)


class CornerEvidence:
    def __init__(self):
        self.direction = None
        self.count = 0
        self.last_frame_at = None

    def reset(self):
        self.direction = None
        self.count = 0
        self.last_frame_at = None

    def update(self, direction, frame_at):
        if direction is None:
            self.reset()
            return None
        if frame_at == self.last_frame_at:
            return direction if self.count >= 3 else None
        if direction != self.direction or (self.last_frame_at is not None
                                           and frame_at - self.last_frame_at > 0.2):
            self.count = 0
        self.direction = direction
        self.last_frame_at = frame_at
        self.count += 1
        return direction if self.count >= 3 else None


def plan(reading, previous_angle, allow_single=False, forward_speed=FORWARD_SPEED,
         camera_center_bias=0.0, filtered_error=None):
    if reading is None or reading.lane not in {"양쪽 선", "한쪽 선"}:
        return None
    single = reading.lane == "한쪽 선"
    if single and not allow_single:
        return None
    curve = curve_direction(reading)
    min_confidence = 0.55 if single else MIN_CONFIDENCE
    min_surface = (0.4 if curve and getattr(reading, "near_surface", 0.0) >= 0.8
                   else 0.65 if single else MIN_SURFACE)
    if reading.confidence < min_confidence or reading.surface < min_surface:
        return None
    if reading.center_error is None or abs(reading.center_error) > MAX_RAW_CENTER_ERROR:
        return None
    raw_error = reading.center_error - camera_center_bias
    strong_curve = curve is not None and abs(reading.heading_error) >= 60
    turning_toward_lane = strong_curve and raw_error * reading.heading_error < 0
    recenter = (single and reading.confidence >= 0.68
                and reading.surface >= 0.9
                and getattr(reading, "near_surface", 0.0) >= 0.9)
    if abs(raw_error) > (180 if turning_toward_lane or recenter else MAX_CENTER_ERROR):
        return None
    steering_error = reading.center_error if filtered_error is None else filtered_error
    error = steering_error - camera_center_bias
    limit = (STRONG_CURVE_STEER_DEGREES if strong_curve else
             MAX_STEER_DEGREES if recenter and abs(raw_error) > MAX_CENTER_ERROR else
             25 if single else MAX_STEER_DEGREES)
    # Logical positive turns right; servo_target handles the linkage direction.
    heading_trim = (SINGLE_HEADING_GAIN * getattr(reading, "heading_error", 0.0)
                    if single else 0.0)
    desired = max(-limit, min(limit, -STEER_KP * error + heading_trim))
    filtered = 0.65 * previous_angle + 0.35 * desired
    angle = max(previous_angle - 6, min(previous_angle + 6, filtered))
    single_speed = min(forward_speed, max(0.22, round(forward_speed * 0.73, 2)))
    return (forward_speed if curve or recenter else single_speed if single else forward_speed), angle


def corner_motion(direction, previous_angle, forward_speed=FORWARD_SPEED):
    desired = MAX_CORNER_ANGLE if direction == "right" else -MAX_CORNER_ANGLE
    angle = max(previous_angle - 10, min(previous_angle + 10, desired))
    return forward_speed, angle


def inward_edge_plan(reading, previous_angle, forward_speed=FORWARD_SPEED,
                     camera_center_bias=0.0):
    if (reading is None or reading.lane not in {"양쪽 선", "한쪽 선"}
            or reading.confidence < MIN_CONFIDENCE
            or reading.surface < 0.58
            or getattr(reading, "near_surface", 0.0) < 0.8
            or reading.center_error is None):
        return None
    error = reading.center_error - camera_center_bias
    inward = getattr(reading, "edge_inward", None)
    if ((inward == "right" and error < -MAX_CENTER_ERROR)
            or (inward == "left" and error > MAX_CENTER_ERROR)):
        desired = EDGE_RECOVERY_ANGLE if inward == "right" else -EDGE_RECOVERY_ANGLE
        angle = max(previous_angle - 6, min(previous_angle + 6, desired))
        return forward_speed, angle
    return None


def corner_plan(reading, previous_angle, forward_speed=FORWARD_SPEED):
    direction = getattr(reading, "corner", None)
    if (direction not in {"left", "right"} or reading.confidence < 0.7
            or reading.surface < 0.7):
        return None
    return corner_motion(direction, previous_angle, forward_speed)


def read_cpu_temp():
    try:
        return int(THERMAL_SENSOR.read_text(encoding="ascii").strip()) / 1000
    except (OSError, ValueError):
        return None


def watch_temperature(server, driver, stop_event, read_temp=read_cpu_temp):
    while not stop_event.wait(1.0):
        temperature = read_temp()
        if temperature is None or temperature >= THERMAL_LIMIT_C:
            print(f"Thermal shutdown: CPU temperature {temperature}", flush=True)
            driver.stop()
            server.shutdown()
            return


def apply_forward(motor1, motor2, speed, motor1_scale=1.0, motor2_scale=1.0):
    motor1.forward(speed * motor1_scale)
    motor2.backward(speed * motor2_scale)


def apply_reverse(motor1, motor2, speed, motor1_scale=1.0, motor2_scale=1.0):
    motor1.backward(speed * motor1_scale)
    motor2.forward(speed * motor2_scale)


def straight_plan(reading, fresh, forward_speed=FORWARD_SPEED,
                  camera_center_bias=0.0):
    if (not fresh or reading is None or reading.lane != "양쪽 선"
            or reading.confidence < MIN_CONFIDENCE
            or reading.center_error is None
            or abs(reading.center_error) > MAX_RAW_CENTER_ERROR
            or abs(reading.center_error - camera_center_bias) > MAX_CENTER_ERROR
            or reading.surface < 0.8):
        return None
    return forward_speed, 0.0


def recovery_plan(reading, fresh, direction, forward_speed=FORWARD_SPEED):
    if (not fresh or reading is None or reading.lane not in {"양쪽 선", "한쪽 선"}
            or reading.center_error is None
            or abs(reading.center_error) > MAX_RAW_CENTER_ERROR
            or reading.surface < 0.7):
        return None
    return forward_speed, (-MAX_STEER_DEGREES if direction == "left"
                           else MAX_STEER_DEGREES)


class DriveController:
    def __init__(self, monitor, motor1_scale=1.0, motor2_scale=1.0,
                 servo_center=0.0, forward_speed=FORWARD_SPEED,
                 run_seconds=RUN_SECONDS, hold_steering=True,
                 camera_center_bias=0.0,
                 manual_left_angle=MANUAL_LEFT_ANGLE,
                 manual_right_angle=MANUAL_RIGHT_ANGLE):
        self.monitor = monitor
        self.motor1_scale = motor1_scale
        self.motor2_scale = motor2_scale
        self.servo_center = servo_center
        self.forward_speed = forward_speed
        self.run_seconds = run_seconds
        self.hold_steering = hold_steering
        self.camera_center_bias = camera_center_bias
        self.manual_left_angle = manual_left_angle
        self.manual_right_angle = manual_right_angle
        self.lock = threading.Lock()
        self.motor1 = None
        self.motor2 = None
        self.servo = None
        self.active = False
        self.deadline = 0.0
        self.started_at = 0.0
        self.last_both_at = 0.0
        self.corner_started_at = None
        self.last_corner_at = None
        self.last_corner_direction = None
        self.edge_recovery_started_at = None
        self.angle = 0.0
        self.last_angle = None
        self.detach_at = 0.0
        self.center_detach_at = None
        self.state = "정지"
        self.mode = "auto"
        self.auto_start_requests = 0
        self.samples = deque(maxlen=600)
        self.manual_events = deque(maxlen=1200)
        self.steering_filter = SteeringErrorFilter()
        self.corner_evidence = CornerEvidence()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start_thread(self):
        self.thread.start()

    def _open_gpio(self):
        if self.motor1 is not None:
            return
        from gpiozero import AngularServo, Motor

        motor1 = Motor(*MOTOR_1_PINS)
        try:
            motor2 = Motor(*MOTOR_2_PINS)
            try:
                servo = AngularServo(SERVO_PIN, initial_angle=None,
                                     min_angle=-90, max_angle=90,
                                     min_pulse_width=0.001, max_pulse_width=0.002)
            except Exception:
                motor2.close()
                raise
        except Exception:
            motor1.close()
            raise
        self.motor1, self.motor2, self.servo = motor1, motor2, servo

    def start(self, mode="auto"):
        if mode not in {"auto", "straight", "recover_left", "recover_right"}:
            return "지원하지 않는 주행 모드입니다."
        if mode == "auto":
            with self.lock:
                self.auto_start_requests += 1
        with self.monitor.lock:
            reading = self.monitor.last_reading
            fresh = time.monotonic() - self.monitor.last_frame_at < 0.5
        if mode == "auto":
            ready = (self.forward_speed, 0.0)
        elif mode.startswith("recover_"):
            ready = recovery_plan(reading, fresh, mode.removeprefix("recover_"),
                                  self.forward_speed)
        else:
            ready = (corner_plan(reading, 0.0) or
                     plan(reading, 0.0, forward_speed=self.forward_speed,
                          camera_center_bias=self.camera_center_bias)) if fresh else None
        if ready is None:
            return "양쪽 차선과 도로를 안정적으로 인식한 뒤 시작할 수 있습니다."
        with self.lock:
            if self.active:
                return "이미 주행 중입니다."
            try:
                self._open_gpio()
                self.servo.angle = self.servo_center
                time.sleep(0.2)
                if not self.hold_steering:
                    self.servo.detach()
                self.center_detach_at = None
            except Exception as exc:
                self.state = "GPIO 오류"
                return f"GPIO를 열 수 없습니다: {exc}"
            self.angle = 0.0
            self.last_angle = None
            self.steering_filter.reset()
            self.corner_evidence.reset()
            self.monitor.begin_capture()
            self.mode = mode
            duration = min(self.run_seconds, RECOVERY_SECONDS) if mode.startswith("recover_") else self.run_seconds
            self.started_at = time.monotonic()
            self.deadline = self.started_at + duration
            self.last_both_at = self.started_at
            self.corner_started_at = None
            self.last_corner_at = None
            self.last_corner_direction = None
            self.edge_recovery_started_at = None
            self.active = True
            self.state = "직진 보정" if mode == "straight" else "주행 중"
        return None

    def _stop_locked(self, state):
        was_active = self.active
        self.steering_filter.reset()
        self.corner_evidence.reset()
        self.corner_started_at = None
        self.last_corner_at = None
        self.last_corner_direction = None
        self.edge_recovery_started_at = None
        self.monitor.end_capture()
        self.active = False
        self.manual_events.append((time.monotonic(), 0, 0.0))
        self.state = state
        self.deadline = 0.0
        if self.motor1 is not None:
            self.motor1.stop()
        if self.motor2 is not None:
            self.motor2.stop()
        if self.servo is not None and (was_active or self.center_detach_at is None):
            self.servo.angle = self.servo_center
            self.center_detach_at = (time.monotonic() + MANUAL_CENTER_SECONDS
                                     if self.last_angle not in (None, 0)
                                     else time.monotonic())
        self.last_angle = None
        self.angle = 0.0

    def stop(self):
        with self.lock:
            self._stop_locked("정지")

    def set_forward_speed(self, speed):
        if (type(speed) not in (int, float) or not math.isfinite(speed)
                or not MIN_FORWARD_SPEED <= speed <= MAX_FORWARD_SPEED):
            return "속도는 0.18~0.30 사이여야 합니다."
        with self.lock:
            self.forward_speed = round(float(speed), 2)
        return None

    def set_motor_scales(self, motor1_scale, motor2_scale):
        if any(type(scale) not in (int, float) or not math.isfinite(scale)
               or not 0.8 <= scale <= 1.2
               for scale in (motor1_scale, motor2_scale)):
            return "모터 보정값은 각각 0.80~1.20 사이여야 합니다."
        with self.lock:
            self.motor1_scale = round(float(motor1_scale), 2)
            self.motor2_scale = round(float(motor2_scale), 2)
        return None

    def manual_command(self, throttle, steer):
        if (type(throttle) is not int or type(steer) not in (int, float)
                or throttle not in (-1, 0, 1) or not math.isfinite(steer)
                or not -1 <= steer <= 1):
            return "잘못된 수동 명령입니다."
        if throttle == 0 and steer == 0:
            self.stop()
            return None
        with self.monitor.lock:
            fresh = time.monotonic() - self.monitor.last_frame_at < 0.5
        if not fresh:
            self.stop()
            return "카메라 연결을 확인해 주세요."
        with self.lock:
            if self.active and self.mode != "manual":
                return "시험 주행을 먼저 정지해 주세요."
            try:
                self._open_gpio()
                angle = ((self.manual_left_angle - self.servo_center) * -steer
                         if steer < 0 else
                         (self.manual_right_angle - self.servo_center) * steer)
                if self.last_angle != angle:
                    self.servo.angle = servo_target(self.servo_center, angle)
                    self.last_angle = angle
                    self.detach_at = (time.monotonic() + 0.18
                                      if abs(angle) > 45 else float("inf"))
                self.center_detach_at = None
                if throttle > 0:
                    apply_forward(self.motor1, self.motor2, self.forward_speed,
                                  self.motor1_scale, self.motor2_scale)
                elif throttle < 0:
                    apply_reverse(self.motor1, self.motor2, self.forward_speed,
                                  self.motor1_scale, self.motor2_scale)
                else:
                    self.motor1.stop()
                    self.motor2.stop()
            except Exception as exc:
                self._stop_locked("GPIO 오류로 정지")
                return f"수동 명령 실패: {exc}"
            if not self.active:
                self.monitor.begin_capture()
            self.active = True
            self.mode = "manual"
            self.manual_events.append((time.monotonic(), throttle, float(steer)))
            self.angle = angle
            self.deadline = time.monotonic() + MANUAL_TIMEOUT
            self.state = "수동 조작"
        return None

    def status(self):
        with self.lock:
            return dict(active=self.active, state=self.state, mode=self.mode, angle=self.angle,
                        auto_start_requests=self.auto_start_requests,
                        servo_target=servo_target(self.servo_center, self.angle),
                        motor1_scale=self.motor1_scale, motor2_scale=self.motor2_scale,
                        servo_center=self.servo_center,
                        manual_left_angle=self.manual_left_angle,
                        manual_right_angle=self.manual_right_angle,
                        hold_steering=self.hold_steering,
                        camera_center_bias=self.camera_center_bias,
                        forward_speed=self.forward_speed, run_seconds=self.run_seconds,
                        remaining=max(0.0, self.deadline - time.monotonic())
                        if self.active else 0.0)

    def history(self):
        with self.lock:
            return list(self.samples)

    def manual_state_at(self, frame_at):
        with self.lock:
            for timestamp, throttle, steer in reversed(self.manual_events):
                if timestamp <= frame_at:
                    age = frame_at - timestamp
                    return (throttle, steer, age,
                            age <= 0.3 and self.mode == "manual")
        return 0, 0.0, None, False

    def _loop(self):
        while self.running:
            with self.monitor.lock:
                reading = self.monitor.last_reading
                frame_at = self.monitor.last_frame_at
                fresh = time.monotonic() - frame_at < 0.5
            with self.lock:
                if self.active:
                    now = time.monotonic()
                    if self.mode == "manual":
                        if now >= self.deadline or not fresh:
                            self._stop_locked("수동 입력 종료")
                        elif abs(self.angle) > 45 and now >= self.detach_at:
                            self.servo.detach()
                            self.detach_at = float("inf")
                        time.sleep(0.05)
                        continue
                    pending_corner = False
                    edge_recovering = False
                    if self.mode.startswith("recover_"):
                        command = recovery_plan(reading, fresh,
                                                self.mode.removeprefix("recover_"),
                                                self.forward_speed)
                    elif self.mode == "straight":
                        command = straight_plan(reading, fresh, self.forward_speed,
                                                self.camera_center_bias)
                    else:
                        if fresh and reading is not None and reading.lane == "양쪽 선":
                            self.last_both_at = now
                        if fresh and reading is not None and getattr(reading, "corner", None):
                            self.edge_recovery_started_at = None
                            confirmed = self.corner_evidence.update(reading.corner, frame_at)
                            if self.last_corner_direction not in (None, reading.corner):
                                command = None
                            elif confirmed is None:
                                pending_corner = True
                                command = (0.0, self.angle)
                            else:
                                if self.corner_started_at is None:
                                    self.corner_started_at = now
                                self.last_corner_at = now
                                self.last_corner_direction = confirmed
                                command = (corner_plan(reading, self.angle,
                                                       self.forward_speed)
                                           if now - self.corner_started_at <= MAX_CORNER_SECONDS
                                           else None)
                            self.steering_filter.reset()
                        elif (fresh and reading is not None
                              and self.last_corner_at is not None
                              and now - self.last_corner_at <= CORNER_HOLD_SECONDS
                              and now - self.corner_started_at <= MAX_CORNER_SECONDS
                              and reading.surface >= 0.7
                              and reading.lane != "양쪽 선"):
                            self.edge_recovery_started_at = None
                            command = corner_motion(self.last_corner_direction, self.angle,
                                                    self.forward_speed)
                        else:
                            self.corner_evidence.reset()
                            self.corner_started_at = None
                            self.last_corner_at = None
                            self.last_corner_direction = None
                            edge_command = (inward_edge_plan(
                                reading, self.angle, self.forward_speed,
                                self.camera_center_bias) if fresh else None)
                            if edge_command is not None:
                                edge_recovering = True
                                if self.edge_recovery_started_at is None:
                                    self.edge_recovery_started_at = now
                                command = (edge_command if now - self.edge_recovery_started_at
                                           <= EDGE_RECOVERY_SECONDS else None)
                                self.steering_filter.reset()
                            else:
                                self.edge_recovery_started_at = None
                                single_age = now - self.last_both_at
                                allow_single = (single_age <= SINGLE_LINE_SECONDS
                                                or (single_age <= SINGLE_CURVE_SECONDS
                                                    and reading is not None
                                                    and curve_direction(reading) is not None))
                                filtered_error = self.steering_filter.update(
                                    reading.center_error if fresh and reading else None, frame_at)
                                command = plan(reading, self.angle, allow_single,
                                               self.forward_speed,
                                               self.camera_center_bias,
                                               filtered_error) if fresh else None
                        if command is None:
                            self.steering_filter.reset()
                    self.samples.append(dict(time=round(now, 3),
                                             run=self.auto_start_requests,
                                             mode=self.mode,
                                             lane=reading.lane if reading else "없음",
                                             confidence=round(reading.confidence, 3) if reading else 0,
                                             edge_inward=getattr(reading, "edge_inward", None),
                                             edge_recovering=edge_recovering,
                                             surface=round(reading.surface, 3) if reading else 0,
                                             error=round(reading.center_error, 1)
                                             if reading and reading.center_error is not None else None,
                                             corrected_error=round(reading.center_error - self.camera_center_bias, 1)
                                             if reading and reading.center_error is not None else None,
                                             angle=round(self.angle, 1),
                                             speed=round(command[0], 2) if command else 0,
                                             fresh=fresh))
                    if now >= self.deadline:
                        self._stop_locked("시간 종료")
                    elif command is None:
                        self._stop_locked("인식 실패로 정지")
                    else:
                        speed, angle = command
                        try:
                            min_change = 0.5 if self.hold_steering else 2
                            if self.last_angle is None or abs(angle - self.last_angle) >= min_change:
                                self.servo.angle = servo_target(self.servo_center, angle)
                                self.last_angle = angle
                                if not self.hold_steering:
                                    self.detach_at = now + 0.18
                            if not self.hold_steering and now >= self.detach_at:
                                self.servo.detach()
                                self.detach_at = float("inf")
                            if speed == 0:
                                self.motor1.stop()
                                self.motor2.stop()
                            else:
                                apply_forward(self.motor1, self.motor2, speed,
                                              self.motor1_scale, self.motor2_scale)
                            self.angle = angle
                            if edge_recovering:
                                self.state = "경계 안쪽 복귀"
                            elif self.mode.startswith("recover_"):
                                self.state = "차선 복귀 시험"
                            elif self.mode == "straight":
                                self.state = "직진 보정"
                            elif pending_corner:
                                self.state = "코너 확인 중"
                            elif getattr(reading, "corner", None):
                                self.state = "코너 회전"
                            else:
                                self.state = ("한쪽 선 보조" if reading.lane == "한쪽 선"
                                              else "주행 중")
                        except Exception:
                            self._stop_locked("GPIO 오류로 정지")
                elif self.center_detach_at is not None and time.monotonic() >= self.center_detach_at:
                    self.servo.detach()
                    self.center_detach_at = None
            time.sleep(0.05)

    def close(self):
        self.running = False
        self.stop()
        self.thread.join(timeout=2)
        if self.servo is not None:
            self.servo.detach()
        for device in (self.motor1, self.motor2, self.servo):
            if device is not None:
                device.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--collection-only", action="store_true",
                        help="Allow manual control and recording, but disable autonomous routes")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--rotate", dest="rotate", action="store_true", default=True)
    parser.add_argument("--no-rotate", dest="rotate", action="store_false")
    parser.add_argument("--gesture", action="store_true",
                        help="Show gesture recognition without controlling the motors")
    parser.add_argument("--motor1-scale", type=float, default=1.0)
    parser.add_argument("--motor2-scale", type=float, default=1.0)
    parser.add_argument("--servo-center", type=float, default=0.0)
    parser.add_argument("--forward-speed", type=float, default=FORWARD_SPEED)
    parser.add_argument("--run-seconds", type=float, default=RUN_SECONDS)
    parser.add_argument("--hold-steering", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Keep servo PWM active while driving; detach after centering on stop")
    parser.add_argument("--camera-center-bias", type=float, default=0.0)
    parser.add_argument("--manual-left-angle", type=float, default=MANUAL_LEFT_ANGLE)
    parser.add_argument("--manual-right-angle", type=float, default=MANUAL_RIGHT_ANGLE)
    args = parser.parse_args()
    if not 0.8 <= args.motor1_scale <= 1.2 or not 0.8 <= args.motor2_scale <= 1.2:
        parser.error("motor scales must be between 0.8 and 1.2")
    if not -12 <= args.servo_center <= 12:
        parser.error("servo center must be between -12 and 12 degrees")
    if not (-80 <= args.manual_left_angle < args.servo_center
            < args.manual_right_angle <= 85):
        parser.error("manual angles must bracket servo center and stay within -80..85")
    if not -130 <= args.camera_center_bias <= 130:
        parser.error("camera center bias must be between -130 and 130 pixels")
    if not MIN_FORWARD_SPEED <= args.forward_speed <= MAX_FORWARD_SPEED:
        parser.error("forward speed must be between 0.18 and 0.30")
    if not 0.5 <= args.run_seconds <= 120.0:
        parser.error("run seconds must be between 0.5 and 120.0")
    if not 1 <= args.fps <= 30:
        parser.error("camera fps must be between 1 and 30")
    camera = Camera("csi", 0, 640, 480, args.fps, args.rotate)
    monitor = Monitor(camera, enable_gesture=args.gesture)
    driver = DriveController(monitor, args.motor1_scale, args.motor2_scale,
                             args.servo_center, args.forward_speed,
                             args.run_seconds, args.hold_steering,
                             args.camera_center_bias,
                             args.manual_left_angle, args.manual_right_angle)
    server = None
    thermal_stop = threading.Event()
    thermal_thread = None
    try:
        temperature = read_cpu_temp()
        if temperature is None or temperature >= THERMAL_LIMIT_C:
            raise RuntimeError(f"Pi CPU temperature unsafe: {temperature}")
        camera.start()
        deadline = time.monotonic() + 8
        while camera.frame is None and camera.error is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if camera.frame is None:
            raise RuntimeError(camera.error or "No camera frame within 8 seconds")
        monitor.start()
        driver.start_thread()
        server = make_server("0.0.0.0", args.port,
                             build_app(monitor, driver, manual_only=args.collection_only),
                             threaded=True)
        thermal_thread = threading.Thread(
            target=watch_temperature, args=(server, driver, thermal_stop), daemon=True)
        thermal_thread.start()
        print(f"Bounded drive test: http://<pi-ip>:{args.port}/", flush=True)
        server.serve_forever(poll_interval=0.2)
    finally:
        thermal_stop.set()
        if thermal_thread is not None:
            thermal_thread.join(timeout=2)
        if server is not None:
            server.server_close()
        if driver.thread.is_alive():
            driver.close()
        monitor.running = False
        camera.stop()
        if monitor.thread.is_alive():
            monitor.stop()


if __name__ == "__main__":
    main()
