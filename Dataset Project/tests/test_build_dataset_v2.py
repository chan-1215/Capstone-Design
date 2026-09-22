import unittest

from training.build_dataset_v2 import labeled_pwm


class BuildDatasetV2Tests(unittest.TestCase):
    def test_expert_command_uses_command_pwm_as_label(self):
        row = {
            "control_mode": "expert",
            "command": "expert_path_follow",
            "left_pwm": "0.42",
            "right_pwm": "0.36",
        }

        self.assertEqual(labeled_pwm(row), (0.42, 0.36, "expert_command"))

    def test_recovery_row_uses_expert_reference_pwm_as_label(self):
        row = {
            "control_mode": "learned",
            "command": "learned_model",
            "left_pwm": "0.57",
            "right_pwm": "0.12",
            "expert_left_pwm": "0.39",
            "expert_right_pwm": "0.44",
        }

        self.assertEqual(labeled_pwm(row), (0.39, 0.44, "expert_reference"))


if __name__ == "__main__":
    unittest.main()
