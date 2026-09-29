"""Dataset-model driving and live Flask monitoring in one camera process."""

from __future__ import annotations

import argparse
import signal
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from dataset_model import DriveabilityModel, LearnedSteeringModel, extract_steering_features
from lane_heading import VideoTurnAssist, estimate_lane_heading
from motor_module import DEFAULT_MOTOR_PINS, DEFAULT_MOTOR_TRIM, MotorController
from road_drive_p_control import LaneDetector, load_vision_dependencies
from road_surface import VisionGate
from road_drive_dataset import (
    LowPass,
    OpenCvCamera,
    RateLimiter,
    RpicamMjpegCamera,
    parse_pin_pair,
    postprocess_pwm,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STEERING_MODEL = SCRIPT_DIR / "models" / "steering_v2.npz"
DEFAULT_SAFETY_MODEL = SCRIPT_DIR / "models" / "driveability_v1.npz"


PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Dataset Driving Monitor</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #111315; color: #f2f4f5; }
    header { display: flex; justify-content: space-between; align-items: center; gap: 14px;
      padding: 14px 18px; background: #1b1e21; border-bottom: 1px solid #353a3f; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(0, 2fr) minmax(270px, 1fr);
      gap: 16px; max-width: 1200px; margin: 0 auto; padding: 16px; }
    .video { width: 100%; aspect-ratio: 4 / 3; object-fit: contain; display: block;
      background: #050505; border: 1px solid #353a3f; }
    .view-switch { display: inline-grid; grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 2px; margin-bottom: 8px; padding: 2px; background: #353a3f; border-radius: 5px; }
    .view-switch button { min-height: 34px; padding: 0 12px; background: transparent; color: #c4cbd0; }
    .view-switch button[aria-pressed="true"] { background: #596b52; color: #fff; }
    .panel { display: grid; gap: 12px; align-content: start; }
    .box { padding: 12px; border: 1px solid #353a3f; background: #1b1e21; border-radius: 6px; }
    .box h2 { margin: 0 0 10px; font-size: 14px; color: #bcc3c8; }
    dl { margin: 0; display: grid; grid-template-columns: 1fr auto; gap: 8px 14px; font-size: 14px; }
    dt { color: #aeb5ba; } dd { margin: 0; font-variant-numeric: tabular-nums; }
    .badge { display: inline-flex; align-items: center; min-height: 28px; padding: 4px 9px;
      border-radius: 5px; font-size: 13px; font-weight: 700; background: #4b5055; }
    .ok { background: #17683c; color: #eafff1; }
    .warn { background: #8a651d; color: #fff8dc; }
    .bad { background: #8a2930; color: #fff0f1; }
    .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .manual-pad { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-template-areas: ". forward ." "left stop right" ". backward ."; gap: 8px;
      touch-action: none; user-select: none; }
    button { min-height: 42px; border: 0; border-radius: 5px; font-size: 14px;
      font-weight: 700; cursor: pointer; }
    #start { background: #2f9e62; color: #071d11; }
    #stopAll { background: #d94b54; color: #fff; grid-area: stop; }
    .manual { background: #3f474d; color: #fff; touch-action: none; }
    .manual:active { background: #2f9e62; color: #071d11; }
    [data-direction="forward"] { grid-area: forward; }
    [data-direction="backward"] { grid-area: backward; }
    [data-direction="left"] { grid-area: left; }
    [data-direction="right"] { grid-area: right; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    .error { min-height: 20px; color: #ff949b; font-size: 13px; overflow-wrap: anywhere; }
    .legend { color: #9fa7ac; font-size: 12px; line-height: 1.5; }
    @media (max-width: 760px) { main { grid-template-columns: 1fr; padding: 10px; } header { padding: 12px; } }
  </style>
</head>
<body>
  <header><h1>Dataset Driving Monitor</h1><span id="badge" class="badge">WAITING</span></header>
  <main>
    <section>
      <div class="view-switch" role="group" aria-label="Camera view">
        <button id="modelView" aria-pressed="true" onclick="setView('model')">Model</button>
        <button id="laneView" aria-pressed="false" onclick="setView('lane')">OpenCV</button>
      </div>
      <img id="cameraStream" class="video" src="/video_feed" alt="Dataset driving stream">
    </section>
    <aside class="panel">
      <section class="box">
        <h2>Model recognition</h2>
        <dl>
          <dt>Camera</dt><dd id="camera">-</dd>
          <dt>Safety state</dt><dd id="safety">-</dd>
          <dt>Driveability</dt><dd id="score">-</dd>
          <dt>Threshold</dt><dd id="threshold">-</dd>
          <dt>Frame rate</dt><dd id="fps">-</dd>
          <dt>OpenCV lane</dt><dd id="laneStatus">-</dd>
          <dt>Lane center error</dt><dd id="laneError">-</dd>
          <dt>Road surface</dt><dd id="surfaceState">-</dd>
          <dt>Track near / far</dt><dd id="surfaceFraction">-</dd>
          <dt>Vision gate</dt><dd id="visionGate">-</dd>
          <dt>Line heading</dt><dd id="lineHeading">-</dd>
          <dt>Turn assist</dt><dd id="turnAssist">-</dd>
        </dl>
      </section>
      <section class="box">
        <h2>Dataset model output</h2>
        <dl>
          <dt>Model left</dt><dd id="modelLeft">-</dd>
          <dt>Model right</dt><dd id="modelRight">-</dd>
          <dt>Steering error</dt><dd id="steeringError">-</dd>
          <dt>Drive phase</dt><dd id="drivePhase">-</dd>
          <dt>Planned left</dt><dd id="plannedLeft">-</dd>
          <dt>Planned right</dt><dd id="plannedRight">-</dd>
          <dt>Motor left</dt><dd id="motorLeft">-</dd>
          <dt>Motor right</dt><dd id="motorRight">-</dd>
          <dt>Command</dt><dd id="command">-</dd>
        </dl>
      </section>
      <section class="box">
        <h2>Autonomous control</h2>
        <div class="controls">
          <button id="start" onclick="motor('start')">Start driving</button>
          <button onclick="stopAll()">Stop</button>
        </div>
      </section>
      <section class="box">
        <h2>Manual control (hold)</h2>
        <div class="manual-pad">
          <button class="manual" data-direction="forward" aria-keyshortcuts="W">Forward</button>
          <button class="manual" data-direction="left" aria-keyshortcuts="A">Left</button>
          <button id="stopAll" onclick="stopAll()">Stop</button>
          <button class="manual" data-direction="right" aria-keyshortcuts="D">Right</button>
          <button class="manual" data-direction="backward" aria-keyshortcuts="S">Backward</button>
        </div>
      </section>
      <div id="runtimeError" class="error"></div>
      <div id="legend" class="legend">Yellow box: model crop area<br>Top-right inset: image features supplied to the steering model</div>
    </aside>
  </main>
  <script>
    const get = id => document.getElementById(id);
    const fmt = value => value === null || value === undefined ? '-' : Number(value).toFixed(3);
    const keyDirections = {w: 'forward', a: 'left', s: 'backward', d: 'right'};
    let manualTimer = null;
    let manualDirection = null;
    function setView(view) {
      const lane = view === 'lane';
      get('modelView').setAttribute('aria-pressed', String(!lane));
      get('laneView').setAttribute('aria-pressed', String(lane));
      get('cameraStream').src = lane ? '/lane_feed' : '/video_feed';
      get('cameraStream').alt = lane ? 'OpenCV lane detection stream' : 'Dataset driving stream';
      get('legend').innerHTML = lane
        ? 'Blue: camera center &nbsp; Green: detected road center<br>Top-right inset: threshold mask'
        : 'Yellow box: model crop area<br>Top-right inset: image features supplied to the steering model';
    }
    async function motor(action) {
      try {
        const response = await fetch('/api/motors/' + action, {method: 'POST'});
        if (!response.ok) throw new Error('Driving rejected: road is not confirmed driveable');
        await refresh();
      } catch (error) { get('runtimeError').textContent = error.message; }
    }
    async function manualPulse(direction) {
      try {
        const response = await fetch('/api/manual/' + direction, {method: 'POST', keepalive: true});
        if (!response.ok) throw new Error('Manual control rejected');
      } catch (error) { get('runtimeError').textContent = error.message; }
    }
    function beginManual(direction, event) {
      event.preventDefault();
      if (manualDirection === direction) return;
      endManual();
      manualDirection = direction;
      manualPulse(direction);
      manualTimer = setInterval(() => manualPulse(direction), 200);
    }
    function endManual(event, direction) {
      if (event) event.preventDefault();
      if (direction && manualDirection !== direction) return;
      if (manualTimer !== null) {
        clearInterval(manualTimer);
        manualTimer = null;
        manualDirection = null;
        fetch('/api/manual/stop', {method: 'POST', keepalive: true});
      }
    }
    function stopAll() {
      endManual();
      motor('stop');
    }
    async function refresh() {
      try {
        const s = await (await fetch('/api/status', {cache: 'no-store'})).json();
        get('camera').textContent = s.camera_online ? 'online' : 'waiting';
        get('safety').textContent = s.safety_state;
        get('score').textContent = fmt(s.driveability_score);
        get('threshold').textContent = fmt(s.driveability_threshold);
        get('fps').textContent = fmt(s.fps);
        get('laneStatus').textContent = s.opencv_lane_status;
        get('laneError').textContent = fmt(s.opencv_lane_error);
        get('surfaceState').textContent = s.road_surface;
        get('surfaceFraction').textContent = fmt(s.surface_near) + ' / ' + fmt(s.surface_far);
        get('visionGate').textContent = s.vision_gate;
        get('lineHeading').textContent = fmt(s.vision_heading);
        get('turnAssist').textContent = s.vision_turn;
        get('modelLeft').textContent = fmt(s.model_left_pwm);
        get('modelRight').textContent = fmt(s.model_right_pwm);
        get('steeringError').textContent = fmt(s.steering_error);
        get('drivePhase').textContent = s.drive_phase;
        get('plannedLeft').textContent = fmt(s.planned_left_pwm);
        get('plannedRight').textContent = fmt(s.planned_right_pwm);
        get('motorLeft').textContent = fmt(s.actual_left_pwm);
        get('motorRight').textContent = fmt(s.actual_right_pwm);
        get('command').textContent = s.command;
        get('runtimeError').textContent = s.error_message || '';
        const badge = get('badge');
        const driveable = s.safety_state === 'driveable' || s.safety_state === 'disabled';
        const visionFault = s.command.startsWith('vision_') && s.command !== 'vision_wait';
        badge.textContent = s.manual_active ? 'MANUAL ' + s.manual_direction.toUpperCase()
          : (s.motor_enabled ? (s.drive_phase === 'paused' ? 'PAUSED' : 'DRIVING')
            : (visionFault ? 'VISION STOP' : s.safety_state.toUpperCase()));
        badge.className = 'badge ' + (visionFault ? 'bad' : (s.drive_phase === 'paused' ? 'warn' : ((s.manual_active || driveable) ? 'ok'
          : (s.safety_state === 'uncertain' ? 'warn' : 'bad'))));
        const laneReady = s.opencv_lane_error !== null && Math.abs(s.opencv_lane_error) <= 40;
        get('start').disabled = !s.camera_online || !driveable || !laneReady || s.vision_gate !== 'ready' || s.motor_enabled || s.manual_active || s.dry_run;
        document.querySelectorAll('.manual').forEach(button => {
          button.disabled = !s.camera_online || s.motor_enabled || s.dry_run;
        });
        get('stopAll').disabled = !s.motor_enabled && !s.manual_active;
      } catch (error) { get('runtimeError').textContent = 'Dashboard connection lost'; }
    }
    document.querySelectorAll('.manual').forEach(button => {
      button.addEventListener('pointerdown', event => beginManual(button.dataset.direction, event));
      button.addEventListener('pointerup', endManual);
      button.addEventListener('pointercancel', endManual);
      button.addEventListener('pointerleave', endManual);
    });
    document.addEventListener('keydown', event => {
      const direction = keyDirections[event.key.toLowerCase()];
      if (!direction || event.repeat) return;
      beginManual(direction, event);
    });
    document.addEventListener('keyup', event => {
      const direction = keyDirections[event.key.toLowerCase()];
      if (direction) endManual(event, direction);
    });
    window.addEventListener('blur', endManual);
    document.addEventListener('visibilitychange', () => { if (document.hidden) endManual(); });
    setInterval(refresh, 300); refresh();
  </script>
</body>
</html>"""


def rotate_frame(frame, rotation: int):
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def draw_model_preview(frame, steering_model, status):
    preview = frame.copy()
    height, width = preview.shape[:2]
    crop_y1 = min(55, height - 1)
    crop_y2 = min(230, height)
    cv2.rectangle(preview, (0, crop_y1), (width - 1, crop_y2 - 1), (0, 210, 255), 1)

    features = extract_steering_features(
        frame,
        steering_model.image_width,
        steering_model.image_height,
        steering_model.feature_mode,
    )
    feature_image = (features.reshape(steering_model.image_height, steering_model.image_width) * 255).astype(np.uint8)
    inset_width = max(96, width // 3)
    inset_height = max(60, height // 3)
    inset = cv2.resize(feature_image, (inset_width, inset_height), interpolation=cv2.INTER_NEAREST)
    preview[0:inset_height, width - inset_width : width] = cv2.cvtColor(inset, cv2.COLOR_GRAY2BGR)

    if status["manual_active"]:
        state = f"MANUAL {status['manual_direction'].upper()}"
    else:
        state = "DRIVING" if status["motor_enabled"] else ("DRY RUN" if status["dry_run"] else "MONITOR")
    color = (50, 220, 110) if status["motor_enabled"] or status["manual_active"] else (0, 200, 255)
    cv2.rectangle(preview, (0, height - 42), (width, height), (20, 20, 20), -1)
    cv2.putText(
        preview,
        f"{state} safety={status['safety_state']} score={status['driveability_score']:.2f}",
        (7, height - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.43, color, 1, cv2.LINE_AA,
    )
    cv2.putText(
        preview,
        f"model L={status['model_left_pwm']:.2f} R={status['model_right_pwm']:.2f}  motor L={status['actual_left_pwm']:.2f} R={status['actual_right_pwm']:.2f}",
        (7, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA,
    )
    return preview


class TurnDecision:
    def __init__(self, enter_threshold: float, exit_threshold: float, straight_frames: int,
                 enter_frames: int = 1) -> None:
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.straight_frames = straight_frames
        self.enter_frames = enter_frames
        self.direction: Optional[str] = None
        self.candidate: Optional[str] = None
        self.candidate_frames = 0
        self.aligned_frames = 0
        self.opposite_frames = 0

    def reset(self) -> None:
        self.direction = None
        self.candidate = None
        self.candidate_frames = 0
        self.aligned_frames = 0
        self.opposite_frames = 0

    def update(self, steering_error: float) -> Optional[str]:
        if self.direction is None:
            if abs(steering_error) >= self.enter_threshold:
                candidate = "left" if steering_error > 0 else "right"
                self.candidate_frames = self.candidate_frames + 1 if self.candidate == candidate else 1
                self.candidate = candidate
                if self.candidate_frames >= self.enter_frames:
                    self.direction = candidate
            else:
                self.candidate = None
                self.candidate_frames = 0
            return self.direction

        if abs(steering_error) <= self.exit_threshold:
            self.aligned_frames += 1
            self.opposite_frames = 0
            if self.aligned_frames >= self.straight_frames:
                self.reset()
        else:
            self.aligned_frames = 0
            opposite = (steering_error < -self.enter_threshold if self.direction == "left"
                        else steering_error > self.enter_threshold)
            self.opposite_frames = self.opposite_frames + 1 if opposite else 0
            if self.opposite_frames >= 3:
                self.direction = "right" if self.direction == "left" else "left"
                self.opposite_frames = 0
        return self.direction


class DatasetWebRuntime:
    def __init__(self, args) -> None:
        self.args = args
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.latest_jpeg: Optional[bytes] = None
        self.latest_lane_jpeg: Optional[bytes] = None
        self.motor_enabled = False
        self.fault_reason = ""
        self.fault_command = ""
        self.manual_direction: Optional[str] = None
        self.manual_deadline = 0.0
        self.reset_requested = False
        self.last_client_seen = time.monotonic()
        self.status = {
            "camera_online": False,
            "safety_state": "waiting",
            "driveability_score": 0.0,
            "driveability_threshold": 0.0,
            "fps": 0.0,
            "opencv_lane_status": "waiting",
            "opencv_lane_error": None,
            "road_surface": "waiting",
            "surface_near": 0.0,
            "surface_far": 0.0,
            "vision_gate": "waiting",
            "vision_heading": None,
            "vision_turn": "off" if not getattr(args, "video_turn_assist", False) else "waiting",
            "model_left_pwm": 0.0,
            "model_right_pwm": 0.0,
            "steering_error": 0.0,
            "drive_phase": "stopped",
            "planned_left_pwm": 0.0,
            "planned_right_pwm": 0.0,
            "actual_left_pwm": 0.0,
            "actual_right_pwm": 0.0,
            "motor_enabled": False,
            "manual_active": False,
            "manual_direction": "",
            "dry_run": args.dry_run,
            "command": "starting",
            "error_message": "",
        }
        self.thread = threading.Thread(target=self._run, name="dataset-web-runtime", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def snapshot(self):
        with self.lock:
            self.last_client_seen = time.monotonic()
            return dict(self.status)

    def set_motor_enabled(self, enabled: bool) -> bool:
        with self.lock:
            driveable = self.status["safety_state"] in {"driveable", "disabled"}
            if enabled and (self.args.dry_run or not self.status["camera_online"] or not driveable):
                return False
            lane_error = self.status["opencv_lane_error"]
            if enabled and (lane_error is None or abs(lane_error) > 40
                            or self.status["vision_gate"] != "ready"):
                return False
            self.last_client_seen = time.monotonic()
            if enabled:
                self.fault_reason = ""
                self.fault_command = ""
                self.status["error_message"] = ""
                self.manual_direction = None
                self.manual_deadline = 0.0
                self.status["manual_active"] = False
                self.status["manual_direction"] = ""
            self.motor_enabled = enabled
            self.reset_requested = enabled
            self.status["motor_enabled"] = enabled
            if not enabled:
                self.status["actual_left_pwm"] = 0.0
                self.status["actual_right_pwm"] = 0.0
            return True

    def set_manual(self, direction: str) -> bool:
        if direction not in {"forward", "backward", "left", "right"}:
            return False
        with self.lock:
            if self.args.dry_run or not self.status["camera_online"]:
                return False
            direction_changed = direction != self.manual_direction
            self.motor_enabled = False
            self.manual_direction = direction
            self.manual_deadline = time.monotonic() + 0.6
            self.reset_requested = self.reset_requested or direction_changed
            self.status.update(
                motor_enabled=False,
                manual_active=True,
                manual_direction=direction,
                command=f"manual_{direction}",
            )
            return True

    def stop_all(self) -> None:
        with self.lock:
            self.motor_enabled = False
            self.manual_direction = None
            self.manual_deadline = 0.0
            self.reset_requested = True
            self.status.update(
                motor_enabled=False,
                manual_active=False,
                manual_direction="",
                actual_left_pwm=0.0,
                actual_right_pwm=0.0,
                command="stopped",
            )

    def jpeg_stream(self, lane_view: bool = False):
        while not self.stop_event.is_set():
            with self.lock:
                jpeg = self.latest_lane_jpeg if lane_view else self.latest_jpeg
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(1.0 / max(1, self.args.web_fps))

    def close(self) -> None:
        self.stop_all()
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
            motor_trim={
                1: self.args.motor1_trim,
                2: self.args.motor2_trim,
                3: self.args.motor3_trim,
                4: self.args.motor4_trim,
            },
            left_motors=(3, 4),
            right_motors=(1, 2),
            dry_run=self.args.dry_run,
            invert_left_pins=self.args.invert_left_pins,
            invert_right_pins=self.args.invert_right_pins,
        )

    def _apply_turn(self, motors, direction: str, speed: float):
        speed = max(0.0, min(1.0, speed))
        left_speed = speed * self.args.left_motor_scale
        right_speed = speed * self.args.right_motor_scale
        if direction == "left":
            motors.stop((motors.left_motors[0],))
            motors.backward((motors.left_motors[1],), left_speed, direct_pwm=True)
            motors.forward(motors.right_motors, right_speed, direct_pwm=True)
            return -left_speed / 2.0, right_speed
        motors.forward(motors.left_motors, left_speed, direct_pwm=True)
        motors.stop((motors.right_motors[0],))
        motors.backward((motors.right_motors[1],), right_speed, direct_pwm=True)
        return left_speed, -right_speed / 2.0

    def _apply_manual(self, motors, direction: str):
        speed = max(0.0, min(1.0, self.args.manual_speed))
        if direction in {"left", "right"}:
            return self._apply_turn(motors, direction, self.args.turn_speed)
        left_speed = speed * self.args.left_motor_scale
        right_speed = speed * self.args.right_motor_scale
        if direction == "forward":
            motors.set_side_pwm(left_speed, right_speed)
            return left_speed, right_speed
        motors.backward(motors.left_motors, left_speed, direct_pwm=True)
        motors.backward(motors.right_motors, right_speed, direct_pwm=True)
        return -left_speed, -right_speed

    def _apply_forward(self, motors, planned_left: float, planned_right: float,
                       lane_error: Optional[float] = None):
        forward_pwm = (planned_left + planned_right) / 2.0
        turn = 0.0 if lane_error is None else max(
            -self.args.lane_max_correction,
            min(self.args.lane_max_correction, self.args.lane_kp * lane_error),
        )
        left_pwm = max(0.0, min(self.args.max_pwm, forward_pwm - turn)) * self.args.left_motor_scale
        right_pwm = max(0.0, min(self.args.max_pwm, forward_pwm + turn)) * self.args.right_motor_scale
        motors.set_side_pwm(left_pwm, right_pwm)
        return left_pwm, right_pwm

    def _run(self) -> None:
        camera = None
        motors = None
        try:
            steering_model = LearnedSteeringModel(self.args.model)
            safety_model = None if self.args.no_safety else DriveabilityModel(self.args.safety_model)
            load_vision_dependencies()
            lane_detector = LaneDetector(
                self.args.lane_mode, 0.45, 0.98, self.args.lane_threshold,
                50, 70, 55,
            )
            camera = self._camera()
            motors = self._motors()
            pwm_filter = LowPass(self.args.pwm_alpha)
            pwm_limiter = RateLimiter(self.args.pwm_step)
            turn_decision = TurnDecision(
                self.args.turn_enter_threshold,
                self.args.turn_exit_threshold,
                self.args.turn_straight_frames,
                self.args.turn_enter_frames,
            )
            video_assist = VideoTurnAssist()
            vision_gate = VisionGate(self.args.road_surface, self.args.lane_loss_limit)
            turn_started = 0.0
            resume_until = 0.0
            was_waiting = False
            unsafe_frames = 0
            camera_started = time.monotonic()
            last_frame_time = camera_started
            last_lane_time = 0.0
            lane_status = "waiting"
            lane_error = None
            filtered_lane_error = None
            vision_state = "waiting"
            vision_heading = None
            fps_value = 0.0

            while not self.stop_event.is_set():
                frame = camera.read()
                if frame is None:
                    motors.stop()
                    process = getattr(camera, "process", None)
                    if process is not None and process.poll() is not None and time.monotonic() - camera_started > 2.0:
                        raise RuntimeError("Pi camera stopped. Another process may be using it.")
                    time.sleep(0.02)
                    continue
                frame = rotate_frame(frame, self.args.rotation)

                now = time.monotonic()
                instant_fps = 1.0 / max(0.001, now - last_frame_time)
                fps_value = instant_fps if fps_value == 0 else 0.15 * instant_fps + 0.85 * fps_value
                last_frame_time = now

                if safety_model is None:
                    score = 1.0
                    threshold = 0.0
                    safety_state = "disabled"
                else:
                    score = safety_model.predict_probability(frame)
                    threshold = safety_model.threshold
                    if score >= threshold:
                        unsafe_frames = 0
                        safety_state = "driveable"
                    else:
                        unsafe_frames += 1
                        safety_state = "unsafe" if unsafe_frames >= self.args.unsafe_frame_limit else "uncertain"

                model_left, model_right = steering_model.predict(frame)
                lane_jpeg = None
                if now - last_lane_time >= 1.0 / max(1, self.args.lane_fps):
                    lane = lane_detector.process(frame)
                    lane_status = lane.status
                    lane_error = lane.error
                    vision_state = vision_gate.update(frame, lane.visible)
                    if lane.visible and lane.error is not None:
                        filtered_lane_error = (lane.error if filtered_lane_error is None else
                                               0.5 * lane.error + 0.5 * filtered_lane_error)
                    else:
                        filtered_lane_error = None
                    if self.args.video_turn_assist:
                        vision_heading = estimate_lane_heading(frame)
                        video_assist.observe(vision_heading)
                    last_lane_time = now
                    lane_ok, lane_encoded = cv2.imencode(
                        ".jpg", lane.debug_frame, [cv2.IMWRITE_JPEG_QUALITY, self.args.jpeg_quality]
                    )
                    if lane_ok:
                        lane_jpeg = lane_encoded.tobytes()
                with self.lock:
                    reset_requested = self.reset_requested
                    self.reset_requested = False
                    enabled = self.motor_enabled
                    manual_direction = self.manual_direction
                    manual_timed_out = manual_direction is not None and now > self.manual_deadline
                    if manual_timed_out:
                        manual_direction = None
                        self.manual_direction = None
                    timed_out = enabled and now - self.last_client_seen > 2.0
                    if timed_out:
                        enabled = False
                        self.motor_enabled = False
                if reset_requested:
                    pwm_filter.reset()
                    pwm_limiter.reset()
                    turn_decision.reset()
                    video_assist.reset()
                    filtered_lane_error = None
                    resume_until = now + self.args.resume_seconds
                    was_waiting = False

                if safety_state == "unsafe":
                    pwm_filter.reset()
                    pwm_limiter.reset()
                    turn_decision.reset()
                    video_assist.reset()
                    filtered_lane_error = None
                    planned_left = 0.0
                    planned_right = 0.0
                    command = "safety_stop"
                else:
                    planned_left, planned_right = postprocess_pwm(model_left, model_right, self.args)
                    planned_left, planned_right = pwm_filter.update(planned_left, planned_right)
                    planned_left, planned_right = pwm_limiter.update(planned_left, planned_right)
                    command = "dataset_model"

                steering_error = planned_right - planned_left
                control_error, vision_conflict = (
                    video_assist.control_error(steering_error, self.args.turn_enter_threshold)
                    if self.args.video_turn_assist else (steering_error, False)
                )
                if lane_status == "both_edges" and video_assist.direction is None:
                    turn_decision.reset()
                    control_error = 0.0
                if manual_direction is not None and not self.args.dry_run:
                    turn_decision.reset()
                    video_assist.reset()
                    actual_left, actual_right = self._apply_manual(motors, manual_direction)
                    command = f"manual_{manual_direction}"
                    drive_phase = f"manual_{manual_direction}"
                elif enabled and vision_state in {"off_track", "surface_timeout", "lane_timeout"}:
                    motors.stop()
                    turn_decision.reset()
                    video_assist.reset()
                    with self.lock:
                        self.motor_enabled = False
                        self.fault_reason = f"Vision gate: {vision_state}. Driving stopped."
                        self.fault_command = f"vision_{vision_state}"
                    enabled = False
                    actual_left = actual_right = 0.0
                    command = self.fault_command
                    drive_phase = "stopped"
                elif enabled and vision_state != "ready":
                    motors.stop()
                    turn_decision.reset()
                    video_assist.reset()
                    filtered_lane_error = None
                    was_waiting = True
                    actual_left = actual_right = 0.0
                    command = "vision_wait"
                    drive_phase = "paused"
                elif enabled and vision_conflict:
                    motors.stop()
                    turn_decision.reset()
                    video_assist.reset()
                    with self.lock:
                        self.motor_enabled = False
                        self.fault_reason = "Model and road-line turn directions disagree. Driving stopped."
                        self.fault_command = "vision_conflict"
                    enabled = False
                    actual_left = actual_right = 0.0
                    command = "vision_conflict"
                    drive_phase = "stopped"
                elif enabled and safety_state != "unsafe" and not self.args.dry_run:
                    if was_waiting:
                        resume_until = now + self.args.resume_seconds
                        was_waiting = False
                    previous_direction = turn_decision.direction
                    turn_direction = turn_decision.update(control_error)
                    if turn_direction is not None:
                        if previous_direction != turn_direction:
                            motors.stop()
                        if previous_direction is None:
                            turn_started = now
                        if now - turn_started > self.args.max_turn_seconds:
                            motors.stop()
                            turn_decision.reset()
                            with self.lock:
                                self.motor_enabled = False
                            enabled = False
                            actual_left = actual_right = 0.0
                            command = "turn_timeout"
                            drive_phase = "stopped"
                        else:
                            actual_left, actual_right = self._apply_turn(
                                motors, turn_direction,
                                min(self.args.turn_speed, self.args.resume_speed)
                                if now < resume_until else self.args.turn_speed,
                            )
                            command = f"auto_turn_{turn_direction}"
                            drive_phase = f"turn_{turn_direction}"
                    else:
                        if previous_direction is not None:
                            motors.stop()
                        base = (planned_left + planned_right) / 2.0
                        if now < resume_until:
                            base = min(base, self.args.resume_speed)
                        actual_left, actual_right = self._apply_forward(
                            motors, base, base,
                            filtered_lane_error if lane_status == "both_edges" else None,
                        )
                        command = "auto_forward_recovery" if now < resume_until else "auto_forward"
                        drive_phase = "forward"
                else:
                    turn_decision.reset()
                    actual_left = 0.0
                    actual_right = 0.0
                    motors.stop()
                    drive_phase = "stopped"
                    if self.fault_reason:
                        command = self.fault_command

                frame_status = {
                    "motor_enabled": enabled,
                    "manual_active": manual_direction is not None,
                    "manual_direction": manual_direction or "",
                    "dry_run": self.args.dry_run,
                    "safety_state": safety_state,
                    "driveability_score": score,
                    "model_left_pwm": model_left,
                    "model_right_pwm": model_right,
                    "actual_left_pwm": actual_left,
                    "actual_right_pwm": actual_right,
                }
                annotated = draw_model_preview(frame, steering_model, frame_status)
                ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, self.args.jpeg_quality])

                with self.lock:
                    if ok:
                        self.latest_jpeg = encoded.tobytes()
                    if lane_jpeg is not None:
                        self.latest_lane_jpeg = lane_jpeg
                    self.status.update(
                        camera_online=True,
                        opencv_lane_status=lane_status,
                        opencv_lane_error=lane_error,
                        road_surface=vision_gate.surface.reading.state,
                        surface_near=vision_gate.surface.reading.near_fraction,
                        surface_far=vision_gate.surface.reading.far_fraction,
                        vision_gate=vision_state,
                        vision_heading=vision_heading,
                        vision_turn=(video_assist.direction or "none") if self.args.video_turn_assist else "off",
                        safety_state=safety_state,
                        driveability_score=score,
                        driveability_threshold=threshold,
                        fps=fps_value,
                        model_left_pwm=model_left,
                        model_right_pwm=model_right,
                        steering_error=steering_error,
                        drive_phase=drive_phase,
                        planned_left_pwm=planned_left,
                        planned_right_pwm=planned_right,
                        actual_left_pwm=actual_left,
                        actual_right_pwm=actual_right,
                        motor_enabled=enabled,
                        manual_active=manual_direction is not None,
                        manual_direction=manual_direction or "",
                        command=("manual_timeout" if manual_timed_out else
                                 ("dashboard_timeout" if timed_out else command)),
                        error_message=self.fault_reason,
                    )
                time.sleep(1.0 / max(1, self.args.fps))
        except BaseException as exc:
            with self.lock:
                self.motor_enabled = False
                self.manual_direction = None
                self.status.update(
                    camera_online=False,
                    motor_enabled=False,
                    manual_active=False,
                    manual_direction="",
                    actual_left_pwm=0.0,
                    actual_right_pwm=0.0,
                    command="runtime_error",
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
    parser.add_argument("--model", type=Path, default=DEFAULT_STEERING_MODEL)
    parser.add_argument("--safety-model", type=Path, default=DEFAULT_SAFETY_MODEL)
    parser.add_argument("--no-safety", action="store_true")
    parser.add_argument("--unsafe-frame-limit", type=int, default=8)
    parser.add_argument("--camera", choices=["rpicam", "opencv"], default="rpicam")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--rotation", type=int, choices=[0, 90, 180, 270], default=180)
    parser.add_argument("--web-fps", type=int, default=10)
    parser.add_argument("--jpeg-quality", type=int, default=80)
    parser.add_argument("--lane-mode", choices=["auto", "center-line", "lane-borders"], default="auto")
    parser.add_argument("--lane-threshold", type=int, default=150)
    parser.add_argument("--lane-fps", type=int, default=5)
    parser.add_argument("--video-turn-assist", action="store_true")
    parser.add_argument("--no-video-turn-assist", action="store_false", dest="video_turn_assist")
    parser.set_defaults(video_turn_assist=True)
    parser.add_argument("--lane-loss-limit", type=int, default=10)
    parser.add_argument("--road-surface", choices=["white", "black"], default="white")
    parser.add_argument("--resume-seconds", type=float, default=1.0)
    parser.add_argument("--resume-speed", type=float, default=0.34)
    parser.add_argument("--lane-kp", type=float, default=0.0025)
    parser.add_argument("--lane-max-correction", type=float, default=0.07)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manual-speed", type=float, default=0.38)
    parser.add_argument("--left-motor-scale", type=float, default=1.0)
    parser.add_argument("--right-motor-scale", type=float, default=0.90)
    parser.add_argument("--turn-speed", type=float, default=0.48)
    parser.add_argument("--turn-enter-threshold", type=float, default=0.10)
    parser.add_argument("--turn-enter-frames", type=int, default=3)
    parser.add_argument("--turn-exit-threshold", type=float, default=0.04)
    parser.add_argument("--turn-straight-frames", type=int, default=4)
    parser.add_argument("--max-turn-seconds", type=float, default=4.0)

    parser.add_argument("--speed-scale", type=float, default=1.07)
    parser.add_argument("--steering-scale", type=float, default=1.0)
    parser.add_argument("--min-forward-pwm", type=float, default=0.34)
    parser.add_argument("--max-pwm", type=float, default=0.58)
    parser.add_argument("--pwm-alpha", type=float, default=0.65)
    parser.add_argument("--pwm-step", type=float, default=0.08)
    parser.add_argument("--invert-steering", action="store_true")

    parser.add_argument("--motor1-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[1])
    parser.add_argument("--motor2-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[2])
    parser.add_argument("--motor3-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[3])
    parser.add_argument("--motor4-pins", type=parse_pin_pair, default=DEFAULT_MOTOR_PINS[4])
    parser.add_argument("--motor1-trim", type=float, default=DEFAULT_MOTOR_TRIM[1])
    parser.add_argument("--motor2-trim", type=float, default=DEFAULT_MOTOR_TRIM[2])
    parser.add_argument("--motor3-trim", type=float, default=DEFAULT_MOTOR_TRIM[3])
    parser.add_argument("--motor4-trim", type=float, default=DEFAULT_MOTOR_TRIM[4])
    parser.add_argument("--invert-left-pins", action="store_true")
    parser.add_argument("--invert-right-pins", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        from flask import Flask, Response, jsonify
    except ModuleNotFoundError as exc:
        raise SystemExit("Flask is not installed. Run: sudo apt install -y python3-flask") from exc

    args = parse_args()
    if not (0 <= args.turn_exit_threshold < args.turn_enter_threshold <= 1):
        raise SystemExit("turn thresholds must satisfy 0 <= exit < enter <= 1")
    if (args.turn_straight_frames < 1 or args.turn_enter_frames < 1 or args.lane_loss_limit < 1
            or args.max_turn_seconds <= 0 or not (0 < args.turn_speed <= 1)):
        raise SystemExit("turn frames, timeout, and speed must be positive")
    if args.lane_kp < 0 or not (0 <= args.lane_max_correction <= 1):
        raise SystemExit("lane P-control gain and maximum correction must be nonnegative")
    if args.resume_seconds < 0 or not (0 < args.resume_speed <= 1):
        raise SystemExit("recovery duration and speed must be positive")
    if not args.model.exists():
        raise SystemExit(f"steering model not found: {args.model}")
    if not args.no_safety and not args.safety_model.exists():
        raise SystemExit(f"safety model not found: {args.safety_model}")

    runtime = DatasetWebRuntime(args)
    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/video_feed")
    def video_feed():
        return Response(runtime.jpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/lane_feed")
    def lane_feed():
        return Response(runtime.jpeg_stream(lane_view=True), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/status")
    def status():
        return jsonify(runtime.snapshot())

    @app.post("/api/motors/start")
    def start_motors():
        accepted = runtime.set_motor_enabled(True)
        return jsonify({"ok": accepted}), 200 if accepted else 409

    @app.post("/api/motors/stop")
    def stop_motors():
        runtime.stop_all()
        return jsonify({"ok": True})

    @app.post("/api/manual/<direction>")
    def manual_control(direction):
        if direction == "stop":
            runtime.stop_all()
            return jsonify({"ok": True})
        accepted = runtime.set_manual(direction)
        return jsonify({"ok": accepted}), 200 if accepted else 409

    def stop_runtime(*_):
        runtime.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_runtime)
    runtime.start()
    print(f"Dataset driving monitor: http://<pi-ip>:{args.port}")
    print("One camera process supplies both model inference and the web stream.")
    print("Motors remain stopped until Start driving is pressed.")
    try:
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
