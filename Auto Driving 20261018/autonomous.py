"""Opt-in OpenCV/P pilot with bounded trials or supervised continuous mode."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import math
import threading
import time

from media_capture import timestamp


@dataclass(frozen=True)
class PilotConfig:
    kp: float = 60
    max_angle: float = 20
    rate: float = 60
    speed: float = .26
    duration: float = 1
    heading_gain: float = .8
    continuous: bool = False
    curve_scale: float = .75

    def __post_init__(self):
        if type(self.continuous) is not bool:
            raise ValueError('continuous must be a boolean')
        limits = {'kp':(1, 120), 'max_angle':(5, 40), 'rate':(10, 120),
                  'speed':(.1, .30), 'duration':(.5, 3), 'heading_gain':(0, 2),
                  'curve_scale':(.4, .8)}
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{name} must be between {low} and {high}')


class AutoPilot:
    def __init__(self, monitor, control, store):
        self.monitor, self.control, self.store = monitor, control, store
        self.lock = threading.RLock()
        self.log_lock = threading.Lock()
        self.config = PilotConfig()
        self.active = False
        self.client = self.owner = None
        self.started = self.heartbeat_at = self.last_tick = 0
        self.last_frame = -1
        self.sequence = 0
        self.angle = 0
        self.reason = 'idle'
        self.error = None
        self.log = None
        self.last_log = None
        self.reference_reset = False
        self.space_checked_at = 0
        self.commanded_speed = None
        self.speed_target = 0
        self.speed_reason = 'stopped'
        self.straight_since = None

    def configure(self, values):
        with self.lock:
            if self.active:
                raise PermissionError('Stop the pilot before changing settings')
            if not isinstance(values, dict) or not values or set(values) - set(asdict(self.config)):
                raise ValueError('Unknown or empty pilot settings')
            self.config = replace(self.config, **values)

    def calibrate(self):
        with self.lock:
            if self.active or self.control.status()['armed']:
                raise PermissionError('Stop all motion before setting the central reference')
            self.store.check_space()
            reference = self.monitor.calibrate_path()
            path = self.store.root / 'runs' / ('reference_' + timestamp() + '.json')
            path.write_text(json.dumps({'reference':reference,
                                        'path':self.monitor.control_snapshot()['path'],
                                        'camera':self.monitor.status()['settings']}, indent=2))
            self.reference_reset = True
            self.angle = 0
            return reference

    def start(self, client):
        with self.lock:
            hardware = self.control.status()
            if self.active or hardware['armed']:
                raise PermissionError('Stop existing control before starting the pilot')
            frame = self.monitor.control_snapshot()
            if (frame['age'] is None or frame['age'] > .2 or not frame['path'].get('valid')
                    or not frame['path'].get('reference_set') or frame['streak'] < 3):
                raise ValueError('A fresh, stable path and central reference are required')
            if self.excessive_error(frame['path']):
                raise ValueError('Path error is too large without a corroborated curve corridor')
            if not hardware['motors_enabled']:
                raise ValueError('DC motors are not enabled')
            self.store.check_space()
            # After a fresh straight reference use neutral; otherwise resume
            # from the last command, not a fictional zero/measured wheel angle.
            initial_angle = 0 if self.reference_reset else hardware['angle']
            initial_angle = max(-self.config.max_angle, min(self.config.max_angle, initial_angle))
            self.owner = 'auto:' + client
            path = self.store.root / 'runs' / ('run_' + timestamp() + '.jsonl')
            try:
                self.log = path.open('w', encoding='utf-8')
                self.log.write(json.dumps({'event':'start', 'settings':asdict(self.config),
                                          'initial_angle':initial_angle,
                                          'reference':frame['path']['reference_normalized'],
                                          'timestamp_utc':datetime.now(timezone.utc).isoformat()}) + '\n')
                self.control.arm(self.owner)
                now = time.monotonic()
                if not self.config.continuous:
                    self.control.set_deadline(self.owner, now + self.config.duration)
            except Exception:
                self.control.stop(client=self.owner)
                if self.log:
                    self.log.close()
                self.log = None
                raise
            self.last_log = path.relative_to(self.store.root).as_posix()
            self.active = True
            self.client = client
            self.started = self.heartbeat_at = self.last_tick = now
            self.space_checked_at = now
            self.commanded_speed = None
            self.speed_target = 0
            self.speed_reason = 'stopped'
            self.straight_since = None
            self.sequence = 0
            self.last_frame = -1
            self.angle = float(initial_angle)
            self.reference_reset = False
            self.reason = 'running'
            self.error = None

    def heartbeat(self, client):
        with self.lock:
            if not self.active:
                return False
            if client != self.client:
                raise PermissionError('This browser does not own the pilot')
            self.heartbeat_at = time.monotonic()
            return True

    def stop(self, reason='operator_stop', observation=None):
        with self.lock:
            if self.owner:
                self.control.stop(client=self.owner, reason=reason)
            self.active = False
            self.commanded_speed = self.speed_target = 0
            self.speed_reason = 'stopped'
            self.straight_since = None
            self.reason = reason
            self.owner = self.client = None
            log, self.log = self.log, None
            observation = observation or self.monitor.control_snapshot()
            stopped_angle = self.angle
        diagnostic = None
        if log and reason in ('path_lost', 'path_error_large', 'pilot_error', 'camera_error'):
            try:
                pair = getattr(self.monitor, 'diagnostic_pair', lambda number:None)(observation['number'])
                if pair:
                    diagnostic = self.store.photo(*pair, dict(event='failure_frame', reason=reason,
                                                              observation=observation))
            except Exception as error:
                diagnostic = dict(error=f'{type(error).__name__}: {error}')
        with self.log_lock:
            if log:
                try:
                    log.write(json.dumps({'event':'stop', 'reason':reason, 'angle':stopped_angle,
                                          'observation':observation, 'diagnostic':diagnostic}) + '\n')
                finally:
                    log.close()

    def status(self):
        with self.lock:
            frame = self.monitor.control_snapshot()
            prediction = frame['path']
            error = prediction.get('normalized_error')
            preview = None if error is None else self.wanted_angle(prediction)
            blocked = ('path_invalid' if not prediction.get('valid') else
                       ('reference_on_straight' if abs(prediction.get('heading_degrees', 0)) > 12 else
                        'reference_required') if not prediction.get('reference_set') else
                       'path_stale' if frame['age'] is None or frame['age'] > .2 else
                       'path_unstable' if frame['streak'] < 3 else
                       'path_error_large' if self.excessive_error(prediction) else None)
            return dict(available=True, active=self.active, client=self.client,
                        reason=self.reason, error=self.error, settings=asdict(self.config),
                        steering=self.angle, predicted_angle=preview,
                        commanded_speed=self.commanded_speed or 0,
                        speed_target=self.speed_target, speed_reason=self.speed_reason,
                        remaining=(None if self.config.continuous else
                                   max(0, round(self.config.duration - (time.monotonic() - self.started), 2))) if self.active else 0,
                        reference_set=prediction.get('reference_set', False),
                        blocked_reason=blocked, last_log=self.last_log)

    @staticmethod
    def excessive_error(path):
        return (abs(path['normalized_error']) > .55 and
                not (path.get('curve_corridor_supported') and abs(path['normalized_error']) <= 1.05))

    def wanted_angle(self, path):
        wanted = (self.config.kp * path['normalized_error'] +
                  self.config.heading_gain * path.get('heading_error_degrees', 0))
        return max(-self.config.max_angle, min(self.config.max_angle, wanted))

    def update_speed(self, path, wanted, now):
        """Brake on current turn evidence; only accelerate after a stable straight."""
        heading = abs(path.get('heading_error_degrees', 0))
        steering = max(abs(wanted), abs(self.angle))
        scale = max(0, min(1, path.get('speed_scale', 1)))
        weak_path = (scale <= .8 or path.get('source') == 'dash_boundary' or
                     path.get('curve_corridor_supported', False))
        turning = heading >= 8 or steering >= 6
        if turning or weak_path:
            self.straight_since = None
            severity = min(1, max(heading / 45, steering / self.config.max_angle))
            scale = min(scale, .8 - (.8 - self.config.curve_scale) * severity)
            if weak_path:
                scale = min(scale, self.config.curve_scale)
            reason = 'curve' if turning else 'limited_path'
        else:
            if heading < 5 and steering < 4 and scale >= .99:
                if self.straight_since is None:
                    self.straight_since = now
            else:
                self.straight_since = None
            reason = 'base_output'
        target = max(.1, self.config.speed * scale)
        current = self.commanded_speed
        if current is None or target <= current:
            current = target
        elif self.straight_since is not None and now - self.straight_since >= .7:
            current = min(target, current + .04 * min(now - self.last_tick, .1))
            reason = 'accelerating'
        else:
            reason = 'curve_hold' if turning or weak_path else 'straight_wait'
        self.commanded_speed = float(current)
        self.speed_target, self.speed_reason = float(target), reason
        return self.commanded_speed

    def tick(self):
        record = log = None
        try:
            with self.lock:
                if not self.active:
                    return
                now = time.monotonic()
                hardware = self.control.status()
                if not self.config.continuous and now - self.started >= self.config.duration:
                    self.stop('time_limit')
                    return
                if not hardware['armed'] or hardware['owner'] != self.owner:
                    self.stop(hardware['reason'])
                    return
                if now - self.heartbeat_at > .7:
                    self.stop('browser_timeout')
                    return
                frame = self.monitor.control_snapshot()
                path = frame['path']
                if (frame['age'] is None or frame['age'] > .2 or not path.get('valid')
                        or not path.get('reference_set')):
                    self.stop('path_lost', frame)
                    return
                if self.excessive_error(path):
                    self.stop('path_error_large', frame)
                    return
                if now - self.space_checked_at >= 1:
                    try:
                        self.store.check_space()
                    except OSError as error:
                        self.error = f'{type(error).__name__}: {error}'
                        self.stop('storage_error', frame)
                        return
                    self.space_checked_at = now
                if frame['number'] == self.last_frame:
                    return
                wanted = self.wanted_angle(path)
                change = self.config.rate * min(now - self.last_tick, .1)
                self.angle = float(max(self.angle - change, min(self.angle + change, wanted)))
                self.sequence += 1
                speed = self.update_speed(path, wanted, now)
                self.control.follow(self.owner, self.sequence, self.angle, speed)
                interval = now - self.last_tick
                self.last_tick = now
                self.last_frame = frame['number']
                record = dict(event='frame', t=round(now - self.started, 4), frame=frame['number'],
                              path=path, wanted_angle=wanted, commanded_angle=self.angle, speed=speed,
                              speed_target=self.speed_target, speed_reason=self.speed_reason,
                              frame_age_seconds=frame['age'], control_interval=round(interval,4),
                              motor_outputs=self.control.status()['motor_outputs'])
                log = self.log
            with self.log_lock:
                if log and not log.closed:
                    log.write(json.dumps(record) + '\n')
        except Exception as error:
            self.error = f'{type(error).__name__}: {error}'
            self.stop('pilot_error')
