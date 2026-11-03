"""Versioned image and telemetry recorder for Webots driving runs."""

import csv
import json
from datetime import datetime
from pathlib import Path

import cv2


class DatasetRecorder:
    FIELDNAMES = [
        "sample_id",
        "simulation_time",
        "image_path",
        "control_mode",
        "target_lane",
        "corner_radius_m",
        "corner_curvature_1pm",
        "lane_status",
        "lane_error",
        "lane_direction",
        "decision_reason",
        "command",
        "left_pwm",
        "right_pwm",
        "expert_left_pwm",
        "expert_right_pwm",
        "driveability_score",
        "safety_state",
        "position_x",
        "position_y",
        "yaw",
        "cross_track_error",
        "heading_error",
        "target_x",
        "target_y",
    ]

    def __init__(self, project_root, sample_interval_frames=5,
                 track_name="three_lane_oval", target_lane="middle",
                 corner_radius_m=""):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_name = f"run_{timestamp}"
        self.run_dir = Path(project_root) / "dataset" / "runs" / self.run_name
        self.image_dir = self.run_dir / "images"
        self.image_dir.mkdir(parents=True, exist_ok=False)

        self.csv_path = self.run_dir / "driving.csv"
        self.csv_file = self.csv_path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.csv_file, fieldnames=self.FIELDNAMES)
        self.writer.writeheader()

        self.sample_interval_frames = sample_interval_frames
        self.frame_counter = 0
        self.sample_counter = 0
        self.enabled = True

        metadata = {
            "run_name": self.run_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "camera_resolution": [320, 240],
            "sample_interval_frames": sample_interval_frames,
            "track": track_name,
            "start_lane": target_lane,
            "corner_radius_m": corner_radius_m,
            "corner_curvature_1pm": (
                1.0 / corner_radius_m if corner_radius_m else ""
            ),
        }
        (self.run_dir / "run_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled

    def record(self, frame, row):
        self.frame_counter += 1
        if not self.enabled or self.frame_counter % self.sample_interval_frames != 0:
            return False

        image_name = f"frame_{self.sample_counter:06d}.jpg"
        image_path = self.image_dir / image_name
        if not cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise RuntimeError(f"Failed to save dataset image: {image_path}")

        record = dict(row)
        record.update({
            "sample_id": self.sample_counter,
            "image_path": f"images/{image_name}",
        })
        self.writer.writerow(record)
        self.csv_file.flush()
        self.sample_counter += 1
        return True

    def close(self):
        if not self.csv_file.closed:
            self.csv_file.flush()
            self.csv_file.close()
