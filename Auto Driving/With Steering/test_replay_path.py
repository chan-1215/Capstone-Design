import json
from pathlib import Path
import tempfile
import unittest

import cv2

from replay_path import review, raw_image, validate_reference
from test_track_vision import sample_track


class ReplayPathTests(unittest.TestCase):
    def test_screen_and_processed_images_cannot_be_used_as_raw_stills(self):
        for name in ('screen.mp4','manual_screen.png','photo_opencv.jpg','frame.jpg'):
            with self.assertRaises(ValueError):raw_image(name)
        self.assertEqual(raw_image('photo_raw.png'),Path('photo_raw.png'))
        for reference,heading in ((float('nan'),0),(.5,float('inf')),(0,0),(1,0),(None,10)):
            with self.assertRaises(ValueError):validate_reference(reference,heading)

    def test_independent_replay_is_repeatable_and_records_evidence_not_accuracy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source_raw.png'
            cv2.imwrite(str(source),sample_track())
            report=review([source,source],root/'report',reference=.5,lap_mode=True,joint_guidance=True)
            self.assertFalse(report['hardware_access'])
            self.assertEqual(report['kind'],'independent_raw_stills')
            self.assertEqual(report['records'][0]['selected'],report['records'][1]['selected'])
            self.assertEqual(report['records'][0]['decoded_bgr_sha256'],report['records'][1]['decoded_bgr_sha256'])
            self.assertEqual(set(report['source_hashes']),
                             {'track_vision.py', 'lane_path.py', 'boundary_guidance.py', 'crosswalk.py'})
            saved=json.loads((root/'report/report.json').read_text())
            self.assertEqual(saved['summary']['images'],2)
            self.assertTrue((root/'report'/saved['records'][0]['preview']).is_file())
            self.assertTrue(source.is_file())

    def test_source_directory_and_invalid_profile_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source_raw.png'
            cv2.imwrite(str(source),sample_track())
            with self.assertRaises(ValueError):review([source],root)
            with self.assertRaises(ValueError):review([source],root/'report',joint_guidance=True)
            with self.assertRaises(ValueError):review([],root/'report')
            self.assertEqual(list(root.iterdir()),[source])


if __name__=='__main__':unittest.main()
