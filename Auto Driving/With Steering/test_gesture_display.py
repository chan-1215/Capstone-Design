import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from track_web import Monitor, create_app


class GestureDisplayTests(unittest.TestCase):
    def test_display_exists_below_video_even_when_gesture_is_disabled(self):
        app=create_app(Monitor(None))
        client=app.test_client()
        page=client.get('/').data.decode()
        self.assertLess(page.index('id="video"'),page.index('id="display-title"'))
        self.assertIn('디스플레이',page)
        self.assertIn('window.gestureDisplayOptions={enabled:false}',page)
        self.assertEqual(client.get('/gesture/status').json,{'available':False,'gesture':None})

    def test_display_route_only_reads_worker_and_has_no_motion_dispatch(self):
        monitor=Monitor(None)
        monitor.gesture=SimpleNamespace(snapshot=Mock(return_value=dict(
            initialized=True,ready=True,hand_detected=True,decision_label='stop',
            mode='preview',result_age_seconds=.05)))
        app=create_app(monitor)
        # The lightweight route must not ask the camera or full pilot/control status.
        monitor.status=Mock(side_effect=AssertionError('Unexpected camera/control query'))
        result=app.test_client().get('/gesture/status')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['gesture']['decision_label'],'stop')
        self.assertEqual(result.headers['Cache-Control'],'no-store')
        self.assertEqual(app.test_client().post('/gesture/status').status_code,405)

    def test_native_gif_assets_and_pedestrian_mapping(self):
        root=Path(__file__).resolve().parent
        app=create_app(Monitor(None));client=app.test_client()
        page=client.get('/').data.decode()
        self.assertIn('data-go-src="/static/signals/vehicle_go_red.gif"',page)
        self.assertIn('data-stop-src="/static/signals/vehicle_stop_green.gif"',page)
        for name in ('vehicle_go_red.gif','vehicle_stop_green.gif'):
            data=(root/'static/signals'/name).read_bytes()
            self.assertIn(data[:6],(b'GIF87a',b'GIF89a'))
            self.assertEqual(struct.unpack('<HH',data[6:10]),(1050,450))
            response=client.get('/static/signals/'+name)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'image/gif')
            self.assertEqual(hashlib.sha256(response.data).digest(),hashlib.sha256(data).digest())
            response.close()


if __name__=='__main__':unittest.main()
