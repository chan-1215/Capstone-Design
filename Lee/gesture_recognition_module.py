# file name: gesture_recognition_module.py

import time
from collections import deque

import cv2
import mediapipe as mp
import numpy as np


class GestureRecognizer:
    def __init__(
        self,
        model_path="/home/pi/gesture_knn_model.npz",
        threshold=30.0,
        sequence_length=30,
        k=3,
        hold_seconds=1.0,
        min_hand_ratio=0.6,
    ):
        self.threshold = threshold
        self.sequence_length = sequence_length
        self.k = k
        self.hold_seconds = hold_seconds
        self.min_hand_ratio = min_hand_ratio

        self.model_features, self.model_labels = self.load_model(model_path)

        self.hand_buffer = deque(maxlen=sequence_length)
        self.hand_valid_buffer = deque(maxlen=sequence_length)
        self.prediction_buffer = deque(maxlen=5)

        self.display_label = "unknown"
        self.last_valid_label = "unknown"
        self.last_valid_time = 0.0

        self.label_map = {
            "0": "stop",
            "1": "go",
            "2": "unknown",
            0: "stop",
            1: "go",
            2: "unknown",
        }

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils

        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )

    def load_model(self, model_path):
        data = np.load(model_path, allow_pickle=True)

        features = data["features"].astype(np.float32)
        labels = data["labels"]

        print(f"Gesture model loaded: {model_path}")
        print(f"Feature shape: {features.shape}")

        return features, labels

    def normalize_hand(self, hand_landmarks):
        points = []

        for lm in hand_landmarks.landmark:
            points.append([lm.x, lm.y, lm.z])

        points = np.array(points, dtype=np.float32)

        wrist = points[0].copy()
        points = points - wrist

        scale = np.linalg.norm(points[9])

        if scale < 1e-6:
            scale = 1.0

        points = points / scale

        return points.flatten()

    def make_feature(self):
        features = []

        zero_hand = np.zeros(21 * 3, dtype=np.float32)

        for hand, valid in zip(self.hand_buffer, self.hand_valid_buffer):
            if valid:
                features.append(hand)
            else:
                features.append(zero_hand)

        return np.concatenate(features).astype(np.float32)

    def predict_knn(self, feature):
        model_dim = self.model_features.shape[1]
        input_dim = feature.shape[0]

        if model_dim != input_dim:
            print(f"Feature size mismatch: model={model_dim}, input={input_dim}")
            return "unknown", 9999.0

        distances = np.linalg.norm(self.model_features - feature, axis=1)

        nearest_idx = np.argsort(distances)[:self.k]
        nearest_labels = self.model_labels[nearest_idx]
        nearest_distances = distances[nearest_idx]

        avg_distance = float(np.mean(nearest_distances))

        if avg_distance > self.threshold:
            return "unknown", avg_distance

        labels, counts = np.unique(nearest_labels, return_counts=True)
        best_label = labels[np.argmax(counts)]
        best_label = self.label_map.get(best_label, str(best_label))
        best_label = self.label_map.get(str(best_label), best_label)

        return str(best_label), avg_distance

    def smooth_prediction(self, label):
        self.prediction_buffer.append(label)

        labels, counts = np.unique(list(self.prediction_buffer), return_counts=True)
        return str(labels[np.argmax(counts)])

    def update_display_label(self, raw_label):
        now = time.time()

        if raw_label in ("stop", "go"):
            self.display_label = raw_label
            self.last_valid_label = raw_label
            self.last_valid_time = now
            return self.display_label

        if self.last_valid_label in ("stop", "go"):
            if now - self.last_valid_time < self.hold_seconds:
                self.display_label = self.last_valid_label
                return self.display_label

        self.display_label = "unknown"
        return self.display_label

    def process(self, frame):
        debug_frame = frame.copy()

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb_frame)

        hand_detected = False
        hand_feature = np.zeros(21 * 3, dtype=np.float32)

        if result.multi_hand_landmarks:
            hand_detected = True
            hand_landmarks = result.multi_hand_landmarks[0]

            hand_feature = self.normalize_hand(hand_landmarks)

            self.mp_draw.draw_landmarks(
                debug_frame,
                hand_landmarks,
                self.mp_hands.HAND_CONNECTIONS,
            )

        self.hand_buffer.append(hand_feature)
        self.hand_valid_buffer.append(hand_detected)

        raw_label = "unknown"
        distance = 9999.0

        if len(self.hand_buffer) == self.sequence_length:
            hand_ratio = sum(self.hand_valid_buffer) / self.sequence_length

            if hand_ratio >= self.min_hand_ratio:
                feature = self.make_feature()
                raw_label, distance = self.predict_knn(feature)
                raw_label = self.smooth_prediction(raw_label)

        display_label = self.update_display_label(raw_label)

        cv2.putText(
            debug_frame,
            f"Gesture: {display_label}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )

        cv2.putText(
            debug_frame,
            f"Raw: {raw_label} Dist: {distance:.1f}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )

        return {
            "label": display_label,
            "raw_label": raw_label,
            "distance": distance,
            "debug_frame": debug_frame,
            "hand_detected": hand_detected,
        }

    def close(self):
        self.hands.close()