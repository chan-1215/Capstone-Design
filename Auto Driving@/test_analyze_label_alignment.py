import unittest

import numpy as np

from analyze_label_alignment import aligned_samples, confirm_turns


class AlignmentTest(unittest.TestCase):
    def test_future_label_and_turn_proximity_are_separate(self):
        times = np.arange(7, dtype=float) * 0.1
        actions = [0, 0, 0, 1, 1, 1, 1]
        observations = [(0.0, 0.0, 20.0, "양쪽 선")]
        session = (times, actions, observations, times[3:])
        features, labels, sample_times, lanes, away = aligned_samples(session, 0.4)
        self.assertEqual(features.tolist(), [[0.0, 20.0]])
        self.assertEqual(labels.tolist(), [1])
        self.assertEqual(sample_times.tolist(), [0.0])
        self.assertEqual(lanes.tolist(), ["양쪽 선"])
        self.assertEqual(away.tolist(), [False])

    def test_turn_confirmation_requires_contiguous_same_direction(self):
        predictions = np.array([1, 1, 1, 0, -1, -1, -1], dtype=np.int8)
        times = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.7, 0.8])
        self.assertEqual(confirm_turns(predictions, times).tolist(),
                         [0, 0, 1, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
