"""Offline experimental colour -> blur -> Canny -> Hough pipeline. No control."""

from dataclasses import dataclass
import math

import cv2
import numpy as np


FULL_ROI = ((0., 1.), (0., 0.), (1., 0.), (1., 1.))
TEXTBOOK_ROI = ((0., 1.), (.3125, 1/3), (.6875, 1/3), (1., 1.))


@dataclass(frozen=True)
class HoughConfig:
    max_side: int = 480
    roi_top: float = .20
    blur_size: int = 5
    colour: str = "yellow"
    canny_low: int = 50
    canny_high: int = 150
    votes_at_320: int = 30
    length_at_320: int = 30
    gap_at_320: int = 20
    polygon: tuple = FULL_ROI
    bird_eye: bool = False

    def __post_init__(self):
        if isinstance(self.max_side, bool) or not isinstance(self.max_side, int) or self.max_side < 64:
            raise ValueError("max_side must be an integer >= 64")
        if (isinstance(self.roi_top, bool) or not isinstance(self.roi_top, (int, float))
                or not math.isfinite(self.roi_top) or not 0 <= self.roi_top <= .90):
            raise ValueError("roi_top must be finite and between 0 and .90")
        if type(self.blur_size) is not int or self.blur_size not in (0, 3, 5, 7):
            raise ValueError("blur_size must be 0, 3, 5 or 7")
        if self.colour not in ("yellow", "white", "both"):
            raise ValueError("colour must be yellow, white or both")
        if (type(self.canny_low) is not int or type(self.canny_high) is not int
                or not 0 <= self.canny_low < self.canny_high <= 255):
            raise ValueError("Canny thresholds must satisfy 0 <= low < high <= 255")
        for value in (self.votes_at_320, self.length_at_320, self.gap_at_320):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("Hough settings must be positive integers")
        points = np.asarray(self.polygon, dtype=np.float32)
        if (points.shape != (4, 2) or not np.isfinite(points).all()
                or np.any(points < 0) or np.any(points > 1)
                or not cv2.isContourConvex(points)
                or cv2.contourArea(points) < .02
                or not (points[0, 0] < points[3, 0] and points[1, 0] < points[2, 0]
                        and points[0, 1] > points[1, 1] and points[3, 1] > points[2, 1])):
            raise ValueError("polygon must be convex normalized BL, TL, TR, BR crop coordinates")
        if not isinstance(self.bird_eye, bool):
            raise ValueError("bird_eye must be a boolean")


@dataclass
class HoughResult:
    frame: np.ndarray
    crop: np.ndarray
    masks: dict
    metrics: dict


def merge_segments(segments, width):
    """Textbook endpoint means, without substituting image edges for missing lines."""
    left, right = [], []
    crossing = 0
    for x1, y1, x2, y2 in segments:
        if x1 < width/2 and x2 < width/2:
            left.extend((x1, x2))
        elif x1 > width/2 and x2 > width/2:
            right.extend((x1, x2))
        else:
            crossing += 1
    left_x = float(np.mean(left)) if left else None
    right_x = float(np.mean(right)) if right else None
    observed = bool(left and right)
    center = (left_x+right_x)/2 if observed else None
    error = center-width/2 if observed else None
    return dict(two_sided_observation=observed,
                reason="two_sides" if observed else "left_only" if left else
                "right_only" if right else "unassigned_segments" if crossing else "no_segments",
                left_x=left_x, right_x=right_x, center_x=center, error_px=error,
                normalized_error=error/(width/2) if observed else None,
                left_segment_count=len(left)//2, right_segment_count=len(right)//2,
                crossing_segment_count=crossing,
                target_semantics="midpoint_of_yellow_or_selected_colour_groups",
                drive_authorized=False)


def analyze_hough(frame, config=None):
    config = config or HoughConfig()
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 8):
        raise ValueError("Expected a nonempty uint8 BGR image")
    source_height, source_width = frame.shape[:2]
    ratio = min(1., config.max_side/max(source_height, source_width))
    size = (max(1, round(source_width*ratio)), max(1, round(source_height*ratio)))
    frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA) if ratio < 1 else frame.copy()
    top = int(frame.shape[0]*config.roi_top)
    crop = frame[top:].copy()
    height, width = crop.shape[:2]
    if min(height, width) < 8:
        raise ValueError("Cropped image must have at least 8 pixels on each side")
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (20, 100, 100), (40, 255, 255))
    white = cv2.inRange(hsv, (0, 0, 175), (179, 80, 255))
    colour = (yellow if config.colour == "yellow" else white if config.colour == "white"
              else cv2.bitwise_or(yellow, white))
    blurred = (cv2.GaussianBlur(colour, (config.blur_size, config.blur_size), 0)
               if config.blur_size else colour.copy())
    edges = cv2.Canny(blurred, config.canny_low, config.canny_high)
    source = np.asarray(config.polygon, np.float32)*np.array([width-1, height-1], np.float32)
    roi = np.zeros_like(edges)
    cv2.fillPoly(roi, [np.rint(source).astype(np.int32)], 255)
    roi_edges = cv2.bitwise_and(edges, roi)
    transform = np.eye(3, dtype=np.float64)
    if config.bird_eye:
        destination = np.asarray(FULL_ROI, np.float32)*np.array([width-1, height-1], np.float32)
        transform = cv2.getPerspectiveTransform(source, destination)
        transformed = cv2.warpPerspective(roi_edges, transform, (width, height))
        # Keep Hough input binary after interpolation of the transformed edge map.
        transformed = cv2.threshold(transformed, 127, 255, cv2.THRESH_BINARY)[1]
    else:
        transformed = roi_edges.copy()
    scale = width/320.
    parameters = dict(threshold=max(1, round(config.votes_at_320*scale)),
                      minLineLength=max(1, round(config.length_at_320*scale)),
                      maxLineGap=max(1, round(config.gap_at_320*scale)))
    found = cv2.HoughLinesP(transformed, 1, np.pi/180, **parameters)
    segments = [] if found is None else found.reshape(-1, 4).tolist()
    metrics = merge_segments(segments, width)
    metrics.update(segment_count=len(segments), segments=segments,
                   original_size=[source_width, source_height], analysis_size=list(size),
                   crop_y=top, crop_size=[width, height], bird_eye=config.bird_eye,
                   roi_polygon=source.tolist(),
                   perspective_matrix=transform.tolist(), hough_parameters=parameters,
                   colour_pixels=int(np.count_nonzero(colour)),
                   edge_pixels=int(np.count_nonzero(transformed)))
    return HoughResult(frame, crop, dict(colour=colour, blur=blurred, edges=edges,
                                        roi=roi_edges, transformed=transformed), metrics)


def overlay_hough(result):
    """Render outside the timed perception path."""
    metrics = result.metrics
    height, width = result.crop.shape[:2]
    rendered = (cv2.warpPerspective(result.crop, np.asarray(metrics["perspective_matrix"]),
                                    (width, height))
                if metrics["bird_eye"] else result.crop.copy())
    for x1, y1, x2, y2 in metrics["segments"]:
        cv2.line(rendered, (x1, y1), (x2, y2), (255, 100, 220), 1)
    for key, colour_value in (("left_x", (0, 215, 255)), ("right_x", (0, 215, 255)),
                              ("center_x", (0, 255, 0))):
        if metrics[key] is not None:
            x = int(round(metrics[key]))
            cv2.line(rendered, (x, 0), (x, height-1), colour_value, 2)
    cv2.line(rendered, (width//2, 0), (width//2, height-1), (255, 100, 0), 1)
    if not metrics["bird_eye"]:
        polygon = np.rint(metrics["roi_polygon"]).astype(np.int32)
        cv2.polylines(rendered, [polygon], True, (180, 180, 180), 1)
    return rendered
