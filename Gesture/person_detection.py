"""YOLOv8n-seg person outlines with a single latest-frame worker."""

import threading
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PERSON_MODEL = Path(__file__).with_name("models") / "yolov8n-seg.pt"


@dataclass(frozen=True)
class PersonInstance:
    xyxy: tuple[int, int, int, int]
    confidence: float
    outline: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PersonResult:
    persons: tuple[PersonInstance, ...]
    captured_at: float
    inference_ms: float

    def is_fresh(self, now, max_age=1.0):
        return 0 <= now - self.captured_at <= max_age


class YoloPersonModel:
    def __init__(self, model_path=DEFAULT_PERSON_MODEL, confidence=0.5,
                 image_size=320, cpu_threads=2):
        import numpy as np
        import torch
        from ultralytics import YOLO

        torch.set_num_threads(cpu_threads)
        model_path = Path(model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(model_path), task="segment")
        if self.model.task != "segment":
            raise ValueError("Person outlines require a segmentation model such as yolov8n-seg.pt.")
        if self.model.names[0] != "person":
            raise ValueError("The person detector requires a COCO model with class 0 = person.")
        self.confidence = confidence
        self.image_size = image_size
        # Ultralytics initializes its backend on first prediction and resets
        # CPU threads there. Warm it up before applying the steady-state limit.
        self(np.zeros((image_size, image_size, 3), dtype=np.uint8))
        torch.set_num_threads(cpu_threads)

    def __call__(self, frame):
        result = self.model.predict(
            source=frame, classes=[0], conf=self.confidence,
            imgsz=self.image_size, device="cpu", max_det=20,
            retina_masks=True, verbose=False, save=False,
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            return ()
        if result.masks is None:
            raise RuntimeError("The segmentation model returned persons without masks.")
        coordinates = result.boxes.xyxy.cpu().tolist()
        confidences = result.boxes.conf.cpu().tolist()
        polygons = result.masks.xy
        if len(polygons) != len(coordinates):
            raise RuntimeError("Person boxes and segmentation masks do not match.")
        height, width = frame.shape[:2]
        persons = []
        for (left, top, right, bottom), confidence, polygon in zip(coordinates, confidences, polygons):
            xyxy = (
                max(0, min(width - 1, round(left))),
                max(0, min(height - 1, round(top))),
                max(0, min(width - 1, round(right))),
                max(0, min(height - 1, round(bottom))),
            )
            outline = tuple(
                (max(0, min(width - 1, round(x))), max(0, min(height - 1, round(y))))
                for x, y in polygon.tolist()
            )
            if len(outline) >= 3:
                persons.append(PersonInstance(xyxy, float(confidence), outline))
        return tuple(persons)


class LatestFrameDetector:
    def __init__(self, predict, interval=0.2):
        if interval <= 0:
            raise ValueError("Detection interval must be positive.")
        self.predict = predict
        self.interval = interval
        self.condition = threading.Condition()
        self.pending = None
        self.result = None
        self.error = None
        self.completed = 0
        self.stopping = False
        self.thread = threading.Thread(target=self._run, name="YOLO-person", daemon=True)

    def start(self):
        self.thread.start()

    def submit(self, frame, captured_at):
        with self.condition:
            if not self.stopping:
                # Replace queued input instead of falling behind the live camera.
                self.pending = (frame.copy(), captured_at)
                self.condition.notify()

    def snapshot(self):
        with self.condition:
            return self.result, self.error, self.completed

    def _run(self):
        next_run = 0.0
        while True:
            with self.condition:
                while not self.stopping:
                    delay = next_run - time.monotonic()
                    if self.pending is not None and delay <= 0:
                        frame, captured_at = self.pending
                        self.pending = None
                        break
                    self.condition.wait(timeout=max(0.0, delay) if self.pending else None)
                if self.stopping:
                    return
            started = time.monotonic()
            next_run = started + self.interval
            try:
                persons = self.predict(frame)
            except Exception as exc:
                with self.condition:
                    self.error = str(exc)
                    self.stopping = True
                    self.pending = None
                    self.condition.notify_all()
                return
            result = PersonResult(tuple(persons), captured_at,
                                  (time.monotonic() - started) * 1000)
            with self.condition:
                self.result = result
                self.completed += 1
                self.condition.notify_all()

    def close(self):
        with self.condition:
            self.stopping = True
            self.pending = None
            self.condition.notify_all()
        if self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError("YOLO worker did not stop within 5 seconds.")
