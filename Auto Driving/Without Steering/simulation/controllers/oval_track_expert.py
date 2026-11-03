"""Ground-truth path follower for the three-lane oval Webots track."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ExpertDecision:
    left_pwm: float
    right_pwm: float
    cross_track_error: float
    heading_error: float
    target_x: float
    target_y: float


def wrap_angle(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


class OvalTrackExpert:
    """Follow the middle lane center using simulator position ground truth."""

    def __init__(self, half_straight=1.8, lane_radius=1.9,
                 base_pwm=0.48, point_count=720, lookahead_points=22):
        self.base_pwm = base_pwm
        self.lookahead_points = lookahead_points
        self.path = self._make_path(half_straight, lane_radius, point_count)

    @staticmethod
    def _make_path(half_straight, radius, point_count):
        points = []
        section = point_count // 4

        # Bottom straight: left to right.
        for i in range(section):
            ratio = i / section
            points.append((-half_straight + 2 * half_straight * ratio, -radius))

        # Right semicircle: bottom to top.
        for i in range(2 * section):
            angle = -math.pi / 2 + math.pi * i / (2 * section)
            points.append((
                half_straight + radius * math.cos(angle),
                radius * math.sin(angle),
            ))

        # Top straight: right to left.
        for i in range(section):
            ratio = i / section
            points.append((half_straight - 2 * half_straight * ratio, radius))

        # Left semicircle: top to bottom.
        for i in range(2 * section):
            angle = math.pi / 2 + math.pi * i / (2 * section)
            points.append((
                -half_straight + radius * math.cos(angle),
                radius * math.sin(angle),
            ))
        return points

    def decide(self, x, y, yaw):
        nearest_index = min(
            range(len(self.path)),
            key=lambda i: (self.path[i][0] - x) ** 2 + (self.path[i][1] - y) ** 2,
        )
        nearest_x, nearest_y = self.path[nearest_index]
        target_index = (nearest_index + self.lookahead_points) % len(self.path)
        target_x, target_y = self.path[target_index]

        target_heading = math.atan2(target_y - y, target_x - x)
        heading_error = wrap_angle(target_heading - yaw)
        cross_track_error = math.hypot(nearest_x - x, nearest_y - y)

        turn = max(-0.34, min(0.34, heading_error * 0.72))
        curve_slowdown = min(0.12, abs(heading_error) * 0.12)
        base = self.base_pwm - curve_slowdown
        left_pwm = max(0.10, min(0.85, base - turn))
        right_pwm = max(0.10, min(0.85, base + turn))

        return ExpertDecision(
            left_pwm=left_pwm,
            right_pwm=right_pwm,
            cross_track_error=cross_track_error,
            heading_error=heading_error,
            target_x=target_x,
            target_y=target_y,
        )


class RoundedRectangleExpert(OvalTrackExpert):
    """Ground-truth follower for a rounded rectangular centerline."""

    def __init__(self, half_width=3.5, half_height=2.0, corner_radius=1.4,
                 clockwise=True, base_pwm=0.45, lookahead_points=18):
        self.base_pwm = base_pwm
        self.lookahead_points = lookahead_points
        self.path = self._make_rounded_rectangle(
            half_width, half_height, corner_radius
        )
        if clockwise:
            self.path.reverse()

        self.corner_radius = corner_radius

    @property
    def corner_curvature(self):
        """Return the geometric corner curvature in inverse metres."""
        return 1.0 / self.corner_radius

    @classmethod
    def for_lane(cls, lane_number, **kwargs):
        """Build a path for lane 1 (inside), 2 (middle), or 3 (outside)."""
        lane_geometry = {
            # half width, half height, corner radius, PWM, lookahead
            1: (2.9, 1.4, 0.8, 0.34, 12),
            2: (3.5, 2.0, 1.4, 0.42, 18),
            3: (4.1, 2.6, 2.0, 0.48, 22),
        }
        if lane_number not in lane_geometry:
            raise ValueError(f"lane_number must be 1, 2, or 3, got {lane_number}")
        half_width, half_height, corner_radius, base_pwm, lookahead = (
            lane_geometry[lane_number]
        )
        kwargs.setdefault("base_pwm", base_pwm)
        kwargs.setdefault("lookahead_points", lookahead)
        return cls(
            half_width=half_width,
            half_height=half_height,
            corner_radius=corner_radius,
            **kwargs,
        )

    @staticmethod
    def _make_rounded_rectangle(
        half_width, half_height, radius, arc_steps=90, line_steps=120
    ):
        center_x = half_width - radius
        center_y = half_height - radius
        corners = (
            (center_x, -center_y, -math.pi / 2, 0),
            (center_x, center_y, 0, math.pi / 2),
            (-center_x, center_y, math.pi / 2, math.pi),
            (-center_x, -center_y, math.pi, 3 * math.pi / 2),
        )
        points = []
        for corner_index, (cx, cy, start, end) in enumerate(corners):
            for index in range(arc_steps):
                angle = start + (end - start) * index / arc_steps
                points.append((
                    cx + radius * math.cos(angle),
                    cy + radius * math.sin(angle),
                ))
            end_x = cx + radius * math.cos(end)
            end_y = cy + radius * math.sin(end)
            next_cx, next_cy, next_start, _ = corners[(corner_index + 1) % 4]
            next_x = next_cx + radius * math.cos(next_start)
            next_y = next_cy + radius * math.sin(next_start)
            for index in range(line_steps):
                ratio = index / line_steps
                points.append((
                    end_x + (next_x - end_x) * ratio,
                    end_y + (next_y - end_y) * ratio,
                ))
        return points
