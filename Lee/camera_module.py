# file name: camera_module.py

import subprocess
import threading
import time

import cv2
import numpy as np


_camera_process = None
_camera_thread = None
_running = False

_latest_jpeg = None
latest_frame = None

_frame_lock = threading.Lock()


def get_latest_frame():
    with _frame_lock:
        if latest_frame is None:
            return None
        return latest_frame.copy()


def start_camera(width=320, height=240, fps=15, show_preview=False):
    global _camera_process, _camera_thread, _running

    if _running:
        return

    command = [
        "rpicam-vid",
        "-t", "0",
        "-n",
        "--codec", "mjpeg",
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "-o", "-",
    ]

    _camera_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )

    _running = True
    _camera_thread = threading.Thread(target=_capture_loop, daemon=True)
    _camera_thread.start()

    print("rpicam camera started")


def _capture_loop():
    global _latest_jpeg, latest_frame, _running

    buffer = b""

    while _running:
        try:
            if _camera_process is None or _camera_process.stdout is None:
                time.sleep(0.1)
                continue

            chunk = _camera_process.stdout.read(4096)

            if not chunk:
                time.sleep(0.02)
                continue

            buffer += chunk

            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9")

            if start == -1 or end == -1 or end < start:
                continue

            jpg = buffer[start:end + 2]
            buffer = buffer[end + 2:]

            frame = cv2.imdecode(
                np.frombuffer(jpg, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )

            if frame is None:
                continue

            display_frame = frame.copy()

            cv2.putText(
                display_frame,
                "Pi-Rover Camera",
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

            ok, encoded = cv2.imencode(".jpg", display_frame)

            with _frame_lock:
                latest_frame = frame.copy()

                if ok:
                    _latest_jpeg = encoded.tobytes()

        except Exception as exc:
            print(f"Camera capture error: {exc}")
            time.sleep(0.2)

        time.sleep(0.01)


def generate_camera_stream():
    while True:
        with _frame_lock:
            frame = _latest_jpeg

        if frame is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )

        time.sleep(0.03)


def stop_camera():
    global _camera_process, _running

    _running = False

    if _camera_process is not None:
        try:
            _camera_process.terminate()
            _camera_process.wait(timeout=2)
        except Exception:
            try:
                _camera_process.kill()
            except Exception:
                pass

    _camera_process = None
    print("rpicam camera stopped")


if __name__ == "__main__":
    try:
        start_camera(show_preview=False)

        while True:
            frame = get_latest_frame()

            if frame is not None:
                cv2.imshow("rpicam preview", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            time.sleep(0.03)

    except KeyboardInterrupt:
        print("Stopped by Ctrl+C")

    finally:
        stop_camera()
        cv2.destroyAllWindows()