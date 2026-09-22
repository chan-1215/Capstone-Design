"""Road driving test using OpenCV lane filtering and P-control.

This file is intentionally standalone in the "Driving test" folder. It avoids
the existing dataset/model/gesture/ultrasonic/LCD/IMU paths and only uses:

- camera frames
- OpenCV lane filtering
- P-control
- gpiozero motor output

Default motor pins match the professor PDF examples, but every pin pair can be
overridden from the command line for a newly built robot.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


cv2 = None
np = None


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEE_DIRECTORY = REPOSITORY_ROOT / "Lee"

from motor_module import MotorController  # noqa: E402


def load_vision_dependencies() -> None:
    global cv2, np
    if cv2 is not None and np is not None:
        return
    try:
        import cv2 as cv2_module
        import numpy as np_module
    except ModuleNotFoundError as exc:
        missing = exc.name or "opencv-python/numpy"
        raise SystemExit(
            f"Missing Python package: {missing}\n"
            "Install on Raspberry Pi with:\n"
            "  sudo apt update\n"
            "  sudo apt install -y python3-opencv python3-numpy python3-gpiozero python3-lgpio"
        ) from exc
    cv2 = cv2_module
    np = np_module


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_pin_pair(text: str) -> Tuple[int, int]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("pin pair must look like 22,27")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pins must be integers") from exc


class MovingAverage:
    def __init__(self, window: int) -> None:
        self.values = deque(maxlen=max(1, window))

    def reset(self) -> None:
        self.values.clear()

    def update(self, value: float) -> float:
        self.values.append(value)
        return sum(self.values) / len(self.values)


class LowPass:
    def __init__(self, alpha: float) -> None:
        self.alpha = clamp(alpha, 0.0, 1.0)
        self.value: Optional[float] = None

    def reset(self, value: float = 0.0) -> None:
        self.value = value

    def update(self, target: float) -> float:
        if self.value is None:
            self.value = target
        else:
            self.value = self.alpha * target + (1.0 - self.alpha) * self.value
        return self.value


class RateLimiter:
    def __init__(self, max_delta: float) -> None:
        self.max_delta = max(0.0, max_delta)
        self.value = 0.0

    def reset(self, value: float = 0.0) -> None:
        self.value = value

    def update(self, target: float) -> float:
        delta = clamp(target - self.value, -self.max_delta, self.max_delta)
        self.value += delta
        return self.value


@dataclass
class LaneDetection:
    visible: bool
    status: str
    error: Optional[float]
    target_x: Optional[float]
    center_x: float
    debug_frame: object


@dataclass
class ControlOutput:
    left_pwm: float
    right_pwm: float
    turn: float
    target_speed: float
    filtered_error: float
    stop: bool
    reason: str


class LaneDetector:
    def __init__(
        self,
        mode: str,
        crop_top_ratio: float,
        crop_bottom_ratio: float,
        threshold: int,
        min_area: int,
        lane_half_width: int,
        min_lane_gap: int,
    ) -> None:
        self.mode = mode
        self.crop_top_ratio = clamp(crop_top_ratio, 0.0, 0.95)
        self.crop_bottom_ratio = clamp(crop_bottom_ratio, 0.05, 1.0)
        self.threshold = threshold
        self.min_area = max(1, min_area)
        self.lane_half_width = max(1, lane_half_width)
        self.min_lane_gap = max(1, min_lane_gap)

    def process(self, frame) -> LaneDetection:
        height, width = frame.shape[:2]
        center_x = width / 2.0
        y1 = int(height * self.crop_top_ratio)
        y2 = int(height * self.crop_bottom_ratio)
        if y2 <= y1:
            y1 = int(height * 0.45)
            y2 = height

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        roi_gray = gray[y1:y2, :]
        roi_gray = self._normalize_polarity(roi_gray)
        blur = cv2.GaussianBlur(roi_gray, (5, 5), 0)

        if self.threshold <= 0:
            _, mask = cv2.threshold(
                blur,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
        else:
            _, mask = cv2.threshold(blur, self.threshold, 255, cv2.THRESH_BINARY)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        target_x, status = self._find_target_x(mask, center_x)
        debug = self._draw_debug(frame, mask, y1, y2, target_x, center_x, status)

        if target_x is None:
            return LaneDetection(
                visible=False,
                status="lost",
                error=None,
                target_x=None,
                center_x=center_x,
                debug_frame=debug,
            )

        error = center_x - target_x
        return LaneDetection(
            visible=True,
            status=status,
            error=error,
            target_x=target_x,
            center_x=center_x,
            debug_frame=debug,
        )

    def _normalize_polarity(self, roi_gray):
        sample_y = int(roi_gray.shape[0] * 0.65)
        sample = roi_gray[sample_y:, int(roi_gray.shape[1] * 0.35) : int(roi_gray.shape[1] * 0.65)]
        if sample.size and float(np.median(sample)) > 127.0:
            return 255 - roi_gray
        return roi_gray

    def _find_target_x(self, mask, center_x: float) -> Tuple[Optional[float], str]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area:
                continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            cx = moments["m10"] / moments["m00"]
            x, _, w, _ = cv2.boundingRect(contour)
            candidates.append((area, cx, x, w))

        if not candidates:
            return None, "lost"

        candidates.sort(reverse=True)

        if self.mode == "center-line":
            return self._weighted_mask_center(mask), "center_line"

        if self.mode in {"auto", "lane-borders"}:
            left_right = self._two_separated_candidates(candidates)
            if left_right is not None:
                left_x, right_x = left_right
                return (left_x + right_x) / 2.0, "both_edges"

        if self.mode == "lane-borders":
            largest_x = candidates[0][1]
            if largest_x < center_x:
                return largest_x + self.lane_half_width, "left_edge"
            return largest_x - self.lane_half_width, "right_edge"

        return self._weighted_mask_center(mask), "center_line"

    def _weighted_mask_center(self, mask) -> Optional[float]:
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None
        weights = ys.astype(np.float32) + 1.0
        return float(np.average(xs, weights=weights))

    def _two_separated_candidates(self, candidates) -> Optional[Tuple[float, float]]:
        by_x = sorted(candidates[:6], key=lambda item: item[1])
        best = None
        best_area = -1.0

        for left in by_x:
            for right in by_x:
                if right[1] - left[1] < self.min_lane_gap:
                    continue
                area = left[0] + right[0]
                if area > best_area:
                    best_area = area
                    best = (left[1], right[1])
        return best

    def _draw_debug(self, frame, mask, y1: int, y2: int, target_x, center_x: float, status: str):
        debug = frame.copy()
        cv2.rectangle(debug, (0, y1), (frame.shape[1] - 1, y2 - 1), (80, 80, 80), 1)
        cv2.line(debug, (int(center_x), y1), (int(center_x), y2), (255, 0, 0), 2)
        if target_x is not None:
            cv2.line(debug, (int(target_x), y1), (int(target_x), y2), (0, 255, 0), 2)
        cv2.putText(
            debug,
            status,
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        small_mask = cv2.resize(mask, (frame.shape[1] // 3, frame.shape[0] // 3))
        small_mask = cv2.cvtColor(small_mask, cv2.COLOR_GRAY2BGR)
        mh, mw = small_mask.shape[:2]
        debug[0:mh, frame.shape[1] - mw : frame.shape[1]] = small_mask
        return debug


class RoadPController:
    def __init__(
        self,
        base_speed: float,
        min_speed: float,
        max_speed: float,
        kp: float,
        max_turn: float,
        slowdown: float,
        error_window: int,
        pwm_alpha: float,
        pwm_step: float,
        lost_frame_limit: int,
        invert_steering: bool,
    ) -> None:
        self.base_speed = base_speed
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.kp = kp
        self.max_turn = max_turn
        self.slowdown = slowdown
        self.error_filter = MovingAverage(error_window)
        self.left_low_pass = LowPass(pwm_alpha)
        self.right_low_pass = LowPass(pwm_alpha)
        self.left_rate = RateLimiter(pwm_step)
        self.right_rate = RateLimiter(pwm_step)
        self.lost_frame_limit = max(0, lost_frame_limit)
        self.invert_steering = invert_steering
        self.lost_frames = 0
        self.last_error: Optional[float] = None

    def update(self, lane: LaneDetection) -> ControlOutput:
        if lane.visible and lane.error is not None:
            self.lost_frames = 0
            self.last_error = lane.error
            error = lane.error
            reason = lane.status
            lane_visible = True
        else:
            self.lost_frames += 1
            lane_visible = False
            if self.last_error is None or self.lost_frames > self.lost_frame_limit:
                self._reset_pwm()
                return ControlOutput(0.0, 0.0, 0.0, 0.0, 0.0, True, "lane_lost")
            error = self.last_error
            reason = "short_lane_gap"

        filtered_error = self.error_filter.update(error)
        turn = clamp(self.kp * filtered_error, -self.max_turn, self.max_turn)
        if self.invert_steering:
            turn = -turn

        target_speed = self.base_speed - abs(turn) * self.slowdown
        target_speed = clamp(target_speed, self.min_speed, self.max_speed)
        if not lane_visible:
            target_speed = min(target_speed, self.min_speed)

        raw_left = clamp(target_speed - turn, 0.0, self.max_speed)
        raw_right = clamp(target_speed + turn, 0.0, self.max_speed)

        smooth_left = self.left_low_pass.update(raw_left)
        smooth_right = self.right_low_pass.update(raw_right)
        left_pwm = self.left_rate.update(smooth_left)
        right_pwm = self.right_rate.update(smooth_right)

        return ControlOutput(
            left_pwm=left_pwm,
            right_pwm=right_pwm,
            turn=turn,
            target_speed=target_speed,
            filtered_error=filtered_error,
            stop=False,
            reason=reason,
        )

    def _reset_pwm(self) -> None:
        self.left_low_pass.reset(0.0)
        self.right_low_pass.reset(0.0)
        self.left_rate.reset(0.0)
        self.right_rate.reset(0.0)

    def reset(self) -> None:
        """Clear steering history before a new driving session."""
        self.error_filter.reset()
        self.last_error = None
        self.lost_frames = 0
        self._reset_pwm()


class OpenCvCamera:
    def __init__(self, index: int, width: int, height: int, fps: int) -> None:
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        if not self.cap.isOpened():
            raise SystemExit(f"OpenCV camera index {index} is not available")

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def stop(self) -> None:
        self.cap.release()


class VideoFileCamera:
    def __init__(self, path: Path, loop: bool) -> None:
        self.path = path
        self.loop = loop
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise SystemExit(f"Cannot open video file: {path}")

    def read(self):
        ok, frame = self.cap.read()
        if ok:
            return frame
        if not self.loop:
            return None
        self.cap.release()
        self.cap = cv2.VideoCapture(str(self.path))
        ok, frame = self.cap.read()
        return frame if ok else None

    def stop(self) -> None:
        self.cap.release()


class LeeCamera:
    def __init__(self, width: int, height: int, fps: int) -> None:
        if str(LEE_DIRECTORY) not in sys.path:
            sys.path.insert(0, str(LEE_DIRECTORY))
        try:
            from camera_module import get_latest_frame, start_camera, stop_camera
        except ModuleNotFoundError as exc:
            raise SystemExit(f"Cannot import Lee camera module from {LEE_DIRECTORY}") from exc

        self.get_latest_frame = get_latest_frame
        self.stop_camera = stop_camera
        start_camera(width=width, height=height, fps=fps, show_preview=False)

    def read(self):
        return self.get_latest_frame()

    def stop(self) -> None:
        self.stop_camera()


def build_camera(args):
    if args.input_video is not None:
        return VideoFileCamera(args.input_video, args.loop_video)
    if args.camera == "lee":
        return LeeCamera(args.width, args.height, args.fps)
    return OpenCvCamera(args.camera_index, args.width, args.height, args.fps)


def build_motors(args):
    return MotorController(
        motor_pins={
            1: args.right_front_pins,
            2: args.right_rear_pins,
            3: args.left_front_pins,
            4: args.left_rear_pins,
        },
        left_motors=(3, 4),
        right_motors=(1, 2),
        dry_run=args.dry_run,
        dry_run_verbose=False,
        invert_left_pins=args.invert_left_pins,
        invert_right_pins=args.invert_right_pins,
    )


def open_csv_log(path: Optional[Path]):
    if path is None:
        return None, None
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    writer.writerow(
        [
            "time_s",
            "frame",
            "lane_status",
            "error",
            "filtered_error",
            "turn",
            "target_speed",
            "left_pwm",
            "right_pwm",
            "reason",
        ]
    )
    return handle, writer


def format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--camera", choices=["opencv", "lee"], default="opencv")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--input-video", type=Path)
    parser.add_argument("--loop-video", action="store_true")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-csv", type=Path)
    parser.add_argument("--print-every", type=int, default=5)

    parser.add_argument("--mode", choices=["auto", "center-line", "lane-borders"], default="auto")
    parser.add_argument("--crop-top-ratio", type=float, default=0.45)
    parser.add_argument("--crop-bottom-ratio", type=float, default=0.98)
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--min-area", type=int, default=50)
    parser.add_argument("--lane-half-width", type=int, default=70)
    parser.add_argument("--min-lane-gap", type=int, default=55)

    parser.add_argument("--base-speed", type=float, default=0.25)
    parser.add_argument("--min-speed", type=float, default=0.08)
    parser.add_argument("--max-speed", type=float, default=0.45)
    parser.add_argument("--kp", type=float, default=0.0035)
    parser.add_argument("--max-turn", type=float, default=0.22)
    parser.add_argument("--slowdown", type=float, default=0.55)
    parser.add_argument("--error-window", type=int, default=5)
    parser.add_argument("--pwm-alpha", type=float, default=0.45)
    parser.add_argument("--pwm-step", type=float, default=0.04)
    parser.add_argument("--lost-frame-limit", type=int, default=4)
    parser.add_argument("--invert-steering", action="store_true")

    parser.add_argument("--left-front-pins", type=parse_pin_pair, default=(22, 27))
    parser.add_argument("--left-rear-pins", type=parse_pin_pair, default=(24, 23))
    parser.add_argument("--right-front-pins", type=parse_pin_pair, default=(26, 19))
    parser.add_argument("--right-rear-pins", type=parse_pin_pair, default=(20, 21))
    parser.add_argument("--invert-left-pins", action="store_true")
    parser.add_argument("--invert-right-pins", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_vision_dependencies()

    detector = LaneDetector(
        mode=args.mode,
        crop_top_ratio=args.crop_top_ratio,
        crop_bottom_ratio=args.crop_bottom_ratio,
        threshold=args.threshold,
        min_area=args.min_area,
        lane_half_width=args.lane_half_width,
        min_lane_gap=args.min_lane_gap,
    )
    controller = RoadPController(
        base_speed=args.base_speed,
        min_speed=args.min_speed,
        max_speed=args.max_speed,
        kp=args.kp,
        max_turn=args.max_turn,
        slowdown=args.slowdown,
        error_window=args.error_window,
        pwm_alpha=args.pwm_alpha,
        pwm_step=args.pwm_step,
        lost_frame_limit=args.lost_frame_limit,
        invert_steering=args.invert_steering,
    )

    camera = build_camera(args)
    motors = build_motors(args)
    csv_handle, csv_writer = open_csv_log(args.log_csv)

    print("OpenCV road driver started")
    print(f"camera={args.input_video if args.input_video else args.camera} dry_run={args.dry_run}")
    print(f"mode={args.mode} kp={args.kp:.4f} base={args.base_speed:.2f} max={args.max_speed:.2f}")
    if args.dry_run:
        print("dry-run: motor GPIO output is disabled")

    start_time = time.monotonic()
    frame_index = 0

    try:
        while True:
            if args.duration > 0 and time.monotonic() - start_time >= args.duration:
                break

            frame = camera.read()
            if frame is None:
                if args.input_video is not None:
                    break
                motors.stop()
                time.sleep(0.02)
                continue

            lane = detector.process(frame)
            output = controller.update(lane)
            motors.set(output.left_pwm, output.right_pwm)

            elapsed = time.monotonic() - start_time
            if frame_index % max(1, args.print_every) == 0:
                print(
                    f"t={elapsed:6.2f}s frame={frame_index:05d} lane={lane.status:11s} "
                    f"err={format_number(lane.error):>6s} filt={output.filtered_error:7.1f} "
                    f"turn={output.turn:+.3f} left={output.left_pwm:.3f} right={output.right_pwm:.3f} "
                    f"{output.reason}"
                )

            if csv_writer is not None:
                csv_writer.writerow(
                    [
                        f"{elapsed:.3f}",
                        frame_index,
                        lane.status,
                        "" if lane.error is None else f"{lane.error:.3f}",
                        f"{output.filtered_error:.3f}",
                        f"{output.turn:.4f}",
                        f"{output.target_speed:.4f}",
                        f"{output.left_pwm:.4f}",
                        f"{output.right_pwm:.4f}",
                        output.reason,
                    ]
                )

            if args.preview:
                cv2.imshow("Driving test - OpenCV P-control", lane.debug_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            frame_index += 1
            time.sleep(1.0 / max(1, args.fps))

    except KeyboardInterrupt:
        print("stopped by user")
    finally:
        motors.stop()
        motors.cleanup()
        camera.stop()
        if csv_handle is not None:
            csv_handle.close()
        if args.preview:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
