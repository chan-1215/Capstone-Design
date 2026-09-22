"""Build a compact balanced training dataset from recorded Webots runs."""

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "dataset" / "runs"
OUTPUT_DIR = PROJECT_ROOT / "dataset_v2"

DEFAULT_TARGET_PER_LANE = 3000
DEFAULT_RECOVERY_PER_LANE = 500
DEFAULT_JPEG_QUALITY = 85
RANDOM_SEED = 2401

VALID_LANES = ("1", "2", "3")
VALID_LANE_STATUS = {"both_lanes", "left_only", "right_only"}
STATUS_PENALTY = {
    "both_lanes": 0.0,
    "left_only": 0.22,
    "right_only": 0.22,
}

LANE_LIMITS = {
    "1": {
        "cross_track_error": 0.060,
        "heading_error": 0.300,
        "steering_delta": 0.350,
    },
    "2": {
        "cross_track_error": 0.040,
        "heading_error": 0.160,
        "steering_delta": 0.260,
    },
    "3": {
        "cross_track_error": 0.070,
        "heading_error": 0.160,
        "steering_delta": 0.260,
    },
}

RECOVERY_LIMITS = {
    "1": {
        "cross_track_error": 0.180,
        "heading_error": 0.700,
        "steering_delta": 0.500,
    },
    "2": {
        "cross_track_error": 0.250,
        "heading_error": 0.750,
        "steering_delta": 0.500,
    },
    "3": {
        "cross_track_error": 0.320,
        "heading_error": 0.800,
        "steering_delta": 0.500,
    },
}

SOURCE_FIELDS = [
    "simulation_time",
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

MANIFEST_FIELDS = [
    "dataset_sample_id",
    "image_path",
    "source_run",
    "source_sample_id",
    "source_image_path",
    "label_source",
    "source_left_pwm",
    "source_right_pwm",
    "quality_score",
    "steering",
    "steering_delta",
    "steering_bin",
    *SOURCE_FIELDS,
]


@dataclass(frozen=True)
class Candidate:
    row: dict
    source_run: str
    source_image_path: Path
    source_sample_id: int
    lane: str
    label_left_pwm: float
    label_right_pwm: float
    label_source: str
    source_left_pwm: float
    source_right_pwm: float
    steering: float
    steering_delta: float
    quality_score: float
    steering_bin: str


def parse_float(row, key):
    value = row.get(key, "")
    if value == "":
        raise ValueError(f"missing {key}")
    return float(value)


def steering_bin(steering):
    edges = [-0.45, -0.30, -0.22, -0.15, -0.09, -0.03, 0.03, 0.09, 0.15, 0.22, 0.30, 0.45]
    for index in range(len(edges) - 1):
        if edges[index] <= steering < edges[index + 1]:
            return f"{edges[index]:+.2f}:{edges[index + 1]:+.2f}"
    if steering < edges[0]:
        return f"<{edges[0]:+.2f}"
    return f">={edges[-1]:+.2f}"


def labeled_pwm(row):
    if row.get("control_mode") == "expert" and row.get("command") == "expert_path_follow":
        return parse_float(row, "left_pwm"), parse_float(row, "right_pwm"), "expert_command"
    if row.get("expert_left_pwm", "") and row.get("expert_right_pwm", ""):
        return (
            parse_float(row, "expert_left_pwm"),
            parse_float(row, "expert_right_pwm"),
            "expert_reference",
        )
    raise ValueError("row has no usable expert PWM label")


def candidate_quality(row, lane, steering_delta, limits):
    cross_track_error = abs(parse_float(row, "cross_track_error"))
    heading_error = abs(parse_float(row, "heading_error"))
    lane_error = abs(parse_float(row, "lane_error"))
    status = row.get("lane_status", "")

    return (
        cross_track_error / limits["cross_track_error"]
        + heading_error / limits["heading_error"]
        + min(1.0, steering_delta / limits["steering_delta"]) * 0.30
        + min(1.0, lane_error / 120.0) * 0.12
        + STATUS_PENALTY.get(status, 1.0)
    )


def iter_run_rows(run_dir):
    csv_path = run_dir / "driving.csv"
    if not csv_path.exists():
        return

    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        previous_steering = None
        for row in csv.DictReader(csv_file):
            lane = row.get("target_lane", "")
            if lane not in VALID_LANES:
                continue
            if row.get("command") == "safety_stop":
                continue
            if row.get("lane_status") not in VALID_LANE_STATUS:
                continue

            try:
                source_left_pwm = parse_float(row, "left_pwm")
                source_right_pwm = parse_float(row, "right_pwm")
                left_pwm, right_pwm, label_source = labeled_pwm(row)
                cross_track_error = abs(parse_float(row, "cross_track_error"))
                heading_error = abs(parse_float(row, "heading_error"))
                source_sample_id = int(row["sample_id"])
            except (KeyError, TypeError, ValueError):
                continue

            if not (0.0 <= left_pwm <= 0.85 and 0.0 <= right_pwm <= 0.85):
                continue

            steering = right_pwm - left_pwm
            steering_delta = 0.0 if previous_steering is None else abs(steering - previous_steering)
            previous_steering = steering

            limits = (
                LANE_LIMITS[lane]
                if label_source == "expert_command"
                else RECOVERY_LIMITS[lane]
            )
            if cross_track_error > limits["cross_track_error"]:
                continue
            if heading_error > limits["heading_error"]:
                continue
            if steering_delta > limits["steering_delta"]:
                continue

            image_path = run_dir / row.get("image_path", "")
            if not image_path.exists():
                continue

            yield Candidate(
                row=row,
                source_run=run_dir.name,
                source_image_path=image_path,
                source_sample_id=source_sample_id,
                lane=lane,
                label_left_pwm=left_pwm,
                label_right_pwm=right_pwm,
                label_source=label_source,
                source_left_pwm=source_left_pwm,
                source_right_pwm=source_right_pwm,
                steering=steering,
                steering_delta=steering_delta,
                quality_score=candidate_quality(row, lane, steering_delta, limits),
                steering_bin=steering_bin(steering),
            )


def load_candidates():
    by_lane = {lane: [] for lane in VALID_LANES}
    source_runs = []

    for run_dir in sorted(RUNS_DIR.glob("run_*")):
        before = sum(len(rows) for rows in by_lane.values())
        for candidate in iter_run_rows(run_dir):
            by_lane[candidate.lane].append(candidate)
        after = sum(len(rows) for rows in by_lane.values())
        if after > before:
            source_runs.append(run_dir.name)

    return by_lane, source_runs


def choose_evenly(records, count):
    if count >= len(records):
        return list(records)
    if count <= 0:
        return []

    ordered = sorted(records, key=lambda item: (item.source_run, item.source_sample_id))
    indices = np.linspace(0, len(ordered) - 1, count, dtype=int)
    return [ordered[index] for index in indices]


def stratified_quality_select(records, target_count):
    if len(records) <= target_count:
        return list(records)

    groups = defaultdict(list)
    for record in records:
        groups[(record.row.get("lane_status", ""), record.steering_bin)].append(record)

    selected = []
    selected_keys = set()
    total = len(records)
    for group in groups.values():
        quota = int(round(target_count * len(group) / total))
        quota = max(1, min(quota, len(group)))
        quality_pool_size = min(len(group), max(quota * 3, quota))
        quality_pool = sorted(group, key=lambda item: item.quality_score)[:quality_pool_size]
        for record in choose_evenly(quality_pool, quota):
            key = (record.source_run, record.source_sample_id)
            if key not in selected_keys:
                selected.append(record)
                selected_keys.add(key)

    if len(selected) < target_count:
        for record in sorted(records, key=lambda item: item.quality_score):
            key = (record.source_run, record.source_sample_id)
            if key in selected_keys:
                continue
            selected.append(record)
            selected_keys.add(key)
            if len(selected) >= target_count:
                break

    if len(selected) > target_count:
        selected = sorted(selected, key=lambda item: item.quality_score)[:target_count]

    return sorted(selected, key=lambda item: (item.lane, item.source_run, item.source_sample_id))


def stratified_select(records, target_count, recovery_count):
    recovery_records = [
        record for record in records
        if record.label_source == "expert_reference"
    ]
    base_records = [
        record for record in records
        if record.label_source != "expert_reference"
    ]
    selected_recovery_count = min(max(recovery_count, 0), len(recovery_records), target_count)
    selected = stratified_quality_select(
        base_records,
        target_count - selected_recovery_count,
    )
    selected.extend(stratified_quality_select(recovery_records, selected_recovery_count))

    if len(selected) < target_count:
        selected_keys = {(record.source_run, record.source_sample_id) for record in selected}
        remaining = [
            record for record in records
            if (record.source_run, record.source_sample_id) not in selected_keys
        ]
        selected.extend(stratified_quality_select(remaining, target_count - len(selected)))

    return sorted(selected, key=lambda item: (item.lane, item.source_run, item.source_sample_id))


def metric_summary(records):
    summary = {
        "count": len(records),
        "status": dict(Counter(record.row.get("lane_status", "") for record in records)),
        "source_runs": dict(Counter(record.source_run for record in records)),
        "label_sources": dict(Counter(record.label_source for record in records)),
        "steering_bins": dict(Counter(record.steering_bin for record in records)),
    }

    for key in ("cross_track_error", "heading_error", "lane_error", "left_pwm", "right_pwm"):
        values = []
        for record in records:
            try:
                values.append(abs(parse_float(record.row, key)) if key in {"cross_track_error", "heading_error", "lane_error"} else parse_float(record.row, key))
            except ValueError:
                continue
        if values:
            summary[key] = {
                "min": min(values),
                "mean": float(np.mean(values)),
                "max": max(values),
            }

    return summary


def write_dataset(selected_by_lane, source_runs, output_dir, jpeg_quality, overwrite):
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} already exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)

    image_root = output_dir / "images"
    image_root.mkdir(parents=True)

    manifest_path = output_dir / "manifest.csv"
    manifest_rows = []

    for lane in VALID_LANES:
        lane_dir = image_root / f"lane_{lane}"
        lane_dir.mkdir()
        for index, candidate in enumerate(selected_by_lane[lane]):
            image = cv2.imread(str(candidate.source_image_path))
            if image is None:
                continue

            image_name = f"lane{lane}_{index:05d}.jpg"
            relative_image_path = Path("images") / f"lane_{lane}" / image_name
            output_image_path = output_dir / relative_image_path
            if not cv2.imwrite(
                str(output_image_path),
                image,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            ):
                raise RuntimeError(f"failed to write {output_image_path}")

            output_row = {
                "dataset_sample_id": f"lane{lane}_{index:05d}",
                "image_path": relative_image_path.as_posix(),
                "source_run": candidate.source_run,
                "source_sample_id": candidate.source_sample_id,
                "source_image_path": str(candidate.source_image_path.relative_to(PROJECT_ROOT)),
                "label_source": candidate.label_source,
                "source_left_pwm": f"{candidate.source_left_pwm:.4f}",
                "source_right_pwm": f"{candidate.source_right_pwm:.4f}",
                "quality_score": f"{candidate.quality_score:.6f}",
                "steering": f"{candidate.steering:.6f}",
                "steering_delta": f"{candidate.steering_delta:.6f}",
                "steering_bin": candidate.steering_bin,
            }
            for field in SOURCE_FIELDS:
                output_row[field] = candidate.row.get(field, "")
            output_row["left_pwm"] = f"{candidate.label_left_pwm:.4f}"
            output_row["right_pwm"] = f"{candidate.label_right_pwm:.4f}"
            manifest_rows.append(output_row)

    with manifest_path.open("w", encoding="utf-8", newline="") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_per_lane": {lane: len(selected_by_lane[lane]) for lane in VALID_LANES},
        "requested_recovery_per_lane": {
            lane: sum(
                1 for record in selected_by_lane[lane]
                if record.label_source == "expert_reference"
            )
            for lane in VALID_LANES
        },
        "jpeg_quality": jpeg_quality,
        "source_runs": source_runs,
        "manifest_path": str(manifest_path.relative_to(PROJECT_ROOT)),
        "selected_by_lane": {
            lane: metric_summary(selected_by_lane[lane])
            for lane in VALID_LANES
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-per-lane", type=int, default=DEFAULT_TARGET_PER_LANE)
    parser.add_argument("--recovery-per-lane", type=int, default=DEFAULT_RECOVERY_PER_LANE)
    parser.add_argument("--jpeg-quality", type=int, default=DEFAULT_JPEG_QUALITY)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("--jpeg-quality must be between 1 and 100")

    by_lane, source_runs = load_candidates()
    selected_by_lane = {}
    for lane, candidates in by_lane.items():
        selected_by_lane[lane] = stratified_select(
            candidates,
            args.target_per_lane,
            args.recovery_per_lane,
        )

    summary = {
        "candidate_counts": {lane: len(rows) for lane, rows in by_lane.items()},
        "selected_counts": {lane: len(rows) for lane, rows in selected_by_lane.items()},
        "selected_recovery_counts": {
            lane: sum(
                1 for record in rows
                if record.label_source == "expert_reference"
            )
            for lane, rows in selected_by_lane.items()
        },
        "source_runs": source_runs,
    }

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    written_summary = write_dataset(
        selected_by_lane=selected_by_lane,
        source_runs=source_runs,
        output_dir=output_dir,
        jpeg_quality=args.jpeg_quality,
        overwrite=args.overwrite,
    )
    print(json.dumps({
        **summary,
        "output_dir": str(output_dir),
        "written": written_summary["target_per_lane"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
