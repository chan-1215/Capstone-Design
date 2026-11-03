import json
from pathlib import Path
import re
import tempfile
import time
import unittest

import cv2
import numpy as np

from media_capture import CaptureStore
from test_track_vision import sample_track
from track_web import Monitor, create_app


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store=CaptureStore(self.directory.name,min_free_bytes=0,max_seconds=2)
        self.addCleanup(self.store.close)
        self.image=np.full((120,160,3),90,np.uint8)

    def test_photo_pair_and_json(self):
        files=self.store.photo(self.image,self.image,{'test':True})
        self.assertEqual(len(files),3)
        for name in files[:2]:
            self.assertEqual(cv2.imread(str(Path(self.directory.name)/name)).shape,self.image.shape)
        self.assertEqual(json.loads((Path(self.directory.name)/files[2]).read_text()),{'test':True})

    def test_lossless_raw_photo_roundtrips_every_pixel_and_is_downloadable(self):
        rng=np.random.default_rng(123)
        raw=rng.integers(0,256,(120,160,3),dtype=np.uint8)
        files=self.store.photo(raw,self.image,{'event':'failure_frame'},lossless_raw=True)
        self.assertTrue(files[0].endswith('_raw.png'))
        self.assertTrue(files[1].endswith('_opencv.jpg'))
        decoded=cv2.imread(str(self.store.root/files[0]))
        np.testing.assert_array_equal(decoded,raw)
        self.assertIn(files[0],[f['path'] for f in self.store.status()['files']])
        client=create_app(Monitor(None),capture=self.store).test_client()
        response=client.get('/media/'+files[0])
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/png')
        response.close()
        self.assertEqual(client.get('/media/photos/../../outside.png').status_code,404)

    def test_mp4_pair_can_be_decoded_after_stop(self):
        self.store.start_video((160,120))
        for index in range(4):
            self.store.next_frame=0
            self.store.offer(self.image,self.image,{'t':index})
        self.store.stop_video()
        status=self.store.status()
        self.assertFalse(status['recording'])
        self.assertIsNone(status['error'])
        self.assertEqual(status['frames'],4)
        for name in status['last_files'][:2]:
            video=cv2.VideoCapture(str(Path(self.directory.name)/name))
            try:
                ok,frame=video.read()
                self.assertTrue(ok)
                self.assertEqual(frame.shape,self.image.shape)
            finally:video.release()

    def test_low_storage_and_duplicate_recording(self):
        self.store.minimum_free=10**18
        with self.assertRaises(OSError):self.store.photo(self.image,self.image,{})
        with self.assertRaises(OSError):self.store.start_video((160,120))
        self.store.minimum_free=0
        self.store.start_video((160,120))
        with self.assertRaises(ValueError):self.store.start_video((160,120))

    def test_native_capture_and_processed_video_have_matching_960_dimensions(self):
        monitor=Monitor(None,rotation=0)
        monitor.capture=self.store
        frame=cv2.resize(sample_track(),(960,720))
        self.store.start_video((960,720))
        for _ in range(2):
            self.store.next_frame=0
            monitor.process_frame(frame)
        self.store.stop_video()
        state=self.store.status()
        self.assertIsNone(state['error'])
        self.assertEqual(state['frames'],2)
        for name in state['last_files'][:2]:
            video=cv2.VideoCapture(str(self.store.root/name))
            try:
                ok,image=video.read()
                self.assertTrue(ok)
                self.assertEqual(image.shape,(720,960,3))
            finally:video.release()

    def test_duration_limit_finishes_without_new_frames(self):
        self.store.max_seconds=.1
        self.store.start_video((160,120))
        deadline=time.monotonic()+2
        while self.store.status()['recording'] and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(self.store.status()['recording'])

    def test_photo_routes_auth_download_and_traversal(self):
        monitor=Monitor(None,rotation=0)
        monitor.process_frame(sample_track())
        client=create_app(monitor,capture=self.store).test_client()
        page=client.get('/').data.decode()
        options=json.loads(re.search(r'window.captureOptions=(.*?);</script>',page).group(1))
        self.assertLess(page.index('id="video"'),page.index('id="capture-photo"'))
        self.assertEqual(client.post('/capture/photo',json={'client':'one'}).status_code,403)
        result=client.post('/capture/photo',json={'client':'one'},headers={'X-Manual-Token':options['token']})
        self.assertEqual(result.status_code,200)
        path=result.json['last_files'][0]
        response=client.get('/media/'+path)
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response.headers['Content-Disposition'])
        response.close()
        self.assertEqual(client.get('/media/../README.md').status_code,404)
        self.assertEqual(client.get('/media/videos/../../README.md').status_code,404)


if __name__=='__main__':unittest.main()
