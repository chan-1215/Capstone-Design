import threading
import time
import unittest
import sys

import numpy as np

from person_detection import LatestFrameDetector, PersonResult
from camera_guard import webcam_guard
from person_detection import PersonInstance


def wait_for(worker, predicate, timeout=2):
    deadline = time.monotonic() + timeout
    with worker.condition:
        while not predicate():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("Worker did not reach the expected state.")
            worker.condition.wait(timeout=remaining)


class LatestFrameDetectorTests(unittest.TestCase):
    def test_slow_detector_uses_only_latest_pending_frame(self):
        started = threading.Event()
        release = threading.Event()
        received = []

        def predict(frame):
            received.append(int(frame[0, 0, 0]))
            if len(received) == 1:
                started.set()
                if not release.wait(timeout=2):
                    raise RuntimeError("Test predictor was not released.")
            return ()

        worker = LatestFrameDetector(predict, interval=0.001)
        worker.start()
        try:
            worker.submit(np.full((2, 2, 3), 1), time.monotonic())
            self.assertTrue(started.wait(timeout=2))
            worker.submit(np.full((2, 2, 3), 2), time.monotonic())
            latest = np.full((2, 2, 3), 3)
            worker.submit(latest, time.monotonic())
            latest.fill(9)
            release.set()
            wait_for(worker, lambda: worker.completed == 2)
            self.assertEqual(received, [1, 3])
        finally:
            release.set()
            worker.close()

    def test_inference_start_rate_is_limited(self):
        starts = []

        def predict(frame):
            starts.append(time.monotonic())
            return ()

        worker = LatestFrameDetector(predict, interval=0.1)
        worker.start()
        try:
            worker.submit(np.zeros((2, 2, 3)), time.monotonic())
            wait_for(worker, lambda: worker.completed == 1)
            worker.submit(np.zeros((2, 2, 3)), time.monotonic())
            wait_for(worker, lambda: worker.completed == 2)
            self.assertGreaterEqual(starts[1] - starts[0], 0.095)
        finally:
            worker.close()

    def test_inference_error_is_reported(self):
        def predict(frame):
            raise RuntimeError("Prediction failed")

        worker = LatestFrameDetector(predict)
        worker.start()
        try:
            worker.submit(np.zeros((2, 2, 3)), time.monotonic())
            wait_for(worker, lambda: worker.error is not None)
            result, error, completed = worker.snapshot()
            self.assertIsNone(result)
            self.assertEqual(error, "Prediction failed")
            self.assertEqual(completed, 0)
        finally:
            worker.close()

    def test_result_age_includes_inference_delay(self):
        result = PersonResult((), captured_at=10.0, inference_ms=1200)
        self.assertTrue(result.is_fresh(10.2))
        self.assertFalse(result.is_fresh(11.2))
        self.assertFalse(result.is_fresh(9.9))

    def test_idle_worker_stops(self):
        worker = LatestFrameDetector(lambda frame: ())
        worker.start()
        worker.close()
        self.assertFalse(worker.thread.is_alive())


class OutlineRenderingTests(unittest.TestCase):
    def test_outline_is_drawn_without_box_or_background_fill(self):
        from run_webcam import draw_person_result

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        person = PersonInstance((200, 200, 300, 300), 0.9,
                                ((200, 300), (250, 200), (300, 300)))
        draw_person_result(frame, PersonResult((person,), 10.0, 30.0), 10.1)
        self.assertGreater(int(frame[200, 250].sum()), 0)
        self.assertEqual(int(frame[250, 200].sum()), 0)
        self.assertEqual(int(frame[260, 250].sum()), 0)

    def test_stale_person_outline_is_hidden(self):
        from run_webcam import draw_person_result

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        person = PersonInstance((200, 200, 300, 300), 0.9,
                                ((200, 300), (250, 200), (300, 300)))
        draw_person_result(frame, PersonResult((person,), 10.0, 30.0), 12.0)
        self.assertEqual(int(frame[180:320, 180:320].sum()), 0)


@unittest.skipUnless(sys.platform == "win32", "Windows camera guard")
class CameraGuardTests(unittest.TestCase):
    def test_duplicate_camera_session_is_rejected(self):
        with webcam_guard(9999):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                with webcam_guard(9999):
                    self.fail("Duplicate camera session was allowed.")

    def test_camera_session_can_restart_after_release(self):
        with webcam_guard(9999):
            pass
        with webcam_guard(9999):
            pass


if __name__ == "__main__":
    unittest.main()
