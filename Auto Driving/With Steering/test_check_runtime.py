import io
import json
import unittest
from unittest.mock import patch

from check_runtime import summarize, collect


class RuntimeCheckTests(unittest.TestCase):
    def sample(self, number=1):
        return dict(camera_online=True,error=None,runtime=dict(python_version='3.11.17',hardware_enabled=False),
                    source_frame_number=number,source_age_seconds=.05,fps=22,
                    gesture=dict(initialized=True,error=None,decision_label='unknown'))

    def test_preview_without_hardware_is_healthy_without_any_hand(self):
        self.assertTrue(summarize([self.sample(1),self.sample(2)],True)['ok'])

    def test_active_output_model_error_wrong_python_and_stale_input_fail(self):
        for kind in ('armed','output','pwm','pilot','model','python','stale','camera','hardware'):
            sample = self.sample()
            if kind == 'armed': sample['manual'] = dict(armed=True)
            elif kind == 'output': sample['manual'] = dict(motor_outputs=[.26,.26])
            elif kind == 'pwm': sample['manual'] = dict(pwm_active=True)
            elif kind == 'pilot': sample['autonomous'] = dict(active=True)
            elif kind == 'model': sample['gesture']['error'] = 'bad model'
            elif kind == 'python': sample['runtime']['python_version'] = '3.13.0'
            elif kind == 'stale': sample['source_age_seconds'] = .3
            elif kind == 'camera': sample['camera_online'] = False
            else: sample['runtime']['hardware_enabled'] = True
            self.assertFalse(summarize([sample],True)['ok'],kind)

    def test_repeated_frame_numbers_are_not_healthy_live_video(self):
        self.assertIn('camera_not_advancing',summarize([self.sample(),self.sample()])['problems'])

    def test_collector_only_uses_read_only_status_get(self):
        with patch('check_runtime.urllib.request.urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps(self.sample()).encode())) as request, patch('check_runtime.time.sleep'):
            self.assertEqual(len(collect('http://127.0.0.1:5001',2)),2)
        for call in request.call_args_list:
            self.assertEqual(call.args,('http://127.0.0.1:5001/status',))
            self.assertNotIn('data',call.kwargs)
