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

    def send(self, sequence=1, speed=.2, trim1=1, trim2=1, **held):
        self.drive.input('one', sequence, {key:held.get(key, False) for key in 'wsad'},
                         speed, trim1, trim2)

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
        self.assertEqual(page.count(b'role="tab"'), 5)
        self.assertIn(b'/static/manual.js', page)
        self.assertFalse(self.options['motors_enabled'])
        self.assertFalse(self.client.get('/status').json['control_enabled'])

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
