"""Check syntax and mocked-GPIO tests, including Windows Unicode image paths."""

import ast
import os
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np


def unicode_imread(filename, flags=cv2.IMREAD_COLOR):
    path = Path(filename)
    if not path.is_file():
        return None
    return cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), flags)


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.dont_write_bytecode = True
    sources = sorted(root.glob('*.py'))
    for source in sources:
        compile(ast.parse(source.read_text(encoding='utf-8-sig')), str(source), 'exec')
    print(f'Syntax OK: {len(sources)} Python files', flush=True)
    original_imread = cv2.imread
    if os.name == 'nt':
        cv2.imread = unicode_imread
    try:
        suite = unittest.defaultTestLoader.discover(str(root), pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        cv2.imread = original_imread
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
