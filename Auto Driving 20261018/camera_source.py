"""Frame sources only; never imports motor, GPIO, gesture or old robot code."""

from pathlib import Path
from collections import deque
import logging
import shutil
import subprocess
import threading
import time

import cv2
import numpy as np

from analyze_photos import read_image


class RpicamSource:
    """Use the OS camera application without Python-version-specific bindings."""

    def __init__(self, width, height, fps, sensor_size=None):
        self.size = (width, height)
        self.fps = fps
        self.sensor_size = sensor_size
        self.process = None
        self.threads = []
        self.condition = threading.Condition()
        self.stopping = False
        self.jpeg = None
        self.number = self.consumed = 0
        self.error = None
        self.messages = deque(maxlen=12)

    def start(self):
        executable = shutil.which('rpicam-vid') or shutil.which('libcamera-vid')
        if not executable:
            raise RuntimeError('Python camera bindings unavailable; install rpicam-apps')
        command = [executable, '--codec', 'mjpeg', '--quality', '95',
                   '--width', str(self.size[0]), '--height', str(self.size[1]),
                   '--framerate', str(self.fps), '--timeout', '0', '--nopreview',
                   '--flush', '--output', '-']
        if self.sensor_size:
            command += ['--mode', f'{self.sensor_size[0]}:{self.sensor_size[1]}']
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        bufsize=0)
        self.threads = [threading.Thread(target=self._read_pipe, daemon=True,
                                        name='rpicam-frames'),
                        threading.Thread(target=self._read_errors, daemon=True,
                                         name='rpicam-errors')]
        for thread in self.threads:
            thread.start()
        try:
            with self.condition:
                ready = self.condition.wait_for(lambda: self.jpeg is not None or self.error,
                                                timeout=10)
                if not ready or self.error:
                    raise RuntimeError(self._error_text('No camera frame within 10 seconds'))
        except BaseException:
            self.stop()
            raise

    def _error_text(self, default):
        return (self.error or default) + ': ' + ' '.join(self.messages)[-2000:]

    def _read_errors(self):
        while True:
            line = self.process.stderr.readline(2048)
            if not line:
                break
            with self.condition:
                self.messages.append(line.decode(errors='replace').strip())

    def _read_pipe(self):
        buffer = bytearray()
        limit = max(2_000_000, self.size[0] * self.size[1] * 6)
        try:
            while not self.stopping:
                chunk = self.process.stdout.read(65536)
                if not chunk:
                    raise RuntimeError('CSI camera process stopped')
                buffer.extend(chunk)
                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9', start + 2) if start >= 0 else -1
                    if end < 0:
                        if start > 0:
                            del buffer[:start]
                        if len(buffer) > limit:
                            raise RuntimeError('Invalid or oversized camera frame')
                        break
                    jpeg = bytes(buffer[start:end + 2])
                    del buffer[:end + 2]
                    with self.condition:
                        self.jpeg = jpeg
                        self.number += 1
                        self.condition.notify_all()
        except Exception as error:
            with self.condition:
                if not self.stopping:
                    self.error = str(error)
                self.condition.notify_all()

    def read(self):
        with self.condition:
            ready = self.condition.wait_for(
                lambda: self.number != self.consumed or self.error or self.stopping, timeout=2)
            if not ready or self.error or self.stopping:
                raise RuntimeError(self._error_text('No fresh camera frame within 2 seconds'))
            jpeg = self.jpeg
            self.consumed = self.number
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2] != (self.size[1], self.size[0]):
            raise RuntimeError('Invalid camera frame dimensions or JPEG data')
        return frame

    def stop(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            for thread in self.threads:
                thread.join(timeout=2)
            self.process.stdout.close()
            self.process.stderr.close()
            self.process = None


class PiCameraSource:
    def __init__(self, width=640, height=480, fps=30, sensor_size=None):
        self.size = (width, height)
        self.fps = fps
        self.sensor_size = sensor_size
        self.camera = None
        self.bridge = None

    def start(self):
        try:
            from picamera2 import Picamera2
        except ModuleNotFoundError as error:
            if error.name not in ('picamera2', 'libcamera', 'libcamera._libcamera'):
                raise
            logging.warning('Using rpicam-vid camera input; Flask/OpenCV stay in this Python environment')
            self.bridge = RpicamSource(*self.size, self.fps, self.sensor_size)
            self.bridge.start()
            return

        self.camera = Picamera2()
        # libcamera RGB888 arrays use BGR byte order, as expected by OpenCV.
        # https://github.com/raspberrypi/picamera2/blob/main/picamera2/request.py
        # The IMX219 640x480 sensor mode crops the centre; selecting its
        # 1640x1232 mode preserves full sensor coverage before ISP downscaling.
        options = {'raw':{'size':tuple(self.sensor_size)}} if self.sensor_size else {}
        configuration = self.camera.create_video_configuration(
            main={"size": self.size, "format": "RGB888"},
            controls={"FrameRate": self.fps}, buffer_count=3, **options)
        self.camera.configure(configuration)
        self.camera.start()

    def read(self):
        if self.bridge is not None:
            return self.bridge.read()
        return self.camera.capture_array("main")

    def stop(self):
        if self.bridge is not None:
            self.bridge.stop()
            self.bridge = None
        if self.camera is not None:
            try:
                self.camera.stop()
            finally:
                self.camera.close()
                self.camera = None


class ImageSource:
    def __init__(self, path, fps=10):
        self.path = Path(path)
        self.delay = 1.0 / fps
        self.frame = None

    def start(self):
        self.frame = read_image(self.path)

    def read(self):
        time.sleep(self.delay)
        return self.frame.copy()

    def stop(self):
        pass
