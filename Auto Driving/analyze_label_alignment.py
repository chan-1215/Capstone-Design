"""Test camera-to-manual-command lead times on held-out driving sessions.

No model is exported, and this script cannot access motor or servo hardware.
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from evaluate_hybrid_control import (THRESHOLDS, balanced_recall, predict,
                                     select_parameters)
from road_drive_web import plan
from road_vision import analyze


LEADS = (0.0, 0.2, 0.4, 0.6)


def read_session(session):
    with (session / "frames.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    times = np.array([float(row["pi_frame_at"]) for row in rows])
    actions = [None if row["manual_valid"] != "1" or int(row["throttle"]) != 1
               else (-1 if float(row["steer"]) < -0.5 else
                     1 if float(row["steer"]) > 0.5 else 0) for row in rows]
    ages = [float(row["command_age"]) for row in rows
            if row["command_age"] and row["manual_valid"] == "1"]
    observations = []
    for row, action, timestamp in zip(rows, actions, times):
        if action is None:
            continue
        image = session / row["file"]
        frame = cv2.imread(str(image))
        if frame is None:
            raise ValueError(f"Missing frame: {image}")
        reading = analyze(frame)
        if plan(reading, 0, allow_single=True) is not None:
            observations.append((timestamp, reading.center_error,
                                 reading.heading_error, reading.lane))
    print(f"{session.name}: frames={len(rows)} moving={sum(a is not None for a in actions)} "
          f"vision_eligible={len(observations)} "
          f"median_command_age={np.median(ages):.3f}s")
    turn_times = times[np.array([action is not None and action != 0
                                 for action in actions])]
    return times, actions, observations, turn_times


def aligned_samples(session, lead):
    times, actions, observations, turn_times = session
    features = []
    labels = []
    sample_times = []
    lane_types = []
    away_from_turn = []
    for timestamp, center, heading, lane in observations:
        target = timestamp + lead
        index = int(np.searchsorted(times, target))
        if index >= len(times):
            continue
        if index > 0 and target - times[index - 1] < times[index] - target:
            index -= 1
        if (index == 0 or index == len(times) - 1
                or abs(times[index] - target) > 0.13
                or times[index + 1] - times[index - 1] > 0.35):
            continue
        action = actions[index]
        if action is None or actions[index - 1] != action or actions[index + 1] != action:
            continue
        features.append((center, heading))
        labels.append(action)
        sample_times.append(timestamp)
        lane_types.append(lane)
        away_from_turn.append(bool(len(turn_times) == 0 or
                                   np.min(np.abs(turn_times - timestamp)) >= 1.0))
    return (np.asarray(features, np.float32).reshape(-1, 2),
            np.asarray(labels, np.int8), np.asarray(sample_times),
            np.asarray(lane_types), np.asarray(away_from_turn))


def confirm_turns(predictions, times, required=3):
    confirmed = np.zeros_like(predictions)
    streak = 0
    for index, direction in enumerate(predictions):
        if (direction != 0 and index > 0 and direction == predictions[index - 1]
                and times[index] - times[index - 1] <= 0.2):
            streak += 1
        else:
            streak = 1 if direction != 0 else 0
        if streak >= required:
            confirmed[index] = direction
    return confirmed


def evaluate(sessions):
    for lead in LEADS:
        aligned = [aligned_samples(session, lead) for session in sessions]
        print(f"lead={lead:.1f}s")
        for index, (test_x, test_y, test_times, lane_types,
                    away_from_turn) in enumerate(aligned):
            train_x = np.concatenate([sample[0] for other, sample in enumerate(aligned)
                                      if other != index])
            train_y = np.concatenate([sample[1] for other, sample in enumerate(aligned)
                                      if other != index])
            if not len(test_y) or not len(train_y):
                print(f"  held_out={index}: insufficient samples")
                continue
            gain, threshold = select_parameters(train_x, train_y)
            base_threshold = max(THRESHOLDS, key=lambda value: balanced_recall(
                train_y, predict(train_x, 0, value)))
            predictions = predict(test_x, gain, threshold)
            baseline = predict(test_x, 0, base_threshold)
            confirmed = confirm_turns(predictions, test_times)
            straight = test_y == 0
            turns = test_y != 0
            false_turns = int(np.sum(straight & (predictions != 0)))
            turn_hits = int(np.sum(turns & (predictions == test_y)))
            both_edges = lane_types == "양쪽 선"
            both_false_turns = int(np.sum(straight & both_edges & (predictions != 0)))
            both_turn_hits = int(np.sum(turns & both_edges & (predictions == test_y)))
            unambiguous_straight = straight & away_from_turn
            distant_false_turns = int(np.sum(unambiguous_straight & (predictions != 0)))
            confirmed_false_turns = int(np.sum(straight & (confirmed != 0)))
            confirmed_turn_hits = int(np.sum(turns & (confirmed == test_y)))
            print(f"  held_out={index} n={len(test_y)} gain={gain:.3f} "
                  f"threshold={threshold:.1f} "
                  f"balanced={balanced_recall(test_y, predictions):.3f} "
                  f"center_only={balanced_recall(test_y, baseline):.3f} "
                  f"false_turns={false_turns}/{int(straight.sum())} "
                  f"correct_turns={turn_hits}/{int(turns.sum())} "
                  f"both_edge_false_turns={both_false_turns}/{int(np.sum(straight & both_edges))} "
                  f"both_edge_correct_turns={both_turn_hits}/{int(np.sum(turns & both_edges))} "
                  f"far_straight_false_turns={distant_false_turns}/{int(unambiguous_straight.sum())} "
                  f"confirmed_false_turns={confirmed_false_turns}/{int(straight.sum())} "
                  f"confirmed_correct_turns={confirmed_turn_hits}/{int(turns.sum())}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", type=Path, nargs="+")
    args = parser.parse_args()
    if len(args.sessions) < 2:
        parser.error("at least two sessions are required")
    evaluate([read_session(path) for path in args.sessions])


if __name__ == "__main__":
    main()
