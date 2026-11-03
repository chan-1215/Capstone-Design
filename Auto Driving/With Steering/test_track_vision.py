import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import cv2
import numpy as np

from track_vision import VisionConfig, analyze, overlay, combined_lines, _markings, _restore_white_paint
from analyze_photos import read_image, write_image, report_html


def sample_track():
    image = np.full((400, 600, 3), 210, dtype=np.uint8)
    cv2.rectangle(image, (120, 20), (480, 380), (45, 45, 45), cv2.FILLED)
    cv2.rectangle(image, (120, 20), (480, 380), (0, 230, 255), 6)
    for y in (65, 145, 225, 305):
        cv2.rectangle(image, (290, y), (302, y + 36), (245, 245, 245), cv2.FILLED)
    return image


class TrackVisionTests(unittest.TestCase):
    def test_fast_colour_and_signed_contrast_masks_match_original_formulas(self):
        frame=sample_track()
        rng=np.random.default_rng(103)
        noise=rng.integers(-12,13,frame.shape,dtype=np.int16)
        frame=np.clip(frame.astype(np.int16)+noise,0,255).astype(np.uint8)
        for value,saturation,contrast in ((175,80,16),(0,255,0),(255,0,255)):
            config=VisionConfig(white_min_value=value,white_max_saturation=saturation,
                                white_min_contrast=contrast)
            with patch('track_vision._restore_white_paint',wraps=_restore_white_paint) as restore:
                result=analyze(frame,config)
            seed,support=restore.call_args.args
            hsv=cv2.cvtColor(result.frame,cv2.COLOR_BGR2HSV)
            interior=cv2.erode(result.road,np.ones((3,3),np.uint8))>0
            expected=interior & (hsv[:,:,2]>=value) & (hsv[:,:,1]<=saturation)
            gray=cv2.cvtColor(result.frame,cv2.COLOR_BGR2GRAY)
            delta=gray.astype(np.int16)-cv2.GaussianBlur(gray,(0,0),7).astype(np.int16)
            np.testing.assert_array_equal(support,np.where(expected,255,0).astype(np.uint8))
            np.testing.assert_array_equal(seed,np.where(expected & (delta>=contrast),255,0).astype(np.uint8))

    def test_fast_combined_preview_matches_colours_and_overlap_priority(self):
        result=analyze(sample_track())
        result.dashes[30:50,120:130]=255
        expected=np.zeros_like(result.frame)
        expected[result.yellow>0]=(0,215,255)
        expected[result.dashes>0]=(255,255,255)
        np.testing.assert_array_equal(combined_lines(result),expected)

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


class OpenRoadRegionTests(unittest.TestCase):
    def open_track(self):
        image = sample_track()
        # Break the far yellow boundary, joining the road to the exterior mat.
        image[15:27, 275:325] = 210
        return image

    def test_open_boundary_keeps_observed_road_and_dashes_not_white_floor(self):
        for flip in (False, True):
            image = self.open_track()
            if flip:
                image = cv2.flip(image, 1)
            result = analyze(image)
            self.assertEqual(result.road[200, 200], 255)
            self.assertFalse(np.any(result.road[:, :100]))
            self.assertFalse(np.any(result.road[:, 500:]))
            self.assertFalse(np.any(result.road[:12]))
            self.assertEqual(result.metrics['dash_candidate_count'], 4)
            self.assertGreater(np.count_nonzero(result.yellow[:, 470:490]), 100)

    def test_no_yellow_or_only_one_side_cannot_recover_dark_patch(self):
        for mode in ('none', 'one_side', 'short_contacts'):
            image = self.open_track()
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            yellow = cv2.inRange(hsv, (18, 55, 95), (42, 255, 255)) > 0
            image[yellow] = 210
            if mode == 'one_side':
                cv2.line(image, (120, 20), (120, 380), (0, 230, 255), 6)
            elif mode == 'short_contacts':
                for x in (120, 480):
                    cv2.line(image, (x, 180), (x, 200), (0, 230, 255), 6)
            result = analyze(image)
            self.assertFalse(np.any(result.road), mode)
            self.assertFalse(np.any(result.dashes), mode)

    def test_exterior_white_and_large_glare_are_not_filled(self):
        image = self.open_track()
        cv2.rectangle(image, (330, 150), (430, 260), (245, 245, 245), cv2.FILLED)
        cv2.rectangle(image, (20, 140), (50, 220), (255, 255, 255), cv2.FILLED)
        result = analyze(image)
        self.assertEqual(result.road[280, 200], 255)
        self.assertEqual(result.road[200, 380], 0)
        self.assertFalse(np.any(result.white[:, :100]))
        self.assertEqual(result.metrics['dash_candidate_count'], 4)

    def test_blurred_grey_paint_rim_is_not_mistaken_for_open_floor(self):
        image = cv2.GaussianBlur(self.open_track(), (9, 9), 2)
        result = analyze(image)
        self.assertEqual(result.metrics['dash_candidate_count'], 4)
        self.assertEqual(result.road[80, 296], 255)
        self.assertFalse(np.any(result.road[:, :100]))
        self.assertFalse(np.any(result.road[:, 500:]))

    def test_white_opening_to_exterior_is_not_restored(self):
        image = self.open_track()
        cv2.rectangle(image, (275, 15), (325, 125), (210, 210, 210), cv2.FILLED)
        result = analyze(image)
        self.assertEqual(result.road[100, 296], 0)
        self.assertEqual(result.road[250, 200], 255)
        self.assertEqual(result.metrics['dash_candidate_count'], 3)

    def test_roi_and_observed_yellow_are_not_filled_as_road(self):
        image = self.open_track()
        image[180:210, 115:127] = 210
        result = analyze(image, VisionConfig(roi_top=.25))
        for mask in (result.road, result.yellow, result.white, result.dashes):
            self.assertFalse(np.any(mask[:100]))
        self.assertEqual(result.road[250, 200], 255)
        self.assertEqual(result.road[250, 120], 0)
        self.assertEqual(result.road[195, 120], 0)
        self.assertFalse(np.any(result.road[:, :100]))

    def test_bottom_clipped_white_island_keeps_surrounding_dark_requirement(self):
        image = np.full((400, 600, 3), 210, np.uint8)
        cv2.rectangle(image, (160, 30), (440, 399), (45, 45, 45), cv2.FILLED)
        for x in (160, 440):
            cv2.line(image, (x, 30), (x, 399), (0, 230, 255), 6)
        cv2.rectangle(image, (290, 330), (310, 399), (245, 245, 245), cv2.FILLED)
        result = analyze(image)
        self.assertEqual(result.road[380, 300], 255)
        self.assertEqual(result.dashes[380, 300], 255)
        self.assertFalse(np.any(result.road[:, :140]))


class WhitePaintRepairTests(unittest.TestCase):
    def masks(self):
        support=np.zeros((400,600),np.uint8)
        cv2.rectangle(support,(250,300),(278,380),255,cv2.FILLED)
        seed=support.copy()
        seed[305:375,260:279]=0
        return seed,support

    def test_fragmented_paint_restores_only_colour_confirmed_pixels(self):
        seed,support=self.masks()
        original=seed.copy()
        repaired=_restore_white_paint(seed,support)
        self.assertTrue(np.array_equal(seed,original))
        self.assertTrue(np.array_equal(repaired,support))
        _,dashes,markings=_markings(repaired)
        self.assertTrue(markings[0]['dash_candidate'])
        self.assertGreaterEqual(markings[0]['fill_ratio'],.60)
        self.assertEqual(dashes[340,268],255)

    def test_bright_patch_without_enough_contrast_seed_is_not_invented(self):
        seed,support=self.masks()
        for count in (0,1,5):
            sparse=np.zeros_like(seed)
            sparse[300:300+count,250:252]=255
            self.assertTrue(np.array_equal(_restore_white_paint(sparse,support),sparse))

    def test_dark_hole_or_nonwhite_gap_is_not_filled(self):
        seed,support=self.masks()
        support[325:340,258:270]=0
        repaired=_restore_white_paint(seed,support)
        self.assertFalse(np.any(repaired[325:340,260:270]))
        self.assertFalse(np.any((repaired>0)&(seed==0)&(support==0)))

    def test_separate_dashes_are_not_joined_by_reconstruction(self):
        seed,support=self.masks()
        cv2.rectangle(support,(250,210),(268,260),255,cv2.FILLED)
        seed[210:261,250:257]=255
        repaired=_restore_white_paint(seed,support)
        self.assertFalse(np.any(repaired[265:295,240:285]))
        _,_,markings=_markings(repaired)
        self.assertEqual(sum(m['dash_candidate'] for m in markings),2)

    def test_thin_seam_large_far_patch_and_jagged_glare_keep_shape_limits(self):
        shapes=[[(400,100),(402,100),(402,350),(400,350)],
                [(250,20),(280,20),(280,100),(250,100)],
                [(200,300),(240,300),(240,305),(205,305),(205,380),(200,380)]]
        for points in shapes:
            support=np.zeros((400,600),np.uint8)
            cv2.fillPoly(support,[np.array(points,np.int32)],255)
            seed=support.copy()
            seed[305:375,201:205]=0
            self.assertTrue(np.array_equal(_restore_white_paint(seed,support),seed))

    def test_white_outside_road_is_still_excluded_and_metric_is_reported(self):
        image=sample_track()
        cv2.rectangle(image,(20,100),(60,200),(245,245,245),cv2.FILLED)
        result=analyze(image)
        self.assertFalse(np.any(result.white[:, :100]))
        self.assertIsInstance(result.metrics['white_restored_pixels'],int)
        self.assertGreaterEqual(result.metrics['white_restored_pixels'],0)

    def test_bottom_clipped_near_stripe_uses_existing_maximum_near_area(self):
        support=np.zeros((400,600),np.uint8)
        cv2.rectangle(support,(250,300),(282,399),255,cv2.FILLED)
        seed=support.copy();seed[310:395,260:283]=0
        repaired=_restore_white_paint(seed,support)
        self.assertTrue(np.array_equal(repaired,support))
        _,_,markings=_markings(repaired)
        self.assertTrue(markings[0]['dash_candidate'])
        self.assertAlmostEqual(markings[0]['area_limit_px'],support.size*.014,places=1)
        cv2.rectangle(support,(282,300),(315,399),255,cv2.FILLED)
        _,dashes,_=_markings(support)
        self.assertFalse(np.any(dashes))


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
