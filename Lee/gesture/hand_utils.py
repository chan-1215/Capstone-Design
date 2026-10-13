# file name: hand_utils.py

import numpy as np


def normalize_hand_frame(frame):
    frame = np.asarray(frame, dtype=np.float32).copy()

    wrist = frame[0].copy()
    frame -= wrist

    scale = np.linalg.norm(frame[9])

    if scale < 1e-6:
        scale = np.max(np.linalg.norm(frame, axis=1))

    if scale < 1e-6:
        scale = 1.0

    return frame / scale


def normalize_hand_sequence(hand_sequence):
    hand = np.asarray(hand_sequence, dtype=np.float32).copy()

    for frame_index in range(hand.shape[0]):
        hand[frame_index] = normalize_hand_frame(hand[frame_index])

    return hand


def is_open_hand(hand):
    # Extended = fingertip sits farther from the wrist than its own PIP joint.
    # Distance-from-wrist is rotation-invariant (unlike comparing tip/pip y in
    # image space), so this still works when the hand isn't held perfectly
    # upright to the camera. A small margin avoids flicker for near-straight
    # fingers sitting right at the fold/extend boundary.
    margin = 1.05

    wrist = hand[0]
    finger_pairs = [
        (8, 6),
        (12, 10),
        (16, 14),
        (20, 18),
    ]
    extended = [
        np.linalg.norm(hand[tip] - wrist) > np.linalg.norm(hand[pip] - wrist) * margin
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
