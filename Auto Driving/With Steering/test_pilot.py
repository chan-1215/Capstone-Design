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

    def test_full_dash_chain_turn_has_no_heading_based_speed_reduction(self):
        for xs in ((300,280,240,200),(300,320,360,400)):
            prediction=LanePath().predict(dashed_result(xs))
            self.assertTrue(prediction['valid'],prediction)
            self.assertGreater(abs(prediction['heading_degrees']),8)
            self.assertEqual(prediction['speed_scale'],1)


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
        # Retain narrow travel as an explicit fixture for the original rate tests.
        self.pilot.configure({'max_left_angle':20, 'max_right_angle':20,'curve_scale':1})
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
        # Continuous removes the trial deadline, not the independent input lease.
        for now in (1000.1,1000.6,1001.1,1001.6,1002.1,1002.6,1003.1):
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
        self.assertEqual(self.control.outputs, (.26,.26))
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


class AsymmetricSteeringTests(unittest.TestCase):
    setUp = PilotTests.setUp
    advance = PilotTests.advance

    def set_limits(self):
        self.pilot.configure({'max_left_angle':105, 'max_right_angle':85,
                              'continuous':True})

    def test_defaults_match_confirmed_asymmetric_hardware(self):
        self.assertEqual(PilotConfig().max_left_angle,105)
        self.assertEqual(PilotConfig().max_right_angle,85)
        pilot = AutoPilot(self.monitor,self.control,self.store)
        self.assertEqual(pilot.config.max_left_angle,105)
        self.assertEqual(pilot.config.max_right_angle,85)
        self.assertFalse(self.control.armed)
        self.assertEqual(self.servo.commands,[])

    def test_p_heading_is_proportional_not_always_full_lock(self):
        self.set_limits()
        self.assertEqual(self.pilot.wanted_angle(dict(normalized_error=.2)),12)
        self.assertEqual(self.pilot.wanted_angle(dict(normalized_error=-.2)),-12)
        last_path = dict(normalized_error=-1.00936,heading_error_degrees=-31.2)
        self.assertAlmostEqual(self.pilot.wanted_angle(last_path),-85.5216)
        self.assertEqual(self.pilot.wanted_angle(dict(normalized_error=-3)),-105)
        self.assertEqual(self.pilot.wanted_angle(dict(normalized_error=3)),85)

    def test_both_limits_reached_gradually_and_path_loss_still_stops(self):
        self.set_limits()
        for sign, limit in [(-1,-105),(1,85)]:
            with self.subTest(sign=sign):
                self.now.return_value=1000
                self.control.angle=0
                self.monitor.frame['path'].update(valid=True,normalized_error=sign,
                    heading_error_degrees=sign*90,curve_corridor_supported=True)
                before=len(self.servo.commands)
                self.pilot.start('one')
                self.assertEqual(len(self.servo.commands),before)
                previous=0
                for step in range(1,41):
                    self.advance(1000+step*.05)
                    self.assertTrue(self.pilot.active)
                    self.assertLessEqual(abs(self.pilot.angle-previous),3.00001)
                    self.assertGreaterEqual(self.pilot.angle,-105)
                    self.assertLessEqual(self.pilot.angle,85)
                    previous=self.pilot.angle
                self.assertEqual(self.servo.angle,limit)
                self.assertAlmostEqual(self.control.outputs[0],.26)
                self.monitor.frame['path']['valid']=False
                self.pilot.tick()
                self.assertFalse(self.pilot.active)
                self.assertFalse(self.control.armed)
                self.assertEqual(self.control.outputs,(0,0))
                self.assertIsNone(self.servo.angle)

    def test_restart_uses_last_asymmetric_command_without_actuating(self):
        self.set_limits()
        for angle in (-105,85):
            self.control.angle=angle
            before=len(self.servo.commands)
            self.pilot.start('one')
            self.assertEqual(self.pilot.angle,angle)
            self.assertEqual(len(self.servo.commands),before)
            self.pilot.stop()

    def test_invalid_or_over_hardware_settings_are_atomic(self):
        self.set_limits()
        for key,maximum in [('max_left_angle',105),('max_right_angle',85)]:
            for invalid in (4,maximum+1,True,None,float('nan'),float('inf')):
                previous=self.pilot.config
                with self.assertRaises(ValueError):
                    self.pilot.configure({key:invalid,'kp':50})
                self.assertEqual(self.pilot.config,previous)
        with self.assertRaises(ValueError):
            self.pilot.configure({'max_angle':20})
        control=ManualDrive(Servo(),(Motor(),Motor()),
                            DriveConfig(motors_confirmed=True,a_angle=-35,d_angle=25))
        pilot=AutoPilot(self.monitor,control,self.store)
        self.assertEqual((pilot.config.max_left_angle,pilot.config.max_right_angle),(35,25))
        for settings in ({'max_left_angle':36},{'max_right_angle':26}):
            with self.assertRaises(ValueError):pilot.configure(settings)

    def test_steering_travel_does_not_change_requested_base_output(self):
        self.set_limits()
        for angle in (-105,-20,20,85):
            self.pilot.commanded_speed=None
            self.pilot.angle=0
            self.pilot.angle=angle
            speed=self.pilot.update_speed({'normalized_error':0})
            self.assertAlmostEqual(speed,.26)


class BaseOutputTests(unittest.TestCase):
    setUp = PilotTests.setUp
    advance = PilotTests.advance

    def test_curve_ratio_restored_without_raising_base_output(self):
        self.assertEqual(PilotConfig().curve_scale,.85)
        self.pilot.configure({'curve_scale':.85})
        self.assertEqual(PilotConfig().speed,.26)
        self.start(heading_error_degrees=45)
        self.advance(1000.05)
        self.assertAlmostEqual(self.control.outputs[0],.221)
        self.assertAlmostEqual(self.control.outputs[1],.221)

    def start(self, **path):
        self.monitor.frame['path'].update({'normalized_error':0,'heading_error_degrees':0,**path})
        self.pilot.configure({'continuous':True})
        self.pilot.start('one')

    def test_straight_and_turn_prediction_keep_base_output(self):
        self.start()
        self.advance(1000.05)
        self.assertEqual(self.control.outputs,(.26,.26))
        self.monitor.frame['path']['heading_error_degrees']=10
        self.advance(1000.1)
        self.assertAlmostEqual(self.pilot.angle,3)
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)
        self.assertEqual(self.pilot.speed_reason,'base_output')

    def test_sharp_turns_both_directions_keep_base_output(self):
        for heading in (-45,45):
            self.monitor.frame['path']['heading_error_degrees']=heading
            self.pilot.configure({'continuous':True})
            self.pilot.start('one')
            self.advance(1000.05)
            self.assertAlmostEqual(self.control.outputs[0],.26)
            self.assertEqual(self.control.outputs[0],self.control.outputs[1])
            self.pilot.stop()
            self.now.return_value=1000

    def test_limited_path_scale_remains_without_changing_manual_preferences(self):
        self.start(speed_scale=.8)
        self.advance(1000.05)
        self.assertAlmostEqual(self.pilot.commanded_speed,.208)
        self.assertEqual(self.pilot.speed_reason,'limited_path')
        self.assertEqual(self.control.speed,.30)

    def test_large_lateral_correction_does_not_change_output(self):
        self.start()
        self.monitor.frame['path']['normalized_error']=.3
        self.advance(1000.05)
        self.assertEqual(self.pilot.commanded_speed,.26)
        self.assertEqual(self.pilot.speed_reason,'base_output')

    def test_source_name_alone_cannot_reduce_output(self):
        self.start(source='dash_boundary',speed_scale=1)
        self.advance(1000.05)
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)

    def test_no_curve_hold_or_straight_recovery_delay_remains(self):
        self.start()
        self.monitor.frame['path']['heading_error_degrees']=45
        self.advance(1000.05)
        self.monitor.frame['path']['heading_error_degrees']=0
        self.advance(1000.1)
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)
        self.assertEqual(self.pilot.speed_reason,'base_output')
        self.monitor.frame['path']['speed_scale']=.8
        self.advance(1000.15)
        self.assertAlmostEqual(self.pilot.commanded_speed,.208)
        self.monitor.frame['path']['speed_scale']=1
        self.advance(1000.2)
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)
        self.assertLessEqual(self.pilot.commanded_speed,self.pilot.config.speed)

    def test_intermittent_turn_detection_does_not_change_output(self):
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
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)

    def test_deflected_servo_no_longer_holds_previous_low_output(self):
        self.start()
        self.pilot.angle=20
        self.pilot.commanded_speed=.143
        self.advance(1000.05)
        self.assertGreater(self.pilot.angle,6)
        self.assertAlmostEqual(self.pilot.commanded_speed,.26)

    def test_output_floor_and_caps_settings_validation_stop_and_log(self):
        for invalid in (.09,.31,True,float('nan')):
            with self.assertRaises(ValueError):self.pilot.configure({'speed':invalid})
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


class CurveStateTests(unittest.TestCase):
    setUp = PilotTests.setUp
    advance = PilotTests.advance

    def start(self, **path):
        self.pilot.configure({'curve_scale':.85,'continuous':True,
                              'max_left_angle':105,'max_right_angle':85})
        self.monitor.frame['path'].update({'normalized_error':0,'heading_error_degrees':0,**path})
        self.pilot.start('one')

    def test_turns_both_directions_reduce_base_output(self):
        for sign,direction in ((-1,'left'),(1,'right')):
            self.now.return_value=1000
            self.start(heading_error_degrees=45*sign)
            self.advance(1000.05)
            self.assertEqual(self.pilot.turn_direction,direction)
            self.assertAlmostEqual(self.control.outputs[0],.221)
            self.assertEqual(self.pilot.speed_reason,'curve')
            self.pilot.stop()
            self.control.angle=0

    def test_one_straight_frame_does_not_exit_turn_but_steering_tracks_current_path(self):
        self.start(heading_error_degrees=-45)
        self.advance(1000.05)
        self.monitor.frame['path'].update(heading_error_degrees=0)
        self.advance(1000.1)
        self.assertAlmostEqual(self.pilot.angle,0)
        self.assertEqual(self.pilot.turn_direction,'left')
        self.assertEqual(self.pilot.straight_frames,1)
        self.assertAlmostEqual(self.control.outputs[0],.221)
        self.now.return_value=1000.15
        self.pilot.tick()
        self.assertEqual(self.pilot.straight_frames,1)

    def test_exit_requires_distinct_straight_frames_for_at_least_point_three_seconds(self):
        self.start(heading_error_degrees=-45)
        self.advance(1000.05)
        self.monitor.frame['path']['heading_error_degrees']=0
        for now in (1000.1,1000.2,1000.3):
            self.advance(now)
            self.assertEqual(self.pilot.turn_direction,'left')
        self.advance(1000.41)
        self.assertEqual(self.pilot.turn_direction,'straight')
        self.assertEqual(self.control.outputs,(.26,.26))

    def test_intermittent_turn_or_frame_gap_restarts_exit_confirmation(self):
        self.start(heading_error_degrees=-45)
        self.advance(1000.05)
        self.monitor.frame['path']['heading_error_degrees']=0
        self.advance(1000.1)
        self.advance(1000.4)
        self.assertEqual(self.pilot.straight_frames,1)
        self.monitor.frame['path']['heading_error_degrees']=-10
        self.advance(1000.45)
        self.assertEqual(self.pilot.straight_frames,0)
        self.assertEqual(self.pilot.turn_direction,'left')

    def test_new_opposite_turn_switches_without_waiting_for_a_straight(self):
        self.start(heading_error_degrees=-45)
        self.advance(1000.05)
        self.monitor.frame['path']['heading_error_degrees']=45
        self.advance(1000.1)
        self.assertEqual(self.pilot.turn_direction,'right')
        self.assertAlmostEqual(self.control.outputs[0],.221)

    def test_supported_pair_keeps_independent_output_cap(self):
        self.start(heading_error_degrees=-45,speed_scale=.8,source='dash_boundary')
        self.advance(1000.05)
        self.assertEqual(self.pilot.turn_direction,'left')
        self.assertAlmostEqual(self.control.outputs[0],.208)
        self.assertEqual(self.pilot.speed_reason,'curve_limited')

    def test_latched_turn_never_bypasses_lost_or_stale_path(self):
        for failure in ('lost','stale'):
            self.now.return_value=1000
            self.monitor.frame['path']['valid']=True
            self.monitor.frame['age']=0
            self.start(heading_error_degrees=-45)
            self.advance(1000.05)
            if failure=='lost':self.monitor.frame['path']['valid']=False
            else:self.monitor.frame['age']=.21
            before=len(self.servo.commands)
            self.pilot.tick()
            self.assertFalse(self.pilot.active)
            self.assertEqual(self.control.outputs,(0,0))
            self.assertIsNone(self.servo.angle)
            self.assertEqual(self.pilot.reason,'path_lost')
            self.assertEqual(self.pilot.turn_direction,'straight')
            self.assertGreaterEqual(len(self.servo.commands),before)

    def test_curve_scale_validated_and_logged(self):
        for value in (.74,1.01,True,float('nan')):
            with self.assertRaises(ValueError):self.pilot.configure({'curve_scale':value})
        self.start(heading_error_degrees=-45)
        self.advance(1000.05)
        self.pilot.stop()
        rows=[json.loads(x) for x in (self.store.root/self.pilot.last_log).read_text().splitlines()]
        self.assertEqual(rows[0]['settings']['curve_scale'],.85)
        self.assertEqual(rows[1]['turn_direction'],'left')
        self.assertAlmostEqual(rows[1]['speed'],.221)


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

    def test_asymmetric_limits_page_api_and_hardware_caps(self):
        page=self.client.get('/').data.decode()
        for side,limit in [('left',105),('right',85)]:
            match=re.search(r'<input id="auto-max-'+side+r'-angle"[^>]+>',page).group()
            self.assertIn('max="'+str(limit)+'"',match)
            self.assertIn('value="'+str(limit)+'"',match)
            self.assertEqual(self.options['settings']['max_'+side+'_angle'],limit)
        self.assertNotIn('id="auto-max-angle"',page)
        self.assertIn('auto-curve-scale',page)
        self.assertEqual(self.options['settings']['curve_scale'],.85)
        self.assertEqual(self.post('settings',settings={'max_left_angle':106}).status_code,400)
        self.assertEqual(self.post('settings',settings={'max_right_angle':86}).status_code,400)
        response=self.post('settings',settings={'max_left_angle':100,'max_right_angle':80})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['settings']['max_left_angle'],100)
        self.assertEqual(response.get_json()['settings']['max_right_angle'],80)
        self.assertFalse(self.control.armed)
        self.assertEqual(self.control.outputs,(0,0))

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
