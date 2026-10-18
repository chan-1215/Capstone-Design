"""Camera monitor, local media capture and explicitly opt-in robot control."""

import argparse
from collections import deque
import logging
import math
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from datetime import datetime, timezone
import signal
import secrets
import threading
import time

import cv2
from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory

from camera_source import ImageSource, PiCameraSource
from track_vision import VisionConfig, analyze, overlay, combined_lines
from lane_path import LanePath, draw_path


MASK_VIEWS = ("road", "yellow", "white", "dashes")
VIEWS = ("processed", "raw", "lines", *MASK_VIEWS)


@contextmanager
def camera_lock():
    if not Path("/tmp").is_dir() or __import__("sys").platform == "win32":
        yield
        return
    import fcntl

    with open("/tmp/new_track_vision_camera.lock", "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another Track Vision camera server is running") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class Monitor:
    def __init__(self, source, config=None, rotation=180, path_enabled=False):
        self.source = source
        self.config = config or VisionConfig(max_side=640, roi_top=0.20)
        self.rotation = rotation
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.images = {}
        self.metrics = {}
        self.last_frame_at = None
        self.frame_number = 0
        self.fps = 0.0
        self.error = None
        self.thread = None
        self.path_tracker = LanePath() if path_enabled else None
        self.prediction = {'valid':False, 'reference_set':False, 'reason':'disabled'}
        self.path_streak = 0
        self.diagnostic_frames = deque(maxlen=3)
        self.capture = self.manual = self.pilot = None

    def start(self):
        self.source.start()
        self.thread = threading.Thread(target=self._loop, name="track-vision", daemon=True)
        self.thread.start()

    def process_frame(self, frame):
        started = time.monotonic()
        with self.condition:
            config = self.config
            rotation = self.rotation
        if rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        result = analyze(frame, config)
        processed = overlay(result, lines_only=True)
        lines = combined_lines(result)
        signature = (rotation, result.frame.shape, tuple(asdict(config).values()))
        prediction = (self.path_tracker.predict(result, signature) if self.path_tracker else
                      {'valid':False, 'reference_set':False, 'reason':'disabled'})
        if self.path_tracker:
            draw_path(processed, prediction)
        height, width = processed.shape[:2]
        roi_row = int(height * config.roi_top)
        cv2.rectangle(processed, (0, roi_row), (width - 1, height - 1), (25, 25, 25), 3)
        cv2.rectangle(processed, (0, roi_row), (width - 1, height - 1), (200, 200, 200), 1)
        label_y = roi_row - 6 if roi_row >= 20 else 16
        cv2.putText(processed, "ROI", (8, label_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (25, 25, 25), 3, cv2.LINE_AA)
        cv2.putText(processed, "ROI", (8, label_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (230, 230, 230), 1, cv2.LINE_AA)
        inset_width = width // 3
        inset_height = max(1, round(height * inset_width / width))
        inset = cv2.resize(lines, (inset_width, inset_height), interpolation=cv2.INTER_NEAREST)
        processed[:inset_height, width - inset_width:] = inset
        cv2.rectangle(processed, (width - inset_width, 0), (width - 1, inset_height), (100, 110, 120), 1)
        raw = result.frame
        if frame.shape[:2] != result.frame.shape[:2]:
            # Keep native camera detail; enlarge only analysis annotations.
            native_size = (frame.shape[1], frame.shape[0])
            changed = cv2.bitwise_not(cv2.inRange(cv2.absdiff(processed, result.frame),
                                                (0, 0, 0), (0, 0, 0)))
            annotations = cv2.resize(processed, native_size, interpolation=cv2.INTER_NEAREST)
            changed = cv2.resize(changed, native_size, interpolation=cv2.INTER_NEAREST)
            raw = frame.copy()
            processed = cv2.copyTo(annotations, changed, raw.copy())
        images = {"processed": processed, "raw": raw, "lines": lines,
                  **{name: getattr(result, name) for name in MASK_VIEWS}}
        with self.condition:
            now = time.monotonic()
            if self.last_frame_at is not None:
                instantaneous = 1.0 / max(now - self.last_frame_at, 0.001)
                self.fps = instantaneous if not self.fps else self.fps * 0.8 + instantaneous * 0.2
            self.images = images
            self.metrics = {**result.metrics,
                            "mode": "camera_vision_only",
                            "inset_view": "lines",
                            "processing_ms": round((now - started) * 1000, 1)}
            self.last_frame_at = now
            self.frame_number += 1
            self.prediction = prediction
            if self.path_tracker:
                self.diagnostic_frames.append((self.frame_number, images['raw'], processed))
            self.path_streak = self.path_streak + 1 if prediction.get('valid') else 0
            self.condition.notify_all()
        if self.capture:
            self.capture.offer(raw, processed, self.telemetry())

    def control_snapshot(self):
        with self.condition:
            return dict(path=dict(self.prediction), number=self.frame_number,
                        age=None if self.last_frame_at is None else time.monotonic() - self.last_frame_at,
                        streak=self.path_streak)

    def calibrate_path(self):
        with self.condition:
            if (not self.path_tracker or self.path_streak < 3 or self.last_frame_at is None
                    or time.monotonic() - self.last_frame_at > .2):
                raise ValueError('A fresh stable path is required')
            reference = self.path_tracker.calibrate(self.prediction)
            self.prediction = {**self.prediction, 'reference_set':True,
                               'reference_normalized':reference, 'normalized_error':0.0,
                               'reference_heading_degrees':self.path_tracker.reference_heading,
                               'heading_error_degrees':0.0, 'forward_direction':'straight'}
            return reference

    def fresh_pair(self):
        with self.condition:
            if (self.last_frame_at is None or time.monotonic() - self.last_frame_at > 2
                    or self.error or self.stop_event.is_set()):
                raise ValueError('No fresh camera frame')
            return self.images['raw'].copy(), self.images['processed'].copy()

    def diagnostic_pair(self, number):
        with self.condition:
            for frame_number, raw, processed in self.diagnostic_frames:
                if frame_number == number:
                    return raw, processed
        return None

    def telemetry(self):
        with self.condition:
            data = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                        monotonic=time.monotonic(), frame_number=self.frame_number,
                        vision=dict(self.metrics), path=dict(self.prediction))
        data['control'] = self.manual.status() if self.manual else None
        data['pilot'] = self.pilot.status() if self.pilot else None
        return data

    def _loop(self):
        try:
            while not self.stop_event.is_set():
                self.process_frame(self.source.read())
        except Exception as error:
            with self.condition:
                self.error = f"{type(error).__name__}: {error}"
        finally:
            self.stop_event.set()
            with self.condition:
                self.condition.notify_all()

    def status(self):
        with self.condition:
            age = None if self.last_frame_at is None else time.monotonic() - self.last_frame_at
            online = self.error is None and age is not None and age < 2 and not self.stop_event.is_set()
            return {**self.metrics, "camera_online": online,
                    "frame_age_seconds": None if age is None else round(age, 3),
                    "frame_number": self.frame_number, "fps": round(self.fps, 1),
                    "error": self.error, "settings": {**asdict(self.config), "rotation": self.rotation},
                    "path_prediction": dict(self.prediction),
                    "control_enabled": False, "target_path": None}

    def settings(self, values):
        if not isinstance(values, dict) or not values:
            raise ValueError("Expected a nonempty settings object")
        allowed = {"roi_top", "white_min_value", "yellow_min_saturation", "rotation"}
        if set(values) - allowed:
            raise ValueError("Unknown vision setting")
        with self.condition:
            rotation = values.get("rotation", self.rotation)
            if type(rotation) is not int or rotation not in (0, 180):
                raise ValueError("rotation must be 0 or 180")
            changes = {key: value for key, value in values.items() if key != "rotation"}
            for key, value in changes.items():
                if key == "roi_top":
                    if type(value) not in (int, float) or not 0 <= value <= 0.8:
                        raise ValueError("roi_top must be between 0 and 0.8")
                elif type(value) is not int:
                    raise ValueError("Colour thresholds must be integers")
            config = replace(self.config, **changes)
            self.config = config
            self.rotation = rotation

    def jpeg(self, view):
        with self.condition:
            if (self.last_frame_at is None or time.monotonic() - self.last_frame_at > 2
                    or self.error or self.stop_event.is_set()):
                return None
            frame = self.images.get(view)
        if frame is None:
            return None
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return jpeg.tobytes() if ok else None

    def close(self):
        self.stop_event.set()
        try:
            self.source.stop()
        finally:
            if self.thread:
                self.thread.join(timeout=4)
            with self.condition:
                self.condition.notify_all()


def create_app(monitor, manual=None, capture=None, pilot=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 4096
    manual_token = secrets.token_urlsafe(32)

    def current_status():
        status = monitor.status()
        if manual is not None:
            status['manual'] = manual.status()
            status['mode'] = 'camera_manual'
            status['control_enabled'] = status['manual']['armed']
        if pilot:
            status['autonomous'] = pilot.status()
            if status['autonomous']['active']:
                status['mode'] = 'camera_pilot'
        if capture:
            status['capture'] = capture.status()
        return status

    def authorized_payload():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400)
        token = request.headers.get('X-Manual-Token', data.get('token', ''))
        if (not isinstance(token, str) or not token.isascii() or
                not secrets.compare_digest(token, manual_token)):
            abort(403)
        client = data.get('client')
        if not isinstance(client, str) or not 1 <= len(client) <= 100:
            abort(400)
        return data

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def index():
        options = None if manual is None else dict(token=manual_token, **manual.status())
        return render_template("monitor.html", manual_options=options,
                               capture_options=dict(token=manual_token, **capture.status()) if capture else None,
                               pilot_options=dict(token=manual_token, **pilot.status()) if pilot else None)

    @app.get("/status")
    def status():
        return jsonify(current_status())

    @app.post("/settings")
    def settings():
        try:
            if pilot and pilot.active:
                return jsonify(error='Stop autonomous driving before changing camera settings'), 409
            monitor.settings(request.get_json(silent=True))
            if monitor.path_tracker:
                monitor.path_tracker.reset()
                with monitor.condition:
                    monitor.prediction = {'valid':False, 'reference_set':False, 'reason':'settings_changed'}
                    monitor.path_streak = 0
        except (ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400
        return jsonify(current_status())

    if manual is not None:
        @app.post('/manual/<action>')
        def manual_action(action):
            if action not in ('arm', 'input', 'stop'):
                abort(404)
            data = authorized_payload()
            try:
                if action in ('arm', 'input') and not monitor.status()['camera_online']:
                    manual.stop('camera_error')
                    return jsonify(error='No fresh camera frame'), 503
                if action == 'arm':
                    manual.arm(data['client'])
                elif action == 'stop':
                    if type(data.get('emergency', False)) is not bool:
                        raise ValueError('emergency must be boolean')
                    manual.stop(client=None if data.get('emergency') else data['client'])
                    if pilot and pilot.active and (data.get('emergency') or pilot.client == data['client']):
                        pilot.stop()
                else:
                    manual.input(data['client'], data.get('sequence'), data.get('keys'),
                                 data.get('speed'), data.get('motor1_scale'), data.get('motor2_scale'))
            except ValueError as error:
                return jsonify(error=str(error)), 400
            except PermissionError as error:
                return jsonify(error=str(error)), 409
            except RuntimeError as error:
                return jsonify(error=str(error)), 503
            return jsonify(manual.status())

    if pilot:
        @app.post('/auto/<action>')
        def auto_action(action):
            if action not in ('reference', 'settings', 'start', 'heartbeat', 'stop'):
                abort(404)
            data = authorized_payload()
            try:
                if action == 'reference':
                    pilot.calibrate()
                elif action == 'settings':
                    pilot.configure(data.get('settings'))
                elif action == 'start':
                    if 'settings' in data:
                        pilot.configure(data['settings'])
                    pilot.start(data['client'])
                elif action == 'heartbeat':
                    pilot.heartbeat(data['client'])
                else:
                    if pilot.active and pilot.client != data['client']:
                        raise PermissionError('Another browser owns autonomous control')
                    pilot.stop()
            except ValueError as error:
                return jsonify(error=str(error)), 400
            except PermissionError as error:
                return jsonify(error=str(error)), 409
            except (OSError, RuntimeError) as error:
                return jsonify(error=str(error)), 503
            return jsonify(pilot.status())

    if capture:
        @app.post('/capture/<action>')
        def capture_action(action):
            if action not in ('photo', 'start', 'stop'):
                abort(404)
            authorized_payload()
            try:
                if action == 'stop':
                    capture.stop_video()
                else:
                    raw, processed = monitor.fresh_pair()
                    if action == 'photo':
                        capture.photo(raw, processed, monitor.telemetry())
                    else:
                        capture.start_video(raw.shape[1::-1])
            except ValueError as error:
                return jsonify(error=str(error)), 400
            except OSError as error:
                return jsonify(error=str(error)), 507
            return jsonify(capture.status())

        @app.get('/media/<path:name>')
        def media_file(name):
            path = Path(name)
            if (path.is_absolute() or '..' in path.parts or len(path.parts) != 2 or
                    path.parts[0] not in ('photos', 'videos', 'runs') or
                    path.suffix not in ('.jpg', '.mp4', '.json', '.jsonl')):
                abort(404)
            return send_from_directory(capture.root, name, as_attachment=True)

    @app.get("/snapshot/<view>.jpg")
    def snapshot(view):
        if view not in VIEWS:
            abort(404)
        jpeg = monitor.jpeg(view)
        if jpeg is None:
            return jsonify(error="No fresh camera frame"), 503
        return Response(jpeg, mimetype="image/jpeg")

    @app.get("/stream/<view>")
    def stream(view):
        if view not in VIEWS:
            abort(404)

        def frames():
            previous = -1
            while not monitor.stop_event.is_set():
                with monitor.condition:
                    monitor.condition.wait_for(
                        lambda: monitor.frame_number != previous or monitor.stop_event.is_set(), timeout=1)
                    number = monitor.frame_number
                if number == previous:
                    continue
                previous = number
                jpeg = monitor.jpeg(view)
                if jpeg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="PC fixture instead of Pi camera")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--rotation", type=int, choices=(0, 180), default=180)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument('--sensor-size', type=int, nargs=2, metavar=('WIDTH','HEIGHT'),
                        help='Request a raw sensor mode before resizing; IMX219 full view: 1640 1232')
    parser.add_argument('--manual', action='store_true', help='Enable the manual panel and servo; no automatic motion')
    parser.add_argument('--autonomous', action='store_true', help='Expose the short P-control pilot; never starts automatically')
    parser.add_argument('--capture-dir', type=Path, default=Path(__file__).resolve().parent / 'captures')
    parser.add_argument('--initial-speed', type=float, default=.30,
                        help='Initial manual output, 0..0.50; does not arm or move motors')
    parser.add_argument('--motor-wiring-confirmed', action='store_true',
                        help='Explicitly confirm BOTH DC pin pairs and forward polarities before enabling W/S')
    parser.add_argument('--motor1-pins', type=int, nargs=2, default=(20, 21))
    parser.add_argument('--motor2-pins', type=int, nargs=2, default=(23, 24))
    parser.add_argument('--motor1-direction', type=int, choices=(-1, 1), default=1)
    parser.add_argument('--motor2-direction', type=int, choices=(-1, 1), default=1)
    args = parser.parse_args()
    if min(args.width, args.height, args.fps) <= 0 or not 1 <= args.port <= 65535:
        parser.error("Invalid capture dimensions, frame rate or port")
    if args.sensor_size and min(args.sensor_size) <= 0:
        parser.error('Sensor dimensions must be positive')
    if not math.isfinite(args.initial_speed) or not 0 <= args.initial_speed <= .50:
        parser.error('--initial-speed must be between 0 and 0.50')
    if args.motor_wiring_confirmed and not args.manual:
        parser.error('--motor-wiring-confirmed requires --manual')
    if args.autonomous and not (args.manual and args.motor_wiring_confirmed):
        parser.error('--autonomous requires --manual --motor-wiring-confirmed')
    if args.manual and args.image:
        parser.error('Image fixtures are camera-only; manual hardware mode requires the Pi camera')
    source = ImageSource(args.image) if args.image else PiCameraSource(
        args.width, args.height, args.fps, args.sensor_size)
    from media_capture import CaptureStore
    capture = CaptureStore(args.capture_dir)
    monitor = Monitor(source, rotation=args.rotation, path_enabled=args.autonomous)
    monitor.capture = capture
    manual = None
    manual_stop = threading.Event()
    manual_thread = None
    pilot = None
    pilot_thread = None

    def shutdown(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        with camera_lock():
            try:
                monitor.start()
                deadline = time.monotonic() + 10
                while monitor.frame_number == 0 and monitor.error is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if not monitor.status()["camera_online"]:
                    raise RuntimeError(monitor.error or "No camera frame within 10 seconds")
                if args.manual:
                    from manual_drive import DriveConfig, open_hardware
                    manual = open_hardware(DriveConfig(
                        motors_confirmed=args.motor_wiring_confirmed,
                        motor1_pins=tuple(args.motor1_pins), motor2_pins=tuple(args.motor2_pins),
                        motor1_direction=args.motor1_direction, motor2_direction=args.motor2_direction))
                    manual.speed = args.initial_speed
                    monitor.manual = manual

                    def watchdog():
                        while not manual_stop.wait(.04):
                            if not monitor.status()['camera_online']:
                                manual.stop('camera_error')
                            else:
                                manual.tick()

                    manual_thread = threading.Thread(target=watchdog, name='manual-watchdog', daemon=True)
                    manual_thread.start()
                    logging.getLogger('werkzeug').setLevel(logging.WARNING)
                if args.autonomous:
                    from autonomous import AutoPilot
                    pilot = AutoPilot(monitor, manual, capture)
                    monitor.pilot = pilot

                    def pilot_loop():
                        while not manual_stop.wait(.04):
                            pilot.tick()

                    pilot_thread = threading.Thread(target=pilot_loop, name='pilot', daemon=True)
                    pilot_thread.start()
                create_app(monitor, manual, capture, pilot).run(host=args.host, port=args.port, threaded=True,
                                        debug=False, use_reloader=False)
            finally:
                manual_stop.set()
                if manual:
                    manual.stop('shutdown')
                if pilot:
                    pilot.stop('shutdown')
                if pilot_thread:
                    pilot_thread.join(timeout=2)
                if manual_thread:
                    manual_thread.join(timeout=2)
                try:
                    if manual:
                        manual.close()
                finally:
                    try:
                        monitor.close()
                    finally:
                        capture.close()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
