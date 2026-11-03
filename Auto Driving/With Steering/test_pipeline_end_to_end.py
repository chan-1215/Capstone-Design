"""Image-to-command integration tests with fake GPIO and a fake gesture source."""

import tempfile
import unittest
from unittest.mock import patch

import cv2

from autonomous import AutoPilot
from manual_drive import ManualDrive, DriveConfig
from media_capture import CaptureStore
from test_manual_drive import Motor, Servo
from test_track_vision import sample_track
from track_web import Monitor


class FakeGestureSource:
    def __init__(self):
        self.mode = 'off'
        self.epoch = 0
        self.number = None
        self.received = None
        self.label = 'unknown'

    def set_mode(self, mode):
        if mode != self.mode:
            self.epoch += 1
            self.mode = mode

    def offer(self, frame, number, received):
        self.number, self.received = number, received

    def snapshot(self):
        return dict(initialized=True,error=None,mode=self.mode,epoch=self.epoch,
                    number=self.number,received_at=self.received,decision_label=self.label,
                    label='go',ready=True,hand_detected=True)

    def image(self, frame): return frame.copy()


class PipelineImageTests(unittest.TestCase):
    def setUp(self):
        self.timer = patch('autonomous.time.monotonic', return_value=1000.)
        self.now = self.timer.start()
        self.addCleanup(self.timer.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = CaptureStore(directory.name,min_free_bytes=0)
        self.addCleanup(self.store.close)
        self.monitor = Monitor(None,rotation=0,path_enabled=True)
        self.monitor.gesture = FakeGestureSource()
        self.control = ManualDrive(Servo(),(Motor(),Motor()),DriveConfig(motors_confirmed=True))
        self.pilot = AutoPilot(self.monitor,self.control,self.store)
        self.monitor.pilot, self.monitor.manual = self.pilot,self.control
        self.addCleanup(self.pilot.stop)
        self.number = 0
        for at in (1000.,1000.07,1000.14): self.offer(sample_track(),at,tick=False)
        self.pilot.calibrate()

    def offer(self, image, at, tick=True):
        self.now.return_value = at
        self.number += 1
        self.monitor.process_frame(image,(self.number,at))
        if tick:
            self.pilot.heartbeat('one')
            self.pilot.tick()
            self.control.tick()

    def crossing(self):
        image = sample_track()
        for x in (160,225,355,420):
            cv2.rectangle(image,(x,205),(x+28,330),(245,245,245),-1)
        return image

    def test_actual_colour_masks_crossing_pause_unknown_go_depart_and_stop(self):
        self.pilot.configure(dict(crosswalk_gesture=True,continuous=True))
        self.pilot.start('one')
        for at in (1000.22,1000.29,1000.36):
            self.offer(self.crossing(),at)
        self.assertTrue(self.monitor.crosswalk['stop'],self.monitor.crosswalk)
        self.assertTrue(self.pilot.crossing.waiting,self.pilot.reason)
        self.assertEqual(self.control.outputs,(0,0))
        self.assertIsNone(self.control.servo.angle)
        for at in (1000.43,1000.50): self.offer(self.crossing(),at)
        self.assertTrue(self.pilot.crossing.waiting)
        self.assertEqual(self.monitor.gesture.mode,'wait')
        self.assertEqual(self.control.outputs,(0,0))
        self.monitor.gesture.label='go'
        for i in range(8): self.offer(self.crossing(),1000.6+i*.1)
        self.assertTrue(self.pilot.active,self.pilot.reason)
        self.assertEqual(self.pilot.crossing.state,'depart')
        self.assertGreater(self.control.outputs[0],0)
        for i in range(8): self.offer(sample_track(),1001.4+i*.1)
        self.assertEqual(self.pilot.crossing.state,'follow')
        self.pilot.stop('operator_stop')
        self.offer(self.crossing(),1002.2)
        self.assertFalse(self.pilot.active)
        self.assertFalse(self.control.armed)
        self.assertEqual(self.control.outputs,(0,0))

    def test_no_crossing_has_no_automatic_pause_and_unknown_gesture_never_arms(self):
        self.pilot.configure(dict(crosswalk_gesture=True,continuous=True))
        for i in range(5): self.offer(sample_track(),1000.2+i*.1)
        self.assertFalse(self.pilot.active)
        self.assertFalse(self.control.armed)
        self.pilot.start('one')
        for i in range(5): self.offer(sample_track(),1000.7+i*.1)
        self.assertEqual(self.pilot.crossing.state,'follow')
        self.assertGreater(self.control.outputs[0],0)
