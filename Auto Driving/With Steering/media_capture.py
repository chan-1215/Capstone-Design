"""Bounded local raw/OpenCV capture; never opens a second camera."""

from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import shutil
import threading
import time

import cv2


def timestamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')


class CaptureStore:
    def __init__(self, root, min_free_bytes=150 * 1024 * 1024, max_seconds=120, fps=10):
        self.root = Path(root).resolve()
        for directory in ('photos', 'videos', 'runs'):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        self.minimum_free = min_free_bytes
        self.max_seconds = max_seconds
        self.fps = fps
        self.lock = threading.RLock()
        self.thread = None
        self.stop_event = threading.Event()
        self.frames = queue.Queue(maxsize=8)
        self.started = None
        self.next_frame = 0
        self.written = self.dropped = 0
        self.error = None
        self.last_files = []
        self.active_files = []

    def check_space(self):
        if shutil.disk_usage(self.root).free < self.minimum_free:
            raise OSError('Not enough free storage (150 MiB reserve)')

    def photo(self, raw, processed, metadata, *, lossless_raw=False):
        with self.lock:
            self.check_space()
            name = 'photo_' + timestamp()
            files = []
            for suffix, frame in (('raw', raw), ('opencv', processed)):
                extension = '.png' if suffix == 'raw' and lossless_raw else '.jpg'
                path = self.root / 'photos' / f'{name}_{suffix}{extension}'
                parameters = ([cv2.IMWRITE_PNG_COMPRESSION, 1] if extension == '.png'
                              else [cv2.IMWRITE_JPEG_QUALITY, 94])
                ok, encoded = cv2.imencode(extension, frame, parameters)
                if not ok:
                    raise OSError('Photo encoding failed')
                path.write_bytes(encoded.tobytes())
                files.append(path.relative_to(self.root).as_posix())
            path = self.root / 'photos' / f'{name}.json'
            path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
            files.append(path.relative_to(self.root).as_posix())
            self.last_files = files
            return files

    def start_video(self, size):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Recording is already active')
            self.check_space()
            self.stop_event = threading.Event()
            self.frames = queue.Queue(maxsize=8)
            self.started = time.monotonic()
            self.next_frame = self.started
            self.written = self.dropped = 0
            self.error = None
            name = 'video_' + timestamp()
            self.last_files = [f'videos/{name}_raw.mp4', f'videos/{name}_opencv.mp4',
                               f'videos/{name}.jsonl']
            self.active_files = list(self.last_files)
            self.thread = threading.Thread(target=self._encode,
                                           args=(tuple(size), list(self.last_files)),
                                           name='capture-encoder', daemon=True)
            self.thread.start()

    def offer(self, raw, processed, metadata):
        with self.lock:
            if (not self.thread or not self.thread.is_alive() or self.stop_event.is_set()
                    or time.monotonic() < self.next_frame):
                return
            now = time.monotonic()
            self.next_frame = max(self.next_frame + 1 / self.fps, now - .05)
            try:
                self.frames.put_nowait((raw.copy(), processed.copy(), metadata))
            except queue.Full:
                self.dropped += 1

    def _encode(self, size, names):
        writers = []
        log = None
        try:
            for name in names[:2]:
                writer = cv2.VideoWriter(str(self.root / name), cv2.VideoWriter_fourcc(*'mp4v'),
                                         self.fps, size)
                writers.append(writer)
                if not writer.isOpened():
                    raise OSError('MP4 encoder could not open')
            log = (self.root / names[2]).open('w', encoding='utf-8')
            log.write(json.dumps({'event':'start', 'fps':self.fps, 'size':size,
                                  'timestamp_utc':datetime.now(timezone.utc).isoformat()}) + '\n')
            while not (self.stop_event.is_set() and self.frames.empty()):
                if time.monotonic() - self.started >= self.max_seconds:
                    self.stop_event.set()
                self.check_space()
                try:
                    raw, processed, metadata = self.frames.get(timeout=.1)
                except queue.Empty:
                    continue
                if raw.shape[1::-1] != size or processed.shape[1::-1] != size:
                    raise ValueError('Camera dimensions changed during recording')
                writers[0].write(raw)
                writers[1].write(processed)
                log.write(json.dumps({'frame':self.written, **metadata}) + '\n')
                with self.lock:
                    self.written += 1
            log.write(json.dumps({'event':'stop', 'frames':self.written,
                                  'dropped':self.dropped}) + '\n')
        except Exception as error:
            with self.lock:
                self.error = f'{type(error).__name__}: {error}'
            self.stop_event.set()
        finally:
            for writer in writers:
                writer.release()
            if log:
                log.close()

    def stop_video(self):
        with self.lock:
            self.stop_event.set()
            thread = self.thread
        if thread:
            thread.join(timeout=5)

    def status(self):
        with self.lock:
            active = bool(self.thread and self.thread.is_alive())
            files = []
            for directory in ('photos', 'videos', 'runs'):
                files.extend(p for p in (self.root / directory).iterdir()
                             if p.is_file() and p.suffix in ('.jpg', '.png', '.mp4', '.json', '.jsonl'))
            entries = []
            for path in files:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append(dict(name=path.name, path=path.relative_to(self.root).as_posix(),
                                    bytes=stat.st_size, modified=stat.st_mtime))
            latest = sorted(entries, key=lambda entry:entry['modified'], reverse=True)[:18]
            return dict(recording=active, stopping=active and self.stop_event.is_set(),
                        elapsed_seconds=round(time.monotonic() - self.started, 1) if active else 0,
                        frames=self.written, dropped=self.dropped, error=self.error,
                        directory=str(self.root), free_mib=shutil.disk_usage(self.root).free // (1024 * 1024),
                        max_seconds=self.max_seconds, fps=self.fps,
                        files=[{key:value for key,value in entry.items() if key != 'modified'} for entry in latest],
                        active_files=list(self.active_files) if active else [],
                        last_files=list(self.last_files))

    def close(self):
        self.stop_video()
