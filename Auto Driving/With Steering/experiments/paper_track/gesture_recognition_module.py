"""Historical import name for the shared gesture recognizer."""

import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[4] / 'Gesture'
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location('paper_shared_gesture', root / 'gesture_recognition_module.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
GestureRecognizer = module.GestureRecognizer
