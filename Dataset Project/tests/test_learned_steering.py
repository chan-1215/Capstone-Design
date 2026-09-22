import tempfile
import unittest
from pathlib import Path

import numpy as np

from controllers.learned_steering import LearnedSteeringModel
from controllers.vision_preprocessing import extract_steering_features
from simulation.synthetic_camera import make_lane_frame


class LearnedSteeringModelTests(unittest.TestCase):
    def test_features_are_stable_for_inverted_lane_colors(self):
        normal = make_lane_frame()
        inverted = make_lane_frame(inverted=True)

        normal_features = extract_steering_features(normal, 32, 18)
        inverted_features = extract_steering_features(inverted, 32, 18)

        np.testing.assert_allclose(normal_features, inverted_features)

    def test_edge_features_are_stable_for_inverted_lane_colors(self):
        normal = make_lane_frame()
        inverted = make_lane_frame(inverted=True)

        normal_features = extract_steering_features(
            normal,
            32,
            18,
            feature_mode="lane_edges",
        )
        inverted_features = extract_steering_features(
            inverted,
            32,
            18,
            feature_mode="lane_edges",
        )

        np.testing.assert_allclose(normal_features, inverted_features)

    def test_prediction_is_limited_to_model_output_range(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "test_model.npz"
            image_width = 32
            image_height = 18
            feature_count = image_width * image_height
            weights = np.zeros((feature_count + 1, 2), dtype=np.float32)
            weights[-1] = [1.0, -1.0]
            np.savez_compressed(
                model_path,
                weights=weights,
                feature_mean=np.zeros(feature_count, dtype=np.float32),
                feature_std=np.ones(feature_count, dtype=np.float32),
                output_min=np.array([0.1, 0.1], dtype=np.float32),
                output_max=np.array([0.6, 0.6], dtype=np.float32),
                steering_min=-0.2,
                steering_max=0.2,
                image_width=image_width,
                image_height=image_height,
            )

            model = LearnedSteeringModel(model_path)
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            left_pwm, right_pwm = model.predict(frame)

        self.assertAlmostEqual(left_pwm, 0.45, places=5)
        self.assertAlmostEqual(right_pwm, 0.25, places=5)


if __name__ == "__main__":
    unittest.main()
