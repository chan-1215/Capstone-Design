"""Compatibility imports for the shared gesture worker."""

import sys
from pathlib import Path

GESTURE_ROOT = Path(__file__).resolve().parents[2] / 'Gesture'
if str(GESTURE_ROOT) not in sys.path:
    sys.path.insert(0, str(GESTURE_ROOT))

from worker import GestureWorker, caption, fresh_decision, load_recognizer, reset_history

__all__ = ['GestureWorker', 'caption', 'fresh_decision', 'load_recognizer', 'reset_history']
