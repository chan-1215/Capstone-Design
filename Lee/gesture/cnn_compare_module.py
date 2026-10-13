# file name: cnn_compare_module.py
"""Shadow-mode seq-CNN gesture classifier — runs alongside the production
KNN classifier (GestureRecognizer) purely for comparison and logging. It
never drives the robot; only KNN's prediction does that.

Background: 2026-08-27 benchmarking found this CNN (10-frame skeleton stack,
see ai_rover/BENCHMARKS.md experiment 05-2) matched or beat KNN in every
live test performed that day, but all of that testing was done in a single
session/lighting condition. Before trusting it enough to replace KNN, we
run it here in parallel across many real sessions and log where the two
agree/disagree (ai_rover/gesture_compare_log.csv) to build up real
comparison data. See CHANGELOG.md 2026-08-27 for the decision.
"""

import csv
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import torch
import torch.nn as nn

SEQUENCE_LENGTH = 30
SUBSAMPLE_INDICES = list(range(0, 30, 3))  # 10 frames spanning the sequence
IMG_SIZE = 64
LABELS = ["stop", "go", "unknown"]

HAND_CONNECTIONS = list(mp.solutions.hands.HAND_CONNECTIONS)


class SeqCNN(nn.Module):
    def __init__(self, n_channels, n_classes=3):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(n_channels, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(32 * 8 * 8, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, n_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def draw_skeleton_frame(points_xyz):
    """Same wrist-centered, scale-normalized rasterization used to train
    gesture_seq_skeleton_cnn_model.pt — must stay in sync with
    benchmarks/bench_sequence_skeleton_cnn.py."""
    wrist = points_xyz[0, :2]
    centered = points_xyz[:, :2] - wrist
    scale = np.max(np.linalg.norm(centered, axis=1))
    if scale < 1e-6:
        scale = 1.0
    normalized = centered / scale

    canvas = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.uint8)
    px = ((normalized[:, 0] * 0.42 + 0.5) * IMG_SIZE).astype(np.int32)
    py = ((normalized[:, 1] * 0.42 + 0.5) * IMG_SIZE).astype(np.int32)

    for a, b in HAND_CONNECTIONS:
        cv2.line(canvas, (px[a], py[a]), (px[b], py[b]), 140, 1, cv2.LINE_AA)
    for i in range(21):
        cv2.circle(canvas, (px[i], py[i]), 2, 255, -1, cv2.LINE_AA)

    return canvas.astype(np.float32) / 255.0


class CNNComparator:
    def __init__(self, model_path, log_path, log_interval_sec=1.0):
        self.model = SeqCNN(n_channels=len(SUBSAMPLE_INDICES))
        self.model.load_state_dict(torch.load(model_path, map_location="cpu"))
        self.model.eval()

        self.log_path = Path(log_path)
        self.log_interval_sec = log_interval_sec
        self._last_log_time = 0.0

        if not self.log_path.exists():
            with open(self.log_path, "w", newline="") as f:
                csv.writer(f).writerow(["timestamp", "knn_label", "cnn_label", "agree"])

    def predict(self, raw_sequence):
        """raw_sequence: (30,21,3) raw (unnormalized) mediapipe hand
        landmarks per frame, oldest-first — matches
        GestureRecognizer.get_raw_sequence()'s output."""
        stack = np.stack(
            [draw_skeleton_frame(raw_sequence[i]) for i in SUBSAMPLE_INDICES], axis=0
        ).astype(np.float32)
        x = torch.from_numpy(stack).unsqueeze(0)
        with torch.no_grad():
            probs = torch.softmax(self.model(x), dim=1)[0]
            pred_idx = int(torch.argmax(probs))
        return LABELS[pred_idx], float(probs[pred_idx])

    def log_comparison(self, knn_label, cnn_label):
        now = time.time()
        if now - self._last_log_time < self.log_interval_sec:
            return
        self._last_log_time = now

        with open(self.log_path, "a", newline="") as f:
            csv.writer(f).writerow([
                time.strftime("%Y-%m-%dT%H:%M:%S"),
                knn_label,
                cnn_label,
                int(knn_label == cnn_label),
            ])
