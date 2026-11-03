import csv
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

import cv2
import numpy as np

from build_manual_dataset import action, stable_actions
from build_raw_session_dataset import build
from imitation_features import FEATURE_SIZE, features
from imitation_runtime import ImitationModel
from road_camera_web import build_app
from road_drive_web import DriveController
from shadow_manual_model import mjpeg_frames


class ImitationLearningTest(unittest.TestCase):
    def test_new_manual_recording_uses_shared_crop(self):
        frame = np.full((1364, 1266, 3), 220, np.uint8)
        self.assertEqual(features(frame, screen_recording=True).shape,
                         (FEATURE_SIZE[0] * FEATURE_SIZE[1],))

    def test_shadow_stream_reads_complete_jpeg_frames(self):
        stream = io.BytesIO(b"--frame\r\nContent-Type: image/jpeg\r\n"
                            b"Content-Length: 3\r\n\r\nabc\r\n"
                            b"--frame\r\nContent-Length: 2\r\n\r\nde\r\n")
        self.assertEqual(list(mjpeg_frames(stream)), [b"abc", b"de"])

    def test_manual_labels_exclude_reverse_and_ambiguous_buttons(self):
        self.assertEqual(action(dict(w=True, a=True, s=False, d=False)), -1)
        self.assertEqual(action(dict(w=True, a=False, s=False, d=True)), 1)
        self.assertEqual(action(dict(w=True, a=False, s=False, d=False)), 0)
        self.assertIsNone(action(dict(w=False, a=True, s=False, d=False)))
        self.assertIsNone(action(dict(w=True, a=True, s=True, d=False)))
        self.assertIsNone(action(dict(w=True, a=True, s=False, d=True)))
        self.assertEqual(stable_actions([0, 0, 0, 1, 1, 1], radius=1),
                         [0, 0, None, None, 1, 1])

    def test_runtime_reads_export_without_training_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.npz"
            count = FEATURE_SIZE[0] * FEATURE_SIZE[1]
            coef = np.zeros((3, count), np.float32)
            np.savez_compressed(path, coef=coef,
                                intercept=np.array([0, 0, 4], np.float32),
                                mean=np.zeros(count, np.float32),
                                scale=np.ones(count, np.float32),
                                classes=np.array([-1, 0, 1], np.int8),
                                min_probability=np.float32(0.75),
                                validated=np.bool_(True))
            model = ImitationModel(path)
            command, confidence = model.predict(np.full((480, 640, 3), 220, np.uint8))
            self.assertEqual(command, 1)
            self.assertGreater(confidence, 0.95)
            np.savez_compressed(path, coef=coef,
                                intercept=np.array([0, 0, 4], np.float32),
                                mean=np.zeros(count, np.float32),
                                scale=np.ones(count, np.float32),
                                classes=np.array([-1, 0, 1], np.int8),
                                min_probability=np.float32(0.75),
                                validated=np.bool_(False))
            with self.assertRaisesRegex(ValueError, "not validated"):
                ImitationModel(path)

    def test_raw_session_filters_uncertain_and_transition_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "session_test"
            session.mkdir()
            frame = np.full((480, 640, 3), 230, np.uint8)
            cv2.line(frame, (130, 130), (130, 430), (15, 15, 15), 12)
            cv2.line(frame, (510, 130), (510, 430), (15, 15, 15), 12)
            with (session / "frames.csv").open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(("file", "pi_frame_at", "throttle", "steer",
                                 "command_age", "manual_valid", "pc_received_at"))
                for index, steer in enumerate([-1] * 5 + [0] * 5 + [1] * 5):
                    filename = f"{index:06d}.jpg"
                    cv2.imwrite(str(session / filename), frame)
                    writer.writerow((filename, index * 0.1, 1, steer, 0.05, 1, index))
            dataset, manifest, counts = build(session, Path(directory) / "output")
            self.assertTrue(manifest.exists())
            self.assertEqual(counts, {-1: 4, 0: 3, 1: 4})
            with np.load(dataset, allow_pickle=False) as data:
                self.assertEqual(data["x"].shape, (11, FEATURE_SIZE[0] * FEATURE_SIZE[1]))

    def test_record_endpoint_labels_the_frame_time(self):
        timestamp = time.monotonic()
        camera = SimpleNamespace(condition=threading.Condition(), frame=b"jpeg",
                                 frame_at=timestamp)
        monitor = SimpleNamespace(camera=camera)
        driver = DriveController(monitor)
        driver.mode = "manual"
        driver.manual_events.append((timestamp - 0.05, 1, -1.0))
        response = build_app(monitor, driver).test_client().get("/record/sample")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"jpeg")
        self.assertEqual(response.headers["X-Throttle"], "1")
        self.assertEqual(response.headers["X-Steer"], "-1.0")
        self.assertEqual(response.headers["X-Manual-Valid"], "1")
        self.assertEqual(driver.manual_state_at(timestamp + 0.5)[3], False)

    def test_collection_mode_disables_autonomous_routes(self):
        camera = SimpleNamespace(condition=threading.Condition(), frame=b"jpeg",
                                 frame_at=time.monotonic())
        monitor = SimpleNamespace(camera=camera)
        driver = DriveController(monitor)
        client = build_app(monitor, driver, manual_only=True).test_client()
        for route in ("/drive/start", "/drive/straight", "/drive/recover/right"):
            self.assertEqual(client.post(route).status_code, 403)


if __name__ == "__main__":
    unittest.main()
