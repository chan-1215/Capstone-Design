import time
import unittest
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np

import test_pilot
from test_track_vision import sample_track
from track_web import Monitor, create_app


class IntegratedPilotTests(unittest.TestCase):
    setUp = test_pilot.PilotTests.setUp

    def advance(self, at, valid=True, **extra):
        self.now.return_value = at
        frame = self.monitor.frame
        frame['number'] += 1
        frame.update(source_number=frame['number'], received_at=at, age=0)
        frame['path']['valid'] = valid
        frame.update(extra)
        self.pilot.heartbeat('one')
        self.pilot.tick()
        self.control.tick()

    def enable_crossing(self):
        self.monitor.gesture = SimpleNamespace(snapshot=lambda:dict(initialized=True, error=None))
        self.pilot.configure(dict(crosswalk_gesture=True, continuous=True))
        self.pilot.start('one')
        self.advance(1000.05)
        self.advance(1000.1, crosswalk=dict(stop=True,detected=True))

    def test_crossing_pause_holds_ownership_but_outputs_zero_and_detaches_servo(self):
        self.enable_crossing()
        self.assertTrue(self.pilot.active)
        self.assertTrue(self.pilot.crossing.waiting)
        self.assertTrue(self.control.armed)
        self.assertEqual(self.control.owner, 'auto:one')
        self.assertEqual(self.control.outputs, (0,0))
        self.assertIsNone(self.servo.angle)
        for at in (1000.2,1000.3,1000.4):
            self.advance(at, valid=False)
        self.assertTrue(self.pilot.active)
        self.assertEqual(self.control.outputs, (0,0))

    def test_only_fresh_go_with_valid_path_can_resume_without_rearming(self):
        self.enable_crossing()
        for i in range(7):
            at = 1000.2+i*.11
            gesture = dict(mode='wait',ready=True,hand_detected=True,epoch=1,
                           number=i,received_at=at,decision_label='go')
            self.advance(at, gesture=gesture)
        self.assertEqual(self.pilot.crossing.state, 'depart')
        self.assertGreater(self.control.outputs[0], 0)
        self.assertEqual(self.control.owner,'auto:one')

    def test_pause_still_obeys_browser_timeout_operator_stop_and_deadman(self):
        for failure in ('browser_timeout', 'operator_stop', 'connection_timeout'):
            self.now.return_value = 1000
            self.enable_crossing()
            if failure == 'operator_stop': self.control.stop('operator_stop')
            else:
                self.now.return_value = 1001
                if failure == 'connection_timeout': self.control.tick()
            self.pilot.tick()
            self.assertFalse(self.pilot.active)
            self.assertFalse(self.control.armed)
            self.assertEqual(self.control.outputs,(0,0))
            self.assertEqual(self.pilot.reason, failure)
            self.pilot.stop()

    def test_integration_is_explicit_and_rejects_missing_engine_or_finite_mode(self):
        self.assertFalse(self.pilot.config.crosswalk_gesture)
        for settings in (dict(crosswalk_gesture=True), dict(crosswalk_gesture=True,continuous=True),
                         dict(turn_recovery=1), dict(crosswalk_gesture='true')):
            with self.assertRaises(ValueError): self.pilot.configure(settings)
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))

    def test_auto_and_manual_dispatch_the_same_dc_duty_without_hidden_zeroing(self):
        self.control.arm('manual')
        self.control.input('manual',1,dict(w=True,a=False,s=False,d=False),.221,1,1)
        self.assertEqual([m.value for m in self.motors],[.221,.221])
        self.assertEqual(self.control.motor_write_count,1)
        self.control.stop()
        self.pilot.configure(dict(speed=.221,curve_scale=1,continuous=True))
        self.pilot.start('one')
        self.advance(1000.05)
        self.assertEqual([m.value for m in self.motors],[.221,.221])
        self.assertEqual(self.control.motor_write_count,2)
        self.assertEqual(self.control.reason,'pilot')

    def test_stop_during_wait_never_allows_a_queued_go_to_rearm(self):
        self.enable_crossing()
        self.pilot.stop('operator_stop')
        self.monitor.frame['gesture'] = dict(mode='wait',ready=True,hand_detected=True,
            epoch=1,number=42,received_at=1000.2,decision_label='go')
        self.now.return_value = 1000.2
        self.pilot.tick()
        self.assertFalse(self.control.armed)
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))

    def test_fresh_go_cannot_renew_expired_control_lease_even_if_watchdog_has_not_polled(self):
        self.enable_crossing()
        for i in range(5):
            at=1000.2+i*.1
            self.advance(at,gesture=dict(mode='wait',ready=True,hand_detected=True,
                epoch=1,number=i,received_at=at,decision_label='go'))
        at=1001.4
        self.advance(at,gesture=dict(mode='wait',ready=True,hand_detected=True,
            epoch=1,number=10,received_at=at,decision_label='go'))
        self.assertFalse(self.pilot.active)
        self.assertFalse(self.control.armed)
        self.assertEqual(self.control.reason,'connection_timeout')

    def test_crosswalk_overload_stops_and_engine_failure_prevents_new_start(self):
        self.enable_crossing()
        self.advance(1000.2,crosswalk=dict(reliable=False))
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.pilot.reason,'crosswalk_unavailable')
        self.assertEqual(self.control.outputs,(0,0))
        self.monitor.gesture.snapshot = lambda:dict(initialized=True,error='failed')
        with self.assertRaises(ValueError): self.pilot.start('one')
        self.assertFalse(self.control.armed)

    def test_model_failure_during_run_stops_instead_of_continuing_without_gesture_support(self):
        self.enable_crossing()
        self.monitor.gesture.snapshot = lambda:dict(initialized=True,error='failed')
        self.advance(1000.2)
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.pilot.reason,'gesture_error')
        self.assertEqual(self.control.outputs,(0,0))

    def test_supported_recovery_never_extends_after_single_valid_flicker(self):
        self.pilot.configure(dict(turn_recovery=True,continuous=True))
        self.monitor.frame['path'].update(heading_error_degrees=-30,normalized_error=-.2,source='dash_chain')
        self.pilot.start('one')
        for at in (1000.05,1000.15,1000.25,1000.4): self.advance(at)
        angle = self.pilot.angle
        self.monitor.frame['path']['reason'] = 'insufficient_dashes'
        self.advance(1000.45,valid=False,continuation=dict(supported=True))
        self.assertTrue(self.pilot.recovery.active)
        self.assertEqual(self.pilot.angle, angle)
        self.assertLessEqual(self.control.outputs[0], .26*.8)
        self.advance(1000.5,valid=True)
        self.advance(1000.61,valid=False,continuation=dict(supported=True))
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))

    def test_recovery_cannot_bypass_duplicate_camera_expiry(self):
        self.pilot.configure(dict(turn_recovery=True,continuous=True))
        self.monitor.frame['path'].update(heading_error_degrees=-30,normalized_error=-.2,source='dash_chain')
        self.pilot.start('one')
        for at in (1000.05,1000.15,1000.25,1000.4): self.advance(at)
        self.monitor.frame['path']['reason'] = 'insufficient_dashes'
        self.advance(1000.45,valid=False,continuation=dict(supported=True))
        self.now.return_value = 1000.61
        self.pilot.tick()
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))


class SourceFreshnessTests(unittest.TestCase):
    def test_analysis_size_option_rejects_bad_values_before_hardware(self):
        for value in ('0','319','641'):
            result=subprocess.run([sys.executable,'-B','track_web.py','--analysis-max-side',value],
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2)
            self.assertIn('--analysis-max-side',result.stderr)

    def test_fast_analysis_keeps_native_photo_and_preview_dimensions(self):
        from track_vision import VisionConfig
        monitor=Monitor(None,config=VisionConfig(max_side=480,roi_top=.2),rotation=0,path_enabled=True)
        frame=cv2.resize(sample_track(),(960,720))
        monitor.process_frame(frame,(10,time.monotonic()))
        self.assertEqual(monitor.status()['analysis_size'],[480,360])
        self.assertEqual(monitor.images['raw'].shape,(720,960,3))
        self.assertEqual(monitor.images['processed'].shape,(720,960,3))
        np.testing.assert_array_equal(monitor.images['raw'],frame)

    def test_gesture_receives_same_rotated_resized_capture_before_road_analysis(self):
        from track_vision import analyze
        monitor=Monitor(None,rotation=180)
        offered=[]
        monitor.gesture=SimpleNamespace(set_mode=lambda mode:None,
            offer=lambda frame,number,received:offered.append((frame.copy(),number,received)),
            image=lambda frame:frame.copy(),snapshot=lambda:{})
        frame=cv2.resize(sample_track(),(960,720))
        def inspect(image,config):
            self.assertEqual(len(offered),1)
            self.assertEqual(offered[0][1],10)
            expected=cv2.resize(cv2.rotate(frame,cv2.ROTATE_180),(640,480),interpolation=cv2.INTER_AREA)
            np.testing.assert_array_equal(offered[0][0],expected)
            return analyze(image,config)
        with patch('track_web.analyze',side_effect=inspect):
            monitor.process_frame(frame,(10,time.monotonic()))

    def test_processing_old_input_does_not_make_control_fresh(self):
        monitor = Monitor(None, rotation=0)
        monitor.process_frame(sample_track(), (22,time.monotonic()-1))
        snapshot = monitor.control_snapshot()
        self.assertGreaterEqual(snapshot['age'], 1)
        self.assertEqual(snapshot['source_number'],22)

    def test_optional_gesture_tab_preserves_old_tabs_and_camera_only_has_no_start(self):
        monitor = Monitor(None, rotation=0)
        monitor.gesture = SimpleNamespace(snapshot=lambda:dict(initialized=True,error=None))
        page = create_app(monitor).test_client().get('/').data
        self.assertEqual(page.count(b'data-view='),6)
        self.assertIn(b'data-view="gesture"',page)
        for view in (b'processed', b'raw', b'dashes', b'yellow', b'road'):
            self.assertIn(b'data-view="'+view+b'"',page)
        self.assertNotIn(b'id="auto-start"', page)

    def test_runtime_reports_real_entrypoint_and_no_gpio_in_camera_mode(self):
        monitor = Monitor(None,rotation=0)
        client = create_app(monitor).test_client()
        runtime = client.get('/status').json['runtime']
        self.assertTrue(runtime['entrypoint'].endswith('track_web.py'))
        self.assertFalse(runtime['hardware_enabled'])
        self.assertFalse(runtime['autonomous_panel'])
        self.assertFalse(runtime['gesture_enabled'])

    def test_invalid_pilot_launch_output_is_rejected_before_camera_or_hardware(self):
        for arguments in (['--pilot-speed','.31'],['--pilot-speed','.30']):
            result = subprocess.run([sys.executable,'-B','track_web.py',*arguments],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2)
            self.assertIn('--pilot-speed',result.stderr)
