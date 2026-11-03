"""Web dashboard for inspecting OpenCV lane detection and P-control on a Pi."""

from __future__ import annotations

import argparse
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from motor_module import DEFAULT_MOTOR_PINS, MotorController
from road_drive_p_control import (
    LaneDetector,
    RoadPController,
    load_vision_dependencies,
    parse_pin_pair,
)


PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Pi4 Lane Monitor</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #111315; color: #f2f4f5; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 14px 18px; background: #1b1e21; border-bottom: 1px solid #353a3f; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
      gap: 16px; max-width: 1200px; margin: 0 auto; padding: 16px; }
    .video { width: 100%; aspect-ratio: 4 / 3; object-fit: contain; display: block;
      background: #050505; border: 1px solid #353a3f; }
    .panel { display: grid; gap: 12px; align-content: start; }
    .status { padding: 12px; border: 1px solid #353a3f; background: #1b1e21; border-radius: 6px; }
    .status h2 { margin: 0 0 10px; font-size: 14px; font-weight: 650; color: #bcc3c8; }
    dl { margin: 0; display: grid; grid-template-columns: 1fr auto; gap: 8px 14px; font-size: 14px; }
    dt { color: #aeb5ba; } dd { margin: 0; font-variant-numeric: tabular-nums; }
    .badge { display: inline-flex; align-items: center; min-height: 28px; padding: 4px 9px;
      border-radius: 5px; font-size: 13px; font-weight: 700; background: #3b4146; }
    .ok { background: #17683c; color: #eafff1; } .bad { background: #8a2930; color: #fff0f1; }
    .idle { background: #4b5055; color: #fff; }
    .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    button { min-height: 42px; border: 0; border-radius: 5px; font-size: 14px;
      font-weight: 700; cursor: pointer; }
    #start { background: #2f9e62; color: #071d11; } #stop { background: #d94b54; color: #fff; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    .error { min-height: 20px; color: #ff949b; font-size: 13px; overflow-wrap: anywhere; }
    .legend { color: #9fa7ac; font-size: 12px; line-height: 1.5; }
    @media (max-width: 760px) { main { grid-template-columns: 1fr; padding: 10px; } header { padding: 12px; } }
  </style>
</head>
<body>
  <header><h1>Pi4 Lane Monitor</h1><span id="laneBadge" class="badge idle">WAITING</span></header>
  <main>
    <section><img class="video" src="/video_feed" alt="Lane detection stream"></section>
    <aside class="panel">
      <section class="status">
        <h2>Recognition</h2>
        <dl>
          <dt>Camera</dt><dd id="camera">-</dd>
          <dt>Lane state</dt><dd id="lane">-</dd>
          <dt>Center error</dt><dd id="errorValue">-</dd>
          <dt>Filtered error</dt><dd id="filtered">-</dd>
          <dt>Turn correction</dt><dd id="turn">-</dd>
          <dt>Frame rate</dt><dd id="fps">-</dd>
        </dl>
      </section>
      <section class="status">
        <h2>P-control output</h2>
        <dl>
          <dt>Planned left</dt><dd id="plannedLeft">-</dd>
          <dt>Planned right</dt><dd id="plannedRight">-</dd>
          <dt>Motor left</dt><dd id="motorLeft">-</dd>
          <dt>Motor right</dt><dd id="motorRight">-</dd>
          <dt>Reason</dt><dd id="reason">-</dd>
        </dl>
      </section>
      <section class="status">
        <h2>Motor control</h2>
        <div class="controls">
          <button id="start" onclick="motor('start')">Start driving</button>
          <button id="stop" onclick="motor('stop')">Stop</button>
        </div>
      </section>
      <div id="runtimeError" class="error"></div>
      <div class="legend">Blue: camera center &nbsp; Green: detected road center<br>Top-right inset: threshold mask used for detection</div>
    </aside>
  </main>
  <script>
    const ids = ['camera','lane','errorValue','filtered','turn','fps','plannedLeft',
      'plannedRight','motorLeft','motorRight','reason'];
    const el = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
    const fmt = value => value === null || value === undefined ? '-' : Number(value).toFixed(3);
    async function motor(action) {
      try { await fetch('/api/motors/' + action, {method: 'POST'}); await refresh(); }
      catch (error) { document.getElementById('runtimeError').textContent = error; }
    }
    async function refresh() {
      try {
        const response = await fetch('/api/status', {cache: 'no-store'});
        const s = await response.json();
        el.camera.textContent = s.camera_online ? 'online' : 'waiting';
        el.lane.textContent = s.lane_status;
        el.errorValue.textContent = fmt(s.error);
        el.filtered.textContent = fmt(s.filtered_error);
        el.turn.textContent = fmt(s.turn);
        el.fps.textContent = fmt(s.fps);
        el.plannedLeft.textContent = fmt(s.planned_left_pwm);
        el.plannedRight.textContent = fmt(s.planned_right_pwm);
        el.motorLeft.textContent = fmt(s.actual_left_pwm);
        el.motorRight.textContent = fmt(s.actual_right_pwm);
        el.reason.textContent = s.reason;
        document.getElementById('runtimeError').textContent = s.error_message || '';
        const badge = document.getElementById('laneBadge');
        badge.textContent = s.lane_visible ? 'LANE FOUND' : 'LANE LOST';
        badge.className = 'badge ' + (s.lane_visible ? 'ok' : 'bad');
        document.getElementById('start').disabled = !s.camera_online || !s.lane_visible || s.motor_enabled || s.dry_run;
        document.getElementById('stop').disabled = !s.motor_enabled;
      } catch (error) {
        document.getElementById('runtimeError').textContent = 'Dashboard connection lost';
      }
    }
    setInterval(refresh, 300); refresh();
  </script>
</body>
</html>"""


class RpicamMjpegCamera:
    def __init__(self, width: int, height: int, fps: int) -> None:
        self.process = subprocess.Popen(
            [
                "rpicam-vid", "--codec", "mjpeg", "--inline",
                "--width", str(width), "--height", str(height),
                "--framerate", str(fps), "--timeout", "0", "--nopreview",
                "--output", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self) -> None:
        if self.process.stdout is None:
            return
        buffer = bytearray()
        while self.running:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                if self.process.poll() is not None:
                    break
                time.sleep(0.01)
                continue
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2)
                if start < 0 or end < 0:
                    if start > 0:
                        del buffer[:start]
                    break
                jpeg = bytes(buffer[start : end + 2])
                del buffer[: end + 2]
                frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    with self.lock:
                        self.latest_frame = frame

    def read(self):
        with self.lock:
            return None if self.latest_frame is None else self.latest_frame.copy()

    def stop(self) -> None:
        self.running = False
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.thread.join(timeout=1.0)


class OpenCvCamera:
    def __init__(self, index: int, width: int, height: int, fps: int) -> None:
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        if not self.cap.isOpened():
            raise RuntimeError(f"OpenCV camera index {index} is not available")

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def stop(self) -> None:
        self.cap.release()


def rotate_frame(frame, rotation: int):
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


class LaneWebRuntime:
    def __init__(self, args) -> None:
        self.args = args
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.latest_jpeg: Optional[bytes] = None
        self.motor_enabled = False
        self.reset_requested = False
        self.last_client_seen = time.monotonic()
        self.status = {
            "camera_online": False,
            "lane_visible": False,
            "lane_status": "waiting",
            "error": None,
            "filtered_error": 0.0,
            "turn": 0.0,
            "fps": 0.0,
            "planned_left_pwm": 0.0,
            "planned_right_pwm": 0.0,
            "actual_left_pwm": 0.0,
            "actual_right_pwm": 0.0,
            "motor_enabled": False,
            "dry_run": args.dry_run,
            "reason": "starting",
            "error_message": "",
        }
        self.thread = threading.Thread(target=self._run, name="lane-web-runtime", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def snapshot(self):
        with self.lock:
            self.last_client_seen = time.monotonic()
            return dict(self.status)

    def set_motor_enabled(self, enabled: bool) -> bool:
        with self.lock:
            if enabled and (self.args.dry_run or not self.status["lane_visible"]):
                return False
            self.last_client_seen = time.monotonic()
            self.motor_enabled = enabled
            self.reset_requested = enabled
            self.status["motor_enabled"] = enabled
            if not enabled:
                self.status["actual_left_pwm"] = 0.0
                self.status["actual_right_pwm"] = 0.0
            return True

    def jpeg_stream(self):
        while not self.stop_event.is_set():
            with self.lock:
                jpeg = self.latest_jpeg
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(1.0 / max(1, self.args.web_fps))

    def close(self) -> None:
        self.set_motor_enabled(False)
        self.stop_event.set()
        self.thread.join(timeout=4.0)

    def _camera(self):
        if self.args.camera == "opencv":
            return OpenCvCamera(self.args.camera_index, self.args.width, self.args.height, self.args.fps)
        return RpicamMjpegCamera(self.args.width, self.args.height, self.args.fps)

    def _motors(self):
        return MotorController(
            motor_pins={
                1: self.args.motor1_pins,
                2: self.args.motor2_pins,
                3: self.args.motor3_pins,
                4: self.args.motor4_pins,
            },
            left_motors=(3, 4),
            right_motors=(1, 2),
            dry_run=self.args.dry_run,
            invert_left_pins=self.args.invert_left_pins,
            invert_right_pins=self.args.invert_right_pins,
        )

    def _run(self) -> None:
        camera = None
        motors = None
        try:
            camera = self._camera()
            motors = self._motors()
            detector = LaneDetector(
                self.args.mode,
                self.args.crop_top_ratio,
                self.args.crop_bottom_ratio,
                self.args.threshold,
                self.args.min_area,
                self.args.lane_half_width,
                self.args.min_lane_gap,
            )
            controller = RoadPController(
                self.args.base_speed,
                self.args.min_speed,
                self.args.max_speed,
                self.args.kp,
                self.args.max_turn,
                self.args.slowdown,
                self.args.error_window,
                self.args.pwm_alpha,
                self.args.pwm_step,
                self.args.lost_frame_limit,
                self.args.invert_steering,
            )
            last_frame_time = time.monotonic()
            fps_value = 0.0

            while not self.stop_event.is_set():
                frame = camera.read()
                if frame is None:
                    motors.stop()
                    time.sleep(0.02)
                    continue
                frame = rotate_frame(frame, self.args.rotation)

                now = time.monotonic()
                instant_fps = 1.0 / max(0.001, now - last_frame_time)
                fps_value = instant_fps if fps_value == 0 else 0.15 * instant_fps + 0.85 * fps_value
                last_frame_time = now

                lane = detector.process(frame)
                with self.lock:
                    reset_requested = self.reset_requested
                    self.reset_requested = False
                    enabled = self.motor_enabled
                    timed_out_while_driving = enabled and now - self.last_client_seen > 2.0
                    if timed_out_while_driving:
                        enabled = False
                        self.motor_enabled = False
                if reset_requested:
                    controller.reset()
                output = controller.update(lane)

                if enabled and lane.visible and not output.stop:
                    motors.set(output.left_pwm, output.right_pwm)
                    if self.args.dry_run:
                        actual_left = 0.0
                        actual_right = 0.0
                    else:
                        actual_left = output.left_pwm
                        actual_right = output.right_pwm
                else:
                    actual_left = 0.0
                    actual_right = 0.0
                    motors.stop()

                annotated = lane.debug_frame
                state_text = "DRY RUN" if self.args.dry_run else ("DRIVING" if enabled else "MONITOR ONLY")
                state_color = (40, 210, 110) if enabled else (0, 190, 255)
                cv2.rectangle(annotated, (0, annotated.shape[0] - 30), (annotated.shape[1], annotated.shape[0]), (20, 20, 20), -1)
                cv2.putText(
                    annotated,
                    f"{state_text}  err={lane.error if lane.error is not None else '-'}  L={actual_left:.2f} R={actual_right:.2f}",
                    (7, annotated.shape[0] - 9),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.46,
                    state_color,
                    1,
                    cv2.LINE_AA,
                )
                ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, self.args.jpeg_quality])

                with self.lock:
                    if ok:
                        self.latest_jpeg = encoded.tobytes()
                    self.status.update(
                        camera_online=True,
                        lane_visible=lane.visible,
                        lane_status=lane.status,
                        error=lane.error,
                        filtered_error=output.filtered_error,
                        turn=output.turn,
                        fps=fps_value,
                        planned_left_pwm=output.left_pwm,
                        planned_right_pwm=output.right_pwm,
                        actual_left_pwm=actual_left,
                        actual_right_pwm=actual_right,
                        motor_enabled=enabled,
                        reason="dashboard_timeout" if timed_out_while_driving else output.reason,
                        error_message="",
                    )
                time.sleep(1.0 / max(1, self.args.fps))
        except BaseException as exc:
            with self.lock:
                self.motor_enabled = False
                self.status.update(
                    camera_online=False,
                    motor_enabled=False,
                    actual_left_pwm=0.0,
                    actual_right_pwm=0.0,
                    reason="runtime_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
        finally:
            if motors is not None:
                motors.cleanup()
            if camera is not None:
                camera.stop()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--camera", choices=["rpicam", "opencv"], default="rpicam")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--rotation", type=int, choices=[0, 90, 180, 270], default=0)
    parser.add_argument("--web-fps", type=int, default=10)
    parser.add_argument("--jpeg-quality", type=int, default=80)
    parser.add_argument("--dry-run", action="store_true")

    parser.add_argument("--mode", choices=["auto", "center-line", "lane-borders"], default="auto")
    parser.add_argument("--crop-top-ratio", type=float, default=0.45)
    parser.add_argument("--crop-bottom-ratio", type=float, default=0.98)
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--min-area", type=int, default=50)
    parser.add_argument("--lane-half-width", type=int, default=70)
    parser.add_argument("--min-lane-gap", type=int, default=55)

    parser.add_argument("--base-speed", type=float, default=0.40)
    parser.add_argument("--min-speed", type=float, default=0.32)
    parser.add_argument("--max-speed", type=float, default=0.55)
    parser.add_argument("--kp", type=float, default=0.0035)
    parser.add_argument("--max-turn", type=float, default=0.22)
    parser.add_argument("--slowdown", type=float, default=0.55)
    parser.add_argument("--error-window", type=int, default=5)
    parser.add_argument("--pwm-alpha", type=float, default=0.45)
    parser.add_argument("--pwm-step", type=float, default=0.04)
    parser.add_argument("--lost-frame-limit", type=int, default=4)
    parser.add_argument("--invert-steering", action="store_true")

    parser.add_argument("--motor1-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[1])
    parser.add_argument("--motor2-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[2])
    parser.add_argument("--motor3-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[3])
    parser.add_argument("--motor4-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[4])
    parser.add_argument("--invert-left-pins", action="store_true")
    parser.add_argument("--invert-right-pins", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        from flask import Flask, Response, jsonify
    except ModuleNotFoundError as exc:
        raise SystemExit("Flask is not installed. Run: sudo apt install -y python3-flask") from exc

    args = parse_args()
    load_vision_dependencies()
    runtime = LaneWebRuntime(args)
    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/video_feed")
    def video_feed():
        return Response(runtime.jpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/status")
    def status():
        return jsonify(runtime.snapshot())

    @app.post("/api/motors/start")
    def start_motors():
        accepted = runtime.set_motor_enabled(True)
        return jsonify({"ok": accepted}), 200 if accepted else 409

    @app.post("/api/motors/stop")
    def stop_motors():
        runtime.set_motor_enabled(False)
        return jsonify({"ok": True})

    def stop_runtime(*_):
        runtime.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_runtime)
    runtime.start()
    print(f"Lane monitor: http://<pi-ip>:{args.port}")
    print("Motors remain stopped until Start driving is pressed.")
    try:
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
