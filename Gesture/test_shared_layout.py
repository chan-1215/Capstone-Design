import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import worker


class SharedLayoutTests(unittest.TestCase):
    def test_flask_imports_the_shared_worker(self):
        adapter_path = Path(__file__).resolve().parents[1] / 'Auto Driving' / 'With Steering' / 'gesture_adapter.py'
        spec = importlib.util.spec_from_file_location('layout_adapter_test', adapter_path)
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        self.assertIs(adapter.GestureWorker, worker.GestureWorker)
        self.assertIs(adapter.load_recognizer, worker.load_recognizer)

    def test_shared_loader_and_default_recognizer_use_the_same_model(self):
        fake = SimpleNamespace(solutions=SimpleNamespace(
            hands=SimpleNamespace(Hands=lambda **kw: SimpleNamespace(close=lambda: None)),
            drawing_utils=SimpleNamespace()))
        with patch.dict(sys.modules, {'mediapipe': fake}):
            loaded = worker.load_recognizer()
            direct = type(loaded)()
        self.addCleanup(loaded.close)
        self.addCleanup(direct.close)
        self.assertEqual(loaded.model_features.shape, (256, 1890))
        np.testing.assert_array_equal(loaded.model_features, direct.model_features)
        np.testing.assert_array_equal(loaded.model_labels, direct.model_labels)
