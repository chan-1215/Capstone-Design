#!/usr/bin/env python3

import argparse
import subprocess
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

try:
    from RPLCD.i2c import CharLCD
except ImportError:
    CharLCD = None


FRAME_WIDTH = 480
FRAME_HEIGHT = 320
CAMERA_FPS = 20
SEQUENCE_LENGTH = 30
POSE_INDICES = [11, 12, 13, 14, 15, 16]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run real-time gesture test with a simple KNN model."
    )
    parser.add_argument(
        "--model",
        default=str(Path.home() / "gesture_knn_model.npz"),
        help="Path to gesture_knn_model.npz",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Raspberry Pi camera index",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=40.0,
        help="Distance threshold. Larger value accepts more predictions.",
    )
    parser.add_argument(
        "--min-hand-ratio",
        type=float,
        default=0.7,
        help="Minimum hand detection ratio in the recent sequence.",
    )
    parser.add_argument(
        "--go-motion",
        type=float,
        default=0.12,
        help="Minimum palm motion required to accept GO.",
    )
    parser.add_argument(
        "--palm-sign",
        choices=["positive", "negative", "off"],
        default="off",
        help="Use positive or negative palm score as palm-facing camera. Use off to disable.",
    )
    parser.add_argument(
        "--lcd",
        action="store_true",
        help="Show the result on an I2C LCD.",
    )
    parser.add_argument(
        "--lcd-address",
        default="0x27",
        help="I2C LCD address, for example 0x27.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=1.5,
        help="Keep STOP or GO visible for this many seconds.",
    )
    return parser.parse_args()


def start_camera(camera_index):
    return subprocess.Popen(
        [
            "rpicam-vid",
            "--camera", str(camera_index),
            "-t", "0",
            "-n",
            "--autofocus-mode", "continuous",
            "--codec", "mjpeg",
            "--width", str(FRAME_WIDTH),
            "--height", str(FRAME_HEIGHT),
            "--framerate", str(CAMERA_FPS),
            "-o", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )


class MjpegReader:
    def __init__(self, process):
        self.process = process
        self.buffer = b""

    def read(self):
        while True:
            chunk = self.process.stdout.read(4096)

            if not chunk:
                return None

            self.buffer += chunk
            start = self.buffer.find(b"\xff\xd8")
            end = self.buffer.find(b"\xff\xd9", start + 2)

            if start == -1 or end == -1:
                if len(self.buffer) > 2_000_000:
                    self.buffer = self.buffer[-1_000_000:]
                continue

            jpg = self.buffer[start:end + 2]
            self.buffer = self.buffer[end + 2:]

            frame = cv2.imdecode(
                np.frombuffer(jpg, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )

            if frame is not None:
                return frame


def extract_hand(result):
    landmarks = np.zeros((21, 3), dtype=np.float32)

    if not result.multi_hand_landmarks:
        return landmarks, False

    hand = result.multi_hand_landmarks[0]

    for index, landmark in enumerate(hand.landmark):
        landmarks[index] = [landmark.x, landmark.y, landmark.z]

    return landmarks, True


def extract_pose(result):
    landmarks = np.zeros((len(POSE_INDICES), 4), dtype=np.float32)

    if not result.pose_landmarks:
        return landmarks

    for output_index, pose_index in enumerate(POSE_INDICES):
        landmark = result.pose_landmarks.landmark[pose_index]
        landmarks[output_index] = [
            landmark.x,
            landmark.y,
            landmark.z,
            landmark.visibility,
        ]

    return landmarks


def process_frame(frame, hands, pose):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False

    hand_result = hands.process(rgb)
    pose_result = pose.process(rgb)

    rgb.flags.writeable = True

    hand_landmarks, hand_detected = extract_hand(hand_result)

    return {
        "hand_result": hand_result,
        "pose_result": pose_result,
        "hand": hand_landmarks,
        "hand_detected": hand_detected,
        "pose": extract_pose(pose_result),
    }


def is_open_hand(hand):
    finger_pairs = [
        (8, 6),
        (12, 10),
        (16, 14),
        (20, 18),
    ]
    extended = [
        hand[tip][1] < hand[pip][1]
        for tip, pip in finger_pairs
    ]
    return sum(extended) >= 3


def palm_score(hand):
    wrist = hand[0]
    index_mcp = hand[5]
    pinky_mcp = hand[17]
    normal = np.cross(index_mcp - wrist, pinky_mcp - wrist)
    return float(normal[2])


def is_palm_allowed(hand, palm_sign):
    if palm_sign == "off":
        return True

    score = palm_score(hand)

    if palm_sign == "positive":
        return score > 0

    return score < 0


def has_go_motion(hand_sequence, min_motion):
    hands = np.asarray(hand_sequence, dtype=np.float32)

    palm_points = hands[:, [0, 5, 9, 13, 17], :]
    palm_center = palm_points.mean(axis=1)

    palm_x_motion = float(palm_center[:, 0].max() - palm_center[:, 0].min())
    palm_y_motion = float(palm_center[:, 1].max() - palm_center[:, 1].min())

    wrist_x_motion = float(hands[:, 0, 0].max() - hands[:, 0, 0].min())
    wrist_y_motion = float(hands[:, 0, 1].max() - hands[:, 0, 1].min())

    total_motion = max(
        palm_x_motion,
        palm_y_motion,
        wrist_x_motion,
        wrist_y_motion,
    )

    return total_motion >= min_motion


def normalize_hand(hand):
    hand = hand.astype(np.float32).copy()

    for frame_index in range(hand.shape[0]):
        frame = hand[frame_index]
        wrist = frame[0].copy()
        frame -= wrist

        scale = np.linalg.norm(frame[9])
        if scale < 1e-6:
            scale = np.max(np.linalg.norm(frame, axis=1))
        if scale < 1e-6:
            scale = 1.0

        hand[frame_index] = frame / scale

    return hand


def normalize_pose(pose):
    pose = pose.astype(np.float32).copy()

    for frame_index in range(pose.shape[0]):
        frame = pose[frame_index]
        left_shoulder = frame[0, :3].copy()
        right_shoulder = frame[1, :3].copy()
        center = (left_shoulder + right_shoulder) / 2.0
        scale = np.linalg.norm(left_shoulder - right_shoulder)

        if scale < 1e-6:
            scale = 1.0

        frame[:, :3] = (frame[:, :3] - center) / scale
        pose[frame_index] = frame

    return pose


def make_feature(hand_sequence, pose_sequence):
    hand = normalize_hand(np.asarray(hand_sequence, dtype=np.float32))
    pose = normalize_pose(np.asarray(pose_sequence, dtype=np.float32))

    return np.concatenate(
        [
            hand.reshape(-1),
            pose.reshape(-1),
        ]
    ).astype(np.float32)


def predict_knn(feature, model_features, model_labels, label_names, threshold):
    distances = np.linalg.norm(model_features - feature, axis=1)
    nearest_indices = np.argsort(distances)[:3]
    nearest_labels = model_labels[nearest_indices]
    nearest_distances = distances[nearest_indices]

    best_distance = float(nearest_distances[0])

    if best_distance > threshold:
        return "unknown", best_distance

    label_counter = Counter(nearest_labels.tolist())
    best_label_index = label_counter.most_common(1)[0][0]

    return str(label_names[best_label_index]), best_distance


def draw_landmarks(frame, processed, drawer):
    if processed["hand_result"].multi_hand_landmarks:
        drawer.draw_landmarks(
            frame,
            processed["hand_result"].multi_hand_landmarks[0],
            mp.solutions.hands.HAND_CONNECTIONS,
        )

    if processed["pose_result"].pose_landmarks:
        drawer.draw_landmarks(
            frame,
            processed["pose_result"].pose_landmarks,
            mp.solutions.pose.POSE_CONNECTIONS,
        )


def setup_lcd(enabled, address_text):
    if not enabled:
        return None

    if CharLCD is None:
        print("RPLCD is not installed. Run: pip install RPLCD smbus2")
        return None

    address = int(address_text, 16)

    lcd = CharLCD(
        i2c_expander="PCF8574",
        address=address,
        port=1,
        cols=16,
        rows=2,
        charmap="A00",
        auto_linebreaks=True,
    )
    lcd.clear()
    lcd.write_string("Gesture Ready")
    return lcd


def update_lcd(lcd, label, last_label):
    if lcd is None:
        return last_label

    if label == last_label:
        return last_label

    lcd.clear()

    if label == "stop":
        lcd.write_string("STOP")
        lcd.cursor_pos = (1, 0)
        lcd.write_string("Please wait")
    elif label == "go":
        lcd.write_string("GO")
        lcd.cursor_pos = (1, 0)
        lcd.write_string("You can pass")
    elif label == "unknown":
        lcd.write_string("UNKNOWN")
        lcd.cursor_pos = (1, 0)
        lcd.write_string("Checking...")
    else:
        lcd.write_string("COLLECTING")

    return label


def update_display_label(raw_label, display_label, hold_until, hold_seconds):
    now = time.monotonic()

    if raw_label in ("stop", "go"):
        return raw_label, now + hold_seconds

    if now < hold_until and display_label in ("stop", "go"):
        return display_label, hold_until

    return raw_label, hold_until


def main():
    args = parse_args()
    model_path = Path(args.model).expanduser().resolve()
    model = np.load(model_path, allow_pickle=True)

    model_features = model["features"].astype(np.float32)
    model_labels = model["labels"]
    label_names = model["label_names"]

    hand_buffer = deque(maxlen=SEQUENCE_LENGTH)
    hand_detected_buffer = deque(maxlen=SEQUENCE_LENGTH)
    pose_buffer = deque(maxlen=SEQUENCE_LENGTH)
    prediction_buffer = deque(maxlen=5)

    camera = start_camera(args.camera)
    reader = MjpegReader(camera)
    drawer = mp.solutions.drawing_utils
    lcd = setup_lcd(args.lcd, args.lcd_address)
    last_lcd_label = None
    display_label = "collecting"
    hold_until = 0.0

    try:
        with mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        ) as hands, mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        ) as pose:
            while True:
                frame = reader.read()
                if frame is None:
                    print("Camera stream ended.")
                    break

                frame = cv2.flip(frame, 1)
                processed = process_frame(frame, hands, pose)

                hand_buffer.append(processed["hand"])
                hand_detected_buffer.append(processed["hand_detected"])
                pose_buffer.append(processed["pose"])

                raw_label = "collecting"
                distance = 0.0
                hand_ratio = 0.0
                palm_value = 0.0

                if len(hand_buffer) == SEQUENCE_LENGTH:
                    hand_ratio = sum(hand_detected_buffer) / SEQUENCE_LENGTH
                    current_hand = hand_buffer[-1]
                    palm_value = palm_score(current_hand)

                    if hand_ratio < args.min_hand_ratio:
                        raw_label = "unknown"
                    else:
                        feature = make_feature(hand_buffer, pose_buffer)
                        raw_label, distance = predict_knn(
                            feature,
                            model_features,
                            model_labels,
                            label_names,
                            args.threshold,
                        )

                        if raw_label == "go" and not has_go_motion(
                            hand_buffer,
                            args.go_motion,
                        ):
                            raw_label = "unknown"

                        if raw_label == "stop" and not is_open_hand(current_hand):
                            raw_label = "unknown"

                        if raw_label == "stop" and not is_palm_allowed(
                            current_hand,
                            args.palm_sign,
                        ):
                            raw_label = "unknown"

                    prediction_buffer.append(raw_label)

                    raw_label = Counter(prediction_buffer).most_common(1)[0][0]

                display_label, hold_until = update_display_label(
                    raw_label,
                    display_label,
                    hold_until,
                    args.hold_seconds,
                )

                last_lcd_label = update_lcd(lcd, display_label, last_lcd_label)

                draw_landmarks(frame, processed, drawer)

                cv2.putText(
                    frame,
                    f"Gesture: {display_label.upper()}",
                    (15, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )
                cv2.putText(
                    frame,
                    f"Raw: {raw_label.upper()} Dist: {distance:.2f}",
                    (15, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
                cv2.putText(
                    frame,
                    f"Hand: {hand_ratio:.2f} Palm: {palm_value:.4f}",
                    (15, 100),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                )
                cv2.putText(
                    frame,
                    "Q: quit",
                    (15, FRAME_HEIGHT - 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )

                cv2.imshow("Gesture KNN Test", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        if camera.poll() is None:
            camera.terminate()
            try:
                camera.wait(timeout=3)
            except subprocess.TimeoutExpired:
                camera.kill()

        cv2.destroyAllWindows()

        if lcd is not None:
            lcd.clear()
            lcd.write_string("Gesture End")


if __name__ == "__main__":
    main()
