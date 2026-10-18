from pathlib import Path
from types import SimpleNamespace
import json
import re
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from autonomous import AutoPilot, PilotConfig
from lane_path import LanePath
from manual_drive import DriveConfig, ManualDrive
from media_capture import CaptureStore
from test_manual_drive import Servo, Motor
from test_track_vision import sample_track
from track_web import Monitor, create_app


def dashed_result(xs=(300, 300, 300, 300)):
    return SimpleNamespace(frame=np.zeros((400, 600, 3), np.uint8),
                           markings=[dict(center=[x,y], dash_candidate=True)
                                     for x,y in zip(xs, (330,240,160,100))])


class PathTests(unittest.TestCase):
    def test_straight_path_and_explicit_reference(self):
        path = LanePath()
        first = path.predict(dashed_result())
        self.assertTrue(first['valid'])
        self.assertFalse(first['reference_set'])
        path.calibrate(first)
        shifted = path.predict(dashed_result((330,330,330,330)))
        self.assertTrue(shifted['valid'])
        self.assertGreater(shifted['normalized_error'], 0)

    def test_blank_single_dash_and_ambiguous_chains_rejected(self):
        for count in (0, 1, 2):
            result = dashed_result()
            result.markings = result.markings[:count]
            self.assertFalse(LanePath().predict(result)['valid'])
        result = dashed_result((250,250,250,250))
        result.markings += dashed_result((350,350,350,350)).markings
        self.assertEqual(LanePath().predict(result)['reason'], 'ambiguous_dash_chain')

    def test_geometry_change_invalidates_reference(self):
        path = LanePath()
        path.calibrate(path.predict(dashed_result(), ('camera',0)))
        self.assertTrue(path.predict(dashed_result(), ('camera',0))['reference_set'])
        self.assertFalse(path.predict(dashed_result(), ('camera',180))['reference_set'])

    def test_excessive_path_jump_rejected(self):
        path = LanePath()
        path.predict(dashed_result())
        self.assertFalse(path.predict(dashed_result((500,500,500,500)))['valid'])


class StubMonitor:
    def __init__(self):
        self.frame = dict(path=dict(valid=True, reference_set=True,
                                   reference_normalized=.5, normalized_error=.2),
                          age=0, number=1, streak=5)

    def control_snapshot(self):
        return self.frame


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch('autonomous.time.monotonic', return_value=1000)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = CaptureStore(self.directory.name, min_free_bytes=0)
        self.addCleanup(self.store.close)
        self.monitor = StubMonitor()
        self.servo, self.motors = Servo(), (Motor(), Motor())
        self.control = ManualDrive(self.servo, self.motors, DriveConfig(motors_confirmed=True))
        self.pilot = AutoPilot(self.monitor, self.control, self.store)
        # Retain the stronger-braking policy as an explicit regression fixture.
        self.pilot.configure({'curve_scale':.55})
        self.addCleanup(self.pilot.stop)

    def test_constructing_and_start_reserving_do_not_move(self):
        self.assertEqual(self.servo.commands, [])
        self.assertFalse(self.control.armed)
        self.pilot.start('one')
        self.assertEqual(self.servo.commands, [])
        self.assertEqual(self.control.outputs, (0,0))

    def advance(self, now):
        self.now.return_value = now
        self.monitor.frame['number'] += 1
        self.pilot.heartbeat('one')
        self.pilot.tick()
        self.control.tick()

    def test_continuous_is_explicit_and_has_no_elapsed_time_deadline(self):
        self.assertFalse(self.pilot.config.continuous)
        for invalid in (1, 0, None, 'true', [], {}):
            with self.assertRaises(ValueError):
                self.pilot.configure({'continuous':invalid})
        self.pilot.configure({'continuous':True})
        self.pilot.start('one')
        self.assertIsNone(self.control.motion_deadline)
        for now in (1000.1, 1003.1, 4600):
            self.advance(now)
            self.assertTrue(self.pilot.active)
            self.assertTrue(self.control.armed)
            self.assertIsNone(self.pilot.status()['remaining'])
        self.pilot.stop()
        self.assertEqual(self.control.outputs, (0,0))
        self.assertIsNone(self.servo.angle)
        self.assertEqual(self.pilot.status()['remaining'],0)
        records = [json.loads(line) for line in (self.store.root/self.pilot.last_log).read_text().splitlines()]
        self.assertTrue(records[0]['settings']['continuous'])

    def test_switching_modes_does_not_leave_or_remove_wrong_deadline(self):
        for continuous in (False, True, False):
            self.pilot.configure({'continuous':continuous})
            self.pilot.start('one')
            self.assertEqual(self.control.motion_deadline, None if continuous else 1001)
            self.pilot.stop()
        with self.assertRaises(ValueError):
            self.pilot.configure({'duration':float('inf'), 'continuous':True})

    def test_continuous_keeps_all_safety_stops(self):
        for failure in ('path_lost','camera_stale','path_error_large','browser_timeout',
                        'connection_timeout','operator_stop','storage_error'):
            with self.subTest(failure=failure):
                self.monitor.frame['path'].update(valid=True,normalized_error=.2)
                self.monitor.frame['age']=0
                self.now.return_value=1000
                self.pilot.configure({'continuous':True})
                self.pilot.start('one')
                self.advance(1000.1)
                if failure == 'path_lost':self.monitor.frame['path']['valid']=False
                elif failure == 'camera_stale':self.monitor.frame['age']=.21
                elif failure == 'path_error_large':self.monitor.frame['path']['normalized_error']=.6
                elif failure == 'browser_timeout':self.now.return_value=1001
                elif failure == 'connection_timeout':
                    self.now.return_value=1001
                    self.control.tick()
                elif failure == 'operator_stop':self.control.stop(reason='operator_stop')
                if failure == 'storage_error':
                    with patch.object(self.store,'check_space',side_effect=OSError('full')):
                        self.advance(1001.1)
                else:self.pilot.tick()
                self.assertFalse(self.pilot.active)
                self.assertFalse(self.control.armed)
                self.assertEqual(self.control.outputs,(0,0))
                self.assertIsNone(self.servo.angle)
                self.assertEqual(self.pilot.reason, 'path_lost' if failure == 'camera_stale' else failure)

    def test_continuous_ownership_and_config_lock(self):
        self.pilot.configure({'continuous':True})
        self.pilot.start('one')
        with self.assertRaises(PermissionError):self.pilot.heartbeat('two')
        with self.assertRaises(PermissionError):self.pilot.configure({'continuous':False})
        with self.assertRaises(PermissionError):self.control.arm('two')

    def test_reference_stable_path_and_enabled_dc_required(self):
        for key,value in [('reference_set',False),('valid',False)]:
            self.monitor.frame['path'][key] = value
            with self.assertRaises(ValueError):
                self.pilot.start('one')
            self.monitor.frame['path'][key] = True
        self.monitor.frame['age'] = .3
        with self.assertRaises(ValueError):
            self.pilot.start('one')
        self.assertEqual(self.servo.commands, [])

    def test_p_gain_angle_and_rate_limiter(self):
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertAlmostEqual(self.servo.angle, 3)
        self.assertEqual(self.control.outputs, (.169,.169))
        self.assertTrue(self.control.hold_servo)
        self.monitor.frame['number'] = 2
        self.now.return_value = 1000.1
        self.pilot.tick()
        self.assertAlmostEqual(self.servo.angle, 6)

    def test_independent_hardware_deadline_without_pilot_tick(self):
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.now.return_value = 1001.01
        self.control.tick()
        self.assertFalse(self.control.armed)
        self.assertEqual(self.control.outputs, (0,0))
        self.assertIsNone(self.servo.angle)
        self.assertEqual(self.control.reason, 'time_limit')

    def test_hold_is_pilot_only_and_manual_pwm_release_is_unchanged(self):
        self.pilot.configure({'duration':3})
        self.pilot.start('one')
        for index in range(1, 10):
            self.now.return_value = 1000 + index * .1
            self.monitor.frame['number'] = index
            self.pilot.heartbeat('one')
            self.pilot.tick()
            self.control.tick()
        self.assertTrue(self.control.hold_servo)
        self.assertIsNotNone(self.servo.angle)
        self.pilot.stop()
        self.assertFalse(self.control.hold_servo)
        self.assertFalse(self.pilot.heartbeat('one'))

    def test_path_loss_and_browser_timeout_stop(self):
        self.pilot.configure({'duration':3})
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.monitor.frame['path']['valid'] = False
        self.pilot.tick()
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs, (0,0))
        self.monitor.frame['path']['valid'] = True
        self.pilot.start('one')
        self.now.return_value = 1000.8
        self.pilot.tick()
        self.assertEqual(self.pilot.reason, 'browser_timeout')

    def test_owner_conflict_invalid_settings_and_log(self):
        for settings in [dict(speed=.4),dict(duration=4),dict(kp=float('nan'))]:
            with self.assertRaises(ValueError):
                self.pilot.configure(settings)
        self.pilot.start('one')
        with self.assertRaises(PermissionError):
            self.control.arm('two')
        with self.assertRaises(PermissionError):
            self.pilot.heartbeat('two')
        with self.assertRaises(PermissionError):
            self.pilot.configure({'kp':50})
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.pilot.stop()
        records = [json.loads(line) for line in (Path(self.directory.name)/self.pilot.last_log).read_text().splitlines()]
        self.assertEqual([r['event'] for r in records], ['start','frame','stop'])


class AdaptiveSpeedTests(unittest.TestCase):
    setUp = PilotTests.setUp
    advance = PilotTests.advance

    def test_default_ratio_revised_after_user_reports_near_stall(self):
        self.assertEqual(PilotConfig().curve_scale,.75)
        self.pilot.configure({'curve_scale':PilotConfig().curve_scale})
        self.start(heading_error_degrees=45)
        self.advance(1000.05)
        self.assertAlmostEqual(self.control.outputs[0],.195)
        self.assertLess(self.control.outputs[0],.208)

    def start(self, **path):
        self.monitor.frame['path'].update({'normalized_error':0,'heading_error_degrees':0,**path})
        self.pilot.configure({'continuous':True})
        self.pilot.start('one')

    def test_straight_keeps_base_output_and_turn_prediction_brakes_before_servo_arrives(self):
        self.start()
        self.advance(1000.05)
        self.assertEqual(self.control.outputs,(.26,.26))
        self.monitor.frame['path']['heading_error_degrees']=10
        self.advance(1000.1)
        self.assertAlmostEqual(self.pilot.angle,3)
        self.assertAlmostEqual(self.pilot.commanded_speed,.182)
        self.assertEqual(self.pilot.speed_reason,'curve')

    def test_sharp_turns_both_directions_brake_to_configured_ratio(self):
        for heading in (-45,45):
            self.monitor.frame['path']['heading_error_degrees']=heading
            self.pilot.configure({'continuous':True,'curve_scale':.55})
            self.pilot.start('one')
            self.advance(1000.05)
            self.assertAlmostEqual(self.control.outputs[0],.143)
            self.assertEqual(self.control.outputs[0],self.control.outputs[1])
            self.pilot.stop()
            self.now.return_value=1000

    def test_weak_path_and_steering_only_also_slow_without_changing_manual_preferences(self):
        self.start(speed_scale=.8)
        self.advance(1000.05)
        self.assertAlmostEqual(self.pilot.commanded_speed,.143)
        self.assertEqual(self.pilot.speed_reason,'limited_path')
        self.assertEqual(self.control.speed,.30)

    def test_large_lateral_correction_slows_even_without_heading_evidence(self):
        self.start()
        self.monitor.frame['path']['normalized_error']=.3
        self.advance(1000.05)
        self.assertLess(self.pilot.commanded_speed,.18)
        self.assertEqual(self.pilot.speed_reason,'curve')

    def test_boundary_source_limits_output_even_if_scale_and_heading_look_straight(self):
        self.start(source='dash_boundary',speed_scale=1)
        self.advance(1000.05)
        self.assertAlmostEqual(self.pilot.commanded_speed,.143)

    def test_straight_recovery_waits_then_ramps_in_time_not_instantly(self):
        self.start()
        self.monitor.frame['path']['heading_error_degrees']=45
        self.advance(1000.05)
        self.monitor.frame['path']['heading_error_degrees']=0
        self.advance(1000.1)
        self.advance(1000.79)
        self.assertAlmostEqual(self.pilot.commanded_speed,.143)
        self.assertEqual(self.pilot.speed_reason,'straight_wait')
        self.advance(1000.81)
        self.assertAlmostEqual(self.pilot.commanded_speed,.1438)
        self.assertEqual(self.pilot.speed_reason,'accelerating')
        for i in range(1,90):self.advance(1000.81+i*.05)
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)
        self.assertLessEqual(self.pilot.commanded_speed,self.pilot.config.speed)

    def test_intermittent_turn_detection_resets_recovery_wait(self):
        self.start()
        self.monitor.frame['path']['heading_error_degrees']=45
        self.advance(1000.05)
        self.monitor.frame['path']['heading_error_degrees']=0
        self.advance(1000.1)
        self.monitor.frame['path']['heading_error_degrees']=10
        self.advance(1000.75)
        self.monitor.frame['path']['heading_error_degrees']=0
        self.advance(1000.8)
        self.advance(1001.4)
        self.assertAlmostEqual(self.pilot.commanded_speed,.143)

    def test_deflected_servo_cannot_accelerate_on_one_straight_frame(self):
        self.start()
        self.pilot.angle=20
        self.pilot.commanded_speed=.143
        self.advance(1000.05)
        self.assertGreater(self.pilot.angle,6)
        self.assertIsNone(self.pilot.straight_since)
        self.assertAlmostEqual(self.pilot.commanded_speed,.143)

    def test_output_floor_and_caps_settings_validation_stop_and_log(self):
        for invalid in (.39,.81,True,float('nan')):
            with self.assertRaises(ValueError):self.pilot.configure({'curve_scale':invalid})
        self.pilot.configure({'speed':.1})
        self.start(speed_scale=.8)
        self.advance(1000.05)
        self.assertAlmostEqual(self.pilot.commanded_speed,.1)
        self.monitor.frame['path']['valid']=False
        self.pilot.tick()
        self.assertEqual(self.control.outputs,(0,0))
        self.assertEqual(self.pilot.status()['commanded_speed'],0)
        self.assertEqual(self.pilot.status()['speed_reason'],'stopped')
        rows=[json.loads(x) for x in (self.store.root/self.pilot.last_log).read_text().splitlines()]
        frame=next(x for x in rows if x['event']=='frame')
        self.assertEqual(frame['speed_reason'],'limited_path')
        self.assertIn('frame_age_seconds',frame)
        self.assertIn('control_interval',frame)


class PilotWebTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = CaptureStore(self.directory.name, min_free_bytes=0)
        self.addCleanup(self.store.close)
        self.monitor = Monitor(None, rotation=0, path_enabled=True)
        for _ in range(4):
            self.monitor.process_frame(sample_track())
        self.control = ManualDrive(Servo(), (Motor(), Motor()), DriveConfig(motors_confirmed=True))
        self.pilot = AutoPilot(self.monitor, self.control, self.store)
        self.addCleanup(self.pilot.stop)
        self.client = create_app(self.monitor, self.control, self.store, self.pilot).test_client()
        page = self.client.get('/').data.decode()
        self.options = json.loads(re.search(r'window.pilotOptions=(.*?);</script>',page).group(1))
        self.headers = {'X-Manual-Token':self.options['token']}

    def post(self, action, **values):
        return self.client.post('/auto/'+action,json=dict(client='one',**values),headers=self.headers)

    def test_page_tokens_reference_and_start_are_explicit(self):
        self.assertFalse(self.control.armed)
        self.assertEqual(self.client.post('/auto/start',json={'client':'one'}).status_code,403)
        self.assertEqual(self.post('start').status_code,400)
        self.assertEqual(self.post('reference').status_code,200)
        self.assertEqual(self.post('start').status_code,200)
        self.assertEqual(self.control.outputs,(0,0))
        self.assertEqual(self.client.post('/settings',json={'rotation':180}).status_code,409)
        stop=self.client.post('/manual/stop',headers=self.headers,json={'client':'one','emergency':True})
        self.assertEqual(stop.status_code,200)
        self.assertFalse(self.pilot.active)
        self.assertFalse(self.control.armed)

    def test_camera_changes_invalidate_reference(self):
        self.post('reference')
        self.assertTrue(self.monitor.prediction['reference_set'])
        self.client.post('/settings',json={'rotation':180})
        self.assertFalse(self.monitor.prediction['reference_set'])

    def test_continuous_setting_and_emergency_stop(self):
        self.assertFalse(self.options['settings']['continuous'])
        self.assertIn('id="auto-continuous"',self.client.get('/').data.decode())
        self.assertEqual(self.post('settings',settings={'continuous':'true'}).status_code,400)
        self.assertEqual(self.post('settings',settings={'continuous':True}).status_code,200)
        self.post('reference')
        started=self.post('start').get_json()
        self.assertTrue(started['active'])
        self.assertIsNone(started['remaining'])
        self.assertEqual(self.post('settings',settings={'continuous':False}).status_code,409)
        self.client.post('/manual/stop',headers=self.headers,json={'client':'two','emergency':True})
        self.assertFalse(self.control.armed)
        self.assertFalse(self.pilot.active)
