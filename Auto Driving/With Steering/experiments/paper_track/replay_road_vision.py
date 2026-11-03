"""Replay a labeled laptop session through vision and the guarded planner.

This script reads local JPEGs only. It does not access a Pi or GPIO.
"""

import argparse
from collections import Counter
import csv
from pathlib import Path

import cv2

from road_drive_web import (MAX_CENTER_ERROR, MAX_RAW_CENTER_ERROR,
                            MIN_CONFIDENCE, MIN_SURFACE, plan)
from road_vision import analyze


def stop_reason(reading, allow_single):
    if reading.lane not in {"양쪽 선", "한쪽 선"}:
        return "no_lane"
    single = reading.lane == "한쪽 선"
    if single and not allow_single:
        return "single_timeout"
    if reading.confidence < (0.55 if single else MIN_CONFIDENCE):
        return "confidence"
    if reading.surface < (0.65 if single else MIN_SURFACE):
        return "surface"
    if reading.center_error is None or abs(reading.center_error) > MAX_RAW_CENTER_ERROR:
        return "raw_center"
    if abs(reading.center_error) > MAX_CENTER_ERROR:
        return "corrected_center"
    return "eligible"


def replay(manifest):
    session = manifest.parent / "raw_sessions" / manifest.stem.removeprefix("manual_dataset_")
    lanes = Counter()
    decisions = Counter()
    timeout_without_time_gate = Counter()
    examples = {}
    corners = Counter()
    last_both_at = float("-inf")
    first_frame = True
    with manifest.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            image = session / row["file"]
            frame = cv2.imread(str(image))
            if frame is None:
                raise ValueError(f"Missing or invalid frame: {image}")
            reading = analyze(frame)
            label = int(row["steer"])
            seconds = float(row["seconds"])
            lanes[label, reading.lane] += 1
            corners[label, reading.corner] += 1
            if first_frame:
                last_both_at = seconds  # Live start grants a 0.45 s single-line window.
                first_frame = False
            if reading.lane == "양쪽 선":
                last_both_at = seconds
            allow_single = seconds - last_both_at <= 0.45
            reason = stop_reason(reading, allow_single)
            command = plan(reading, 0, allow_single=allow_single)
            if (command is None) == (reason == "eligible"):
                raise AssertionError(f"Replay reason disagrees with planner: {image}")
            decisions[label, reason] += 1
            examples.setdefault((label, reason), row["file"])
            if reason == "single_timeout":
                timeout_without_time_gate[label, stop_reason(reading, True)] += 1
            if command and label != 0 and command[1] * label <= 0:
                decisions[label, "eligible_opposite_steer"] += 1
    return lanes, decisions, examples, corners, timeout_without_time_gate


def continuous_replay(session):
    counts = Counter()
    longest = {}
    active_label = None
    run_start = last_frame_at = None
    run_frames = 0
    last_both_at = None
    with (session / "frames.csv").open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            image = session / row["file"]
            frame = cv2.imread(str(image))
            if frame is None:
                raise ValueError(f"Missing or invalid frame: {image}")
            frame_at = float(row["pi_frame_at"])
            reading = analyze(frame)
            if last_both_at is None or reading.lane == "양쪽 선":
                last_both_at = frame_at
            label = (-1 if float(row["steer"]) < -0.5 else
                     1 if float(row["steer"]) > 0.5 else 0)
            valid = row["manual_valid"] == "1" and int(row["throttle"]) == 1
            eligible = (valid and plan(reading, 0,
                        allow_single=frame_at - last_both_at <= 0.45) is not None)
            if (active_label is not None and
                    (not eligible or label != active_label
                     or frame_at - last_frame_at > 0.2)):
                if run_frames > longest.get(active_label, (0, 0.0))[0]:
                    longest[active_label] = (run_frames, last_frame_at - run_start)
                active_label = None
                run_frames = 0
            if eligible:
                counts[label] += 1
                if active_label is None:
                    active_label = label
                    run_start = frame_at
                run_frames += 1
            last_frame_at = frame_at
    if active_label is not None and run_frames > longest.get(active_label, (0, 0.0))[0]:
        longest[active_label] = (run_frames, last_frame_at - run_start)
    return counts, longest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", type=Path, nargs="+")
    parser.add_argument("--continuous", action="store_true",
                        help="Also replay every raw frame to measure eligible runs")
    args = parser.parse_args()
    for manifest in args.manifests:
        lanes, decisions, examples, corners, timeout_without_time_gate = replay(manifest)
        print(manifest)
        for label in (-1, 0, 1):
            detected = {lane: count for (action, lane), count in lanes.items()
                        if action == label}
            reasons = {reason: count for (action, reason), count in decisions.items()
                       if action == label}
            samples = {reason: file for (action, reason), file in examples.items()
                       if action == label and reason != "eligible"}
            print(f"  action={label}: lanes={detected}, reasons={reasons}, "
                  f"corner_frames={corners[label, 'left'] + corners[label, 'right']}")
            print(f"    first_stopped_frames={samples}")
            if decisions[label, "single_timeout"]:
                other_gates = {reason: count
                               for (action, reason), count in timeout_without_time_gate.items()
                               if action == label}
                print(f"    timed_out_without_time_gate={other_gates}")
        if args.continuous:
            session = manifest.parent / "raw_sessions" / manifest.stem.removeprefix(
                "manual_dataset_")
            counts, longest = continuous_replay(session)
            print(f"  continuous_eligible_frames={dict(counts)}")
            print(f"  longest_runs_frames_and_span_seconds={longest}")


if __name__ == "__main__":
    main()
