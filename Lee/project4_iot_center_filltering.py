# file name: project4_iot_center.py
# Browser-controlled Pi-Rover with filtered motor control and sensor monitoring.

import atexit
import math
import subprocess
import sys
import threading
import time
from pathlib import Path
import cv2

from flask import Flask, Response, jsonify, render_template_string, request
from gpiozero import DistanceSensor
#from mpu6050 import mpu6050
from gesture_recognition_module import GestureRecognizer

from filtering_module import (
    low_pass_filter,
    median_filter,
    moving_average_filter,
    speed_limit_filter,
)
from motor_module import *
from camera_module import (
    start_camera,
    stop_camera,
    generate_camera_stream,
    get_latest_frame
)
from lane_tracking_module import LaneTracker


try:
    from mpu6050 import mpu6050

    imu = mpu6050(0x68)
    imu_available = True
    print("IMU sensor connected.")
except Exception as exc:
    imu = None
    imu_available = False
    print(f"IMU sensor connection failed: {exc}")
    print("Continuing without IMU.")
    
try:
    from RPLCD.i2c import CharLCD
except Exception:
    CharLCD = None

# queue_len=1 keeps obstacle checks responsive. Bigger queues smooth values but add delay.
front_ultra = DistanceSensor(echo=12, trigger=13, max_distance=2.0, queue_len=1)
rear_ultra = DistanceSensor(echo=17, trigger=4, max_distance=2.0, queue_len=1)

app = Flask(__name__)
TEMPLATE_PATH = Path(__file__).with_name("project4_iot_center.html")

MAX_SPEED = 0.65
DEFAULT_SPEED = 0.5
TURN_SPEED = 0.45
current_speed = 0.5
OBSTACLE_STOP_CM = 40.0
SAFETY_CHECK_INTERVAL = 0.03
IMPACT_DELTA_G = 3.5
ACCEL_ALPHA = 0.25
IMPACT_COOLDOWN_SEC = 1.0
LANE_FOLLOW_SPEED = 0.25

lcd = None
last_lcd_text = ""

try:
    if CharLCD is not None:
        lcd = CharLCD(
            i2c_expander="PCF8574",
            address=0x27,
            port=1,
            cols=16,
            rows=2,
            charmap="A00",
        )
        lcd.clear()
        lcd.write_string("Pi-Rover Ready")
        print("LCD connected.")
except Exception as exc:
    lcd = None
    print(f"LCD connection failed: {exc}")

lane_debug_jpeg = None
lane_debug_lock = threading.Lock()

lane_tracker = LaneTracker(
    frame_width=320,
    crop_y1=60,
    crop_y2=220,
    center_tolerance=15,
    smooth_window=5,
)

gesture_recognizer = GestureRecognizer(
    model_path="/home/pi/gesture_knn_model.npz",
    threshold=30,
    hold_seconds=1.0,
)

gesture_label = "unknown"
gesture_debug_jpeg = None
gesture_debug_lock = threading.Lock()

lane_follow_enabled = False

active_motion_command = "stop"
motion_lock = threading.Lock()
stop_event = threading.Event()
last_accel_magnitude = None
filtered_accel_magnitude = None
last_impact_time = 0.0
impact_detected = False
impact_locked = False
impact_value = 0.0

last_applied_gesture = "unknown"

front_dist_median_window = []
front_dist_average_window = []
rear_dist_median_window = []
rear_dist_average_window = []
roll_average_window = []
pitch_average_window = []


@app.route("/")
def index():
    return render_template_string(TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.route("/camera_feed")
def camera_feed():
    return Response(
        generate_camera_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/lane_feed")
def lane_feed():
    def generate_lane_stream():
        while True:
            with lane_debug_lock:
                frame = lane_debug_jpeg

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )

            time.sleep(0.03)

    return Response(
        generate_lane_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
    
@app.route("/gesture_feed")
def gesture_feed():
    def generate():
        while True:
            with gesture_debug_lock:
                frame = gesture_debug_jpeg

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )

            time.sleep(0.03)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

def read_distance_cm(sensor):
    try:
        distance = sensor.distance
        return round(distance * 100, 1) if distance is not None else None
    except Exception:
        return None
    
def update_lcd(line1="", line2=""):
    global last_lcd_text

    if lcd is None:
        return

    line1 = str(line1)[:16].ljust(16)
    line2 = str(line2)[:16].ljust(16)

    text = line1 + line2

    if text == last_lcd_text:
        return

    try:
        lcd.clear()
        lcd.write_string(line1)
        lcd.cursor_pos = (1, 0)
        lcd.write_string(line2)
        last_lcd_text = text
    except Exception as exc:
        print(f"LCD update error: {exc}")


def is_obstacle_close(sensor):
    distance_cm = read_distance_cm(sensor)

    # 센서값을 못 읽으면 안전하게 정지 쪽으로 판단
    if distance_cm is None:
        return True

    return distance_cm <= OBSTACLE_STOP_CM


def read_accel_magnitude():
    if not imu_available:
        return None

    accel = imu.get_accel_data()
    x, y, z = accel["x"], accel["y"], accel["z"]
    return math.sqrt((x * x) + (y * y) + (z * z))


def is_impact_detected():
    global filtered_accel_magnitude, impact_detected, impact_value, last_accel_magnitude, last_impact_time

    if not imu_available:
        impact_detected = False
        impact_value = 0.0
        return False

    now = time.monotonic()
    raw_magnitude = read_accel_magnitude()

    if filtered_accel_magnitude is None:
        filtered_accel_magnitude = raw_magnitude
        last_accel_magnitude = filtered_accel_magnitude
        impact_value = 0.0
        impact_detected = False
        return False

    filtered_accel_magnitude = low_pass_filter(
        raw_magnitude,
        filtered_accel_magnitude,
        alpha=ACCEL_ALPHA,
    )
    delta = abs(filtered_accel_magnitude - last_accel_magnitude)
    last_accel_magnitude = filtered_accel_magnitude
    impact_value = round(delta, 2)

    if delta >= IMPACT_DELTA_G and (now - last_impact_time) >= IMPACT_COOLDOWN_SEC:
        last_impact_time = now
        impact_detected = True
        return True

    if (now - last_impact_time) >= IMPACT_COOLDOWN_SEC:
        impact_detected = False

    return False


def safety_monitor_loop():
    global active_motion_command, impact_locked

    while not stop_event.is_set():
        with motion_lock:
            cmd = active_motion_command

        if is_impact_detected():
            move_stop()
            with motion_lock:
                active_motion_command = "stop"
                impact_locked = True
        elif cmd in (
            "forward",
            "curve_left",
            "curve_right",
            "lane_follow",
            "lane_forward",
            "lane_left",
            "lane_right",
            "gesture_go_lane_follow",
        ) and is_obstacle_close(front_ultra):
            move_stop()
            with motion_lock:
                active_motion_command = "stop"
                
        elif cmd == "backward" and is_obstacle_close(rear_ultra):
            move_stop()
            with motion_lock:
                active_motion_command = "stop"

        time.sleep(SAFETY_CHECK_INTERVAL)


def lane_follow_loop():
    global active_motion_command, current_speed, lane_debug_jpeg

    while not stop_event.is_set():
        frame = get_latest_frame()

        if frame is None:
            time.sleep(0.05)
            continue

        result = lane_tracker.process(frame)
        direction = result["direction"]
        error = result["smoothed_error"]
        debug_frame = result["debug_frame"]

        ok, encoded = cv2.imencode(".jpg", debug_frame)

        if ok:
            with lane_debug_lock:
                lane_debug_jpeg = encoded.tobytes()

        # From here, only motor control is stopped.
        if not lane_follow_enabled:
            time.sleep(0.05)
            continue

        if is_obstacle_close(front_ultra):
            move_stop()
            time.sleep(0.05)
            continue

        print(f"Lane error: {error}, direction: {direction}")

        if direction == "forward":
            move_forward(LANE_FOLLOW_SPEED)
            cmd = "lane_forward"
        elif direction == "left":
            move_curve_left(LANE_FOLLOW_SPEED)
            cmd = "lane_left"
        elif direction == "right":
            move_curve_right(LANE_FOLLOW_SPEED)
            cmd = "lane_right"
        else:
            move_stop()
            cmd = "stop"

        with motion_lock:
            active_motion_command = cmd

        time.sleep(0.05)
        
def gesture_loop():
    global gesture_label
    global gesture_debug_jpeg
    global lane_follow_enabled
    global active_motion_command
    global last_applied_gesture

    while not stop_event.is_set():
        frame = get_latest_frame()

        if frame is None:
            time.sleep(0.05)
            continue

        result = gesture_recognizer.process(frame)

        gesture_label = result["label"]
        debug_frame = result["debug_frame"]

        ok, encoded = cv2.imencode(".jpg", debug_frame)

        if ok:
            with gesture_debug_lock:
                gesture_debug_jpeg = encoded.tobytes()

        if gesture_label != last_applied_gesture:
            if gesture_label == "stop":
                update_lcd("GESTURE", "STOP")

                lane_follow_enabled = False
                move_stop()

                with motion_lock:
                    active_motion_command = "stop"

            elif gesture_label == "go":
                update_lcd("GESTURE", "GO")

                lane_follow_enabled = False

                with motion_lock:
                    active_motion_command = "gesture_go_lane_follow"

            last_applied_gesture = gesture_label

        time.sleep(0.08)

@app.route("/control", methods=["POST"])
def control():
    global active_motion_command, current_speed, impact_detected, impact_locked, lane_follow_enabled

    data = request.get_json(silent=True) or {}
    cmd = data.get("command", "stop")
    
    if cmd == "lane_follow":
        if is_obstacle_close(front_ultra):
            move_stop()
            return "BLOCKED", 409

        lane_follow_enabled = True
        impact_locked = False
        impact_detected = False

        with motion_lock:
            active_motion_command = "lane_follow"

        return "OK", 200

    lane_follow_enabled = False

    if cmd == "stop":
        impact_locked = False
        impact_detected = False
    elif impact_locked:
        move_stop()
        with motion_lock:
            active_motion_command = "stop"
        return "LOCKED", 423

    safe_speed = speed_limit_filter(DEFAULT_SPEED, max_limit=MAX_SPEED)
    safe_turn_speed = speed_limit_filter(TURN_SPEED, max_limit=MAX_SPEED)
    current_speed = low_pass_filter(safe_speed, current_speed, alpha=0.8)

    if cmd == "forward":
        if is_obstacle_close(front_ultra):
            move_stop()
            cmd = "stop"
        else:
            move_forward(current_speed)

    elif cmd == "backward":
        if is_obstacle_close(rear_ultra):
            move_stop()
            cmd = "stop"
        else:
            move_backward(current_speed)

    elif cmd == "curve_left":
        if is_obstacle_close(front_ultra):
            move_stop()
            cmd = "stop"
        else:
            move_curve_left(current_speed)

    elif cmd == "curve_right":
        if is_obstacle_close(front_ultra):
            move_stop()
            cmd = "stop"
        else:
            move_curve_right(current_speed)

    elif cmd == "left":
        move_turn_left(safe_turn_speed)

    elif cmd == "right":
        move_turn_right(safe_turn_speed)

    elif cmd == "stop":
        move_stop()

    with motion_lock:
        active_motion_command = cmd

    return "OK", 200


@app.route("/status")
def status():
    front_raw_dist = read_distance_cm(front_ultra)
    front_sensor_error = front_raw_dist is None
    front_raw_dist = 0.0 if front_raw_dist is None else front_raw_dist
    front_median_dist = median_filter(front_dist_median_window, front_raw_dist, window_size=3)
    front_filtered_dist = moving_average_filter(
        front_dist_average_window,
        front_median_dist,
        window_size=3,
    )

    rear_raw_dist = read_distance_cm(rear_ultra)
    rear_sensor_error = rear_raw_dist is None
    rear_raw_dist = 0.0 if rear_raw_dist is None else rear_raw_dist
    rear_median_dist = median_filter(rear_dist_median_window, rear_raw_dist, window_size=3)
    rear_filtered_dist = moving_average_filter(
        rear_dist_average_window,
        rear_median_dist,
        window_size=3,
    )

    if imu_available:
        accel = imu.get_accel_data()
        x, y, z = accel["x"], accel["y"], accel["z"]

        raw_roll = math.atan2(y, z) * 180 / math.pi
        raw_pitch = math.atan2(x, math.sqrt(y * y + z * z)) * 180 / math.pi
        filtered_roll = moving_average_filter(roll_average_window, raw_roll, window_size=5)
        filtered_pitch = moving_average_filter(pitch_average_window, raw_pitch, window_size=5)
    else:
        filtered_roll = 0.0
        filtered_pitch = 0.0

    return jsonify({
        "front_raw_dist": front_raw_dist,
        "front_dist": round(front_filtered_dist, 1),
        "front_blocked": front_sensor_error or front_raw_dist <= OBSTACLE_STOP_CM,
        "rear_raw_dist": rear_raw_dist,
        "rear_dist": round(rear_filtered_dist, 1),
        "rear_blocked": rear_sensor_error or rear_raw_dist <= OBSTACLE_STOP_CM,
        "roll": round(filtered_roll, 1),
        "pitch": round(filtered_pitch, 1),
        "impact_detected": impact_detected or impact_locked,
        "impact_locked": impact_locked,
        "impact_value": impact_value,
        "impact_threshold": IMPACT_DELTA_G,
        "accel_alpha": ACCEL_ALPHA,
        "current_speed": round(current_speed, 2),
        "gesture": gesture_label,
        "lane_follow": lane_follow_enabled,
    })


def get_ip():
    try:
        ret = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
        return ret.stdout.split()[0]
    except Exception:
        return "?.?.?.?"


def cleanup():
    stop_event.set()
    move_stop()
    cleanup_motor()
    stop_camera()
    gesture_recognizer.close()
    
    if lcd is not None:
        try:
            lcd.clear()
            lcd.write_string("System Off")
        except Exception:
            pass


def main():
    atexit.register(cleanup)

    start_camera(show_preview=False)

    safety_thread = threading.Thread(target=safety_monitor_loop, daemon=True)
    lane_thread = threading.Thread(target=lane_follow_loop, daemon=True)
    gesture_thread = threading.Thread(target=gesture_loop, daemon=True)

    safety_thread.start()
    lane_thread.start()
    gesture_thread.start()

    ip = get_ip()
    print("=" * 40)
    print("   [Project 4] Pi-Rover IoT Center")
    print(f"   - URL: http://{ip}:5000")
    print("   - Features: remote control + fast obstacle stop")
    print("=" * 40)

    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
