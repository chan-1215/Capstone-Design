# file name: project4_iot_center.py
# Browser-controlled Pi-Rover with filtered motor control and sensor monitoring.

import atexit
import math
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["NCNN_THREADS"] = "1"

import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2

cv2.setNumThreads(1)
cv2.ocl.setUseOpenCL(False)

from flask import Flask, Response, jsonify, render_template_string, request
# from gpiozero import DistanceSensor  # 초음파 센서 비활성화

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
    get_latest_frame
)
from lane_tracking_module import LaneTracker
from ultralytics import YOLO

# 여러 스레드(safety_monitor_loop, lane_follow_loop, yolo_detection_loop,
# threaded Flask의 /control 요청)가 동시에 GPIO/모터를 건드리면 gpiozero/lgpio
# 내부 상태가 꼬여 "corrupted size vs. prev_size" 같은 네이티브 크래시가 날 수 있다.
# 모든 이동 함수를 락으로 감싸서 한 번에 하나의 스레드만 GPIO를 제어하도록 강제한다.
_gpio_lock = threading.Lock()

_raw_move_forward = move_forward
_raw_move_backward = move_backward
_raw_move_stop = move_stop
_raw_move_curve_left = move_curve_left
_raw_move_curve_right = move_curve_right
_raw_move_turn_left = move_turn_left
_raw_move_turn_right = move_turn_right


def move_forward(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_forward(*args, **kwargs)


def move_backward(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_backward(*args, **kwargs)


def move_stop(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_stop(*args, **kwargs)


def move_curve_left(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_curve_left(*args, **kwargs)


def move_curve_right(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_curve_right(*args, **kwargs)


def move_turn_left(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_turn_left(*args, **kwargs)


def move_turn_right(*args, **kwargs):
    with _gpio_lock:
        return _raw_move_turn_right(*args, **kwargs)


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

# YOLO 객체 감지 모델 로드 (person, car 감지 시 정지)
# NCNN으로 export한 모델을 사용 — torch의 ARM Compute Library를 거치지 않아
# Pi4(Cortex-A72)에서도 Illegal instruction 없이 안정적으로 동작한다.
# PC/Colab에서 `yolo export model=yolo11n.pt format=ncnn` 실행 후
# 생성된 'yolo11n_ncnn_model' 폴더를 이 스크립트와 같은 위치에 복사해둘 것.
YOLO_MODEL_PATH = "/home/pi/pi-rover/ch09_project/yolov8n_ncnn_model"
YOLO_TARGET_CLASSES = {"person", "car"}
YOLO_CONFIDENCE_THRESHOLD = 0.5
YOLO_DETECT_INTERVAL = 1.5  # 라즈베리파이 부하를 고려해 매 프레임이 아닌 주기적으로만 추론

try:
    yolo_model = YOLO(YOLO_MODEL_PATH, task="detect")
    yolo_available = True
    print("YOLO model loaded.")
    print(
        f"  OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS', '(미설정)')}, "
        f"NCNN_THREADS={os.environ.get('NCNN_THREADS', '(미설정)')}"
    )
except Exception as exc:
    yolo_model = None
    yolo_available = False
    print(f"YOLO model load failed: {exc}")
    print("Continuing without YOLO object detection.")

# queue_len=1 keeps obstacle checks responsive. Bigger queues smooth values but add delay.
# front_ultra = DistanceSensor(echo=12, trigger=13, max_distance=2.0, queue_len=1)  # 초음파 센서 비활성화
# rear_ultra = DistanceSensor(echo=17, trigger=4, max_distance=2.0, queue_len=1)  # 초음파 센서 비활성화

app = Flask(__name__)
TEMPLATE_PATH = Path(__file__).with_name("project4_iot_center.html")

MAX_SPEED = 0.65
DEFAULT_SPEED = 0.5
TURN_SPEED = 0.45
current_speed = 0.5
# OBSTACLE_STOP_CM = 40.0  # 초음파 센서 비활성화
SAFETY_CHECK_INTERVAL = 0.03
IMPACT_DELTA_G = 3.5
ACCEL_ALPHA = 0.25
IMPACT_COOLDOWN_SEC = 1.0
LANE_FOLLOW_SPEED = 0.35
yolo_clear_count = 0
YOLO_CLEAR_FRAMES = 3

lane_debug_jpeg = None
lane_debug_lock = threading.Lock()

lane_tracker = LaneTracker(
    frame_width=320,
    crop_y1=60,
    crop_y2=220,
    center_tolerance=25,
    smooth_window=5,
)

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

yolo_locked = False
yolo_detected_classes = []
yolo_debug_jpeg = None
yolo_debug_lock = threading.Lock()
yolo_release_required = False

# front_dist_median_window = []  # 초음파 센서 비활성화
# front_dist_average_window = []  # 초음파 센서 비활성화
# rear_dist_median_window = []  # 초음파 센서 비활성화
# rear_dist_average_window = []  # 초음파 센서 비활성화
roll_average_window = []
pitch_average_window = []

@app.route("/")
def index():
    return render_template_string(TEMPLATE_PATH.read_text(encoding="utf-8"))


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


@app.route("/yolo_feed")
def yolo_feed():
    def generate_yolo_stream():
        while True:
            with yolo_debug_lock:
                frame = yolo_debug_jpeg

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )

            time.sleep(0.03)

    return Response(
        generate_yolo_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# def read_distance_cm(sensor):  # 초음파 센서 비활성화
#     try:
#         distance = sensor.distance
#         return round(distance * 100, 1) if distance is not None else None
#     except Exception:
#         return None


# def is_obstacle_close(sensor):  # 초음파 센서 비활성화
#     distance_cm = read_distance_cm(sensor)
#
#     # 센서값을 못 읽으면 안전하게 정지 쪽으로 판단
#     if distance_cm is None:
#         return True
#
#     return distance_cm <= OBSTACLE_STOP_CM

def is_obstacle_close(sensor=None):
    # 초음파 센서 비활성화: 항상 "장애물 없음"으로 취급해 기존 호출부를 그대로 살려둠
    return False


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
        # elif cmd in (
        #     "forward",
        #     "curve_left",
        #     "curve_right",
        #     "lane_forward",
        #     "lane_left",
        #     "lane_right",
        # ) and is_obstacle_close(front_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     with motion_lock:
        #         active_motion_command = "stop"

        # elif cmd == "backward" and is_obstacle_close(rear_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     with motion_lock:
        #         active_motion_command = "stop"

        time.sleep(SAFETY_CHECK_INTERVAL)


def calculate_inner_ratio(error):
    abs_error = abs(error)

    if abs_error < 20:
        return 0.75
    elif abs_error < 40:
        return 0.55
    else:
        return 0.35


def run_yolo_detection(frame):
    global yolo_debug_jpeg

    if not yolo_available:
        return []

    inference_start = time.monotonic()
    results = yolo_model.predict(
        frame,
        verbose=False,
        conf=0.5,
        iou=0.45,
        max_det=20,
        imgsz=256,
    )
    inference_ms = (time.monotonic() - inference_start) * 1000
    print(f"YOLO inference: {inference_ms:.0f}ms")

    detected = []
    debug_frame = frame.copy()

    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = yolo_model.names[cls_id]
            confidence = float(box.conf[0])

            # 진단용: threshold와 무관하게 감지된 모든 후보를 로그로 출력
            if cls_name in YOLO_TARGET_CLASSES:
                print(f"  candidate: {cls_name} conf={confidence:.2f}")

            if cls_name not in YOLO_TARGET_CLASSES or confidence < YOLO_CONFIDENCE_THRESHOLD:
                continue

            detected.append(cls_name)

            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            label = f"{cls_name} {confidence:.2f}"

            cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            label_y = y1 - 8 if y1 - 8 > 10 else y1 + 18
            cv2.putText(
                debug_frame,
                label,
                (x1, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
            )

    ok, encoded = cv2.imencode(".jpg", debug_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

    if ok:
        with yolo_debug_lock:
            yolo_debug_jpeg = encoded.tobytes()

    return detected


def yolo_detection_loop():
    global active_motion_command, yolo_locked, yolo_detected_classes, yolo_clear_count
    global lane_follow_enabled, yolo_release_required

    while not stop_event.is_set():
        if not yolo_available:
            time.sleep(1.0)
            continue

        frame = get_latest_frame()

        if frame is None:
            time.sleep(YOLO_DETECT_INTERVAL)
            continue

        try:
            detected = run_yolo_detection(frame)
        except Exception as exc:
            print(f"YOLO detection error: {exc}")
            detected = []

        with motion_lock:
            yolo_detected_classes = detected

        if detected:
            yolo_clear_count = 0
            lane_follow_enabled = False
            yolo_release_required = True
            move_stop()

            with motion_lock:
                active_motion_command = "stop"
                yolo_locked = True

            print(f"YOLO stop triggered: {detected}")

        else:
            yolo_clear_count += 1

            if yolo_clear_count >= YOLO_CLEAR_FRAMES:
                yolo_locked = False
                yolo_detected_classes = []

        time.sleep(YOLO_DETECT_INTERVAL)


def lane_follow_loop():
    global active_motion_command, current_speed, lane_debug_jpeg

    while not stop_event.is_set():
        try:
            frame = get_latest_frame()

            if frame is None:
                time.sleep(0.05)
                continue

            result = lane_tracker.process(frame)
            direction = result["direction"]
            error = result["smoothed_error"]
            debug_frame = result["debug_frame"]

            ok, encoded = cv2.imencode(".jpg", debug_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

            if ok:
                with lane_debug_lock:
                    lane_debug_jpeg = encoded.tobytes()

            if not lane_follow_enabled:
                time.sleep(0.05)
                continue

            # if is_obstacle_close(front_ultra):  # 초음파 센서 비활성화
            #     move_stop()
            #     time.sleep(0.05)
            #     continue

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

            time.sleep(0.08)

        except Exception as exc:
            print(f"Lane follow error: {exc}")
            move_stop()
            time.sleep(0.2)

@app.route("/control", methods=["POST"])
def control():
    global active_motion_command, current_speed, impact_detected, impact_locked, lane_follow_enabled, yolo_locked, yolo_detected_classes
    global yolo_release_required

    data = request.get_json(silent=True) or {}
    cmd = data.get("command", "stop")

    if cmd != "stop" and (yolo_locked or yolo_release_required):
        move_stop()
        with motion_lock:
            active_motion_command = "stop"
        return "YOLO_LOCKED", 423

    if cmd == "lane_follow":
        # if is_obstacle_close(front_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     return "BLOCKED", 409

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
        yolo_release_required = False
    elif impact_locked:
        move_stop()
        with motion_lock:
            active_motion_command = "stop"
        return "LOCKED", 423

    safe_speed = speed_limit_filter(DEFAULT_SPEED, max_limit=MAX_SPEED)
    safe_turn_speed = speed_limit_filter(TURN_SPEED, max_limit=MAX_SPEED)
    current_speed = low_pass_filter(safe_speed, current_speed, alpha=0.8)

    if cmd == "forward":
        # if is_obstacle_close(front_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     cmd = "stop"
        # else:
        move_forward(current_speed)

    elif cmd == "backward":
        # if is_obstacle_close(rear_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     cmd = "stop"
        # else:
        move_backward(current_speed)

    elif cmd == "curve_left":
        # if is_obstacle_close(front_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     cmd = "stop"
        # else:
        move_curve_left(current_speed)

    elif cmd == "curve_right":
        # if is_obstacle_close(front_ultra):  # 초음파 센서 비활성화
        #     move_stop()
        #     cmd = "stop"
        # else:
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
    # 초음파 센서 비활성화: 거리 읽기/필터링 로직 주석 처리, 응답에는 고정값으로 대체
    # front_raw_dist = read_distance_cm(front_ultra)
    # front_sensor_error = front_raw_dist is None
    # front_raw_dist = 0.0 if front_raw_dist is None else front_raw_dist
    # front_median_dist = median_filter(front_dist_median_window, front_raw_dist, window_size=3)
    # front_filtered_dist = moving_average_filter(
    #     front_dist_average_window,
    #     front_median_dist,
    #     window_size=3,
    # )

    # rear_raw_dist = read_distance_cm(rear_ultra)
    # rear_sensor_error = rear_raw_dist is None
    # rear_raw_dist = 0.0 if rear_raw_dist is None else rear_raw_dist
    # rear_median_dist = median_filter(rear_dist_median_window, rear_raw_dist, window_size=3)
    # rear_filtered_dist = moving_average_filter(
    #     rear_dist_average_window,
    #     rear_median_dist,
    #     window_size=3,
    # )

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
        # "front_raw_dist": front_raw_dist,  # 초음파 센서 비활성화
        # "front_dist": round(front_filtered_dist, 1),  # 초음파 센서 비활성화
        # "front_blocked": front_sensor_error or front_raw_dist <= OBSTACLE_STOP_CM,  # 초음파 센서 비활성화
        # "rear_raw_dist": rear_raw_dist,  # 초음파 센서 비활성화
        # "rear_dist": round(rear_filtered_dist, 1),  # 초음파 센서 비활성화
        # "rear_blocked": rear_sensor_error or rear_raw_dist <= OBSTACLE_STOP_CM,  # 초음파 센서 비활성화
        "roll": round(filtered_roll, 1),
        "pitch": round(filtered_pitch, 1),
        "impact_detected": impact_detected or impact_locked,
        "impact_locked": impact_locked,
        "impact_value": impact_value,
        "impact_threshold": IMPACT_DELTA_G,
        "accel_alpha": ACCEL_ALPHA,
        "current_speed": round(current_speed, 2),
        "yolo_available": yolo_available,
        "yolo_locked": yolo_locked,
        "yolo_detected_classes": yolo_detected_classes,
        "yolo_release_required": yolo_release_required,
        "active_motion_command": active_motion_command,
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


def main():
    atexit.register(cleanup)

    start_camera(show_preview=False)

    safety_thread = threading.Thread(target=safety_monitor_loop, daemon=True)
    safety_thread.start()

    lane_thread = threading.Thread(target=lane_follow_loop, daemon=True)
    lane_thread.start()

    yolo_thread = threading.Thread(target=yolo_detection_loop, daemon=True)
    yolo_thread.start()

    ip = get_ip()
    print("=" * 40)
    print("   [Project 4] Pi-Rover IoT Center")
    print(f"   - URL: http://{ip}:5000")
    print("   - Features: remote control + YOLO stop (person, car)")
    print("=" * 40)

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()