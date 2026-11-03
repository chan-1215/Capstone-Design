import unittest
from unittest.mock import patch

import servo_ad_test as app


class FakeServo:
    def __init__(self):
        self.commands = []

    @property
    def angle(self):
        return self.commands[-1]

    @angle.setter
    def angle(self, value):
        self.commands.append(value)

    def detach(self):
        self.commands.append(None)


class ServoTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(app.time, 'monotonic', return_value=0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.servo = FakeServo()
        self.control = app.ServoControl(self.servo)
        self.client = app.create_app(self.control).test_client()

    def send(self, a=False, d=False, client='one', sequence=1):
        return self.client.post('/keys', json=dict(
            a=a, d=d, client=client, sequence=sequence
        ))

    def test_startup_detaches_without_repeating_center(self):
        self.now.return_value = .71
        self.control.check_timeout()
        self.now.return_value = 3
        self.control.check_timeout()
        self.assertEqual(self.servo.commands, [0, None])

    def test_held_key_does_not_restart_pwm(self):
        self.send(a=True)
        for sequence in range(2, 101):
            self.now.return_value = sequence * .1
            self.send(a=True, sequence=sequence)
            self.control.check_timeout()
        self.assertEqual(self.servo.commands, [0, app.A_ANGLE, None])

    def test_short_network_stall_keeps_target(self):
        self.send(d=True)
        self.now.return_value = .6
        self.control.check_timeout()
        self.assertEqual(self.control.angle, app.D_ANGLE)
        self.send(d=True, sequence=2)
        self.assertEqual(self.servo.commands, [0, app.D_ANGLE])

    def test_release_centers_and_then_detaches(self):
        self.send(a=True)
        self.now.return_value = .1
        self.send(sequence=2)
        self.now.return_value = .81
        self.control.check_timeout()
        self.assertEqual(self.servo.commands, [0, app.A_ANGLE, 0, None])

    def test_lost_connection_centers_once(self):
        self.send(d=True)
        self.now.return_value = 1.51
        self.control.check_timeout()
        self.now.return_value = 2.22
        self.control.check_timeout()
        self.now.return_value = 5
        self.control.check_timeout()
        self.assertEqual(self.servo.commands, [0, app.D_ANGLE, 0, None])

    def test_other_tab_cannot_override_active_owner(self):
        self.send(a=True)
        self.send(client='two')
        self.send(d=True, client='two', sequence=2)
        self.assertEqual(self.servo.commands, [0, app.A_ANGLE])
        self.now.return_value = 1.51
        self.control.check_timeout()
        self.assertEqual(self.control.angle, 0)
        self.send(d=True, client='two', sequence=3)
        self.assertEqual(self.control.angle, app.D_ANGLE)

    def test_delayed_and_duplicate_commands_are_ignored(self):
        self.send(a=True, sequence=4)
        self.send(sequence=6)
        self.send(a=True, sequence=5)
        self.send(d=True, sequence=6)
        self.assertEqual(self.servo.commands, [0, app.A_ANGLE, 0])

    def test_both_keys_center(self):
        self.send(d=True)
        self.send(a=True, d=True, sequence=2)
        self.assertEqual(self.control.angle, 0)

    def test_invalid_and_old_page_requests_cannot_move_servo(self):
        self.send(a=True)
        for payload in [None, [], {}, {'a': False, 'd': False},
                        {'a': False, 'd': False, 'client': 'one', 'sequence': True}]:
            self.assertEqual(self.client.post('/keys', json=payload).status_code, 400)
        self.assertEqual(self.servo.commands, [0, app.A_ANGLE])


class CalibrationTests(unittest.TestCase):
    def pulse(self, angle):
        settings = app.servo_parameters()
        ratio = ((angle - settings['min_angle']) /
                 (settings['max_angle'] - settings['min_angle']))
        return (settings['min_pulse_width'] + ratio *
                (settings['max_pulse_width'] - settings['min_pulse_width']))

    def test_asymmetric_targets_are_allowed(self):
        with patch.object(app, 'A_ANGLE', -100), patch.object(app, 'D_ANGLE', 80):
            app.servo_parameters()
            self.assertAlmostEqual(self.pulse(-100), .0009444444444444445)
            self.assertAlmostEqual(self.pulse(80), .0019444444444444444)

    def test_old_center_and_scale_are_preserved(self):
        for angle, expected in [(-90, .001), (0, .0015), (90, .002)]:
            self.assertAlmostEqual(self.pulse(angle), expected)

    def test_reversed_limits_and_out_of_range_are_rejected(self):
        for name, value in [('ANGLE_MIN', 130), ('A_ANGLE', -121),
                            ('D_ANGLE', float('nan'))]:
            with self.subTest(name=name), patch.object(app, name, value):
                with self.assertRaises(ValueError):
                    app.servo_parameters()

    def test_invalid_pulses_are_rejected(self):
        with patch.object(app, 'MAX_PULSE_WIDTH', .0005):
            with self.assertRaises(ValueError):
                app.servo_parameters()


if __name__ == '__main__':
    unittest.main()
