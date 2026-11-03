from html.parser import HTMLParser
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from manual_drive import DriveConfig, ManualDrive
from test_manual_drive import Servo, Motor
from test_track_vision import sample_track
from track_web import Monitor, create_app, draw_control_hud


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.elements = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
            self.elements[attrs['id']] = (tag, attrs)


class ControlDisplayTests(TestCase):
    def test_panels_and_all_control_ids_are_unique(self):
        from autonomous import AutoPilot
        drive = ManualDrive(Servo(), (Motor(), Motor()), DriveConfig(motors_confirmed=True))
        monitor = Monitor(None, rotation=0, path_enabled=True)
        pilot = AutoPilot(monitor, drive, Mock())
        page = create_app(monitor, manual=drive, pilot=pilot).test_client().get('/').data.decode()
        parser = Elements()
        parser.feed(page)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertNotIn('manual-enabled', parser.elements)
        for id in ('manual-left-angle', 'manual-right-angle', 'manual-stop', 'drive-speed', 'motor1-scale', 'motor2-scale',
                   'auto-start', 'auto-stop', 'auto-reference', 'camera', 'roi', 'dashLegend'):
            self.assertIn(id, parser.elements)
        self.assertEqual(parser.elements['manual-panel'][1]['role'], 'tabpanel')
        self.assertNotIn('hidden', parser.elements['manual-panel'][1])
        self.assertIn('hidden', parser.elements['auto-panel'][1])
        self.assertLess(page.index('id="manual-panel"'), page.index('카메라 인식 · 통계'))

    def test_hud_is_left_of_inset_and_does_not_cover_near_road(self):
        for width, height in ((320, 240), (480, 360), (640, 480)):
            image = np.full((height, width, 3), 127, np.uint8)
            before = image.copy()
            control = dict(angle=-105, armed=True, keys={'w':True, 'a':True}, motor_outputs=[.3, .27])
            draw_control_hud(image, control)
            self.assertFalse(np.array_equal(image[:30, :width//2], before[:30, :width//2]))
            np.testing.assert_array_equal(image[int(height*.2):], before[int(height*.2):])
            np.testing.assert_array_equal(image[:, width*2//3:], before[:, width*2//3:])

    def test_video_hud_and_metadata_share_command_sample_raw_is_unchanged(self):
        drive = ManualDrive(Servo(), (Motor(), Motor()), DriveConfig(motors_confirmed=True))
        drive.arm('test')
        drive.input('test', 1, dict(w=True, s=False, a=False, d=True), .3, 1, .9)
        monitor = Monitor(None, rotation=0)
        monitor.manual = drive
        monitor.capture = Mock()
        frame = cv2.resize(sample_track(), (960, 720))
        before = frame.copy()
        with patch('track_web.draw_control_hud', wraps=draw_control_hud) as draw:
            monitor.process_frame(frame, (5, 123.))
        raw, processed, metadata = monitor.capture.offer.call_args.args
        np.testing.assert_array_equal(raw, before)
        np.testing.assert_array_equal(frame, before)
        self.assertFalse(np.array_equal(processed[:60], raw[:60]))
        self.assertEqual(metadata['control'], draw.call_args.args[1])
        self.assertTrue(metadata['control']['keys']['w'])
        self.assertTrue(metadata['control']['keys']['d'])
        self.assertIn('control_observed_at', metadata)

    def test_diagnostics_keep_settings_of_published_frame_not_pending_edits(self):
        monitor=Monitor(None,rotation=0,path_enabled=True)
        monitor.path_tracker.reference_heading=-2.43
        monitor.process_frame(sample_track())
        original=monitor.control_snapshot()['vision_settings']
        self.assertEqual(original['roi_top'],.2)
        self.assertEqual(original['rotation'],0)
        monitor.settings({'roi_top':.4,'white_min_value':200})
        self.assertEqual(monitor.control_snapshot()['vision_settings'],original)
        self.assertEqual(monitor.telemetry()['vision_settings'],original)
        original['white_min_value']=1
        self.assertNotEqual(monitor.control_snapshot()['vision_settings']['white_min_value'],1)
        monitor.process_frame(sample_track())
        self.assertEqual(monitor.control_snapshot()['vision_settings']['roi_top'],.4)
