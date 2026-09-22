import tempfile
import unittest
from pathlib import Path

import numpy as np

from controllers.driveability import DriveabilityModel


class DriveabilityModelTests(unittest.TestCase):
    def test_probability_is_clipped_and_thresholded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "driveability.npz"
            image_width = 32
            image_height = 18
            feature_count = image_width * image_height
            weights = np.zeros(feature_count + 1, dtype=np.float32)
            weights[-1] = 1.2
            np.savez_compressed(
                model_path,
                weights=weights,
                feature_mean=np.zeros(feature_count, dtype=np.float32),
                feature_std=np.ones(feature_count, dtype=np.float32),
                threshold=0.45,
                feature_mode="lane_edges",
                image_width=image_width,
                image_height=image_height,
            )

            model = DriveabilityModel(model_path)
            frame = np.zeros((240, 320, 3), dtype=np.uint8)

        self.assertEqual(model.predict_probability(frame), 1.0)
        self.assertTrue(model.is_drivable(frame))


if __name__ == "__main__":
    unittest.main()
