"""Road-presence gating without a camera or GPIO."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from road_surface import RoadSurfaceGuard, VisionGate, measure_surface


WHITE_ROAD = np.full((240, 320, 3), 230, dtype=np.uint8)
TINTED_WHITE_ROAD = np.full((240, 320, 3), (223, 219, 220), dtype=np.uint8)
BROWN_FLOOR = np.full((240, 320, 3), (55, 95, 125), dtype=np.uint8)
BRIGHT_TAN_FLOOR = np.full((240, 320, 3), (145, 175, 205), dtype=np.uint8)
BLACK_ROAD = np.full((240, 320, 3), 30, dtype=np.uint8)


def corner_frame(direction):
    frame = TINTED_WHITE_ROAD.copy()
    if direction == "right":
        frame[106:160, :160] = BROWN_FLOOR[106:160, :160]
    else:
        frame[106:160, 160:] = BROWN_FLOOR[106:160, 160:]
    return frame


class RoadSurfaceTests(unittest.TestCase):
    def test_white_track_and_brown_floor(self):
        self.assertEqual(measure_surface(WHITE_ROAD).state, "track")
        self.assertEqual(measure_surface(TINTED_WHITE_ROAD).state, "track")
        self.assertEqual(measure_surface(BROWN_FLOOR).state, "off_track")
        self.assertEqual(measure_surface(BRIGHT_TAN_FLOOR).state, "off_track")

    def test_far_track_boundary_pauses(self):
        frame = TINTED_WHITE_ROAD.copy()
        frame[106:145, :] = BROWN_FLOOR[106:145, :]
        self.assertEqual(measure_surface(frame).state, "uncertain")

    def test_corner_requires_near_track_and_side_contrast(self):
        self.assertEqual(measure_surface(corner_frame("right")).state, "corner_right")
        self.assertEqual(measure_surface(corner_frame("left")).state, "corner_left")
        lost_near = corner_frame("right")
        lost_near[160:, :] = BROWN_FLOOR[160:, :]
        self.assertEqual(measure_surface(lost_near).state, "off_track")

    def test_corner_needs_three_samples_then_centered_track(self):
        gate = VisionGate()
        corner = corner_frame("right")
        self.assertEqual(gate.update(corner, True, 104.0), "waiting")
        self.assertEqual(gate.update(corner, True, 104.0), "waiting")
        self.assertEqual(gate.update(corner, True, 104.0), "corner_right")
        for _ in range(3):
            self.assertEqual(gate.update(WHITE_ROAD, True, 104.0), "waiting")
        for _ in range(2):
            self.assertEqual(gate.update(WHITE_ROAD, True, 0.0), "ready")

    def test_black_profile(self):
        self.assertEqual(measure_surface(BLACK_ROAD, "black").state, "track")
        self.assertEqual(measure_surface(WHITE_ROAD, "black").state, "off_track")

    def test_uncertainty_pauses_then_recovers(self):
        guard = RoadSurfaceGuard()
        for _ in range(3):
            self.assertIn(guard.update(WHITE_ROAD), {"waiting", "track"})
        self.assertEqual(guard.state, "track")
        mixed = WHITE_ROAD.copy()
        mixed[185:, :] = BROWN_FLOOR[185:, :]
        self.assertEqual(guard.update(mixed), "waiting")
        self.assertEqual(guard.update(WHITE_ROAD), "waiting")
        self.assertEqual(guard.update(WHITE_ROAD), "waiting")
        self.assertEqual(guard.update(WHITE_ROAD), "track")

    def test_confirmed_floor_and_prolonged_uncertainty(self):
        guard = RoadSurfaceGuard()
        self.assertEqual(guard.update(BROWN_FLOOR), "waiting")
        self.assertEqual(guard.update(BROWN_FLOOR), "off_track")
        guard = RoadSurfaceGuard()
        mixed = WHITE_ROAD.copy()
        mixed[185:, :] = BROWN_FLOOR[185:, :]
        for _ in range(10):
            state = guard.update(mixed)
        self.assertEqual(state, "surface_timeout")

    def test_lane_loss_waits_then_times_out(self):
        gate = VisionGate(lane_loss_limit=4)
        for _ in range(3):
            gate.update(WHITE_ROAD, True)
        self.assertEqual(gate.state, "ready")
        for _ in range(3):
            self.assertEqual(gate.update(WHITE_ROAD, False), "waiting")
        self.assertEqual(gate.update(WHITE_ROAD, False), "lane_timeout")

    def test_reacquisition_needs_three_clear_samples(self):
        gate = VisionGate()
        for _ in range(3):
            gate.update(WHITE_ROAD, True)
        self.assertEqual(gate.update(BROWN_FLOOR, True), "waiting")
        for _ in range(2):
            self.assertEqual(gate.update(WHITE_ROAD, True), "waiting")
        self.assertEqual(gate.update(WHITE_ROAD, True), "ready")


if __name__ == "__main__":
    unittest.main()
