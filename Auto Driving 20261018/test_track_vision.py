import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import cv2
import numpy as np

from track_vision import VisionConfig, analyze, overlay, _markings
from analyze_photos import read_image, write_image, report_html


def sample_track():
    image = np.full((400, 600, 3), 210, dtype=np.uint8)
    cv2.rectangle(image, (120, 20), (480, 380), (45, 45, 45), cv2.FILLED)
    cv2.rectangle(image, (120, 20), (480, 380), (0, 230, 255), 6)
    for y in (65, 145, 225, 305):
        cv2.rectangle(image, (290, y), (302, y + 36), (245, 245, 245), cv2.FILLED)
    return image


class TrackVisionTests(unittest.TestCase):
    def test_separates_dark_road_and_yellow_and_white(self):
        result = analyze(sample_track())
        self.assertEqual(result.metrics["status"], "markings_detected")
        self.assertEqual(result.road[200, 200], 255)
        self.assertEqual(result.road[200, 50], 0)
        self.assertEqual(result.yellow[200, 120], 255)
        self.assertEqual(result.white[80, 296], 255)
        self.assertEqual(result.white[200, 120], 0)
        self.assertEqual(result.metrics["dash_candidate_count"], 4)

    def test_white_background_is_not_a_lane(self):
        result = analyze(np.full((300, 400, 3), 255, dtype=np.uint8))
        self.assertEqual(result.metrics["status"], "no_yellow_boundary")
        self.assertFalse(np.any(result.road))
        self.assertFalse(np.any(result.white))

    def test_dark_background_without_boundaries_is_not_a_road(self):
        result = analyze(np.full((300, 400, 3), 45, dtype=np.uint8))
        self.assertFalse(np.any(result.road))
        self.assertIsNone(result.metrics["target_path"])
        self.assertFalse(result.metrics["control_enabled"])

    def test_bright_nonroad_object_is_not_a_marking(self):
        image = sample_track()
        cv2.rectangle(image, (30, 80), (45, 160), (255, 255, 255), cv2.FILLED)
        result = analyze(image)
        self.assertFalse(np.any(result.white[:, :100]))

    def test_without_markings_does_not_invent_a_path(self):
        image = sample_track()
        image[30:370, 280:315] = 45
        result = analyze(image)
        self.assertEqual(result.metrics["status"], "road_only")
        self.assertEqual(result.metrics["dash_candidate_count"], 0)
        self.assertIsNone(result.metrics["target_path"])

    def test_excluded_roi_stays_empty(self):
        result = analyze(sample_track(), VisionConfig(roi_top=0.5))
        for mask in (result.road, result.yellow, result.white, result.dashes):
            self.assertFalse(np.any(mask[:200]))
        self.assertEqual(result.road[250, 200], 255)

    def test_large_nearby_road_is_not_rejected_for_its_size(self):
        image = np.full((400, 600, 3), 45, dtype=np.uint8)
        cv2.rectangle(image, (5, 5), (594, 394), (0, 230, 255), 5)
        result = analyze(image)
        self.assertGreater(result.metrics["road_fraction"], 0.85)

    def test_distant_yellow_object_not_displayed_as_road_boundary(self):
        image = sample_track()
        cv2.rectangle(image, (20, 40), (60, 80), (0, 230, 255), cv2.FILLED)
        result = analyze(image)
        self.assertFalse(np.any(result.yellow[30:90, 10:70]))

    def test_no_input_mutation(self):
        image = sample_track()
        before = image.copy()
        result = analyze(image)
        self.assertTrue(np.array_equal(image, before))
        self.assertEqual(overlay(result).shape, image.shape)

    def test_analysis_size_limit_and_source_dimensions(self):
        result = analyze(sample_track(), VisionConfig(max_side=300))
        self.assertEqual(result.frame.shape, (200, 300, 3))
        self.assertEqual(result.metrics["original_size"], [600, 400])
        self.assertEqual(result.metrics["analysis_size"], [300, 200])

    def test_invalid_input_and_config(self):
        for image in (None, np.zeros((5, 5, 3), np.uint8),
                      np.zeros((100, 100), np.uint8), np.zeros((100, 100, 3), float)):
            with self.assertRaises(ValueError):
                analyze(image)
        for options in ({"roi_top": 1}, {"max_side": 0},
                        {"white_min_value": -1}, {"yellow_hue_low": 50}):
            with self.assertRaises(ValueError):
                VisionConfig(**options)


class DashFilterTests(unittest.TestCase):
    def test_small_threshold_notches_are_closed_before_shape_measurement(self):
        mask = np.zeros((400,600), np.uint8)
        cv2.rectangle(mask, (250,300), (278,380), 255, cv2.FILLED)
        for y in range(305,375,5):
            mask[y:y+2, 253:279] = 0
        _, dashes, markings = _markings(mask)
        self.assertTrue(markings[0]['dash_candidate'])
        self.assertGreater(markings[0]['fill_ratio'], .9)
        self.assertEqual(dashes[330,265], 255)

    def test_gap_repair_does_not_join_separate_dashes_or_accept_thin_seams(self):
        mask = np.zeros((400,600), np.uint8)
        cv2.rectangle(mask, (250,220), (264,260), 255, cv2.FILLED)
        cv2.rectangle(mask, (250,290), (270,350), 255, cv2.FILLED)
        cv2.line(mask, (400,200), (400,380), 255, 2)
        _, dashes, markings = _markings(mask)
        self.assertEqual(sum(m['dash_candidate'] for m in markings), 2)
        self.assertFalse(np.any(dashes[263:288,240:280]))
        self.assertFalse(np.any(dashes[:,395:405]))

    def test_large_nearby_dash_is_retained(self):
        mask = np.zeros((400, 600), np.uint8)
        cv2.rectangle(mask, (250, 300), (280, 380), 255, cv2.FILLED)
        _, dashes, markings = _markings(mask)
        self.assertEqual(markings[0]["dash_basis"], "shape")
        self.assertEqual(dashes[340, 265], 255)

    def test_same_large_patch_far_away_is_not_a_dash(self):
        mask = np.zeros((400, 600), np.uint8)
        cv2.rectangle(mask, (250, 20), (280, 100), 255, cv2.FILLED)
        white, dashes, _ = _markings(mask)
        self.assertTrue(np.any(white))
        self.assertFalse(np.any(dashes))

    def test_compact_dashes_need_repeated_spatial_support(self):
        mask = np.zeros((400, 600), np.uint8)
        for y in (50, 85, 120):
            cv2.rectangle(mask, (280, y), (290, y + 14), 255, cv2.FILLED)
        _, _, markings = _markings(mask)
        self.assertEqual(len(markings), 3)
        self.assertTrue(all(m["dash_candidate"] for m in markings))
        self.assertTrue(all(m["dash_basis"] == "sequence" for m in markings))

    def test_isolated_or_unaligned_compact_patches_are_rejected(self):
        mask = np.zeros((400, 600), np.uint8)
        for x, y in ((50, 50), (280, 85), (500, 120)):
            cv2.rectangle(mask, (x, y), (x + 10, y + 14), 255, cv2.FILLED)
        _, dashes, _ = _markings(mask)
        self.assertFalse(np.any(dashes))


class FileWorkflowTests(unittest.TestCase):
    def test_unicode_image_and_report_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / ("track_" + chr(0xD55C) + chr(0xAE00) + ".png")
            write_image(source, sample_track())
            self.assertTrue(np.array_equal(read_image(source), sample_track()))
            output = root / "report"
            command = [sys.executable, str(Path(__file__).with_name("analyze_photos.py")),
                       str(source), "--output", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["records"]), 1)
            self.assertFalse(report["records"][0]["metrics"]["control_enabled"])
            self.assertEqual(report["records"][0]["metrics"]["dash_candidate_count"], 4)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "photo_01_overlay.jpg").is_file())

    def test_report_escapes_source_names(self):
        record = {"name": '<script>alert("x")</script>', "prefix": "photo_01",
                  "metrics": {"status": "road_only", "white_marking_count": 0,
                              "dash_candidate_count": 0}}
        html = report_html([record])
        self.assertNotIn('<script>alert', html)
        self.assertIn('&lt;script&gt;', html)

    def test_video_headless_without_camera(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "track.avi"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"),
                                     10, (600, 400))
            if not writer.isOpened():
                self.skipTest("MJPG encoder unavailable")
            try:
                for _ in range(5):
                    writer.write(sample_track())
            finally:
                writer.release()
            command = [sys.executable, str(Path(__file__).with_name("preview.py")),
                       "--video", str(video), "--headless", "--frames", "3"]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["frames"], 3)
            self.assertEqual(result["frames_with_candidates"], 3)
            self.assertFalse(result["control_enabled"])


if __name__ == "__main__":
    unittest.main()
