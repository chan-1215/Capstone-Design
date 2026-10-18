from types import SimpleNamespace
import io
import subprocess
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from camera_source import PiCameraSource, RpicamSource


class CameraSourceTests(unittest.TestCase):
    def open(self, **options):
        camera=Mock()
        source=PiCameraSource(**options)
        with patch.dict('sys.modules',{'picamera2':SimpleNamespace(Picamera2=lambda:camera)}):
            source.start()
        return source,camera

    def test_default_requests_30fps_without_forcing_a_sensor_mode(self):
        source,camera=self.open()
        settings=camera.create_video_configuration.call_args.kwargs
        self.assertEqual(settings['controls']['FrameRate'],30)
        self.assertEqual(settings['main']['size'],(640,480))
        self.assertNotIn('raw',settings)
        self.assertEqual(settings['buffer_count'],3)
        camera.start.assert_called_once()

    def test_full_sensor_mode_does_not_increase_analysis_resolution(self):
        source,camera=self.open(sensor_size=(1640,1232))
        settings=camera.create_video_configuration.call_args.kwargs
        self.assertEqual(settings['raw']['size'],(1640,1232))
        self.assertEqual(settings['main']['size'],(640,480))
        source.stop()
        camera.stop.assert_called_once()
        camera.close.assert_called_once()
        self.assertIsNone(source.camera)

    def test_explicit_15fps_override_still_works(self):
        source,camera=self.open(fps=15)
        self.assertEqual(camera.create_video_configuration.call_args.kwargs['controls']['FrameRate'],15)

    def test_missing_python_binding_uses_os_camera_not_a_different_python(self):
        source = PiCameraSource(960, 720, 30)
        with patch.dict('sys.modules', {'picamera2': None}), patch('camera_source.RpicamSource') as bridge:
            source.start()
        bridge.assert_called_once_with(960, 720, 30, None)
        bridge.return_value.start.assert_called_once()
        self.assertIs(source.read(), bridge.return_value.read.return_value)
        source.stop()
        bridge.return_value.stop.assert_called_once()
        self.assertIsNone(source.bridge)

    def test_unrelated_missing_dependency_is_not_hidden_by_fallback(self):
        import builtins
        original = builtins.__import__

        def importing(name, *args, **kwargs):
            if name == 'picamera2':
                raise ModuleNotFoundError('Missing unrelated module', name='some_dependency')
            return original(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=importing), patch('camera_source.RpicamSource') as bridge:
            with self.assertRaises(ModuleNotFoundError):
                PiCameraSource().start()
        bridge.assert_not_called()


class RpicamSourceTests(unittest.TestCase):
    def jpeg(self, value):
        frame = np.full((24, 32, 3), value, dtype=np.uint8)
        ok, encoded = cv2.imencode('.jpg', frame)
        self.assertTrue(ok)
        return encoded.tobytes()

    def test_command_preserves_capture_settings_and_optional_sensor_mode(self):
        for mode in (None, (1640, 1232)):
            source = RpicamSource(960, 720, 30, mode)
            source.jpeg = self.jpeg(20)
            process = Mock(stdout=io.BytesIO(), stderr=io.BytesIO())
            process.poll.return_value = 0
            with patch('camera_source.shutil.which', return_value='/usr/bin/rpicam-vid'), \
                    patch('camera_source.subprocess.Popen', return_value=process) as popen, \
                    patch('camera_source.threading.Thread'):
                source.start()
            command = popen.call_args.args[0]
            self.assertEqual(command[0], '/usr/bin/rpicam-vid')
            for flag, value in [('--width', '960'), ('--height', '720'), ('--framerate', '30'),
                                ('--codec', 'mjpeg'), ('--quality', '95'), ('--timeout', '0')]:
                self.assertEqual(command[command.index(flag) + 1], value)
            self.assertIn('--flush', command)
            if mode:
                self.assertEqual(command[command.index('--mode') + 1], '1640:1232')
            else:
                self.assertNotIn('--mode', command)
            source.stop()

    def test_latest_frame_replaces_old_frames_and_keeps_bgr_order(self):
        source = RpicamSource(32, 24, 30)
        frame = np.zeros((24, 32, 3), dtype=np.uint8)
        frame[:] = (230, 40, 10)
        source.jpeg = cv2.imencode('.jpg', frame)[1].tobytes()
        source.number = 7
        decoded = source.read()
        self.assertEqual(decoded.shape, (24, 32, 3))
        self.assertGreater(int(decoded[0, 0, 0]), int(decoded[0, 0, 2]) + 150)
        self.assertEqual(source.consumed, 7)
        with patch.object(source.condition, 'wait_for', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'No fresh camera frame'):
                source.read()

    def test_fragmented_stream_is_reassembled_and_eof_invalidates_cached_frame(self):
        source = RpicamSource(32, 24, 30)
        first, latest = self.jpeg(10), self.jpeg(200)
        chunks = [b'noise' + first[:1], first[1:17], first[17:] + latest[:10], latest[10:], b'']
        source.process = Mock()
        source.process.stdout.read.side_effect = chunks
        source._read_pipe()
        self.assertEqual(source.number, 2)
        self.assertEqual(source.jpeg, latest)
        with self.assertRaisesRegex(RuntimeError, 'CSI camera process stopped'):
            source.read()

    def test_malformed_stream_and_bad_decoding_fail_closed(self):
        source = RpicamSource(32, 24, 30)
        source.process = Mock(stdout=io.BytesIO(b'x' * 2_100_000))
        source._read_pipe()
        self.assertIn('oversized', source.error)
        for jpeg in (b'invalid', self.jpeg(10)):
            source = RpicamSource(64, 48, 30)
            source.jpeg = jpeg
            source.number = 1
            with self.assertRaisesRegex(RuntimeError, 'Invalid camera frame'):
                source.read()

    def test_stop_terminates_child_and_wakes_readers_without_replaying(self):
        source = RpicamSource(32, 24, 30)
        process = Mock(stdout=io.BytesIO(), stderr=io.BytesIO())
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('rpicam-vid', 2), 0]
        source.process = process
        source.stop()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertIsNone(source.process)
        with self.assertRaises(RuntimeError):
            source.read()
        source.stop()

    def test_start_timeout_cleans_up_child(self):
        source = RpicamSource(32, 24, 30)
        process = Mock(stdout=io.BytesIO(), stderr=io.BytesIO())
        process.poll.return_value = None
        with patch('camera_source.shutil.which', return_value='rpicam-vid'), \
                patch('camera_source.subprocess.Popen', return_value=process), \
                patch('camera_source.threading.Thread'), \
                patch.object(source.condition, 'wait_for', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '10 seconds'):
                source.start()
        process.terminate.assert_called_once()
        self.assertIsNone(source.process)

    def test_missing_executable_has_actionable_error(self):
        with patch('camera_source.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'rpicam-apps'):
                RpicamSource(32, 24, 30).start()
