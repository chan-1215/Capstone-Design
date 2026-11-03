"""PC-side overhead camera guard for bounded Pi driving tests.

Start this before pressing a drive button on the Pi monitor. It never starts
the motors; it only sends a stop request when visual motion is unsafe.
"""

import argparse
from collections import deque
import time
from urllib import error, request

import cv2
import numpy as np


# Reference points for the current fixed 1280x720 overhead camera view.
# Each pair is (image y, expected center x of the outer-left lane).
LANE_CENTER = ((150, 455), (250, 416), (320, 378), (400, 333),
               (470, 310), (540, 285), (610, 330))
LANE_HALF_WIDTH = ((150, 24), (250, 35), (320, 43), (400, 50),
                   (470, 64), (540, 70), (610, 82))


def lane_offset(point, frame_size=(1280, 720)):
    x, y = point
    width, height = frame_size
    if not (0 <= x < width and 150 <= y <= min(610, height - 1)):
        return None
    rows, centers = zip(*LANE_CENTER)
    _, halves = zip(*LANE_HALF_WIDTH)
    center = np.interp(y, rows, centers)
    half_width = np.interp(y, rows, halves)
    return float((x - center) / half_width)


def locate_robot(frame):
    """Return the red chassis center in the current fixed overhead view."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 80, 40), (12, 255, 255))
    red |= cv2.inRange(hsv, (170, 80, 40), (179, 255, 255))
    contours, _ = cv2.findContours(red, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        if (60 <= area <= 1500 and width >= 12 and height >= 4
                and width / height >= 1.3 and y < frame.shape[0] * 0.88):
            candidates.append((area, (x + width / 2, y + height / 2)))
    return max(candidates, default=(0, None))[1]


def track_margin(frame, point):
    if point is None:
        return None
    light, a, b = cv2.split(cv2.cvtColor(frame, cv2.COLOR_BGR2LAB))
    white = ((light > 145) & (np.abs(a.astype(np.int16) - 128) < 20)
             & (np.abs(b.astype(np.int16) - 128) < 20)).astype(np.uint8) * 255
    size = max(3, (frame.shape[1] // 32) | 1)
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE,
                             np.ones((size, size), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    road = max(contours, key=cv2.contourArea)
    if cv2.contourArea(road) < frame.shape[0] * frame.shape[1] * 0.15:
        return None
    return cv2.pointPolygonTest(road, point, True)


def should_stop(active_for, positions, current_offset):
    if current_offset is None or abs(current_offset) >= 0.55:
        return "track_edge_or_camera_lost"
    if active_for >= 1.2 and len(positions) >= 2:
        first_x, first_y = positions[0]
        last_x, last_y = positions[-1]
        if np.hypot(last_x - first_x, last_y - first_y) < 5:
            return "no_visual_motion"
    return None


def should_stop_surface(active_for, positions, margin, frame_width):
    if margin is None or margin < frame_width * 0.02:
        return "track_edge_or_camera_lost"
    if active_for >= 1.2 and len(positions) >= 2:
        first_x, first_y = positions[0]
        last_x, last_y = positions[-1]
        if np.hypot(last_x - first_x, last_y - first_y) < 5:
            return "no_visual_motion"
    return None


def json_request(url, method="GET"):
    import json

    with request.urlopen(request.Request(url, method=method), timeout=1) as response:
        return json.load(response)


def stop_drive(pi_url, reason, point, offset):
    for attempt in range(3):
        try:
            json_request(pi_url + "/drive/stop", "POST")
            break
        except (error.URLError, TimeoutError):
            if attempt == 2:
                print("STOP request failed; disconnect motor power now", flush=True)
            time.sleep(0.1)
    print(f"STOP: {reason}, robot={point}, offset={offset}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-url", default="http://192.168.137.155:5001")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--guard-mode", choices=("lane", "surface"), default="lane",
                        help="surface checks the white track boundary in any camera size")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=0,
                        help="0 keeps watching until Q/Ctrl+C")
    parser.add_argument("--record", help="optional MJPEG AVI recording path")
    args = parser.parse_args()
    if args.max_seconds < 0:
        parser.error("max seconds cannot be negative")
    camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not camera.isOpened():
        parser.error("overhead camera is unavailable")
    ready = False
    for _ in range(30):
        ok, frame = camera.read()
        if ok:
            point = locate_robot(frame)
            metric = (track_margin(frame, point) if args.guard_mode == "surface"
                      else lane_offset(point, (frame.shape[1], frame.shape[0])))
            if metric is not None:
                ready = True
                break
        time.sleep(0.05)
    if not ready:
        camera.release()
        parser.error("robot is not visible in the calibrated overhead view")
    writer = None
    if args.record:
        width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"MJPG"),
                                 10, (width, height))
        if not writer.isOpened():
            camera.release()
            parser.error("cannot open overhead recording")
    started = time.monotonic()
    active_since = None
    positions = deque(maxlen=20)
    last_status = 0.0
    drive_active = False
    print("Overhead guard ready", flush=True)
    try:
        while True:
            if args.max_seconds and time.monotonic() - started >= args.max_seconds:
                break
            ok, frame = camera.read()
            if not ok:
                if drive_active:
                    stop_drive(args.pi_url, "overhead_camera_lost", None, None)
                break
            now = time.monotonic()
            if now - last_status >= 0.2:
                try:
                    drive_active = json_request(args.pi_url + "/status")["drive"]["active"]
                except (error.URLError, TimeoutError, KeyError):
                    if drive_active:
                        stop_drive(args.pi_url, "pi_status_lost", None, None)
                    drive_active = False
                last_status = now
            point = locate_robot(frame) if ok else None
            offset = (track_margin(frame, point) if args.guard_mode == "surface"
                      else lane_offset(point, (frame.shape[1], frame.shape[0]))
                      if point else None)
            if drive_active:
                if active_since is None:
                    active_since = now
                    positions.clear()
                if point is not None:
                    positions.append(point)
                reason = (should_stop_surface(now - active_since, positions, offset,
                                              frame.shape[1])
                          if args.guard_mode == "surface"
                          else should_stop(now - active_since, positions, offset))
                if reason:
                    stop_drive(args.pi_url, reason, point, offset)
                    drive_active = False
                    active_since = None
            else:
                active_since = None
                positions.clear()
            if point is not None:
                cv2.circle(frame, tuple(map(int, point)), 8, (0, 255, 0), 2)
            label = "margin" if args.guard_mode == "surface" else "offset"
            cv2.putText(frame, f"{label}={offset:.2f}" if offset is not None else "robot lost",
                        (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            if writer is not None:
                writer.write(frame)
            if not args.headless:
                cv2.imshow("Overhead guard (Q to quit)", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        if drive_active:
            stop_drive(args.pi_url, "guard_closed", None, None)
        camera.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
