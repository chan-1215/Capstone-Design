import unittest

import cv2
import numpy as np

from hough_vision import (
    FULL_ROI, TEXTBOOK_ROI, HoughConfig, analyze_hough, merge_segments, overlay_hough,
)


def yellow_lines(left=65, right=225):
    frame = np.zeros((240, 320, 3), np.uint8)
    for x in (left, right):
        if x is not None:
            cv2.line(frame, (x, 0), (x, 239), (0, 255, 255), 8)
    return frame


class HoughVisionTests(unittest.TestCase):
    def test_missing_lines_never_invent_a_straight_target(self):
        for segments, reason in (
            ([], "no_segments"),
            ([(50, 0, 70, 100)], "left_only"),
            ([(250, 0, 270, 100)], "right_only"),
            ([(100, 0, 220, 100)], "unassigned_segments"),
        ):
            with self.subTest(reason=reason):
                result = merge_segments(segments, 320)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["two_sided_observation"])
                self.assertFalse(result["drive_authorized"])
                self.assertIsNone(result["center_x"])
                self.assertIsNone(result["error_px"])
                self.assertIsNone(result["normalized_error"])

    def test_endpoint_mean_sign_is_target_minus_image_center(self):
        for segments, target in (
            ([(50, 0, 70, 100), (190, 0, 210, 100)], 130),
            ([(70, 0, 90, 100), (270, 0, 290, 100)], 180),
        ):
            result = merge_segments(segments, 320)
            self.assertEqual(result["center_x"], target)
            self.assertEqual(result["error_px"], target-160)
            self.assertFalse(result["drive_authorized"])

    def test_image_side_groups_do_not_authorize_a_path_between_distinct_boundaries(self):
        # Two pieces of ONE curve can be assigned to opposite image halves.
        result = merge_segments([(10, 30, 150, 40), (170, 45, 310, 80)], 320)
        self.assertTrue(result["two_sided_observation"])
        self.assertEqual(result["center_x"], 160)
        self.assertFalse(result["drive_authorized"])

    def test_known_yellow_lines_and_resolution_normalization(self):
        frame = cv2.resize(yellow_lines(), (640, 480), interpolation=cv2.INTER_NEAREST)
        errors = []
        for size in (320, 480):
            result = analyze_hough(frame, HoughConfig(max_side=size))
            self.assertTrue(result.metrics["two_sided_observation"])
            errors.append(result.metrics["normalized_error"])
            self.assertLess(errors[-1], 0)
        self.assertAlmostEqual(errors[0], errors[1], delta=.025)

    def test_single_boundary_can_be_detected_without_generating_a_target(self):
        result = analyze_hough(yellow_lines(right=None))
        self.assertGreater(result.metrics["segment_count"], 0)
        self.assertEqual(result.metrics["reason"], "left_only")
        self.assertIsNone(result.metrics["center_x"])

    def test_white_is_not_silently_treated_as_yellow(self):
        frame = yellow_lines()
        frame[frame[:, :, 1] > 0] = (255, 255, 255)
        yellow = analyze_hough(frame)
        white = analyze_hough(frame, HoughConfig(colour="white"))
        both = analyze_hough(frame, HoughConfig(colour="both"))
        self.assertEqual(yellow.metrics["segment_count"], 0)
        self.assertTrue(white.metrics["two_sided_observation"])
        np.testing.assert_array_equal(white.masks["colour"], both.masks["colour"])

    def test_crop_rejects_lines_only_above_selected_region(self):
        frame = yellow_lines()
        frame[100:] = 0
        result = analyze_hough(frame, HoughConfig(roi_top=.5))
        self.assertEqual(result.metrics["crop_y"], 120)
        self.assertEqual(result.metrics["segment_count"], 0)

    def test_small_isolated_specks_are_reduced_by_blur(self):
        frame = np.zeros((240, 320, 3), np.uint8)
        frame[::10, ::10] = (0, 255, 255)
        unblurred = analyze_hough(frame, HoughConfig(blur_size=0))
        blurred = analyze_hough(frame, HoughConfig(blur_size=5))
        self.assertLess(blurred.metrics["edge_pixels"], unblurred.metrics["edge_pixels"])
        self.assertFalse(blurred.metrics["two_sided_observation"])

    def test_perspective_maps_supplied_quad_and_keeps_hough_input_binary(self):
        result = analyze_hough(yellow_lines(), HoughConfig(
            roi_top=.5, polygon=TEXTBOOK_ROI, bird_eye=True))
        source = np.asarray(result.metrics["roi_polygon"], np.float32).reshape(1, 4, 2)
        matrix = np.asarray(result.metrics["perspective_matrix"])
        mapped = cv2.perspectiveTransform(source, matrix)[0]
        width, height = result.metrics["crop_size"]
        expected = np.asarray(FULL_ROI)*[width-1, height-1]
        np.testing.assert_allclose(mapped, expected, atol=1e-4)
        self.assertTrue(set(np.unique(result.masks["transformed"])).issubset({0, 255}))
        self.assertEqual(overlay_hough(result).shape, result.crop.shape)

    def test_analysis_and_rendering_preserve_source(self):
        frame = yellow_lines()
        original = frame.copy()
        result = analyze_hough(frame)
        crop = result.crop.copy()
        overlay_hough(result)
        np.testing.assert_array_equal(frame, original)
        np.testing.assert_array_equal(result.crop, crop)

    def test_invalid_config_and_inputs_are_rejected(self):
        for options in (
            {"max_side": 32}, {"max_side": True}, {"roi_top": float("nan")},
            {"roi_top": None}, {"blur_size": 4}, {"blur_size": 3.0},
            {"colour": "red"}, {"canny_low": 150}, {"canny_high": 150.0},
            {"votes_at_320": 0}, {"bird_eye": "yes"},
            {"polygon": ((0, 0), (1, 1), (1, 0), (0, 1))},
            {"polygon": ((0, 0), (0, 0), (0, 0), (0, 0))},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                HoughConfig(**options)
        for frame in (None, np.zeros((20, 20), np.uint8),
                      np.zeros((20, 20, 3), np.float32), np.zeros((0, 20, 3), np.uint8)):
            with self.assertRaises(ValueError):
                analyze_hough(frame)


if __name__ == "__main__":
    unittest.main()
