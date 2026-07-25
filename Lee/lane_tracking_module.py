import cv2
import numpy as np
from collections import deque


class LaneTracker:
    def __init__(
        self,
        frame_width=320,
        crop_y1=60,
        crop_y2=220,
        center_tolerance=25,
        smooth_window=5,
    ):
        self.frame_width = frame_width
        self.crop_y1 = crop_y1
        self.crop_y2 = crop_y2
        self.center_tolerance = center_tolerance
        self.error_history = deque(maxlen=smooth_window)

    def make_coordinates(self, image_height, line_parameters):
        slope, intercept = line_parameters

        if abs(slope) < 1e-6:
            return None

        y1 = image_height
        y2 = 50
        x1 = int((y1 - intercept) / slope)
        x2 = int((y2 - intercept) / slope)

        return np.array([x1, y1, x2, y2])

    def average_slope_intercept(self, image_height, lines):
        left_fit = []
        right_fit = []

        if lines is None:
            return None, None

        for line in lines:
            line = np.array(line).reshape(-1)

            if len(line) != 4:
                continue

            x1, y1, x2, y2 = line

            if x1 == x2:
                continue

            slope, intercept = np.polyfit((x1, x2), (y1, y2), 1)

            if slope < -0.3:
                left_fit.append((slope, intercept))
            elif slope > 0.3:
                right_fit.append((slope, intercept))

        left_line = None
        right_line = None

        if left_fit:
            left_line = self.make_coordinates(
                image_height,
                np.average(left_fit, axis=0),
            )

        if right_fit:
            right_line = self.make_coordinates(
                image_height,
                np.average(right_fit, axis=0),
            )

        return left_line, right_line

    def process(self, frame, save_debug=False):
        cropped_frame = frame[self.crop_y1:self.crop_y2, 0:self.frame_width]
        image_height = cropped_frame.shape[0]

        gray_frame = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)
        blur_frame = cv2.GaussianBlur(gray_frame, (5, 5), 0)
        edge_frame = cv2.Canny(blur_frame, 50, 150)

        mask = np.zeros_like(edge_frame)
        polygon = np.array(
            [[
                (0, image_height),
                (0, 20),
                (self.frame_width, 20),
                (self.frame_width, image_height),
            ]],
            np.int32,
        )
        cv2.fillPoly(mask, polygon, 255)
        masked_edge = cv2.bitwise_and(edge_frame, mask)

        lines = cv2.HoughLinesP(
            masked_edge,
            1,
            np.pi / 180,
            30,
            minLineLength=30,
            maxLineGap=20,
        )

        left_line, right_line = self.average_slope_intercept(image_height, lines)

        camera_center = self.frame_width // 2
        lane_center = None
        error = 0
        status = "no_lane"
        line_result = cropped_frame.copy()

        if left_line is not None and right_line is not None:
            self.draw_line(line_result, left_line, (255, 0, 0))
            self.draw_line(line_result, right_line, (255, 0, 0))

            lane_center = int((left_line[0] + right_line[0]) // 2)
            error = camera_center - lane_center
            status = "both_lanes"

            cv2.line(
                line_result,
                (lane_center, image_height),
                (lane_center, max(0, image_height - 30)),
                (0, 255, 0),
                5,
            )

        elif left_line is not None:
            self.draw_line(line_result, left_line, (255, 0, 0))
            error = -50
            status = "left_only"

        elif right_line is not None:
            self.draw_line(line_result, right_line, (255, 0, 0))
            error = 50
            status = "right_only"

        self.error_history.append(error)
        smoothed_error = int(sum(self.error_history) / len(self.error_history))

        if abs(smoothed_error) < self.center_tolerance:
            direction = "forward"
        elif smoothed_error < 0:
            direction = "right"
        else:
            direction = "left"

        cv2.putText(
            line_result,
            f"error={smoothed_error} dir={direction}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )

        if save_debug:
            cv2.imwrite("lane_debug_cropped.jpg", cropped_frame)
            cv2.imwrite("lane_debug_edge.jpg", edge_frame)
            cv2.imwrite("lane_debug_masked_edge.jpg", masked_edge)
            cv2.imwrite("lane_result.jpg", line_result)

        return {
            "error": error,
            "smoothed_error": smoothed_error,
            "direction": direction,
            "status": status,
            "lane_center": lane_center,
            "camera_center": camera_center,
            "debug_frame": line_result,
        }

    def draw_line(self, image, line, color):
        if line is None:
            return

        x1, y1, x2, y2 = line
        cv2.line(
            image,
            (int(x1), int(y1)),
            (int(x2), int(y2)),
            color,
            5,
        )
