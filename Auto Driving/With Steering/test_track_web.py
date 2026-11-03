import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import cv2
import numpy as np

from test_track_vision import sample_track
from track_web import Monitor, create_app


class TrackWebTests(unittest.TestCase):
    def setUp(self):
        self.monitor = Monitor(None, rotation=0)
        self.client = create_app(self.monitor).test_client()

    def test_page_has_old_style_and_no_drive_controls(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'background:#101214', response.data)
        self.assertIn(b'/stream/processed', response.data)
        self.assertEqual(response.data.count(b'role="tab"'), 5)
        for view in (b'processed', b'raw', b'dashes', b'yellow', b'road'):
            self.assertIn(b'data-view="' + view + b'"', response.data)
        self.assertNotIn(b'data-view="lines"', response.data)
        self.assertNotIn(b'id="road"', response.data)
        for route in ("/drive/start", "/drive/manual", "/drive/stop"):
            self.assertEqual(self.client.post(route).status_code, 404)

    def test_missing_frame_is_not_online(self):
        self.assertFalse(self.client.get("/status").json["camera_online"])
        self.assertEqual(self.client.get("/snapshot/raw.jpg").status_code, 503)

    def test_images_and_status(self):
        self.monitor.process_frame(sample_track())
        status = self.client.get("/status").json
        self.assertTrue(status["camera_online"])
        self.assertFalse(status["control_enabled"])
        self.assertIsNone(status["target_path"])
        for view in ("raw", "processed", "lines", "road", "yellow", "white", "dashes"):
            response = self.client.get(f"/snapshot/{view}.jpg")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.startswith(b'\xff\xd8'))
        self.assertEqual(self.client.get("/snapshot/unknown.jpg").status_code, 404)

    def test_native_detail_survives_while_analysis_remains_small(self):
        frame=cv2.resize(sample_track(),(960,720),interpolation=cv2.INTER_NEAREST)
        frame[300:340,10:30]=np.indices((40,20)).sum(axis=0)[:,:,None]%2*255
        expected=frame.copy()
        self.monitor.process_frame(frame)
        images=self.monitor.images
        self.assertEqual(images['raw'].shape,(720,960,3))
        self.assertEqual(images['processed'].shape,(720,960,3))
        self.assertEqual(images['lines'].shape,(480,640,3))
        self.assertEqual(self.monitor.metrics['analysis_size'],[640,480])
        self.assertEqual(self.monitor.metrics['original_size'],[960,720])
        np.testing.assert_array_equal(images['raw'],expected)
        np.testing.assert_array_equal(images['processed'][300:340,10:30],expected[300:340,10:30])
        frame[:]=0
        np.testing.assert_array_equal(images['raw'],expected)
        for view in ('raw','processed'):
            data=self.client.get('/snapshot/'+view+'.jpg').data
            self.assertEqual(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR).shape,(720,960,3))

    def test_native_output_preserves_rotation_and_matching_capture_sizes(self):
        from unittest.mock import Mock
        frame=cv2.resize(sample_track(),(960,720))
        self.monitor.rotation=180
        self.monitor.capture=Mock()
        self.monitor.process_frame(frame)
        np.testing.assert_array_equal(self.monitor.images['raw'],cv2.rotate(frame,cv2.ROTATE_180))
        raw,processed,_=self.monitor.capture.offer.call_args.args
        self.assertEqual(raw.shape,processed.shape)
        self.assertEqual(raw.shape,(720,960,3))

    def test_stale_frame_is_not_online_or_sent(self):
        self.monitor.process_frame(sample_track())
        self.monitor.last_frame_at = time.monotonic() - 3
        self.assertFalse(self.client.get("/status").json["camera_online"])
        self.assertEqual(self.client.get("/snapshot/raw.jpg").status_code, 503)

    def test_inset_and_combined_tab_use_the_same_mask(self):
        self.monitor.process_frame(sample_track())
        images = self.monitor.images
        height, width = images["processed"].shape[:2]
        inset_width = width // 3
        inset_height = round(height * inset_width / width)
        expected = cv2.resize(images["lines"], (inset_width, inset_height),
                              interpolation=cv2.INTER_NEAREST)
        inset = images["processed"][1:inset_height, width - inset_width + 1:width - 1]
        self.assertTrue(np.array_equal(inset, expected[1:, 1:-1]))
        self.assertEqual(self.monitor.status()["inset_view"], "lines")

    def test_combined_mask_has_yellow_and_white_but_no_road_fill(self):
        self.monitor.process_frame(sample_track())
        lines = self.monitor.images["lines"]
        self.assertTrue(np.array_equal(lines[200, 120], [0, 215, 255]))
        self.assertTrue(np.array_equal(lines[160, 296], [255, 255, 255]))
        self.assertFalse(np.any(lines[200, 200]))
        self.assertTrue(np.any(self.monitor.images["road"]))

    def test_processed_road_pixels_keep_original_colour(self):
        original = sample_track()
        self.monitor.process_frame(original)
        self.assertTrue(np.array_equal(self.monitor.images["processed"][200, 200], original[200, 200]))

    def test_roi_border_follows_setting_without_changing_raw_or_masks(self):
        original = sample_track()
        for fraction in (0.2, 0.4):
            self.monitor.settings({"roi_top": fraction})
            self.monitor.process_frame(original)
            row = int(original.shape[0] * fraction)
            self.assertTrue(np.array_equal(self.monitor.images["processed"][row, 200], [200, 200, 200]))
            self.assertTrue(np.array_equal(self.monitor.images["raw"], original))
            self.assertFalse(np.any(self.monitor.images["lines"][row, 200]))

    def test_settings_are_validated_and_atomic(self):
        self.assertEqual(self.client.post("/settings", json={"roi_top": 0.3, "rotation": 0}).status_code, 200)
        for body in ({"roi_top": 1}, {"rotation": 90}, {"white_min_value": -1},
                     {"yellow_min_saturation": True}, {"speed": 0.2}, [], {}):
            self.assertEqual(self.client.post("/settings", json=body).status_code, 400)
        self.assertEqual(self.monitor.config.roi_top, 0.3)

    def test_stream_returns_jpeg_and_closes(self):
        self.monitor.process_frame(sample_track())
        response = self.client.get("/stream/processed", buffered=False)
        part = next(response.response)
        self.assertIn(b'Content-Type: image/jpeg', part)
        self.assertIn(b'\xff\xd8', part)
        self.assertIn(b'Content-Length: ', part)
        self.assertEqual(self.monitor.status()['preview_clients'], 1)
        response.close()
        self.assertEqual(self.monitor.status()['preview_clients'], 0)

    def test_jpeg_encoding_is_shared_for_concurrent_clients(self):
        self.monitor.process_frame(sample_track())
        with patch('track_web.cv2.imencode', wraps=cv2.imencode) as encode:
            with ThreadPoolExecutor(max_workers=3) as pool:
                data = list(pool.map(self.monitor.jpeg, ['processed'] * 3))
            self.assertTrue(all(item == data[0] for item in data))
            self.assertEqual(encode.call_count, 1)
            self.monitor.jpeg('raw')
            self.assertEqual(encode.call_count, 2)
            self.monitor.process_frame(sample_track())
            self.monitor.jpeg('processed')
            self.assertEqual(encode.call_count, 3)
        self.assertEqual(len(self.monitor.jpeg_cache), 1)

    def test_warm_cache_does_not_bypass_freshness_errors_or_stop(self):
        for failure in ('stale', 'error', 'stop'):
            monitor = Monitor(None, rotation=0)
            monitor.process_frame(sample_track())
            self.assertIsNotNone(monitor.jpeg('raw'))
            if failure == 'stale':
                monitor.last_frame_at = time.monotonic() - 3
            elif failure == 'error':
                monitor.error = 'camera failed'
            else:
                monitor.stop_event.set()
            self.assertIsNone(monitor.jpeg('raw'))

    def test_encode_error_is_not_cached(self):
        self.monitor.process_frame(sample_track())
        with patch('track_web.cv2.imencode', return_value=(False, None)):
            self.assertIsNone(self.monitor.jpeg('raw'))
        self.assertEqual(self.monitor.jpeg_cache, {})
        self.assertIsNotNone(self.monitor.jpeg('raw'))

    def test_preview_rate_does_not_limit_vision_or_recording_and_skips_old_images(self):
        from unittest.mock import Mock
        self.client = create_app(self.monitor, preview_fps=10).test_client()
        self.monitor.capture = Mock()
        self.monitor.process_frame(sample_track())
        response = self.client.get('/stream/raw', buffered=False)
        next(response.response)
        started = time.monotonic()
        for _ in range(3):
            self.monitor.process_frame(sample_track())
        part = next(response.response)
        self.assertGreaterEqual(time.monotonic() - started, .085)
        self.assertEqual(self.monitor.frame_number, 4)
        self.assertEqual(self.monitor.capture.offer.call_count, 4)
        self.assertIn(self.monitor.jpeg('raw'), part)
        response.close()
        self.assertEqual(self.monitor.status()['preview_fps_limit'], 10)

    def test_preview_options_and_independent_camera_delivery_statistics(self):
        from unittest.mock import Mock
        self.monitor.source = Mock()
        self.monitor.source.stats.return_value = {'backend':'rpicam-vid', 'delivery_fps':30.0,
                                                'delivery_frames':100}
        self.monitor.process_frame(sample_track())
        data = self.client.get('/status').json
        self.assertEqual(data['camera_delivery']['delivery_fps'], 30.0)
        self.assertEqual(data['preview_fps_limit'], 30)
        for invalid in (True, 0, -1, 31, '15', None):
            with self.assertRaises(ValueError):
                create_app(self.monitor, preview_fps=invalid)

    def test_preview_budget_includes_encoding_without_catchup_bursts(self):
        for encode_seconds in (.01, .06):
            with self.subTest(encode_seconds=encode_seconds):
                clock=[100.]
                waits=[]
                monitor=Monitor(None,rotation=0)
                monitor.frame_number=1
                def wait(delay):
                    waits.append(delay)
                    clock[0]+=delay
                    return False
                def encode(view):
                    clock[0]+=encode_seconds
                    return b'jpeg'
                with patch('track_web.time.monotonic',side_effect=lambda:clock[0]), \
                        patch.object(monitor.stop_event,'wait',side_effect=wait), \
                        patch.object(monitor,'jpeg',side_effect=encode):
                    response=create_app(monitor,preview_fps=30).test_client().get(
                        '/stream/raw',buffered=False)
                    next(response.response)
                    previous=clock[0]
                    for _ in range(2):
                        monitor.frame_number+=1
                        next(response.response)
                        self.assertAlmostEqual(clock[0]-previous,max(1/30,encode_seconds))
                        self.assertAlmostEqual(waits[-1],max(0.,1/30-encode_seconds))
                        previous=clock[0]
                    response.close()
                self.assertEqual(monitor.preview_clients,0)

    def test_page_keeps_stream_logic_separate_and_names_all_frame_rates(self):
        page = self.client.get('/').data
        self.assertIn(b'/static/preview.js', page)
        self.assertIn(b'id="camera-fps"', page)
        self.assertIn(b'id="preview-fps"', page)
        self.assertIn('처리 후 경과'.encode('utf-8'), page)
        self.assertIn(b'window.trackPreview.select', page)
        self.assertNotIn(b"get('video').src=", page)


if __name__ == "__main__":
    unittest.main()
