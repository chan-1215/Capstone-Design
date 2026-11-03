from collections import deque
import threading
import time
import unittest

import numpy as np

from worker import GestureWorker, fresh_decision, caption


class FakeRecognizer:
    sequence_length = 3
    min_hand_ratio = .6

    def __init__(self, entered=None, release=None, label='go'):
        for name in ('hand_buffer','hand_valid_buffer','raw_points_buffer','prediction_buffer'):
            setattr(self, name, deque(maxlen=3))
        self.entered, self.release, self.label = entered, release, label
        self.processed = []
        self.closed = False

    def process(self, frame):
        number = int(frame[0,0,0]); self.processed.append(number)
        if self.entered and number == 1:
            self.entered.set(); self.release.wait(timeout=2)
        self.hand_buffer.append(np.zeros(63))
        self.hand_valid_buffer.append(True)
        self.raw_points_buffer.append(np.zeros((21,3)))
        return dict(label='go', raw_label='go', hand_detected=True,
                    distance=1., debug_frame=frame.copy())

    def make_feature(self): return np.zeros(189)
    def predict_knn(self, feature): return self.label, 1.
    def close(self): self.closed = True


class GestureAdapterTests(unittest.TestCase):
    def wait(self, predicate):
        until = time.monotonic()+3
        while not predicate() and time.monotonic() < until:
            time.sleep(.005)
        self.assertTrue(predicate())

    def start(self, recognizer=None, factory=None):
        recognizer = recognizer or FakeRecognizer()
        worker = GestureWorker(factory=factory or (lambda:recognizer), fps=1000)
        worker.start()
        self.addCleanup(worker.close)
        self.wait(lambda:worker.initialized or worker.error)
        return worker, recognizer

    def offer(self, worker, number):
        worker.offer(np.full((12,12,3),number,np.uint8), number, time.monotonic())

    def test_direct_unknown_cannot_be_replaced_by_held_or_smoothed_go(self):
        recognizer = FakeRecognizer(label='unknown')
        result = None
        for _ in range(3): result = recognizer.process(np.zeros((12,12,3),np.uint8))
        self.assertEqual(fresh_decision(recognizer, result), ('unknown', True))
        result['hand_detected'] = False
        self.assertEqual(fresh_decision(recognizer, result), ('unknown', False))

    def test_latest_only_queue_and_shutdown(self):
        entered, release = threading.Event(), threading.Event()
        worker, recognizer = self.start(FakeRecognizer(entered,release))
        worker.set_mode('preview'); self.offer(worker, 1)
        self.assertTrue(entered.wait(1))
        self.offer(worker, 2); self.offer(worker, 3)
        release.set()
        self.wait(lambda:worker.snapshot().get('number') == 3)
        self.assertEqual(recognizer.processed, [1,3])
        worker.close()
        self.assertTrue(recognizer.closed)
        self.assertFalse(worker.thread.is_alive())

    def test_epoch_reset_rejects_inflight_result_and_requires_new_full_sequence(self):
        entered, release = threading.Event(), threading.Event()
        worker, recognizer = self.start(FakeRecognizer(entered,release))
        worker.set_mode('preview'); self.offer(worker, 1)
        self.assertTrue(entered.wait(1))
        worker.set_mode('wait'); release.set()
        self.offer(worker, 2)
        self.wait(lambda:worker.snapshot().get('number') == 2)
        result = worker.snapshot()
        self.assertEqual(result['mode'], 'wait')
        self.assertFalse(result['ready'])
        self.assertEqual(len(recognizer.hand_buffer), 1)
        for number in (3,4):
            self.offer(worker, number)
            self.wait(lambda:worker.snapshot().get('number') == number)
        self.assertTrue(worker.snapshot()['ready'])
        self.assertEqual(worker.snapshot()['inference_frames'],3)
        worker.set_mode('off')
        self.offer(worker, 5); time.sleep(.02)
        self.assertNotIn(5, recognizer.processed)
        self.assertFalse(worker.snapshot()['ready'])

    def test_stale_result_and_initialization_failure_are_never_ready(self):
        worker, _ = self.start()
        worker.set_mode('wait')
        with worker.condition:
            worker.result = dict(received_at=time.monotonic()-1, decision_label='go', ready=True, hand_detected=True)
        self.assertFalse(worker.snapshot()['ready'])
        def fail(): raise RuntimeError('broken model')
        failed, _ = self.start(factory=fail)
        self.assertIn('broken model', failed.snapshot()['error'])
        self.assertFalse(failed.snapshot()['ready'])

    def test_freshness_metric_and_pending_overlay_do_not_show_stale_go(self):
        worker, _ = self.start()
        worker.set_mode('wait')
        with worker.condition:
            worker.result=dict(received_at=time.monotonic()-1,decision_label='go',ready=True,
                               hand_detected=True,debug_frame=np.full((100,500,3),255,np.uint8))
        result=worker.snapshot()
        self.assertGreaterEqual(result['result_age_seconds'],1)
        self.assertEqual(result['decision_label'],'unknown')
        fallback=np.zeros((100,500,3),np.uint8)
        expected=caption(fallback.copy(),'unknown','WAIT | Result pending')
        np.testing.assert_array_equal(worker.image(fallback),expected)
        self.assertFalse(np.any(fallback))
