#!/usr/bin/env python3

import argparse
import json
import subprocess
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np


FRAME_WIDTH = 480
FRAME_HEIGHT = 360
CAMERA_FPS = 20
SEQUENCE_LENGTH = 30
COUNTDOWN_SECONDS = 2

LABEL_KEYS = {
    ord("s"): "stop",
    ord("g"): "go",
    ord("u"): "unknown",
}

# Upper-body landmarks: left/right shoulder, elbow, and wrist.
POSE_INDICES = [11, 12, 13, 14, 15, 16]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect hand and upper-body gesture sequences."
    )
    parser.add_argument(
        "--person",
        required=True,
        help="Participant ID, for example person01",
    )
    parser.add_argument(
        "--output",
        default=str(Path.home() / "gesture_dataset"),
        help="Dataset output directory",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Raspberry Pi camera index",
    )
    parser.add_argument(
        "--save-video",
        action="store_true",
        help="Also save an MP4 preview video for each sample",
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
    valid = np.zeros(21, dtype=np.uint8)
    handedness = "none"

    if not result.multi_hand_landmarks:
        return landmarks, valid, handedness

    hand = result.multi_hand_landmarks[0]

    for index, landmark in enumerate(hand.landmark):
        landmarks[index] = [landmark.x, landmark.y, landmark.z]
        valid[index] = 1

    if result.multi_handedness:
        handedness = result.multi_handedness[0].classification[0].label.lower()

    return landmarks, valid, handedness


def extract_pose(result):
    landmarks = np.zeros((len(POSE_INDICES), 4), dtype=np.float32)
    valid = np.zeros(len(POSE_INDICES), dtype=np.uint8)

    if not result.pose_landmarks:
        return landmarks, valid

    for output_index, pose_index in enumerate(POSE_INDICES):
        landmark = result.pose_landmarks.landmark[pose_index]
        landmarks[output_index] = [
            landmark.x,
            landmark.y,
            landmark.z,
            landmark.visibility,
        ]
        valid[output_index] = int(landmark.visibility >= 0.5)

    return landmarks, valid


def process_frame(frame, hands, pose):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False

    hand_result = hands.process(rgb)
    pose_result = pose.process(rgb)

    rgb.flags.writeable = True

    hand_landmarks, hand_valid, handedness = extract_hand(hand_result)
    pose_landmarks, pose_valid = extract_pose(pose_result)

    return {
        "hand_result": hand_result,
        "pose_result": pose_result,
        "hand_landmarks": hand_landmarks,
        "hand_valid": hand_valid,
        "handedness": handedness,
        "pose_landmarks": pose_landmarks,
        "pose_valid": pose_valid,
    }


def draw_skeleton(frame, processed, hand_draw, pose_draw):
    if processed["hand_result"].multi_hand_landmarks:
        hand_draw.draw_landmarks(
            frame,
            processed["hand_result"].multi_hand_landmarks[0],
            mp.solutions.hands.HAND_CONNECTIONS,
        )

    if processed["pose_result"].pose_landmarks:
        pose_draw.draw_landmarks(
            frame,
            processed["pose_result"].pose_landmarks,
            mp.solutions.pose.POSE_CONNECTIONS,
        )


def next_sample_number(label_dir, person_id):
    existing = list(label_dir.glob(f"{person_id}_*.npz"))
    numbers = []

    for path in existing:
        try:
            numbers.append(int(path.stem.rsplit("_", 1)[1]))
        except (IndexError, ValueError):
            continue

    return max(numbers, default=0) + 1


def run_countdown(reader, hands, pose, hand_draw, pose_draw, label):
    end_time = time.monotonic() + COUNTDOWN_SECONDS

    while time.monotonic() < end_time:
        frame = reader.read()
        if frame is None:
            return False

        frame = cv2.flip(frame, 1)
        processed = process_frame(frame, hands, pose)
        draw_skeleton(frame, processed, hand_draw, pose_draw)

        remaining = max(1, int(end_time - time.monotonic()) + 1)
        cv2.putText(
            frame,
            f"{label.upper()} STARTS IN {remaining}",
            (25, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 255),
            2,
        )
        cv2.imshow("Gesture Data Collector", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            return False

    return True


def record_sample(
    reader,
    hands,
    pose,
    hand_draw,
    pose_draw,
    label,
    person_id,
    dataset_dir,
    save_video,
):
    label_dir = dataset_dir / label
    label_dir.mkdir(parents=True, exist_ok=True)

    if not run_countdown(
        reader,
        hands,
        pose,
        hand_draw,
        pose_draw,
        label,
    ):
        return False

    sample_number = next_sample_number(label_dir, person_id)
    sample_name = f"{person_id}_{sample_number:04d}"

    hand_sequence = []
    hand_valid_sequence = []
    pose_sequence = []
    pose_valid_sequence = []
    handedness_sequence = []
    video_frames = []

    for frame_index in range(SEQUENCE_LENGTH):
        frame = reader.read()
        if frame is None:
            return False

        frame = cv2.flip(frame, 1)
        processed = process_frame(frame, hands, pose)

        hand_sequence.append(processed["hand_landmarks"])
        hand_valid_sequence.append(processed["hand_valid"])
        pose_sequence.append(processed["pose_landmarks"])
        pose_valid_sequence.append(processed["pose_valid"])
        handedness_sequence.append(processed["handedness"])

        display_frame = frame.copy()
        draw_skeleton(
            display_frame,
            processed,
            hand_draw,
            pose_draw,
        )

        progress = frame_index + 1
        cv2.putText(
            display_frame,
            f"RECORDING {label.upper()} {progress}/{SEQUENCE_LENGTH}",
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )
        cv2.imshow("Gesture Data Collector", display_frame)

        if save_video:
            video_frames.append(frame.copy())

        if cv2.waitKey(1) & 0xFF == ord("q"):
            return False

    detected_ratio = float(
        np.asarray(hand_valid_sequence)[:, 0].mean()
    )

    metadata = {
        "label": label,
        "person_id": person_id,
        "sample_name": sample_name,
        "sequence_length": SEQUENCE_LENGTH,
        "camera_fps": CAMERA_FPS,
        "frame_width": FRAME_WIDTH,
        "frame_height": FRAME_HEIGHT,
        "hand_detection_ratio": detected_ratio,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pose_indices": POSE_INDICES,
        "video_saved": save_video,
    }

    npz_path = label_dir / f"{sample_name}.npz"
    np.savez_compressed(
        npz_path,
        hand=np.asarray(hand_sequence, dtype=np.float32),
        hand_valid=np.asarray(hand_valid_sequence, dtype=np.uint8),
        pose=np.asarray(pose_sequence, dtype=np.float32),
        pose_valid=np.asarray(pose_valid_sequence, dtype=np.uint8),
        handedness=np.asarray(handedness_sequence),
        label=np.asarray(label),
        person_id=np.asarray(person_id),
    )

    metadata_path = label_dir / f"{sample_name}.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    if save_video and video_frames:
        video_path = label_dir / f"{sample_name}.mp4"
        writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            CAMERA_FPS,
            (FRAME_WIDTH, FRAME_HEIGHT),
        )

        for video_frame in video_frames:
            writer.write(video_frame)

        writer.release()

    print(
        f"Saved {sample_name}: label={label}, "
        f"hand detection={detected_ratio:.1%}"
    )

    return True


def draw_menu(frame, person_id, dataset_dir):
    lines = [
        f"Participant: {person_id}",
        "S: record STOP",
        "G: record GO",
        "U: record UNKNOWN",
        "Q: quit",
        "Video: off by default",
        f"Output: {dataset_dir}",
    ]

    y = 25
    for line in lines:
        cv2.putText(
            frame,
            line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            1,
        )
        y += 24


def main():
    args = parse_args()
    person_id = args.person.strip().replace(" ", "_")
    dataset_dir = Path(args.output).expanduser().resolve()
    dataset_dir.mkdir(parents=True, exist_ok=True)

    camera = start_camera(args.camera)
    reader = MjpegReader(camera)

    hand_draw = mp.solutions.drawing_utils
    pose_draw = mp.solutions.drawing_utils

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

                display_frame = frame.copy()
                draw_skeleton(
                    display_frame,
                    processed,
                    hand_draw,
                    pose_draw,
                )
                draw_menu(display_frame, person_id, dataset_dir)
                cv2.imshow("Gesture Data Collector", display_frame)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    break

                if key in LABEL_KEYS:
                    label = LABEL_KEYS[key]
                    success = record_sample(
                        reader,
                        hands,
                        pose,
                        hand_draw,
                        pose_draw,
                        label,
                        person_id,
                        dataset_dir,
                        args.save_video,
                    )
                    if not success:
                        break

    finally:
        if camera.poll() is None:
            camera.terminate()
            try:
                camera.wait(timeout=3)
            except subprocess.TimeoutExpired:
                camera.kill()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
