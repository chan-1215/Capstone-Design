import unittest
from pathlib import Path

import cv2
import numpy as np

from road_vision import (analyze, curve_direction, edge_inward_direction,
                         road_boundary, scan_road_rows)


class RoadVisionTest(unittest.TestCase):
    def test_paper_edge_is_not_paired_with_internal_solid_line(self):
        image = Path(__file__).with_name("test_fixtures") / "next_curve_false_pair_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertLess(reading.center_error, -110)

    def test_mid_corner_can_resume_with_near_road_and_matching_boundary(self):
        image = Path(__file__).with_name("test_fixtures") / "mid_corner_restart_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertLess(reading.confidence, 0.6)
        self.assertGreater(reading.near_surface, 0.9)
        self.assertEqual(reading.edge_inward, "right")
        self.assertEqual(curve_direction(reading), "우회전")
        reading.edge_inward = None
        self.assertIsNone(curve_direction(reading))

    def test_horizontal_edge_does_not_reverse_inward_direction(self):
        image = Path(__file__).with_name("test_fixtures") / "edge_direction_missing_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.edge_inward, "right")
        self.assertLess(reading.center_error, -130)

    def test_recorded_left_outer_edge_points_right_into_road(self):
        image = Path(__file__).with_name("test_fixtures") / "left_turn_stop_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.edge_inward, "right")
        self.assertLess(reading.center_error, -130)

    def test_right_outer_edge_points_left_into_road(self):
        white = np.zeros((400, 640), dtype=bool)
        for y in range(120, 320):
            white[y, :500 - y // 2] = True
        points = [(500 - y // 2, y) for y in range(120, 320, 12)]
        self.assertEqual(edge_inward_direction(white, points), "left")
        self.assertIsNone(edge_inward_direction(white, points[:2]))

    def test_near_solid_line_beats_small_lower_fragment(self):
        image = Path(__file__).with_name("test_fixtures") / "early_stop_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")
        self.assertGreater(reading.confidence, 0.65)
        self.assertGreater(reading.heading_error, 30)
        self.assertEqual(curve_direction(reading), "우회전")

    def test_near_outer_solid_and_thin_inner_boundary_are_both_visible(self):
        image = Path(__file__).with_name("test_fixtures") / "near_solid_line_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertGreater(reading.confidence, 0.7)
        self.assertIsNotNone(reading.road_edge)

    def test_near_thin_boundary_remains_visible_without_outer_solid(self):
        image = Path(__file__).with_name("test_fixtures") / "next_curve_entry_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")
        self.assertIsNotNone(reading.center_error)
        cyan = np.all(reading.overlay[390:440, 370:440] == (255, 255, 0), axis=2)
        self.assertGreater(np.count_nonzero(cyan), 50)

    def test_near_thin_boundary_is_not_filtered_as_a_floor_seam(self):
        image = Path(__file__).with_name("test_fixtures") / "right_solid_missed_20261014.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        cyan = np.all(reading.overlay[360:440, 505:545] == (255, 255, 0), axis=2)
        self.assertGreater(np.count_nonzero(cyan), 50)

    def test_recorded_right_curve_keeps_lane_and_floor_boundary_separate(self):
        image = Path(__file__).with_name("test_fixtures") / "right_curve_road_above_floor.jpg"
        frame = cv2.imread(str(image))
        self.assertIsNotNone(frame)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")
        self.assertEqual(reading.road_edge, "오른쪽 곡선")
        self.assertEqual(curve_direction(reading), "우회전")
        orange = np.all(reading.overlay[290:420, 420:610] == (0, 140, 255), axis=2)
        self.assertGreater(np.count_nonzero(orange), 20)

    def test_near_road_supports_late_curve_without_accepting_floor_edge(self):
        frame = np.full((480, 640, 3), 70, np.uint8)
        road = np.array([(0, 320), (150, 275), (320, 240), (500, 200),
                         (639, 205), (639, 479), (0, 479)], np.int32)
        cv2.fillPoly(frame, [road], (240, 240, 240))
        line = np.array([(65, 455), (125, 370), (205, 315),
                         (320, 275), (470, 245), (620, 240)], np.int32)
        cv2.polylines(frame, [line], False, (10, 10, 10), 18)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")
        self.assertLess(reading.surface, 0.55)
        self.assertGreater(reading.near_surface, 0.8)
        self.assertEqual(curve_direction(reading), "우회전")
        cv2.fillPoly(frame, [road], (240, 240, 240))
        self.assertIsNone(curve_direction(analyze(frame)))

    def test_curved_outer_edge_is_reported_without_inventing_a_lane(self):
        frame = np.full((480, 640, 3), 70, np.uint8)
        boundary = np.array([(0, 310), (160, 285), (320, 250),
                             (480, 200), (639, 160), (639, 479), (0, 479)], np.int32)
        cv2.fillPoly(frame, [boundary], (240, 240, 240))
        cv2.polylines(frame, [boundary[:5]], False, (10, 10, 10), 9)
        reading = analyze(frame)
        self.assertEqual(reading.road_edge, "오른쪽 곡선")
        self.assertNotEqual(reading.lane, "양쪽 선")
        self.assertIsNone(curve_direction(reading))

    def test_curve_boundary_with_road_above_floor_is_reported(self):
        frame = np.full((480, 640, 3), 70, np.uint8)
        boundary = np.array([(0, 0), (639, 0), (639, 165),
                             (480, 215), (320, 260), (160, 310), (0, 360)], np.int32)
        cv2.fillPoly(frame, [boundary], (240, 240, 240))
        reading = analyze(frame)
        self.assertEqual(reading.road_edge, "오른쪽 곡선")
        self.assertNotEqual(reading.lane, "양쪽 선")

    def test_upper_floor_object_is_not_internal_lane(self):
        frame = np.full((480, 640, 3), 70, np.uint8)
        cv2.rectangle(frame, (0, 200), (639, 479), (240, 240, 240), -1)
        cv2.rectangle(frame, (15, 115), (150, 205), (10, 10, 10), -1)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "선 미검출")
        self.assertIsNone(reading.center_error)

    def test_white_road_with_two_lines_has_no_outer_boundary(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (160, 210), (160, 430), (10, 10, 10), 8)
        cv2.line(frame, (480, 210), (480, 430), (10, 10, 10), 8)
        self.assertIsNone(analyze(frame).road_edge)

    def test_thick_internal_line_is_not_a_road_boundary(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (0, 400), (639, 100), (10, 10, 10), 22)
        self.assertIsNone(analyze(frame).road_edge)

    def test_wide_curved_line_on_white_road_is_visible(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        points = np.array([(0, 315), (100, 290), (220, 260),
                           (350, 215), (480, 180), (630, 165)], np.int32)
        cv2.polylines(frame, [points], False, (10, 10, 10), 11)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")
        self.assertIsNotNone(reading.center_error)
        cyan = np.all(reading.overlay[160:205, 440:530] == (255, 255, 0), axis=2)
        self.assertGreater(np.count_nonzero(cyan), 10)

    def test_distant_fragment_without_vertical_overlap_is_not_second_edge(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (110, 430), (300, 220), (10, 10, 10), 12)
        cv2.line(frame, (430, 145), (490, 170), (10, 10, 10), 12)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")

    def test_row_scan_follows_curved_fragmented_edges(self):
        dark = np.zeros((400, 640), np.uint8)
        white = np.ones((400, 640), np.uint8)
        for y, offset in zip(range(140, 320, 12), range(15)):
            dark[y, 120 + offset * 3:130 + offset * 3] = 255
            dark[y, 420 + offset * 2:430 + offset * 2] = 255
        evidence = scan_road_rows(dark, white)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence[0], "both")

    def test_row_scan_rejects_disconnected_dark_fragments(self):
        dark = np.zeros((400, 640), np.uint8)
        white = np.ones((400, 640), np.uint8)
        for y, x in zip(range(140, 260, 12), (120, 220, 120, 220, 120,
                                                220, 120, 220, 120, 220)):
            dark[y, x:x + 10] = 255
        self.assertIsNone(scan_road_rows(dark, white))

    def test_row_scan_rejects_dashes_separated_by_large_gaps(self):
        dark = np.zeros((400, 640), np.uint8)
        white = np.ones((400, 640), np.uint8)
        for y in (140, 152, 176, 188, 212, 224):
            dark[y, 140:150] = 255
            dark[y, 450:460] = 255
        self.assertIsNone(scan_road_rows(dark, white))

    def test_two_lines_on_white_road(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (160, 210), (160, 430), (10, 10, 10), 8)
        cv2.line(frame, (480, 210), (480, 430), (10, 10, 10), 8)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertGreater(reading.confidence, 0.7)
        self.assertAlmostEqual(reading.center_error, 0, delta=4)

    def test_room_does_not_count_as_road(self):
        frame = np.full((480, 640, 3), 50, np.uint8)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "도로 미확인")
        self.assertEqual(reading.confidence, 0)
        self.assertIsNone(reading.center_error)

    def test_white_sheet_edge_is_not_a_lane_line(self):
        frame = np.full((480, 640, 3), 70, np.uint8)
        frame[:, 150:] = 240
        cv2.line(frame, (400, 210), (400, 430), (10, 10, 10), 12)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")

    def test_white_sheet_edge_is_not_a_corner(self):
        frame = np.full((480, 640, 3), 70, np.uint8)
        frame[90:, :] = 240
        cv2.line(frame, (580, 200), (620, 430), (10, 10, 10), 18)
        reading = analyze(frame)
        self.assertIsNone(reading.corner)

    def test_horizontal_floor_seam_is_not_a_lane(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (160, 210), (160, 430), (10, 10, 10), 8)
        cv2.line(frame, (480, 210), (480, 430), (10, 10, 10), 8)
        cv2.line(frame, (280, 390), (610, 390), (40, 40, 40), 5)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertAlmostEqual(reading.center_error, 0, delta=4)

    def test_prefers_near_lane_line_over_larger_outer_line(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (160, 210), (160, 430), (10, 10, 10), 8)
        cv2.line(frame, (480, 210), (480, 430), (10, 10, 10), 8)
        cv2.line(frame, (620, 210), (620, 430), (10, 10, 10), 18)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertAlmostEqual(reading.center_error, 0, delta=4)

    def test_distant_dash_still_counts_as_second_lane_edge(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (115, 420), (220, 125), (10, 10, 10), 12)
        cv2.line(frame, (500, 125), (545, 180), (10, 10, 10), 12)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertIsNotNone(reading.center_error)
        self.assertLess(abs(reading.center_error), 130)

    def test_top_edge_dash_can_be_seen(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (30, 440), (310, 60), (10, 10, 10), 14)
        cv2.line(frame, (590, 65), (620, 100), (10, 10, 10), 14)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")

    def test_overexposed_white_road_keeps_both_lines(self):
        frame = np.full((480, 640, 3), 255, np.uint8)
        cv2.line(frame, (70, 420), (290, 65), (65, 65, 65), 12)
        cv2.line(frame, (570, 220), (450, 85), (65, 65, 65), 12)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertGreater(reading.confidence, 0.7)

    def test_opposite_perspective_slopes_do_not_imply_turn(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (50, 430), (290, 90), (10, 10, 10), 12)
        cv2.line(frame, (590, 260), (450, 90), (10, 10, 10), 12)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "양쪽 선")
        self.assertEqual(reading.heading_error, 0.0)

    def test_tiny_border_fragment_is_not_second_edge(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (100, 440), (280, 140), (10, 10, 10), 18)
        cv2.line(frame, (636, 135), (639, 155), (10, 10, 10), 5)
        reading = analyze(frame)
        self.assertEqual(reading.lane, "한쪽 선")
        self.assertLess(reading.center_error, 0)

    def test_crossing_line_and_right_side_mark_a_corner(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (0, 130), (540, 130), (10, 10, 10), 15)
        cv2.line(frame, (610, 190), (610, 430), (10, 10, 10), 22)
        reading = analyze(frame)
        self.assertEqual(reading.corner, "right")
        self.assertEqual(reading.lane, "오른쪽 코너")

    def test_crossing_line_alone_is_not_a_corner(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (0, 130), (540, 130), (10, 10, 10), 15)
        reading = analyze(frame)
        self.assertIsNone(reading.corner)

    def test_short_right_dash_with_crossing_line_is_corner(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (0, 145), (540, 145), (10, 10, 10), 12)
        cv2.line(frame, (560, 390), (620, 430), (10, 10, 10), 24)
        reading = analyze(frame)
        self.assertEqual(reading.corner, "right")

    def test_split_crossing_line_with_bottom_dash_is_corner(self):
        frame = np.full((480, 640, 3), 240, np.uint8)
        cv2.line(frame, (0, 195), (300, 150), (10, 10, 10), 12)
        cv2.line(frame, (280, 145), (639, 120), (10, 10, 10), 12)
        cv2.line(frame, (530, 420), (575, 440), (10, 10, 10), 25)
        reading = analyze(frame)
        self.assertEqual(reading.corner, "right")

    def test_both_edges_take_priority_over_corner_markers(self):
        for near in (False, True):
            frame = np.full((480, 640, 3), 240, np.uint8)
            cv2.line(frame, (150, 430), (250, 160), (10, 10, 10), 10)
            cv2.line(frame, (470, 430), (450, 170), (10, 10, 10), 10)
            cv2.line(frame, (0, 125), (639, 125), (10, 10, 10), 12)
            cv2.line(frame, (610, 260 if near else 140),
                     (610, 420 if near else 210), (10, 10, 10), 12)
            reading = analyze(frame)
            self.assertEqual(reading.lane, "양쪽 선")
            self.assertIsNone(reading.corner)

if __name__ == "__main__":
    unittest.main()
