"""Prevent two Gesture PC processes from opening the same Windows webcam."""

import ctypes
import sys
from contextlib import contextmanager


@contextmanager
def webcam_guard(camera_index):
    handle = None
    kernel32 = None
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_bool
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, f"Local\\CapstoneGesturePC.Camera.{camera_index}")
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        if error == 183:
            kernel32.CloseHandle(handle)
            raise RuntimeError(
                f"Gesture PC camera {camera_index} is already running. "
                "Close its window with q or Esc before starting another run or --check."
            )
    try:
        yield
    finally:
        if handle is not None:
            kernel32.CloseHandle(handle)
