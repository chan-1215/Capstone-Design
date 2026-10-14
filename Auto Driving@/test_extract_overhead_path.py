import cv2
import numpy as np

from extract_overhead_path import locate


def test_locate_prefers_nearby_robot_over_larger_change():
    reference = np.full((240, 320, 3), 200, np.uint8)
    frame = reference.copy()
    cv2.rectangle(frame, (40, 40), (70, 70), (255, 0, 0), -1)
    cv2.rectangle(frame, (200, 120), (260, 180), (0, 0, 255), -1)

    point = locate(frame, reference, previous=(50, 50))

    assert point is not None
    assert abs(point[0] - 55) <= 1
    assert abs(point[1] - 55) <= 1


def test_locate_rejects_blank_and_implausible_jump():
    reference = np.full((240, 320, 3), 200, np.uint8)
    frame = reference.copy()
    cv2.rectangle(frame, (200, 120), (260, 180), (0, 0, 255), -1)

    assert locate(np.zeros_like(frame), reference) is None
    assert locate(frame, reference, previous=(50, 50)) is None
