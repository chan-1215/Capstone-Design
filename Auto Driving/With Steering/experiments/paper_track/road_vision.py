"""Frame-level white-road and dark-line diagnostics. No driving decisions."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Reading:
    lane: str
    confidence: float
    surface: float
    center_error: float | None
    overlay: np.ndarray
    heading_error: float = 0.0
    corner: str | None = None
    road_edge: str | None = None
    near_surface: float = 0.0
    edge_inward: str | None = None


def curve_direction(reading: Reading) -> str | None:
    """Infer a bend from the internal lane line, never the outer road edge."""
    near_road = (reading.surface >= 0.4
                 and getattr(reading, "near_surface", 0.0) >= 0.8)
    if reading.lane != "한쪽 선" or reading.center_error is None:
        return None
    if reading.heading_error >= 30:
        direction, inward = "우회전", "right"
    elif reading.heading_error <= -30:
        direction, inward = "좌회전", "left"
    else:
        return None
    boundary_supported = (reading.surface >= 0.45
                          and getattr(reading, "near_surface", 0.0) >= 0.9
                          and reading.confidence >= 0.58
                          and abs(reading.center_error) <= 80
                          and getattr(reading, "edge_inward", None) == inward)
    if (reading.confidence < 0.65
            and not ((near_road and reading.confidence >= 0.6)
                     or boundary_supported)):
        return None
    if reading.surface < 0.65 and not near_road:
        return None
    return direction


def scan_road_rows(dark: np.ndarray, white: np.ndarray):
    height, width = dark.shape
    pairs = []
    sides = {"left": [], "right": []}

    def longest_run(points, positions):
        best = []
        run = []
        for point in points:
            if (run and (point[0] - run[-1][0] != 12
                         or any(abs(point[index] - run[-1][index]) > width * 0.1
                                for index in positions))):
                if len(run) > len(best):
                    best = run
                run = []
            run.append(point)
        return run if len(run) > len(best) else best

    for y in range(int(height * 0.35), int(height * 0.9), 12):
        transitions = np.diff(np.r_[False, dark[y] != 0, False].astype(np.int8))
        starts = np.flatnonzero(transitions == 1)
        ends = np.flatnonzero(transitions == -1)
        centers = []
        for start, end in zip(starts, ends):
            if not 4 <= end - start <= width * 0.11 or start < 20 or end > width - 20:
                continue
            left_white = white[y, start - 20:start - 5]
            right_white = white[y, end + 5:end + 20]
            if np.mean(left_white) >= 0.4 and np.mean(right_white) >= 0.4:
                centers.append((start + end) / 2)
        left = max((x for x in centers if x < width / 2), default=None)
        right = min((x for x in centers if x > width / 2), default=None)
        if left is not None:
            sides["left"].append((y, left))
        if right is not None:
            sides["right"].append((y, right))
        if (left is not None and right is not None
                and width * 0.15 <= right - left <= width * 0.9):
            pairs.append((y, left, right))

    pairs = longest_run(pairs, (1, 2))
    if len(pairs) >= 3:
        near = pairs[-3:]
        target = float(np.mean([(left + right) / 2 for _, left, right in near]))
        heading = float(np.clip((pairs[0][1] + pairs[0][2]) / 2 - target,
                                -width * 0.25, width * 0.25))
        return "both", target, heading, len(pairs)

    runs = {side: longest_run(points, (1,)) for side, points in sides.items()}
    side, points = max(runs.items(), key=lambda item: len(item[1]))
    if len(points) < 4:
        return None
    near_x = float(np.mean([x for _, x in points[-3:]]))
    far_x = float(np.mean([x for _, x in points[:3]]))
    heading = float(np.clip(far_x - near_x, -width * 0.25, width * 0.25))
    target = near_x + (width * 0.25 if side == "left" else -width * 0.25)
    return "single", target + 0.5 * heading, heading, len(points)


def road_boundary(white: np.ndarray):
    """Find a white-track boundary without confusing it with an internal line."""
    height, width = white.shape
    mask = cv2.morphologyEx(white.astype(np.uint8), cv2.MORPH_CLOSE,
                            np.ones((9, 9), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count < 2:
        return None, []
    valid_edges = []
    for component in range(1, count):
        if stats[component, cv2.CC_STAT_AREA] < height * width * 0.12:
            continue
        edges = {"top": [], "bottom": []}
        for x in range(int(width * 0.08), int(width * 0.92), max(1, width // 48)):
            ys = np.flatnonzero(labels[:, x] == component)
            if not len(ys):
                continue
            for side, y in (("top", int(ys[0])), ("bottom", int(ys[-1]))):
                if not height * 0.12 < y < height * 0.82:
                    continue
                strip = slice(max(0, x - 2), min(width, x + 3))
                near_above = white[y - 18:y - 6, strip]
                near_below = white[y + 6:y + 18, strip]
                far = (white[y - 48:y - 28, strip] if side == "top"
                       else white[y + 28:y + 48, strip])
                if not far.size:
                    continue
                if (side == "top" and np.mean(near_above) < 0.25
                        and np.mean(far) < 0.25 and np.mean(near_below) > 0.6):
                    edges[side].append((x, y))
                if (side == "bottom" and np.mean(near_above) > 0.6
                        and np.mean(near_below) < 0.25 and np.mean(far) < 0.25):
                    edges[side].append((x, y))
        valid_edges.extend(edges.values())
    if not valid_edges:
        return None, []
    valid_edges = [points for points in valid_edges
                   if len(points) >= 12 and points[-1][0] - points[0][0] >= width * 0.22]
    if not valid_edges:
        return None, []
    points = max(valid_edges, key=lambda values: float(np.median([y for _, y in values])))
    left_y = float(np.median([y for _, y in points[:len(points) // 4]]))
    right_y = float(np.median([y for _, y in points[-len(points) // 4:]]))
    rise = left_y - right_y
    if rise > height * 0.10:
        direction = "오른쪽 곡선"
    elif rise < -height * 0.10:
        direction = "왼쪽 곡선"
    else:
        direction = "가로 경계"
    return direction, points


def edge_inward_direction(white: np.ndarray, points: list[tuple[int, int]]) -> str | None:
    """Use road surface beside a nearby boundary to identify the safe side."""
    votes = {"left": 0, "right": 0}
    height, width = white.shape
    for index, (x, y) in enumerate(points):
        if y < height * 0.3 or x < 40 or x + 40 >= width:
            continue
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        if abs(after[1] - before[1]) < 0.25 * max(1, abs(after[0] - before[0])):
            continue
        left = float(np.mean(white[y, x - 40:x - 15]))
        right = float(np.mean(white[y, x + 15:x + 40]))
        if right >= 0.7 and left <= 0.3:
            votes["right"] += 1
        elif left >= 0.7 and right <= 0.3:
            votes["left"] += 1
    side = max(votes, key=votes.get)
    other = "left" if side == "right" else "right"
    return side if votes[side] >= 3 and votes[side] >= 3 * votes[other] else None


def line_has_road_on_both_sides(contour, white, x, y, box_width, box_height):
    """A true internal line has road on both sides at multiple heights."""
    support = 0
    for fraction in (0.2, 0.5, 0.8):
        row = min(y + round(box_height * fraction), white.shape[0] - 1)
        intersections = contour[:, 0, :][abs(contour[:, 0, 1] - row) <= 3, 0]
        if not intersections.size:
            continue
        left = max(0, int(np.min(intersections)) - 18)
        right = min(white.shape[1], int(np.max(intersections)) + 18)
        left_road = white[row, left:max(left, int(np.min(intersections)) - 5)]
        right_road = white[row, min(right, int(np.max(intersections)) + 5):right]
        if (left_road.size >= 6 and right_road.size >= 6
                and np.mean(left_road) >= 0.55 and np.mean(right_road) >= 0.55):
            support += 1
    return support >= 2


def analyze(frame: np.ndarray) -> Reading:
    height, width = frame.shape[:2]
    y1, y2 = int(height * 0.12), int(height * 0.92)
    roi = frame[y1:y2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)

    road_light = max(150, float(np.percentile(light, 85)) - 35)
    white = (light > road_light) & (np.abs(a.astype(np.int16) - 128) < 18) & (
        np.abs(b.astype(np.int16) - 128) < 18
    )
    edge_label, edge_points = road_boundary(white)
    edge_inward = edge_inward_direction(white, edge_points)
    middle = white[:, int(width * 0.15):int(width * 0.85)]
    surface = float(np.mean(middle)) if middle.size else 0.0
    near_road = white[int(white.shape[0] * 0.55):,
                      int(width * 0.25):int(width * 0.75)]
    near_surface = float(np.mean(near_road)) if near_road.size else 0.0

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    dark = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 51, 12)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, y1), (width - 1, y2), (0, 200, 255), 1)
    cv2.line(overlay, (width // 2, y1), (width // 2, y2), (255, 0, 0), 2)
    inset_width, inset_height = width // 3, height // 4
    candidates = []
    internal_candidates = []
    roi_area = max(1, (y2 - y1) * width)
    corner_across = False
    across_segments = []
    corner_sides = set()
    near_corner_sides = set()
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if roi_area * 0.002 < area < roi_area * 0.15:
            center_x1 = x + box_width // 4
            center_x2 = x + box_width * 3 // 4
            above = white[max(0, y - 15):max(0, y - 5), center_x1:center_x2]
            below = white[min(white.shape[0], y + box_height + 5):
                          min(white.shape[0], y + box_height + 15), center_x1:center_x2]
            road_across = (above.size and below.size
                           and np.mean(above) >= 0.4 and np.mean(below) >= 0.4)
            if (road_across and box_width > width * 0.6
                    and y + box_height < roi.shape[0] * 0.55
                    and box_height < roi.shape[0] * 0.4):
                corner_across = True
            if (road_across and box_width > width * 0.25
                    and y + box_height < roi.shape[0] * 0.6
                    and box_height < roi.shape[0] * 0.4):
                across_segments.append((x, x + box_width, y + box_height / 2))
            if box_height > roi.shape[0] * 0.1 and y > roi.shape[0] * 0.25:
                if x + box_width > width * 0.96 and x > width * 0.78:
                    corner_sides.add("right")
                    if y + box_height > roi.shape[0] * 0.75:
                        near_corner_sides.add("right")
                if x < width * 0.04 and x + box_width < width * 0.22:
                    corner_sides.add("left")
                    if y + box_height > roi.shape[0] * 0.75:
                        near_corner_sides.add("left")
        if (roi_area * 0.001 < area < roi_area * 0.15
                and y > roi.shape[0] * 0.8):
            if x > width * 0.78 and x + box_width < width * 0.98:
                corner_sides.add("right")
                near_corner_sides.add("right")
            if x < width * 0.04 and x + box_width < width * 0.22:
                corner_sides.add("left")
                near_corner_sides.add("left")
        if area < max(100, roi_area * 0.0004) or area > roi_area * 0.15:
            continue
        if box_height < 12 or box_width > box_height * 6:
            continue
        if x + box_width >= width and x > width * 0.8:
            continue
        internal_line = line_has_road_on_both_sides(
            contour, white, x, y, box_width, box_height)
        outer_line = (bool(edge_points) and area >= roi_area * 0.006
                      and box_height >= roi.shape[0] * 0.45
                      and y + box_height >= roi.shape[0] * 0.75
                      and (x == 0 or x + box_width >= width))
        if not internal_line and not outer_line:
            continue
        local = np.zeros((box_height, box_width), np.uint8)
        shifted = contour - np.array([[[x, y]]], dtype=contour.dtype)
        cv2.drawContours(local, [shifted], -1, 255, -1)
        ys, xs = np.nonzero(local)
        if not xs.size:
            continue
        rows = np.unique(ys)
        top = np.percentile(rows, 20)
        bottom = np.percentile(rows, 80)
        far_x = x + float(np.median(xs[ys <= top]))
        near_x = x + float(np.median(xs[ys >= bottom]))
        span = max(1.0, bottom - top)
        heading = (far_x - near_x) * min(1.5, (y2 - y1) * 0.35 / span)
        heading = float(np.clip(heading, -width * 0.25, width * 0.25))
        candidate = (area, near_x, contour, heading, y + box_height, y)
        candidates.append(candidate)
        if internal_line:
            internal_candidates.append(candidate)

    if not corner_across:
        corner_across = any(
            left_x < width * 0.1 and right_x > width * 0.9
            and abs(left_y - right_y) < roi.shape[0] * 0.2
            for left_x, _, left_y in across_segments
            for _, right_x, right_y in across_segments
        )

    def draw_inset():
        detected = np.zeros((roi.shape[0], width, 3), np.uint8)
        for _, _, contour, _, _, _ in candidates:
            cv2.drawContours(detected, [contour], -1, (255, 255, 255), -1)
        if edge_points:
            cv2.polylines(detected, [np.array(edge_points, np.int32)], False,
                          (0, 140, 255), 3)
        inset = cv2.resize(detected, (inset_width, inset_height))
        overlay[:inset_height, width - inset_width:] = inset
        cv2.putText(overlay, "WHITE LANE / ORANGE EDGE",
                    (width - inset_width + 4, 14), cv2.FONT_HERSHEY_SIMPLEX,
                    0.28, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.rectangle(overlay, (width - inset_width, 0),
                      (width - 1, inset_height - 1), (0, 200, 255), 1)

    if surface < 0.25:
        draw_inset()
        return Reading("도로 미확인", 0.0, surface, None, overlay,
                       road_edge=edge_label)

    if edge_points:
        curve = np.array([(x, y + y1) for x, y in edge_points], np.int32)
        cv2.polylines(overlay, [curve], False, (0, 140, 255), 2)

    for _, _, contour, _, _, _ in candidates:
        shifted = contour + np.array([[[0, y1]]], dtype=contour.dtype)
        cv2.drawContours(overlay, [shifted], -1, (255, 255, 0), 2)

    center = width / 2
    def nearest_edge(options, prefer_right):
        if not options:
            return None
        minimum_area = max(roi_area * 0.0005,
                           max(item[0] for item in options) * 0.05)
        options = [item for item in options if item[0] >= minimum_area]
        if not options:
            return None
        nearest_y = max(item[4] for item in options)
        nearby = [item for item in options if item[4] >= nearest_y - height * 0.035]
        return max(nearby, key=lambda item: item[1] if prefer_right else -item[1])

    left = nearest_edge([c for c in candidates if c[1] < center], True)
    right = nearest_edge([c for c in candidates if c[1] > center], False)
    internal_pairs = [
        (first, second)
        for first in internal_candidates for second in internal_candidates
        if second[1] - first[1] >= width * 0.15
        and min(first[4], second[4]) - max(first[5], second[5]) >= 24
    ]
    default_pair = (left is not None and right is not None
                    and min(left[4], right[4]) - max(left[5], right[5]) >= 24)
    if (default_pair and abs((left[1] + right[1]) / 2 - center) > width * 0.2
            and internal_pairs):
        candidate_pair = min(internal_pairs, key=lambda pair: abs(
            (pair[0][1] + pair[1][1]) / 2 - center))
        if (abs((candidate_pair[0][1] + candidate_pair[1][1]) / 2 - center)
                < abs((left[1] + right[1]) / 2 - center) - 5):
            left, right = candidate_pair
    overlapping_edges = (left is not None and right is not None
                         and min(left[4], right[4]) - max(left[5], right[5]) >= 24)
    row_evidence = (scan_road_rows(dark, white) if not overlapping_edges else None)
    target = None
    heading_error = 0.0
    if overlapping_edges and right[1] - left[1] >= width * 0.15:
        lane = "양쪽 선"
        target = (left[1] + right[1]) / 2
        if left[3] * right[3] > 0:
            heading_error = (left[3] + right[3]) / 2
        line_score = min(1.0, (left[0] + right[0]) / (roi_area * 0.01))
        confidence = 0.4 + 0.35 * min(1.0, surface / 0.7) + 0.25 * line_score
        if max(left[4], right[4]) < roi.shape[0] * 0.45:
            confidence = min(confidence, 0.55)
    elif row_evidence and row_evidence[0] == "both":
        _, target, heading_error, count = row_evidence
        lane = "양쪽 선"
        confidence = 0.55 + 0.15 * min(1.0, surface / 0.7) + 0.1 * min(1.0, count / 5)
    elif left or right:
        lane = "한쪽 선"
        line = max((item for item in (left, right) if item is not None),
                   key=lambda item: item[4])
        target = line[1] + (width * 0.25 if line is left else -width * 0.25)
        target += 0.5 * line[3]
        heading_error = line[3]
        line_score = min(1.0, line[0] / (roi_area * 0.006))
        confidence = 0.2 + 0.3 * min(1.0, surface / 0.7) + 0.2 * line_score
    elif row_evidence:
        _, target, heading_error, count = row_evidence
        lane = "한쪽 선"
        confidence = 0.32 + 0.22 * min(1.0, surface / 0.7) + 0.12 * min(1.0, count / 8)
    else:
        lane = "선 미검출"
        confidence = 0.0

    corner = next(iter(corner_sides)) if corner_across and len(corner_sides) == 1 else None
    if corner and surface >= 0.7 and not overlapping_edges:
        lane = "오른쪽 코너" if corner == "right" else "왼쪽 코너"
        confidence = 0.75
        target = None
    else:
        corner = None

    if target is not None:
        cv2.line(overlay, (round(target), y1), (round(target), y2), (0, 255, 0), 2)
    draw_inset()
    return Reading(lane, min(confidence, 1.0), surface,
                   None if target is None else center - target, overlay,
                   heading_error, corner, edge_label, near_surface, edge_inward)
