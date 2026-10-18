"""Offline colour segmentation for the new black/yellow/white track. No control."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class VisionConfig:
    max_side: int = 1280
    roi_top: float = 0.0
    yellow_hue_low: int = 18
    yellow_hue_high: int = 42
    yellow_min_saturation: int = 55
    yellow_min_value: int = 95
    road_max_value: int = 155
    road_min_dark_fraction: float = 0.70
    white_min_value: int = 175
    white_max_saturation: int = 80
    white_min_contrast: int = 16

    def __post_init__(self):
        if self.max_side < 64 or not 0 <= self.roi_top < 1:
            raise ValueError("max_side must be >= 64; roi_top must be in [0, 1).")
        if not 0 <= self.yellow_hue_low <= self.yellow_hue_high <= 179:
            raise ValueError("Yellow hue bounds must be ordered within [0, 179].")
        if not 0 <= self.road_min_dark_fraction <= 1:
            raise ValueError("road_min_dark_fraction must be in [0, 1].")
        for value in (self.yellow_min_saturation, self.yellow_min_value,
                      self.road_max_value, self.white_min_value,
                      self.white_max_saturation, self.white_min_contrast):
            if not 0 <= value <= 255:
                raise ValueError("Colour/contrast bounds must be in [0, 255].")


@dataclass
class VisionResult:
    frame: np.ndarray
    road: np.ndarray
    yellow: np.ndarray
    white: np.ndarray
    dashes: np.ndarray
    markings: list
    metrics: dict


def _road_regions(hsv, yellow, config):
    # Yellow barriers split the image into regions. Classify the interiors,
    # not every dark pixel: grey floor and dark classroom objects are not road.
    kernel = np.ones((5, 5), dtype=np.uint8)
    barrier = cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, kernel)
    barrier = cv2.dilate(barrier, np.ones((3, 3), dtype=np.uint8))
    roi_row = int(yellow.shape[0] * config.roi_top)
    barrier[:roi_row] = 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(255 - barrier, 8)
    dark = (hsv[:, :, 2] <= config.road_max_value) & (hsv[:, :, 1] < 140)
    dark_counts = np.bincount(labels[dark], minlength=count)
    neighbour = cv2.dilate(barrier, kernel) > 0
    contacts = np.bincount(labels[neighbour], minlength=count)
    area_limit = yellow.size * 0.001
    accepted = np.zeros(count, dtype=bool)
    for index in range(1, count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < area_limit:
            continue
        if contacts[index] < 20:
            continue
        if dark_counts[index] / area >= config.road_min_dark_fraction:
            accepted[index] = True
    return np.where(accepted[labels], 255, 0).astype(np.uint8)


def _markings(mask):
    # Local-contrast thresholding can split blurred paint by a few pixels.
    # Repair those small gaps before measuring rectangular fill, not by
    # relaxing shape/area limits or bridging full dash-to-dash gaps.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cleaned = np.zeros_like(mask)
    dashes = np.zeros_like(mask)
    markings = []
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 8:
            continue
        rect = cv2.minAreaRect(contour)
        length, thickness = sorted(rect[1], reverse=True)
        if thickness < 1:
            continue
        aspect = length / thickness
        fill = area / max(length * thickness, 1)
        depth = rect[0][1] / mask.shape[0]
        # Nearby paint occupies more pixels; a global area cap discarded it.
        area_limit = mask.size * (0.004 + 0.010 * depth * depth)
        eligible = (1.2 <= aspect <= 14 and 12 <= area <= area_limit and fill >= 0.60)
        dash = eligible and aspect >= 1.8
        cv2.drawContours(cleaned, [contour], -1, 255, cv2.FILLED)
        markings.append({
            "center": [round(float(v), 1) for v in rect[0]],
            "length_px": round(float(length), 1),
            "thickness_px": round(float(thickness), 1),
            "area_px": round(float(area), 1),
            "aspect_ratio": round(float(aspect), 3),
            "fill_ratio": round(float(fill), 3),
            "area_limit_px": round(float(area_limit), 1),
            "dash_candidate": bool(dash),
            "dash_basis": "shape" if dash else "rejected",
        })
        candidates.append((contour, rect, eligible))

    # Perspective makes distant dashes look almost square. Admit those only
    # with two vertically separated neighbours, rather than accepting squares
    # everywhere. These are still candidates, not a selected lane/path.
    for index, (_, rect, eligible) in enumerate(candidates):
        if not eligible or markings[index]["dash_candidate"]:
            continue
        neighbours = 0
        for other_index, (_, other, other_eligible) in enumerate(candidates):
            if index == other_index or not other_eligible:
                continue
            dy = abs(rect[0][1] - other[0][1])
            thickness = max(min(rect[1]), min(other[1]))
            if not thickness * 1.2 <= dy <= mask.shape[0] * 0.30:
                continue
            if abs(rect[0][0] - other[0][0]) <= thickness * 2 + dy * 0.25:
                neighbours += 1
        if neighbours >= 2:
            markings[index]["dash_candidate"] = True
            markings[index]["dash_basis"] = "sequence"
    for marking, (contour, _, _) in zip(markings, candidates):
        if marking["dash_candidate"]:
            cv2.drawContours(dashes, [contour], -1, 255, cv2.FILLED)
    return cleaned, dashes, markings


def analyze(frame, config=None):
    config = config or VisionConfig()
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 8):
        raise ValueError("Expected a nonempty uint8 BGR image with 3 channels.")
    original_height, original_width = frame.shape[:2]
    scale = min(1.0, config.max_side / max(original_height, original_width))
    if scale < 1:
        frame = cv2.resize(frame, (round(original_width * scale),
                                   round(original_height * scale)),
                           interpolation=cv2.INTER_AREA)
    else:
        frame = frame.copy()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv,
                        (config.yellow_hue_low, config.yellow_min_saturation,
                         config.yellow_min_value),
                        (config.yellow_hue_high, 255, 255))
    roi_row = int(frame.shape[0] * config.roi_top)
    yellow[:roi_row] = 0
    road = _road_regions(hsv, yellow, config)
    road[:roi_row] = 0
    # Keep complete yellow components only when they touch a road region.
    # Yellow robot parts overlapping the road still need an exclusion ROI.
    count, labels = cv2.connectedComponents(yellow, 8)
    near_road = cv2.dilate(road, np.ones((11, 11), dtype=np.uint8)) > 0
    supported = np.zeros(count, dtype=bool)
    supported[np.unique(labels[near_road])] = True
    supported[0] = False
    yellow_candidates = int(np.count_nonzero(yellow))
    yellow = np.where(supported[labels], 255, 0).astype(np.uint8)
    interior = cv2.erode(road, np.ones((3, 3), dtype=np.uint8)) > 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    local = cv2.GaussianBlur(gray, (0, 0), 7)
    contrast = gray.astype(np.int16) - local.astype(np.int16)
    white = np.where(interior & (hsv[:, :, 2] >= config.white_min_value)
                     & (hsv[:, :, 1] <= config.white_max_saturation)
                     & (contrast >= config.white_min_contrast), 255, 0).astype(np.uint8)
    white, dashes, markings = _markings(white)
    yellow_count = int(np.count_nonzero(yellow))
    road_count = int(np.count_nonzero(road))
    if yellow_candidates < 20:
        status = "no_yellow_boundary"
    elif road_count == 0:
        status = "road_region_unconfirmed"
    elif not markings:
        status = "road_only"
    else:
        status = "markings_detected"
    metrics = {
        "status": status,
        "mode": "offline_segmentation_only",
        "original_size": [original_width, original_height],
        "analysis_size": [frame.shape[1], frame.shape[0]],
        "roi_top": config.roi_top,
        "road_fraction": round(road_count / road.size, 4),
        "yellow_pixels": yellow_count,
        "raw_yellow_pixels": yellow_candidates,
        "white_marking_count": len(markings),
        "dash_candidate_count": sum(m["dash_candidate"] for m in markings),
        "target_path": None,
        "control_enabled": False,
    }
    return VisionResult(frame, road, yellow, white, dashes, markings, metrics)


def combined_lines(result):
    output = np.zeros_like(result.frame)
    output[result.yellow > 0] = (0, 215, 255)
    output[result.dashes > 0] = (255, 255, 255)
    return output


def overlay(result, *, lines_only=False):
    output = result.frame.copy()
    if not lines_only:
        road = result.road > 0
        tint = np.full_like(output, (150, 90, 35))
        output[road] = cv2.addWeighted(output, 0.75, tint, 0.25, 0)[road]
    layers = [(result.yellow, (0, 215, 255) if lines_only else (0, 165, 255))]
    if not lines_only:
        layers.append((result.white, (180, 100, 255)))
    layers.append((result.dashes, (255, 255, 0)))
    for mask, color in layers:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(output, contours, -1, color, 2, cv2.LINE_AA)
    return output
