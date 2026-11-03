import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from analyze_photos import read_image, write_image
from compare_vision import benchmark, compare, file_sha256, frames, html_report, raw_input, reason_label
from test_track_vision import sample_track


class CompareVisionTests(unittest.TestCase):
    def test_raw_guard_rejects_screen_recordings_and_missing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("screen.mp4", "photo_opencv.png", "frame.jpg"):
                path = root/name
                path.touch()
                with self.assertRaises(ValueError):
                    raw_input(path)
            with self.assertRaises(ValueError):
                raw_input(root/"missing_raw.png")
            path = root/"camera_raw.png"
            write_image(path, sample_track())
            self.assertEqual(raw_input(path), path.resolve())

    def test_report_is_independent_offline_and_preserves_unicode_raw_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/"\uc6d0\ubcf8_raw.png"
            frame = sample_track()
            write_image(source, frame)
            before = file_sha256(source)
            output = root/"comparison"
            report = compare([source, source], output, sizes=(320,), blurs=(0, 5),
                             repeats=1, reference=.5, lap=True, joint=True)
            self.assertFalse(report["hardware_access"])
            self.assertFalse(report["physical_calibration_verified"])
            self.assertEqual(report["summary"]["frames"], 2)
            self.assertEqual(report["summary"]["profiles"], 2)
            self.assertEqual(file_sha256(source), before)
            first, second = report["records"]
            self.assertEqual(first["current"]["prediction"], second["current"]["prediction"])
            self.assertEqual(first["source_sha256"], before)
            self.assertEqual(first["decoded_bgr_sha256"],
                             hashlib.sha256(frame.tobytes()).hexdigest())
            self.assertEqual(len(report["source_hashes"]), 6)
            saved = json.loads((output/"report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            html = (output/"index.html").read_text(encoding="utf-8")
            self.assertIn('lang="ko"', html)
            self.assertIn("검출 개수는 정확도가 아닙니다", html)
            self.assertIn("모터 제어 없음", html)
            self.assertIn("실시간 영상 아님", html)
            self.assertIn("단계별 처리 결과", html)
            self.assertNotIn('alt="Five pipeline stages"', html)
            self.assertNotIn('_comparison.png"', html)
            self.assertNotIn("two_sides", html)
            images = []
            class Images(HTMLParser):
                def handle_starttag(self, tag, attrs):
                    if tag == "img":
                        images.append(dict(attrs)["src"])
            Images().feed(html)
            self.assertEqual(len(images), 28)
            self.assertTrue(all((output/name).is_file() for name in images))
            self.assertEqual(read_image(output/"frame_0000_comparison.png").shape, (840, 960, 3))
            for candidate in first["candidates"]:
                self.assertFalse(candidate["metrics"]["drive_authorized"])
                self.assertTrue((output/candidate["stages"]).is_file())
                self.assertEqual(candidate["timing"]["repeats"], 1)
            first["source_name"] = "<script>alert(1)</script>_raw.png"
            localized = html_report(report["records"], report["summary"])
            self.assertNotIn("<script>", localized)
            self.assertIn("&lt;script&gt;", localized)

    def test_unknown_reason_has_korean_fallback(self):
        self.assertEqual(reason_label("no_segments"), "선분 미검출")
        self.assertEqual(reason_label("future_reason"), "추가 확인 필요")

    def test_invalid_configuration_and_existing_output_do_not_modify_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/"source_raw.png"
            write_image(source, sample_track())
            for options in (
                {"joint": True}, {"sizes": ()}, {"blurs": (3, 3)},
                {"repeats": 0}, {"repeats": True}, {"max_frames": 0},
                {"sample_seconds": float("nan")},
                {"reference": 1}, {"roi_top": .95},
            ):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    compare([source], root/"new_report", **options)
                self.assertFalse((root/"new_report").exists())
            with self.assertRaises(ValueError):
                compare([source], root)
            with self.assertRaises(ValueError):
                compare([], root/"new_report")
            self.assertEqual(list(root.iterdir()), [source])

    def test_benchmark_excludes_warmup_and_returns_last_result(self):
        calls = []
        def run():
            calls.append(len(calls))
            return calls[-1]
        result, timing = benchmark(run, 3)
        self.assertEqual(len(calls), 4)
        self.assertEqual(result, 3)
        self.assertEqual(timing["repeats"], 3)
        self.assertLessEqual(timing["min_ms"], timing["median_ms"])
        self.assertLessEqual(timing["median_ms"], timing["max_ms"])

    def test_video_sampling_has_bounded_frame_count_and_releases_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"video_raw.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10., (64, 48))
            if not writer.isOpened():
                self.skipTest("MJPG encoder unavailable")
            try:
                for index in range(12):
                    writer.write(np.full((48, 64, 3), index*15, np.uint8))
            finally:
                writer.release()
            decoded = list(frames(path, .5, 2))
            self.assertEqual([item[0] for item in decoded], [0, 5])
            self.assertEqual([item[1] for item in decoded], [0., .5])
            self.assertGreater(decoded[1][2].mean(), decoded[0][2].mean())
            path.unlink()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
