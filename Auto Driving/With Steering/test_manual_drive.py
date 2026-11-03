import json
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from manual_drive import DriveConfig, ManualDrive, open_hardware
from test_track_vision import sample_track
from track_web import Monitor, create_app


class Servo:
    def __init__(self):
        self.commands = []

    @property
    def angle(self):
        return self.commands[-1] if self.commands else None

    @angle.setter
    def angle(self, value):
        self.commands.append(value)

    def detach(self):
        self.commands.append(None)


class Motor:
    def __init__(self):
        self.value = 0

    def stop(self):
        self.value = 0


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch('manual_drive.time.monotonic', return_value=100)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.servo = Servo()
        self.motors = (Motor(), Motor())
        self.drive = ManualDrive(self.servo, self.motors, DriveConfig(motors_confirmed=True))

    def send(self, sequence=1, speed=.2, trim1=1, trim2=1, left_angle=None, right_angle=None, **held):
        self.drive.input('one', sequence, {key:held.get(key, False) for key in 'wsad'},
                         speed, trim1, trim2, left_angle, right_angle)

    def test_idle_manual_steering_settings_do_not_move_hardware(self):
        self.drive.arm('one')
        self.send(left_angle=30, right_angle=25)
        self.assertEqual(self.servo.commands, [])
        self.assertEqual(self.drive.outputs, (0, 0))
        self.assertEqual(self.drive.status()['left_angle'], 30)
        self.assertEqual(self.drive.status()['right_angle'], 25)

    def test_manual_steering_is_independent_asymmetric_and_does_not_reduce_speed(self):
        self.drive.arm('one')
        self.send(w=True, a=True, left_angle=30, right_angle=25, speed=.3)
        self.assertEqual(self.servo.angle, -30)
        self.assertEqual(self.drive.outputs, (.3, .3))
        self.send(sequence=2, w=True, d=True, speed=.3)
        self.assertEqual(self.servo.angle, 25)
        self.assertEqual(self.drive.outputs, (.3, .3))
        self.send(sequence=3)
        self.assertEqual(self.servo.angle, 0)
        self.assertEqual(self.drive.outputs, (0, 0))
        self.drive.follow('one', 4, 85, .26)
        self.assertEqual(self.servo.angle, 85)
        self.assertEqual(self.drive.status()['right_angle'], 25)
        self.assertEqual((self.drive.config.a_angle, self.drive.config.d_angle), (-105, 85))

    def test_zero_manual_steering_and_opposing_keys_are_neutral(self):
        self.drive.arm('one')
        self.send(a=True, left_angle=0, right_angle=0)
        self.assertEqual(self.servo.angle, 0)
        self.send(sequence=2, d=True)
        self.assertEqual(self.servo.angle, 0)
        self.send(sequence=3, a=True, d=True, left_angle=30, right_angle=40)
        self.assertEqual(self.servo.angle, 0)

    def test_invalid_manual_angles_never_change_outputs_or_saved_values(self):
        self.drive.arm('one')
        for values in (dict(left_angle=106), dict(right_angle=86), dict(left_angle=-1),
                       dict(right_angle=float('inf')), dict(left_angle=float('nan')),
                       dict(left_angle=True), dict(right_angle='30')):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.send(w=True, a=True, **values)
        self.assertEqual(self.servo.commands, [])
        self.assertEqual(self.drive.outputs, (0, 0))
        self.assertEqual((self.drive.left_angle, self.drive.right_angle), (105, 85))

    def test_stale_foreign_expired_and_disarmed_requests_cannot_change_manual_angles(self):
        with self.assertRaises(PermissionError):
            self.send(left_angle=30)
        self.drive.arm('one')
        self.send(sequence=3, left_angle=30, right_angle=40)
        for sequence in (2, 3):
            self.send(sequence=sequence, left_angle=90, right_angle=80)
        with self.assertRaises(PermissionError):
            self.drive.input('other', 4, dict.fromkeys('wsad', False), .2, 1, 1, 10, 10)
        self.assertEqual((self.drive.left_angle, self.drive.right_angle), (30, 40))
        self.now.return_value = 100.71
        with self.assertRaises(PermissionError):
            self.send(sequence=4, left_angle=90, right_angle=80)
        self.assertEqual((self.drive.left_angle, self.drive.right_angle), (30, 40))
        self.assertFalse(self.drive.armed)

    def test_custom_angle_heartbeat_does_not_restart_servo_pwm(self):
        self.drive.arm('one')
        self.send(a=True, left_angle=30)
        for sequence in range(2, 22):
            self.now.return_value = 100 + sequence / 10
            self.send(sequence=sequence, a=True, left_angle=30)
            self.drive.tick()
        self.assertEqual(self.servo.commands, [-30, None])

    def test_timeout_diagnostic_is_written_after_motor_stop(self):
        self.drive.arm('one')
        self.send(w=True)
        self.now.return_value = 100.71
        def recorded(*args):
            self.assertEqual(self.drive.outputs, (0, 0))
            self.assertFalse(self.drive.armed)
            self.assertEqual(args[2], 'connection_timeout')
            self.assertAlmostEqual(args[3], .71)
        with patch('manual_drive.logging.getLogger') as logger:
            logger.return_value.warning.side_effect = recorded
            self.drive.tick()
            logger.return_value.warning.assert_called_once()

    def test_startup_arm_and_idle_do_not_move_servo(self):
        self.assertEqual(self.servo.commands, [])
        self.drive.arm('one')
        self.send()
        self.assertEqual(self.servo.commands, [])
        self.assertEqual(self.drive.outputs, (0, 0))

    def test_w_plus_d_and_independent_trims(self):
        self.drive.arm('one')
        self.send(w=True, d=True, trim1=1.2, trim2=.8)
        self.assertEqual(self.servo.angle, 85)
        for actual, expected in zip(self.drive.outputs, (.24, .16)):
            self.assertAlmostEqual(actual, expected)
        for motor, expected in zip(self.motors, (.24, .16)):
            self.assertAlmostEqual(motor.value, expected)

    def test_recorded_keys_are_copied_and_stale_input_cannot_replace_them(self):
        self.drive.arm('one')
        self.send(sequence=3, w=True, a=True)
        state = self.drive.status()
        self.assertEqual(state['keys'], dict(w=True, s=False, a=True, d=False))
        self.assertEqual(state['command_sequence'], 3)
        state['keys']['w'] = False
        self.send(sequence=2, d=True)
        self.assertTrue(self.drive.status()['keys']['w'])
        self.assertTrue(self.drive.status()['keys']['a'])
        with self.assertRaises(PermissionError):
            self.drive.input('other', 4, dict(w=False, s=True, a=False, d=True), .3, 1, 1)
        self.assertTrue(self.drive.status()['keys']['a'])

    def test_stop_pause_and_pilot_clear_manual_keys(self):
        self.drive.arm('one')
        self.send(w=True, d=True)
        self.drive.follow('one', 2, 20, .26)
        self.assertFalse(any(self.drive.status()['keys'].values()))
        self.send(sequence=3, w=True)
        self.drive.pause('one', 4)
        self.assertFalse(any(self.drive.status()['keys'].values()))
        self.send(sequence=5, a=True)
        self.drive.stop()
        self.assertFalse(any(self.drive.status()['keys'].values()))
        self.drive.arm('one')
        self.assertFalse(any(self.drive.status()['keys'].values()))

    def test_a_and_release(self):
        self.drive.arm('one')
        self.send(a=True)
        self.assertEqual(self.servo.angle, -105)
        self.send(sequence=2)
        self.assertEqual(self.servo.angle, 0)

    def test_heartbeat_does_not_restart_servo_pwm(self):
        self.drive.arm('one')
        self.send(a=True)
        for sequence in range(2, 22):
            self.now.return_value = 100 + sequence / 10
            self.send(sequence=sequence, a=True)
            self.drive.tick()
        self.assertEqual(self.servo.commands, [-105, None])

    def test_unknown_dc_wiring_leaves_outputs_zero(self):
        drive = ManualDrive(self.servo)
        drive.arm('one')
        drive.input('one', 1, dict(w=True, s=False, a=False, d=True), .3, 1, 1)
        self.assertFalse(drive.status()['motors_enabled'])
        self.assertEqual(drive.outputs, (0, 0))
        self.assertEqual(self.servo.angle, 85)

    def test_timeout_detaches_without_centering_and_disarms(self):
        self.drive.arm('one')
        self.send(w=True, d=True)
        self.now.return_value = 100.71
        self.drive.tick()
        self.assertEqual(self.drive.outputs, (0, 0))
        self.assertEqual(self.servo.commands, [85, None])
        self.assertFalse(self.drive.armed)
        with self.assertRaises(PermissionError):
            self.send(sequence=2, w=True)

    def test_late_input_cannot_renew_expired_lease_before_watchdog_polls(self):
        self.drive.arm('one')
        self.send(w=True)
        self.now.return_value = 100.71
        with self.assertRaises(PermissionError): self.send(sequence=2,w=True)
        self.assertFalse(self.drive.armed)
        self.assertEqual(self.drive.outputs,(0,0))
        self.assertEqual(self.drive.reason,'connection_timeout')

    def test_late_follow_and_pause_cannot_cross_deadline_without_watchdog_tick(self):
        for action in ('follow','pause'):
            self.now.return_value = 100
            self.drive.arm('auto')
            self.drive.set_deadline('auto',100.1)
            self.now.return_value = 100.11
            with self.assertRaises(PermissionError):
                if action == 'follow': self.drive.follow('auto',1,20,.26)
                else: self.drive.pause('auto',1)
            self.assertFalse(self.drive.armed)
            self.assertEqual(self.drive.outputs,(0,0))
            self.assertEqual(self.drive.reason,'time_limit')

    def test_estop_and_stale_packets_cannot_restart(self):
        self.drive.arm('one')
        self.send(w=True, sequence=3)
        self.send(sequence=4)
        self.send(w=True, sequence=2)
        self.assertEqual(self.drive.outputs, (0, 0))
        self.drive.stop()
        with self.assertRaises(PermissionError):
            self.send(w=True, sequence=5)

    def test_second_browser_cannot_take_control_or_cancel_owner(self):
        self.drive.arm('one')
        self.send(w=True)
        with self.assertRaises(PermissionError):
            self.drive.arm('two')
        self.drive.stop(client='two')
        self.assertTrue(self.drive.armed)
        self.assertNotEqual(self.drive.outputs, (0, 0))

    def test_simultaneous_opposite_keys_stop_and_speed_is_capped(self):
        self.drive.arm('one')
        self.send(w=True, speed=.5, trim1=1.5, trim2=1.5)
        self.assertEqual(self.drive.outputs, (.5, .5))
        self.send(sequence=2, w=True, s=True, a=True, d=True)
        self.assertEqual(self.drive.outputs, (0, 0))
        self.assertEqual(self.servo.angle, 0)

    def test_invalid_commands_do_not_touch_hardware(self):
        self.drive.arm('one')
        for values in [dict(speed=float('nan')), dict(trim1=2), dict(speed=-1), dict(sequence=True)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.send(**values)
        self.assertEqual(self.servo.commands, [])

    def test_verified_forward_and_backward_polarities(self):
        self.drive.arm('one')
        self.send(w=True)
        self.assertEqual(self.drive.outputs, (.2, .2))
        with patch('manual_drive.time.sleep'):
            self.send(sequence=2, s=True)
        self.assertEqual(self.drive.outputs, (-.2, -.2))

    def test_w_plus_a_uses_full_a_angle_without_turn_speed_ratio(self):
        self.drive.arm('one')
        self.send(w=True, a=True, speed=.3)
        self.assertEqual(self.servo.angle, -105)
        self.assertEqual(self.drive.outputs, (.3, .3))
        self.send(sequence=2, w=True, d=True, speed=.3)
        self.assertEqual(self.servo.angle, 85)
        self.assertEqual(self.drive.outputs, (.3, .3))
        self.send(sequence=3, speed=.3)
        self.assertEqual(self.drive.outputs, (0, 0))
        self.assertEqual(self.servo.angle, 0)

    def test_hardware_error_stops_other_devices(self):
        self.drive.arm('one')
        with patch.object(self.motors[0], 'stop', side_effect=RuntimeError('test fault')):
            self.drive.stop()
        self.assertEqual(self.motors[1].value, 0)
        self.assertIsNone(self.servo.angle)
        self.assertFalse(self.drive.armed)
        self.assertIn('test fault', self.drive.error)

    def test_gpio_factory_does_not_construct_unconfirmed_motors(self):
        servo, motor, factory = Mock(), Mock(), Mock()
        modules = {'gpiozero':SimpleNamespace(AngularServo=servo, Motor=motor),
                   'gpiozero.pins.lgpio':SimpleNamespace(LGPIOFactory=factory)}
        with patch.dict(sys.modules, modules):
            control = open_hardware(DriveConfig())
            motor.assert_not_called()
            self.assertIsNone(servo.call_args.kwargs['initial_angle'])
            control.close()

    def test_invalid_configuration_is_rejected(self):
        for values in [dict(a_angle=-121), dict(motor1_pins=(18, 20)),
                       dict(max_speed=float('nan')), dict(motor2_direction=0)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                DriveConfig(**values)


class ManualWebTests(unittest.TestCase):
    def setUp(self):
        self.monitor = Monitor(None, rotation=0)
        self.monitor.process_frame(sample_track())
        self.drive = ManualDrive(Servo())
        self.client = create_app(self.monitor, self.drive).test_client()
        page = self.client.get('/').data.decode()
        self.options = json.loads(re.search(r'window.manualOptions=(.*?);</script>', page).group(1))

    def post(self, action, **values):
        return self.client.post('/manual/' + action, json=dict(client='one', **values),
                                headers={'X-Manual-Token':self.options['token']})

    def test_manual_page_preserves_five_tabs_and_locked_motors(self):
        page = self.client.get('/').data
        self.assertEqual(page.count(b'data-view='), 5)
        self.assertIn(b'/static/manual.js', page)
        self.assertFalse(self.options['motors_enabled'])
        self.assertFalse(self.client.get('/status').json['control_enabled'])
        self.assertIn(b'id="manual-left-angle"', page)
        self.assertIn(b'id="manual-right-angle"', page)
        self.assertEqual((self.options['left_angle'], self.options['right_angle']), (105, 85))

    def test_http_manual_angles_are_bounded_and_roundtrip_without_widening_limits(self):
        self.post('arm')
        values = dict(sequence=1, keys=dict(w=False, s=False, a=True, d=False),
                      speed=.2, motor1_scale=1, motor2_scale=1, left_angle=35, right_angle=20)
        response = self.post('input', **values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['angle'], -35)
        self.assertEqual(response.json['left_angle'], 35)
        self.assertEqual(response.json['right_angle'], 20)
        self.assertEqual(response.json['a_angle'], -105)
        self.assertEqual(response.json['d_angle'], 85)
        self.assertEqual(self.post('input', **dict(values, sequence=2, right_angle=86)).status_code, 400)
        self.assertEqual(self.drive.angle, -35)
        self.assertEqual(self.drive.status()['right_angle'], 20)

    def test_authentication_arming_and_input(self):
        self.assertEqual(self.client.post('/manual/arm', json={'client':'one'}).status_code, 403)
        self.assertEqual(self.post('arm').status_code, 200)
        self.assertEqual(self.post('input', sequence=1, keys=dict(w=False,s=False,a=True,d=False),
                                   speed=.2,motor1_scale=1,motor2_scale=1).json['angle'], -105)
        self.assertEqual(self.post('input', sequence=2, keys=[], speed=.2,
                                   motor1_scale=1,motor2_scale=1).status_code, 400)
        self.assertEqual(self.post('stop', emergency=True).status_code, 200)
        self.assertFalse(self.drive.armed)

    def test_stale_camera_cannot_arm(self):
        self.monitor.last_frame_at -= 3
        self.assertEqual(self.post('arm').status_code, 503)
        self.assertFalse(self.drive.armed)

    def test_confirmed_motor_page_and_forward_over_unconfirmed_road(self):
        import numpy as np

        self.monitor.process_frame(np.full((480, 640, 3), 255, dtype=np.uint8))
        drive = ManualDrive(Servo(), (Motor(), Motor()), DriveConfig(motors_confirmed=True))
        client = create_app(self.monitor, drive).test_client()
        page = client.get('/').data.decode()
        options = json.loads(re.search(r'window.manualOptions=(.*?);</script>', page).group(1))
        self.assertTrue(options['motors_enabled'])
        self.assertEqual(options['speed'], .3)
        headers = {'X-Manual-Token':options['token']}
        self.assertEqual(client.post('/manual/arm', json={'client':'one'}, headers=headers).status_code, 200)
        response = client.post('/manual/input', headers=headers, json=dict(
            client='one', sequence=1, keys=dict(w=True, s=False, a=False, d=True),
            speed=.3, motor1_scale=1, motor2_scale=1))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['motor_outputs'], [.3, .3])
        self.assertEqual(response.json['angle'], 85)
        state = client.get('/status').json
        self.assertTrue(state['camera_online'])
        self.assertEqual(state['road_fraction'], 0)
        self.assertTrue(state['control_enabled'])
        client.post('/manual/stop', headers=headers, json={'client':'one','emergency':True})
        self.assertEqual(drive.outputs, (0, 0))
        self.assertFalse(drive.armed)


if __name__ == '__main__':
    unittest.main()
