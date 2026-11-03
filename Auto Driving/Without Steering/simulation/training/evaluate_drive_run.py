"""Summarize closed-loop Webots driving runs.

The script reads one or more dataset run directories and reports how long the
car stayed usable, when lane detection first failed, and whether learned-model
PWM output left the expected range.
"""

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "dataset" / "runs"
DEFAULT_CTE_FAILURE_M = 1.0
DEFAULT_NO_LANE_LIMIT = 6
SATURATION_LOW = 0.001
SATURATION_HIGH = 0.849


def parse_float(row, key, default=0.0):
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def parse_int(row, key, default=0):
    value = row.get(key, "")
    if value == "":
        return default
    return int(float(value))


def load_rows(run_dir):
    csv_path = run_dir / "driving.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"missing driving.csv: {csv_path}")
    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def first_consecutive_no_lane(rows, limit):
    streak = 0
    for row in rows:
        if row.get("lane_status") == "no_lane":
            streak += 1
            if streak >= limit:
                return row
        else:
            streak = 0
    return None


def first_row_matching(rows, predicate):
    for row in rows:
        if predicate(row):
            return row
    return None


def average(values):
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def summarize_run(run_dir, cte_failure_m, no_lane_limit):
    rows = load_rows(run_dir)
    images_dir = run_dir / "images"
    image_count = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0

    if not rows:
        return {
            "run": run_dir.name,
            "rows": 0,
            "images": image_count,
            "status": "empty",
        }

    cte_values = [abs(parse_float(row, "cross_track_error")) for row in rows]
    heading_values = [abs(parse_float(row, "heading_error")) for row in rows]
    lane_error_values = [abs(parse_float(row, "lane_error")) for row in rows]
    left_values = [parse_float(row, "left_pwm") for row in rows]
    right_values = [parse_float(row, "right_pwm") for row in rows]
    driveability_values = [
        parse_float(row, "driveability_score")
        for row in rows
        if row.get("driveability_score", "") != ""
    ]

    first_no_lane = first_row_matching(
        rows,
        lambda row: row.get("lane_status") == "no_lane",
    )
    first_cte_failure = first_row_matching(
        rows,
        lambda row: abs(parse_float(row, "cross_track_error")) > cte_failure_m,
    )
    first_no_lane_failure = first_consecutive_no_lane(rows, no_lane_limit)

    failure_rows = [
        row for row in (first_cte_failure, first_no_lane_failure)
        if row is not None
    ]
    first_failure = None
    if failure_rows:
        first_failure = min(
            failure_rows,
            key=lambda row: parse_float(row, "simulation_time"),
        )

    saturated_rows = [
        row for row in rows
        if (
            row.get("command") != "safety_stop"
            and (
            parse_float(row, "left_pwm") <= SATURATION_LOW
            or parse_float(row, "right_pwm") <= SATURATION_LOW
            or parse_float(row, "left_pwm") >= SATURATION_HIGH
            or parse_float(row, "right_pwm") >= SATURATION_HIGH
            )
        )
    ]

    duration_s = parse_float(rows[-1], "simulation_time")
    usable_duration_s = (
        parse_float(first_failure, "simulation_time")
        if first_failure is not None
        else duration_s
    )

    summary = {
        "run": run_dir.name,
        "rows": len(rows),
        "images": image_count,
        "duration_s": round(duration_s, 3),
        "usable_duration_s": round(usable_duration_s, 3),
        "control_modes": dict(Counter(row.get("control_mode", "") for row in rows)),
        "commands": dict(Counter(row.get("command", "") for row in rows)),
        "decision_reasons": dict(Counter(row.get("decision_reason", "") for row in rows)),
        "safety_state": dict(Counter(row.get("safety_state", "") for row in rows)),
        "lane_status": dict(Counter(row.get("lane_status", "") for row in rows)),
        "target_lanes": dict(Counter(row.get("target_lane", "") for row in rows)),
        "mean_abs_cte_m": round(average(cte_values), 5),
        "max_abs_cte_m": round(max(cte_values), 5),
        "mean_abs_heading_rad": round(average(heading_values), 5),
        "max_abs_heading_rad": round(max(heading_values), 5),
        "mean_abs_lane_error_px": round(average(lane_error_values), 2),
        "max_abs_lane_error_px": round(max(lane_error_values), 2),
        "left_pwm_min": round(min(left_values), 4),
        "left_pwm_max": round(max(left_values), 4),
        "right_pwm_min": round(min(right_values), 4),
        "right_pwm_max": round(max(right_values), 4),
        "saturated_rows": len(saturated_rows),
        "mean_driveability_score": (
            round(average(driveability_values), 4)
            if driveability_values else None
        ),
        "min_driveability_score": (
            round(min(driveability_values), 4)
            if driveability_values else None
        ),
        "first_no_lane_sample": (
            parse_int(first_no_lane, "sample_id") if first_no_lane else None
        ),
        "first_no_lane_time_s": (
            round(parse_float(first_no_lane, "simulation_time"), 3)
            if first_no_lane else None
        ),
        "first_failure_sample": (
            parse_int(first_failure, "sample_id") if first_failure else None
        ),
        "first_failure_time_s": (
            round(parse_float(first_failure, "simulation_time"), 3)
            if first_failure else None
        ),
        "failure_reason": failure_reason(first_failure, first_cte_failure),
        "pass": first_failure is None,
    }
    return summary


def failure_reason(first_failure, first_cte_failure):
    if first_failure is None:
        return ""
    if first_failure is first_cte_failure:
        return "cross_track_error"
    return "consecutive_no_lane"


def latest_run():
    runs = sorted(
        [path for path in RUNS_DIR.glob("run_*") if (path / "driving.csv").exists()],
        key=lambda path: path.name,
    )
    if not runs:
        raise RuntimeError(f"no dataset runs found in {RUNS_DIR}")
    return runs[-1]


def resolve_runs(paths, all_runs):
    if all_runs:
        return sorted(
            [path for path in RUNS_DIR.glob("run_*") if (path / "driving.csv").exists()],
            key=lambda path: path.name,
        )
    if not paths:
        return [latest_run()]

    resolved = []
    for path in paths:
        run_dir = Path(path)
        if not run_dir.is_absolute():
            candidate = RUNS_DIR / run_dir
            run_dir = candidate if candidate.exists() else PROJECT_ROOT / run_dir
        resolved.append(run_dir)
    return resolved


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "runs",
        nargs="*",
        help="Run directories or run names. Defaults to latest run.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Evaluate every run under dataset/runs.",
    )
    parser.add_argument(
        "--cte-failure-m",
        type=float,
        default=DEFAULT_CTE_FAILURE_M,
        help="Cross-track error threshold for failed driving.",
    )
    parser.add_argument(
        "--no-lane-limit",
        type=int,
        default=DEFAULT_NO_LANE_LIMIT,
        help="Consecutive no_lane rows treated as a failure.",
    )
    parser.add_argument(
        "--write-json",
        type=Path,
        help="Optional path to write the JSON report.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    run_dirs = resolve_runs(args.runs, args.all)
    summaries = [
        summarize_run(run_dir, args.cte_failure_m, args.no_lane_limit)
        for run_dir in run_dirs
    ]
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "cte_failure_m": args.cte_failure_m,
        "no_lane_limit": args.no_lane_limit,
        "runs": summaries,
    }

    if args.write_json:
        output_path = args.write_json
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
