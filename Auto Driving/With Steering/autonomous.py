"""Opt-in OpenCV/P pilot with bounded trials or supervised continuous mode."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time

from media_capture import timestamp
from turn_recovery import TurnRecovery
from interaction import CrossingGate


def steering_step(angle, wanted, rate, interval, fast_unwind=False):
    target = wanted
    if fast_unwind and angle != 0 and (angle*wanted < 0 or abs(wanted) < abs(angle)):
        rate = min(120., 2*rate)
        # Opposite bends first unwind to neutral; never jump across zero.
        if angle*wanted < 0:
            target = 0.
    change = rate*max(0., min(interval,.1))
    return float(max(angle-change,min(angle+change,target)))


@dataclass(frozen=True)
class PilotConfig:
    kp: float = 60
    max_left_angle: float = 105
    max_right_angle: float = 85
    rate: float = 60
    speed: float = .26
    duration: float = 1
    heading_gain: float = .8
    continuous: bool = False
    curve_scale: float = .85
    turn_recovery: bool = False
    crosswalk_gesture: bool = False
    lap_mode: bool = False
    boundary_guidance: bool = False

    def __post_init__(self):
        if type(self.continuous) is not bool:
            raise ValueError('continuous must be a boolean')
        if type(self.turn_recovery) is not bool:
            raise ValueError('turn_recovery must be a boolean')
        if type(self.crosswalk_gesture) is not bool:
            raise ValueError('crosswalk_gesture must be a boolean')
        if type(self.lap_mode) is not bool:
            raise ValueError('lap_mode must be a boolean')
        if type(self.boundary_guidance) is not bool:
            raise ValueError('boundary_guidance must be a boolean')
        if self.lap_mode and not self.continuous:
            raise ValueError('Lap mode requires supervised continuous mode')
        if self.crosswalk_gesture and not self.continuous:
            raise ValueError('Crosswalk gestures require supervised continuous mode')
        limits = {'kp':(1, 120), 'max_left_angle':(5, 105),
                  'max_right_angle':(5, 85), 'rate':(10, 120),
                  'speed':(.1, .30), 'duration':(.5, 3), 'heading_gain':(0, 2),
                  'curve_scale':(.75, 1)}
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{name} must be between {low} and {high}')
        if self.boundary_guidance and (not self.lap_mode or self.heading_gain < .25):
            raise ValueError('Boundary guidance requires lap mode and heading_gain >= 0.25')


class AutoPilot:
    def __init__(self, monitor, control, store):
        self.monitor, self.control, self.store = monitor, control, store
        self.lock = threading.RLock()
        self.log_lock = threading.Lock()
        self.config = PilotConfig(max_left_angle=min(105, -control.config.a_angle),
                                  max_right_angle=min(85, control.config.d_angle))
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
        self.resume_angle = None
        self.space_checked_at = 0
        self.commanded_speed = None
        self.speed_target = 0
        self.speed_reason = 'stopped'
        self.turn_direction = 'straight'
        self.straight_since = None
        self.straight_frames = 0
        self.recovery = TurnRecovery()
        self.crossing = CrossingGate()

    def gesture_ready(self):
        worker = getattr(self.monitor, 'gesture', None)
        status = worker.snapshot() if worker else {}
        return bool(status.get('initialized') and not status.get('error'))

    def configure(self, values):
        with self.lock:
            if self.active:
                raise PermissionError('Stop the pilot before changing settings')
            if not isinstance(values, dict) or not values or set(values) - set(asdict(self.config)):
                raise ValueError('Unknown or empty pilot settings')
            config = replace(self.config, **values)
            if config.crosswalk_gesture and not self.gesture_ready():
                raise ValueError('Start with --gesture and wait for gesture initialization')
            if (config.max_left_angle > -self.control.config.a_angle or
                    config.max_right_angle > self.control.config.d_angle):
                raise ValueError('Pilot limits must stay within the hardware steering limits')
            self.config = config

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
            self.resume_angle = None
            self.angle = 0
            return reference

    def restore_reference(self, reference_name, stopped_run):
        """Explicit same-camera resume; saved calibration never authorizes motion."""
        with self.lock:
            if self.active or self.control.status()['armed']:
                raise PermissionError('Stop all motion before restoring a reference')
            if not self.config.lap_mode:
                raise ValueError('Reference resume requires explicit lap mode')
            directory=(self.store.root/'runs').resolve()
            def saved(name,prefix,suffix):
                if (not isinstance(name,str) or Path(name).name!=name or
                        not name.startswith(prefix) or not name.endswith(suffix)):
                    raise ValueError('Invalid saved calibration or run name')
                path=(directory/name).resolve()
                if (path.parent!=directory or not path.is_file() or
                        not 0<=time.time()-path.stat().st_mtime<=7200 or
                        path.stat().st_size>32*1024*1024):
                    raise ValueError('Resume evidence is missing, old or outside the run directory')
                return path
            reference_file=saved(reference_name,'reference_','.json')
            run_file=saved(stopped_run,'run_','.jsonl')
            record=json.loads(reference_file.read_text(encoding='utf-8'))
            status=self.monitor.status()
            source=record.get('path',{})
            reference=record.get('reference')
            heading=source.get('reference_heading_degrees')
            if (record.get('camera')!=status['settings'] or
                    status.get('original_size')!=[960,720] or
                    type(reference) not in (int,float) or not math.isfinite(reference) or
                    not .05<=reference<=.95 or source.get('target_normalized')!=reference or
                    not source.get('valid') or source.get('source')!='dash_chain' or
                    source.get('observed_dash_count',0)<3 or
                    source.get('target_y_normalized')!=.55 or
                    type(heading) not in (int,float) or not math.isfinite(heading) or abs(heading)>12):
                raise ValueError('Saved straight reference does not match the current camera')
            with run_file.open(encoding='utf-8') as handle:
                first=json.loads(next(handle))
                last=first
                for line in handle:
                    if line.strip():last=json.loads(line)
            angle=last.get('angle')
            if (first.get('event')!='start' or first.get('reference')!=reference or
                    not first.get('settings',{}).get('lap_mode') or last.get('event')!='stop' or
                    type(angle) not in (int,float) or not math.isfinite(angle) or
                    not -self.config.max_left_angle<=angle<=self.config.max_right_angle):
                raise ValueError('A matching completed stop log and bounded last command are required')
            self.monitor.restore_path_reference(reference,heading)
            self.reference_reset=False
            self.resume_angle=self.angle=float(angle)
            self.reason='reference_restored'
            return reference

    def start(self, client):
        with self.lock:
            hardware = self.control.status()
            if self.active or hardware['armed']:
                raise PermissionError('Stop existing control before starting the pilot')
            frame = self.monitor.control_snapshot()
            if self.config.crosswalk_gesture and not self.gesture_ready():
                raise ValueError('Gesture engine is unavailable')
            if self.config.crosswalk_gesture and not frame.get('crosswalk', {}).get('reliable', True):
                raise ValueError('Crosswalk observation is unavailable')
            if (frame['age'] is None or frame['age'] > .2 or not frame['path'].get('valid')
                    or not frame['path'].get('reference_set') or frame['streak'] < 3
                    or not self.path_mode_matches(frame['path'])):
                raise ValueError('A fresh, stable path and central reference are required')
            if self.excessive_error(frame['path']):
                raise ValueError('Path error is too large without a corroborated curve corridor')
            if not hardware['motors_enabled']:
                raise ValueError('DC motors are not enabled')
            self.store.check_space()
            # After a fresh straight reference use neutral; otherwise resume
            # from the last command, not a fictional zero/measured wheel angle.
            initial_angle = (0 if self.reference_reset else self.resume_angle
                             if self.resume_angle is not None and hardware['reason']=='disabled'
                             else hardware['angle'])
            initial_angle = max(-self.config.max_left_angle,
                                min(self.config.max_right_angle, initial_angle))
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
            self.turn_direction = 'straight'
            self.straight_since = None
            self.straight_frames = 0
            self.recovery.reset()
            self.crossing.reset()
            self.sequence = 0
            self.last_frame = -1
            self.angle = float(initial_angle)
            self.reference_reset = False
            self.resume_angle = None
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
            self.turn_direction = 'straight'
            self.straight_since = None
            self.straight_frames = 0
            self.recovery.reset()
            self.crossing.reset()
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
                                                              observation=observation), lossless_raw=True)
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
            if not self.path_mode_matches(prediction):
                blocked = 'settings_changed'
            if self.config.crosswalk_gesture and not frame.get('crosswalk',{}).get('reliable',True):
                blocked = 'crosswalk_unavailable'
            if self.config.crosswalk_gesture and not self.gesture_ready():
                blocked = 'gesture_unavailable'
            return dict(available=True, active=self.active, client=self.client,
                        reason=self.reason, error=self.error, settings=asdict(self.config),
                        steering=self.angle, predicted_angle=preview,
                        commanded_speed=self.commanded_speed or 0,
                        speed_target=self.speed_target, speed_reason=self.speed_reason,
                        turn_direction=self.turn_direction, straight_frames=self.straight_frames,
                        recovery_active=self.recovery.active,
                        interaction=self.crossing.status(),
                        gesture_available=self.gesture_ready(),
                        remaining=(None if self.config.continuous else
                                   max(0, round(self.config.duration - (time.monotonic() - self.started), 2))) if self.active else 0,
                        reference_set=prediction.get('reference_set', False),
                        blocked_reason=blocked, last_log=self.last_log)

    def path_mode_matches(self, path):
        return path.get('boundary_guidance_enabled', False) == self.config.boundary_guidance

    def excessive_error(self, path):
        return (abs(path['normalized_error']) > .55 and
                not ((path.get('curve_corridor_supported') or
                      self.config.lap_mode and path.get('lap_corridor_supported'))
                     and abs(path['normalized_error']) <= 1.05))

    def wanted_angle(self, path):
        error = path['normalized_error']
        if self.config.lap_mode:
            error = math.copysign(max(0.,abs(error)-.12),error)
        heading = path.get('heading_error_degrees', 0)
        guided = self.config.boundary_guidance and 'guidance_heading_error_degrees' in path
        if guided:
            heading = path['guidance_heading_error_degrees']
        lateral = self.config.kp * error
        direction = self.config.heading_gain * heading
        if guided and path.get('boundary_turn_agreement') and abs(heading) >= 20 and lateral*direction < 0:
            # Confirmed bend direction must not be cancelled by look-ahead
            # lateral offset on the other side of the camera centre.
            lateral = math.copysign(min(abs(lateral), .5*abs(direction)), lateral)
        wanted = lateral + direction
        return max(-self.config.max_left_angle, min(self.config.max_right_angle, wanted))

    def update_speed(self, path):
        """Latch turn slowdown until fresh straight evidence persists; never freeze steering."""
        now = time.monotonic()
        heading = path.get('heading_error_degrees',0)
        if self.config.boundary_guidance:
            heading = path.get('guidance_heading_error_degrees', heading)
        wanted = self.wanted_angle(path)
        evidence = heading if abs(heading) >= 8 else wanted if abs(wanted) >= 6 else None
        if evidence is not None or abs(self.angle) >= 6:
            if evidence is not None or self.turn_direction == 'straight':
                self.turn_direction = 'left' if (self.angle if evidence is None else evidence) < 0 else 'right'
            self.straight_since = None
            self.straight_frames = 0
        elif self.turn_direction != 'straight':
            if abs(heading) < 5 and abs(wanted) < 4 and path.get('source') != 'single_dash_boundary':
                if self.straight_since is None or now-self.last_tick > .2:
                    self.straight_since = now
                    self.straight_frames = 0
                self.straight_frames += 1
                if self.straight_frames >= 3 and now-self.straight_since >= .3:
                    self.turn_direction = 'straight'
                    self.straight_since = None
                    self.straight_frames = 0
            else:
                self.straight_since = None
                self.straight_frames = 0
        scale = max(0, min(1, path.get('speed_scale', 1)))
        turning = self.turn_direction != 'straight'
        if turning:
            scale = min(scale,self.config.curve_scale)
        approaching = self.config.crosswalk_gesture and self.crossing.state == 'crosswalk_approach'
        if approaching:
            scale = min(scale, .85)
        target = max(.1, self.config.speed * scale)
        self.commanded_speed = self.speed_target = float(target)
        self.speed_reason = ('curve_limited' if turning and scale < self.config.curve_scale else
                             'crosswalk_approach' if approaching else
                             'curve' if turning and scale < 1 else
                             'limited_path' if scale < 1 else 'base_output')
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
                if (frame['age'] is None or frame['age'] > .2
                        or not path.get('reference_set') or not self.path_mode_matches(path)):
                    self.stop('path_lost', frame)
                    return
                if now - self.space_checked_at >= 1:
                    try:
                        self.store.check_space()
                    except OSError as error:
                        self.error = f'{type(error).__name__}: {error}'
                        self.stop('storage_error', frame)
                        return
                    self.space_checked_at = now
                if self.config.crosswalk_gesture:
                    if not self.gesture_ready():
                        self.stop('gesture_error', frame)
                        return
                    if not frame.get('crosswalk', {}).get('reliable', True):
                        self.stop('crosswalk_unavailable', frame)
                        return
                    self.crossing.observe_crosswalk(frame.get('crosswalk', {}), frame.get('source_number'), now)
                    if self.crossing.waiting:
                        ready = (path.get('valid') and frame['streak'] >= 3 and not self.excessive_error(path))
                        self.crossing.authorize(frame.get('gesture', {}), now, ready)
                    if self.crossing.waiting:
                        if frame['number'] != self.last_frame:
                            self.sequence += 1
                            self.control.pause(self.owner, self.sequence)
                            self.recovery.reset()
                            self.commanded_speed = self.speed_target = 0
                            self.speed_reason = 'waiting_gesture'
                            self.last_tick, self.last_frame = now, frame['number']
                            with self.log_lock:
                                if self.log and not self.log.closed:
                                    self.log.write(json.dumps(dict(event='wait_gesture', t=round(now-self.started,4),
                                        frame=frame['number'], source_frame=frame.get('source_number'),
                                        interaction=self.crossing.status(), gesture=frame.get('gesture'),
                                        crosswalk=frame.get('crosswalk'), motor_outputs=self.control.status()['motor_outputs']))+'\n')
                        return
                recovery = None
                if not path.get('valid'):
                    recovery = self.recovery.continue_turn(frame, now) if self.config.turn_recovery else None
                    if recovery is None:
                        self.stop('path_lost', frame)
                        return
                if path.get('valid') and self.excessive_error(path):
                    self.stop('path_error_large', frame)
                    return
                if frame['number'] == self.last_frame or recovery and recovery['duplicate']:
                    return
                wanted = recovery['angle'] if recovery else self.wanted_angle(path)
                if not recovery:
                    self.angle = steering_step(self.angle,wanted,self.config.rate,
                                               now-self.last_tick,self.config.lap_mode)
                self.sequence += 1
                if recovery:
                    speed = min(recovery['speed'], max(.1, self.config.speed*.8))
                    self.commanded_speed = self.speed_target = speed
                    self.speed_reason = 'turn_recovery'
                else:
                    speed = self.update_speed(path)
                    if self.config.turn_recovery:
                        self.recovery.observe_valid(frame, now, self.angle, speed, self.turn_direction)
                self.control.follow(self.owner, self.sequence, self.angle, speed)
                interval = now - self.last_tick
                self.last_tick = now
                self.last_frame = frame['number']
                applied = self.control.status()
                record = dict(event='frame', t=round(now - self.started, 4), frame=frame['number'],
                              path=path, wanted_angle=wanted, commanded_angle=self.angle, speed=speed,
                              speed_target=self.speed_target, speed_reason=self.speed_reason,
                              turn_direction=self.turn_direction, straight_frames=self.straight_frames,
                              recovery_active=self.recovery.active,
                              interaction=self.crossing.status(),
                              crosswalk=frame.get('crosswalk'),
                              recovery_elapsed=recovery['elapsed'] if recovery else None,
                              source_frame=frame.get('source_number'), received_at=frame.get('received_at'),
                              frame_age_seconds=frame['age'], control_interval=round(interval,4),
                              motor_outputs=applied['motor_outputs'],
                              motor_write_count=applied['motor_write_count'],
                              last_motor_write_at=applied['last_motor_write_at'])
                log = self.log
            with self.log_lock:
                if log and not log.closed:
                    log.write(json.dumps(record) + '\n')
        except PermissionError as error:
            reason = self.control.status()['reason']
            if reason in ('connection_timeout', 'time_limit', 'operator_stop', 'stopped'):
                self.stop(reason)
            else:
                self.error = f'{type(error).__name__}: {error}'
                self.stop('pilot_error')
        except Exception as error:
            self.error = f'{type(error).__name__}: {error}'
            self.stop('pilot_error')
