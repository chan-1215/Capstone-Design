"""Servo-only A/D test. Run on the Pi, then open http://PI_IP:5002."""

import logging
import math
import threading
import time

from flask import Flask, jsonify, request


SERVO_PIN = 18  # BCM GPIO18 = header pin 12; verify the new wiring first.
CENTER_ANGLE = 0
A_ANGLE = -105
D_ANGLE = 85
ANGLE_MIN = -120  # Software test limits, NOT verified mechanical travel limits.
ANGLE_MAX = 120
MIN_PULSE_WIDTH = 0.001  # Existing calibration at -90 command degrees.
MAX_PULSE_WIDTH = 0.002  # Existing calibration at +90 command degrees.
PORT = 5002
RELEASE_TIMEOUT = 1.5  # Tolerate short network stalls; center on a lost connection.
SIGNAL_SECONDS = 0.7  # Move briefly, then release PWM as in steering_keys.py.


def servo_parameters():
    angles = (ANGLE_MIN, ANGLE_MAX, CENTER_ANGLE, A_ANGLE, D_ANGLE)
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in angles):
        raise ValueError('Angles must be finite numbers')
    if ANGLE_MIN >= ANGLE_MAX or any(
        not ANGLE_MIN <= angle <= ANGLE_MAX
        for angle in (CENTER_ANGLE, A_ANGLE, D_ANGLE)
    ):
        raise ValueError(f'Angles must be between {ANGLE_MIN} and {ANGLE_MAX}; '
                         'adjust ANGLE_MIN / ANGLE_MAX only after checking travel')
    # Extending the command range must not shift 0 or rescale existing movements.
    slope = (MAX_PULSE_WIDTH - MIN_PULSE_WIDTH) / 180
    neutral = (MIN_PULSE_WIDTH + MAX_PULSE_WIDTH) / 2
    minimum = neutral + ANGLE_MIN * slope
    maximum = neutral + ANGLE_MAX * slope
    if not 0 < minimum < maximum < 0.02:
        raise ValueError('Invalid pulse calibration or command limits')
    return dict(min_angle=ANGLE_MIN, max_angle=ANGLE_MAX,
                min_pulse_width=minimum, max_pulse_width=maximum)


PAGE = """<!doctype html>
<html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Servo A/D</title>
<style>
body{background:#101314;color:#eee;font:20px system-ui;margin:40px}
output{display:block;font-size:36px;margin:24px 0}
button{font:inherit;padding:12px 24px;background:#993535;color:white;border:0}
</style>
<h1>Servo A/D</h1><output id="angle">0&deg;</output>
<button id="center" type="button">0&deg;</button>
<script>
const held = new Set();
const client = crypto.randomUUID ? crypto.randomUUID() :
  Date.now().toString(36) + Math.random().toString(36).slice(2);
let sequence = 0, sending = false, pending = false;
const keyName = e => ({KeyA:'a', KeyD:'d'})[e.code];
const clear = () => { held.clear(); update(); };
window.addEventListener('keydown', e => {
  const key = keyName(e);
  if (key) {
    e.preventDefault();
    if (!e.repeat && !held.has(key)) { held.add(key); update(); }
  }
  if (e.code === 'Escape' || e.code === 'Space') {
    e.preventDefault(); clear();
  }
});
window.addEventListener('keyup', e => {
  if (held.delete(keyName(e))) update();
});
window.addEventListener('blur', clear);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) clear();
});
document.getElementById('center').onclick = clear;
window.addEventListener('pagehide', () => {
  held.clear();
  navigator.sendBeacon('/keys', new Blob([
    JSON.stringify({a:false, d:false, client, sequence:++sequence})
  ], {type:'application/json'}));
});
async function update() {
  pending = true;
  if (sending) return;
  sending = true;
  do {
    pending = false;
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 800);
    try {
      const response = await fetch('/keys', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({a:held.has('a'), d:held.has('d'),
          client, sequence:++sequence}), signal:abort.signal
      });
      if (!response.ok) throw new Error(response.status);
      const state = await response.json();
      document.getElementById('angle').textContent = state.angle + '\u00b0';
    } catch (_) {
      // A transient network error is not a physical key release.
      document.getElementById('angle').textContent = 'Disconnected';
    } finally {
      clearTimeout(timer);
    }
  } while (pending);
  sending = false;
}
setInterval(update, 100);
update();
</script></html>"""


class ServoControl:
    def __init__(self, servo):
        self.servo = servo
        self.lock = threading.Lock()
        self.angle = None
        self.signal_until = None
        self.last_update = time.monotonic()
        self.owner = None
        self.last_sequence = -1
        self._set_angle(CENTER_ANGLE)

    def _set_angle(self, angle):
        if self.angle != angle:
            self.servo.angle = angle
            self.angle = angle
            self.signal_until = time.monotonic() + SIGNAL_SECONDS
            print(f'Target: {angle:+g} degrees', flush=True)

    def update(self, a, d, client, sequence):
        with self.lock:
            angle = CENTER_ANGLE if a == d else A_ANGLE if a else D_ANGLE
            # Idle tabs must not center the servo controlled by another tab.
            if client != self.owner:
                if angle == CENTER_ANGLE or self.angle != CENTER_ANGLE:
                    return self.angle
                self.owner = client
                self.last_sequence = -1
            if sequence <= self.last_sequence:
                return self.angle
            self.last_sequence = sequence
            self._set_angle(angle)
            self.last_update = time.monotonic()
            return self.angle

    def check_timeout(self):
        with self.lock:
            now = time.monotonic()
            if now - self.last_update > RELEASE_TIMEOUT:
                self._set_angle(CENTER_ANGLE)
            if self.signal_until is not None and now >= self.signal_until:
                self.servo.detach()
                self.signal_until = None
                print('PWM off', flush=True)


def create_app(control):
    app = Flask(__name__)

    @app.get('/')
    def index():
        return PAGE

    @app.post('/keys')
    def keys():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or any(
            type(data.get(key)) is not bool for key in ('a', 'd')
        ) or not isinstance(data.get('client'), str) or not (
            1 <= len(data['client']) <= 100
        ) or type(data.get('sequence')) is not int or not (
            0 <= data['sequence'] <= 9007199254740991
        ):
            return jsonify(error='Expected a, d, client and sequence'), 400
        return jsonify(angle=control.update(
            data['a'], data['d'], data['client'], data['sequence']
        ))

    return app


def main():
    from gpiozero import AngularServo
    from gpiozero.pins.lgpio import LGPIOFactory

    parameters = servo_parameters()

    factory = LGPIOFactory()
    servo = None
    stopped = threading.Event()
    worker = None
    try:
        servo = AngularServo(
            SERVO_PIN, initial_angle=None, pin_factory=factory, **parameters,
        )
        control = ServoControl(servo)

        def watchdog():
            while not stopped.wait(0.04):
                control.check_timeout()

        worker = threading.Thread(target=watchdog, daemon=True)
        worker.start()
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        print(f'A={A_ANGLE}, D={D_ANGLE}, released={CENTER_ANGLE}; port {PORT}')
        create_app(control).run(host='0.0.0.0', port=PORT, use_reloader=False)
    finally:
        stopped.set()
        if worker is not None:
            worker.join()
        if servo is not None:
            try:
                servo.angle = CENTER_ANGLE
                time.sleep(SIGNAL_SECONDS)
            finally:
                servo.detach()
                servo.close()
        factory.close()


if __name__ == '__main__':
    main()
