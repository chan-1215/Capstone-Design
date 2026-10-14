"""Camera-only browser preview for the steering robot Raspberry Pi."""

import argparse
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Camera:
    def __init__(self, kind, device, width, height, fps, rotate):
        self.kind = kind
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.rotate = rotate
        self.frame = None
        self.frame_at = 0.0
        self.capture_fps = 0.0
        self.error = None
        self.running = False
        self.condition = threading.Condition()
        self.process = None
        self.capture = None
        self.thread = None
        self.cv2 = None

    def start(self):
        if self.kind == "csi":
            executable = shutil.which("rpicam-vid") or shutil.which("libcamera-vid")
            if not executable:
                raise RuntimeError("rpicam-vid/libcamera-vid is not installed")
            command = [executable, "--codec", "mjpeg", "--width", str(self.width),
                       "--height", str(self.height), "--framerate", str(self.fps),
                       "--timeout", "0", "--nopreview", "--output", "-"]
            if self.rotate:
                command.extend(("--hflip", "--vflip"))
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        else:
            try:
                import cv2
            except ImportError as exc:
                raise RuntimeError("USB camera preview requires python3-opencv") from exc
            self.cv2 = cv2
            self.capture = cv2.VideoCapture(self.device)
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.capture.set(cv2.CAP_PROP_FPS, self.fps)
            if not self.capture.isOpened():
                self.capture.release()
                raise RuntimeError(f"USB camera /dev/video{self.device} could not be opened")

        self.running = True
        target = self._read_csi if self.kind == "csi" else self._read_usb
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def _publish(self, jpeg):
        with self.condition:
            now = time.monotonic()
            if self.frame_at:
                sample = 1.0 / max(now - self.frame_at, 0.001)
                self.capture_fps = sample if not self.capture_fps else 0.8 * self.capture_fps + 0.2 * sample
            self.frame_at = now
            self.frame = jpeg
            self.condition.notify_all()

    def _encode_usb(self, frame):
        if self.rotate:
            frame = self.cv2.rotate(frame, self.cv2.ROTATE_180)
        ok, jpeg = self.cv2.imencode(".jpg", frame, [self.cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            self._publish(jpeg.tobytes())

    def _read_usb(self):
        while self.running:
            ok, frame = self.capture.read()
            if not ok:
                self.error = "USB camera stopped delivering frames"
                break
            self._encode_usb(frame)
        self.running = False

    def _read_csi(self):
        buffer = bytearray()
        while self.running:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                self.error = "CSI camera process stopped"
                break
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                if start < 0 or end < 0:
                    if start > 0:
                        del buffer[:start]
                    elif len(buffer) > 2_000_000:
                        buffer.clear()
                    break
                jpeg = bytes(buffer[start:end + 2])
                del buffer[:end + 2]
                self._publish(jpeg)
        self.running = False

    def stop(self):
        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.capture:
            self.capture.release()
        if self.thread:
            self.thread.join(timeout=2)


def make_handler(camera):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                page = ("<!doctype html><html lang='ko'><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        "<title>Pi camera test</title>"
                        "<style>body{margin:0;background:#151719;color:white;font:16px sans-serif}"
                        "header{padding:12px 16px}img{display:block;width:100%;height:auto;max-height:calc(100vh - 50px);object-fit:contain}</style>"
                        "<header>Pi camera test (motors disabled)</header><img src='/stream.mjpg' alt='Camera stream'></html>")
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    previous = None
                    while camera.running:
                        with camera.condition:
                            camera.condition.wait_for(
                                lambda: camera.frame is not previous or not camera.running,
                                timeout=1)
                            frame = camera.frame
                        if frame is None or frame is previous:
                            continue
                        previous = frame
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Preview the Pi camera without driving motors")
    parser.add_argument("--camera", choices=("csi", "usb"), default="csi")
    parser.add_argument("--device", type=int, default=0, help="USB camera index (default: 0)")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--rotate", dest="rotate", action="store_true", default=True,
                        help="Rotate image by 180 degrees (default)")
    parser.add_argument("--no-rotate", dest="rotate", action="store_false")
    args = parser.parse_args()
    if min(args.width, args.height, args.fps) < 1:
        parser.error("width, height and fps must be positive")

    camera = Camera(args.camera, args.device, args.width, args.height, args.fps, args.rotate)
    try:
        camera.start()
        deadline = time.monotonic() + 8
        while camera.frame is None and camera.error is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if camera.frame is None:
            raise RuntimeError(camera.error or "No camera frame received within 8 seconds")
        with ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(camera)) as server:
            print(f"Camera preview: http://<pi-ip>:{args.port}/ (Ctrl+C to stop)", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
