import unittest

import numpy as np

from evaluate_hybrid_control import predict, select_parameters


class HybridEvaluationTest(unittest.TestCase):
    def test_heading_changes_curve_direction_without_changing_center_only(self):
        curve = np.array([[-6.7, 34.0]], dtype=np.float32)
        self.assertEqual(int(predict(curve, 0.0, 14)[0]), 0)
        self.assertEqual(int(predict(curve, 0.35, 14)[0]), 1)

    def test_fit_uses_only_supplied_training_samples(self):
        x = np.array([[0, -100], [0, 0], [0, 100]], dtype=np.float32)
        y = np.array([-1, 0, 1], dtype=np.int8)
        gain, threshold = select_parameters(x, y)
        self.assertGreater(gain, 0)
        self.assertTrue(np.array_equal(predict(x, gain, threshold), y))


if __name__ == "__main__":
    unittest.main()
