"""Webots autonomous controller and GPIO bridge for the blue RC car."""

import sys
from pathlib import Path

import cv2
import numpy as np
from controller import Keyboard, Robot


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from controllers.drive_policy import DriveCommand, LaneFollowPolicy
from controllers.driveability import DriveabilityModel
from controllers.learned_control import stabilize_learned_pwm
from controllers.lee_lane_adapter import LeeLaneAdapter
from controllers.learned_steering import LearnedSteeringModel
from controllers.oval_track_expert import OvalTrackExpert, RoundedRectangleExpert
from dataset_recorder import DatasetRecorder


TIME_STEP = 32
MAX_WHEEL_SPEED = 16.0
DRIVE_PWM = 0.65
AUTO_FORWARD_PWM = 0.55
AUTO_CURVE_PWM = 0.45
TURN_INNER_RATIO = 0.3
LEARNED_UNSAFE_FRAME_LIMIT = 15

# Existing Lee/motor_module.py wiring. Do not change these pairs.
GPIO_MOTOR_PAIRS = {
    1: (22, 27),  # front-left
    2: (24, 23),  # rear-left
    3: (21, 16),  # rear-right
    4: (19, 26),  # front-right
}

WEBOTS_MOTOR_NAMES = {
    1: "motor1_gpio_22_27",
    2: "motor2_gpio_24_23",
    3: "motor3_gpio_21_16",
    4: "motor4_gpio_19_26",
}


def learned_model_path():
    steering_v2 = PROJECT_ROOT / "models" / "steering_v2.npz"
    if steering_v2.exists():
        return steering_v2
    return PROJECT_ROOT / "models" / "steering_v1.npz"


def driveability_model_path():
    model_path = PROJECT_ROOT / "models" / "driveability_v1.npz"
    return model_path if model_path.exists() else None


class VirtualGPIOBridge:
    """Translate H-bridge GPIO PWM states into Webots wheel velocities."""

    def __init__(self, robot):
        self.motors = {}
        self.pin_pwm = {pin: 0.0 for pair in GPIO_MOTOR_PAIRS.values() for pin in pair}
        for motor_id, name in WEBOTS_MOTOR_NAMES.items():
            motor = robot.getDevice(name)
            motor.setPosition(float("inf"))
            motor.setVelocity(0.0)
            self.motors[motor_id] = motor

    def set_motor_pwm(self, motor_id, forward_pwm, backward_pwm):
        forward_pin, backward_pin = GPIO_MOTOR_PAIRS[motor_id]
        self.pin_pwm[forward_pin] = forward_pwm
        self.pin_pwm[backward_pin] = backward_pwm
        signed_pwm = forward_pwm - backward_pwm
        self.motors[motor_id].setVelocity(signed_pwm * MAX_WHEEL_SPEED)

    def set_side_speeds(self, left_pwm, right_pwm):
        for motor_id in (1, 2):
            self._set_signed_pwm(motor_id, left_pwm)
        for motor_id in (3, 4):
            self._set_signed_pwm(motor_id, right_pwm)

    def _set_signed_pwm(self, motor_id, signed_pwm):
        if signed_pwm >= 0:
            self.set_motor_pwm(motor_id, signed_pwm, 0.0)
        else:
            self.set_motor_pwm(motor_id, 0.0, -signed_pwm)

    def stop(self):
        self.set_side_speeds(0.0, 0.0)


def keyboard_command(key):
    if key in (ord("W"), Keyboard.UP):
        return DRIVE_PWM, DRIVE_PWM, "forward"
    if key in (ord("S"), Keyboard.DOWN):
        return -DRIVE_PWM, -DRIVE_PWM, "backward"
    if key in (ord("A"), Keyboard.LEFT):
        return DRIVE_PWM * TURN_INNER_RATIO, DRIVE_PWM, "curve_left"
    if key in (ord("D"), Keyboard.RIGHT):
        return DRIVE_PWM, DRIVE_PWM * TURN_INNER_RATIO, "curve_right"
    if key == ord("Q"):
        return -DRIVE_PWM, DRIVE_PWM, "turn_left"
    if key == ord("E"):
        return DRIVE_PWM, -DRIVE_PWM, "turn_right"
    return 0.0, 0.0, "stop"


def decision_to_pwm(decision):
    if decision.command is DriveCommand.FORWARD:
        return decision.speed, decision.speed, "forward"
    if decision.command is DriveCommand.CURVE_LEFT:
        return decision.speed * TURN_INNER_RATIO, decision.speed, "curve_left"
    if decision.command is DriveCommand.CURVE_RIGHT:
        return decision.speed, decision.speed * TURN_INNER_RATIO, "curve_right"
    return 0.0, 0.0, "stop"


def get_front_frame(camera):
    image = camera.getImage()
    if image is None:
        return None
    bgra = np.frombuffer(image, dtype=np.uint8).reshape(
        (camera.getHeight(), camera.getWidth(), 4)
    )
    return np.ascontiguousarray(bgra[:, :, :3])


def show_front_camera(frame, lane, mode, recording):
    display = lane.get("debug_frame")
    if display is None:
        display = frame.copy()
    else:
        display = display.copy()

    status_color = (40, 220, 40) if mode == "AUTO" else (0, 210, 255)
    cv2.putText(
        display,
        f"{mode}  REC:{'ON' if recording else 'OFF'}",
        (8, display.shape[0] - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        status_color,
        2,
    )
    cv2.imshow("RC Car Front Camera", display)
    cv2.waitKey(1)


def main():
    robot = Robot()
    gpio = VirtualGPIOBridge(robot)

    camera = robot.getDevice("front_camera")
    camera.enable(TIME_STEP)

    gps = robot.getDevice("gps")
    gps.enable(TIME_STEP)
    inertial_unit = robot.getDevice("inertial_unit")
    inertial_unit.enable(TIME_STEP)

    keyboard = robot.getKeyboard()
    keyboard.enable(TIME_STEP)

    tracker = LeeLaneAdapter()
    policy = LaneFollowPolicy(
        base_speed=AUTO_FORWARD_PWM,
        curve_speed=AUTO_CURVE_PWM,
        center_tolerance=20,
        max_missing_frames=5,
    )
    track_name = robot.getCustomData() or "training_oval"
    target_lane = "middle"
    corner_radius_m = ""
    if track_name.startswith("expert_rectangle_lane_"):
        lane_number = int(track_name.rsplit("_", 1)[1])
        target_lane = lane_number
        expert = RoundedRectangleExpert.for_lane(lane_number)
        corner_radius_m = expert.corner_radius
    elif track_name in ("learned_test_rectangle", "learned_test_rectangle_inverted"):
        target_lane = 2
        expert = RoundedRectangleExpert.for_lane(2)
        corner_radius_m = expert.corner_radius
    elif track_name == "learned_test_clockwise":
        expert = OvalTrackExpert(half_straight=3.0, lane_radius=1.3)
    else:
        expert = OvalTrackExpert()

    model_path = learned_model_path()
    learned_model = LearnedSteeringModel(model_path)
    safety_model_path = driveability_model_path()
    safety_model = DriveabilityModel(safety_model_path) if safety_model_path else None
    recorder = DatasetRecorder(
        PROJECT_ROOT,
        sample_interval_frames=5,
        track_name=track_name,
        target_lane=target_lane,
        corner_radius_m=corner_radius_m,
    )

    auto_mode = True
    auto_source = "LEARNED" if track_name.startswith("learned_test_") else "EXPERT"
    previous_key = -1
    last_command = None
    learned_unsafe_frames = 0

    print("Blue RC Car autonomous mode ready")
    print("M: AUTO/MANUAL, V: EXPERT/VISION/LEARNED, R: recording ON/OFF")
    print(f"Learned model: {model_path.name}")
    print(f"Driveability model: {safety_model_path.name if safety_model_path else 'disabled'}")
    print(f"Dataset run: {recorder.run_dir}")

    try:
        while robot.step(TIME_STEP) != -1:
            frame = get_front_frame(camera)
            if frame is None:
                gpio.stop()
                continue

            lane = tracker.process(frame)
            key = keyboard.getKey()
            position = gps.getValues()
            yaw = inertial_unit.getRollPitchYaw()[2]

            if key != previous_key and key == ord("M"):
                auto_mode = not auto_mode
                policy = LaneFollowPolicy(
                    base_speed=AUTO_FORWARD_PWM,
                    curve_speed=AUTO_CURVE_PWM,
                    center_tolerance=20,
                    max_missing_frames=5,
                )
                print(f"Control mode: {'AUTO' if auto_mode else 'MANUAL'}")

            if key != previous_key and key == ord("R"):
                print(f"Dataset recording: {'ON' if recorder.toggle() else 'OFF'}")

            if key != previous_key and key == ord("V"):
                sources = ("EXPERT", "VISION", "LEARNED")
                auto_source = sources[(sources.index(auto_source) + 1) % len(sources)]
                print(f"Automatic control source: {auto_source}")

            path_reference = expert.decide(position[0], position[1], yaw)
            cross_track_error = f"{path_reference.cross_track_error:.5f}"
            heading_error = f"{path_reference.heading_error:.5f}"
            target_x = f"{path_reference.target_x:.5f}"
            target_y = f"{path_reference.target_y:.5f}"
            driveability_score = ""
            safety_state = "disabled"
            if safety_model is not None:
                driveability_score_value = safety_model.predict_probability(frame)
                driveability_score = f"{driveability_score_value:.4f}"
                if driveability_score_value >= safety_model.threshold:
                    learned_unsafe_frames = 0
                    safety_state = "driveable"
                elif lane["visible"]:
                    learned_unsafe_frames = 0
                    safety_state = "uncertain"
                else:
                    learned_unsafe_frames += 1
                    safety_state = (
                        "unsafe"
                        if learned_unsafe_frames >= LEARNED_UNSAFE_FRAME_LIMIT
                        else "uncertain"
                    )

            if auto_mode:
                if auto_source == "EXPERT":
                    left_pwm = path_reference.left_pwm
                    right_pwm = path_reference.right_pwm
                    command = "expert_path_follow"
                    decision_reason = "simulator_ground_truth"
                elif auto_source == "VISION":
                    decision = policy.decide(lane["error"], lane["visible"])
                    left_pwm, right_pwm, command = decision_to_pwm(decision)
                    decision_reason = decision.reason
                else:
                    left_pwm, right_pwm = learned_model.predict(frame)
                    left_pwm, right_pwm = stabilize_learned_pwm(
                        left_pwm,
                        right_pwm,
                        lane["error"],
                        lane["visible"],
                    )
                    command = "learned_model"
                    decision_reason = f"{model_path.stem}+vision_trim"
                    if safety_state == "unsafe":
                        left_pwm = 0.0
                        right_pwm = 0.0
                        command = "safety_stop"
                        decision_reason = f"{model_path.stem}+driveability"
            else:
                left_pwm, right_pwm, command = keyboard_command(key)
                decision_reason = "manual"

            gpio.set_side_speeds(left_pwm, right_pwm)

            recorder.record(
                frame,
                {
                    "simulation_time": f"{robot.getTime():.3f}",
                    "control_mode": auto_source.lower() if auto_mode else "manual",
                    "target_lane": target_lane,
                    "corner_radius_m": corner_radius_m,
                    "corner_curvature_1pm": (
                        f"{expert.corner_curvature:.5f}"
                        if isinstance(expert, RoundedRectangleExpert) else ""
                    ),
                    "lane_status": lane["status"],
                    "lane_error": lane["error"],
                    "lane_direction": lane["direction"],
                    "decision_reason": decision_reason,
                    "command": command,
                    "left_pwm": f"{left_pwm:.4f}",
                    "right_pwm": f"{right_pwm:.4f}",
                    "expert_left_pwm": f"{path_reference.left_pwm:.4f}",
                    "expert_right_pwm": f"{path_reference.right_pwm:.4f}",
                    "driveability_score": driveability_score,
                    "safety_state": safety_state,
                    "position_x": f"{position[0]:.5f}",
                    "position_y": f"{position[1]:.5f}",
                    "yaw": f"{yaw:.5f}",
                    "cross_track_error": cross_track_error,
                    "heading_error": heading_error,
                    "target_x": target_x,
                    "target_y": target_y,
                },
            )

            display_mode = f"AUTO-{auto_source}" if auto_mode else "MANUAL"
            show_front_camera(frame, lane, display_mode, recorder.enabled)

            if command != last_command:
                print(
                    f"command={command} error={lane['error']} "
                    f"left_pwm={left_pwm:.2f} right_pwm={right_pwm:.2f}"
                )
                last_command = command

            previous_key = key
    finally:
        gpio.stop()
        recorder.close()
        cv2.destroyAllWindows()
        print(f"Saved {recorder.sample_counter} samples to {recorder.run_dir}")


if __name__ == "__main__":
    main()
