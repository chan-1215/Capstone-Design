"""Latest-only MediaPipe/KNN worker, isolated from GPIO and camera ownership."""

import importlib.util
from collections import deque
from pathlib import Path
import sys
import threading
import time

import cv2
import numpy as np

def load_recognizer():
    root = Path(__file__).resolve().parent
    # The preserved module uses the historical top-level hand_utils import.
    # Bind exactly that local helper, rejecting an unrelated existing module.
    helper = sys.modules.get('hand_utils')
    if helper is not None and Path(helper.__file__).resolve() != root/'hand_utils.py':
        raise RuntimeError('Conflicting hand_utils module; gesture initialization stopped')
    if helper is None:
        spec = importlib.util.spec_from_file_location('hand_utils', root/'hand_utils.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        sys.modules['hand_utils'] = helper
    spec = importlib.util.spec_from_file_location('track_gesture_reference', root/'gesture_recognition_module.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recognizer = module.GestureRecognizer(model_path=str(root/'models/gesture_knn_model.npz'))
    features, labels = recognizer.model_features, recognizer.model_labels
    if (features.ndim != 2 or features.shape[1] != recognizer.sequence_length*63
            or features.shape[0] < recognizer.k or len(labels) != features.shape[0]
            or not np.all(np.isfinite(features))):
        recognizer.close()
        raise ValueError('Gesture model dimensions or numeric values are invalid')
    return recognizer


def reset_history(recognizer):
    for name in ('hand_buffer', 'hand_valid_buffer', 'raw_points_buffer', 'prediction_buffer'):
        getattr(recognizer, name).clear()
    recognizer.display_label = recognizer.last_valid_label = 'unknown'
    recognizer.last_valid_time = 0.


def fresh_decision(recognizer, result):
    ready = (len(recognizer.hand_buffer) == recognizer.sequence_length
             and sum(recognizer.hand_valid_buffer)/recognizer.sequence_length >= recognizer.min_hand_ratio
             and result['hand_detected'])
    if not ready:
        return 'unknown', False
    # Do not authorize movement from the module's held display or smoothed raw
    # label. Reuse its model/features but obtain the current unsmoothed decision.
    label, _ = recognizer.predict_knn(recognizer.make_feature())
    if label == 'stop':
        helper = sys.modules['hand_utils']
        points = recognizer.raw_points_buffer[-1]
        if not helper.is_open_hand(points) or not helper.is_palm_allowed(points, recognizer.palm_sign):
            label = 'unknown'
    return label, True


def caption(frame, label, detail):
    cv2.rectangle(frame, (0,0), (min(frame.shape[1]-1,430),66), (20,22,25), -1)
    cv2.putText(frame, 'Decision: '+label.upper(), (10,26),
                cv2.FONT_HERSHEY_SIMPLEX,.65,(100,230,130) if label == 'go' else (240,240,240),2)
    cv2.putText(frame, detail, (10,53),cv2.FONT_HERSHEY_SIMPLEX,.48,(210,215,220),1)
    return frame


class GestureWorker:
    def __init__(self, factory=load_recognizer, fps=15):
        self.factory = factory
        self.delay = 1/fps
        self.condition = threading.Condition()
        self.mode = 'off'
        self.epoch = 0
        self.pending = None
        self.result = {}
        self.error = None
        self.closed = False
        self.initialized = False
        self.completed = 0
        self.completed_at = deque(maxlen=31)
        self.thread = threading.Thread(target=self._loop, name='gesture-latest', daemon=True)

    def start(self):
        self.thread.start()

    def set_mode(self, mode):
        if mode not in ('off', 'preview', 'wait'):
            raise ValueError('Invalid gesture mode')
        with self.condition:
            if mode != self.mode:
                self.mode = mode
                self.epoch += 1
                self.pending = None
                self.result = {}
                self.completed_at.clear()
                self.condition.notify_all()

    def offer(self, frame, number, received_at):
        with self.condition:
            if (self.mode != 'off' and not self.closed and not self.error
                    and type(number) is int and type(received_at) in (int, float)):
                self.pending = (frame.copy(), number, received_at, self.epoch, self.mode)
                self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            data = {k:v for k,v in self.result.items() if k != 'debug_frame'}
            data.update(mode=self.mode, epoch=self.epoch, initialized=self.initialized, error=self.error)
            times = list(self.completed_at)
            fps = ((len(times)-1)/(times[-1]-times[0])
                   if len(times)>1 and times[-1]>times[0] and time.monotonic()-times[-1]<1 else 0.)
            data.update(inference_frames=self.completed, inference_fps=round(fps,1))
        received = data.get('received_at')
        age = None if received is None else time.monotonic()-received
        data['result_age_seconds'] = age
        if age is None or not 0 <= age <= .2:
            data.update(ready=False, decision_label='unknown', hand_detected=False)
        return data

    def image(self, fallback):
        with self.condition:
            data = self.result
            mode = self.mode
            if data.get('received_at') is not None and 0 <= time.monotonic()-data['received_at'] <= .2:
                return data['debug_frame'].copy()
        return caption(fallback.copy(),'unknown',mode.upper()+' | Result pending')

    def _loop(self):
        recognizer = None
        last_epoch = last_received = last_number = None
        next_at = 0.
        try:
            recognizer = self.factory()
            with self.condition:
                self.initialized = True
            while True:
                with self.condition:
                    self.condition.wait_for(lambda:self.closed or self.pending is not None)
                    if self.closed:
                        return
                    remaining = next_at-time.monotonic()
                    if remaining > 0:
                        self.condition.wait(timeout=remaining)
                        continue
                    frame, number, received, epoch, mode = self.pending
                    self.pending = None
                now = time.monotonic()
                if received is None or not 0 <= now-received <= .2:
                    continue
                if epoch != last_epoch or last_received is None or received-last_received > .2:
                    reset_history(recognizer)
                if (epoch == last_epoch and last_received is not None
                        and (received < last_received or number <= last_number)):
                    continue
                started = time.monotonic()
                result = recognizer.process(frame)
                label, ready = fresh_decision(recognizer, result)
                caption(result['debug_frame'],label,
                        f'{mode.upper()}  Hand: {"yes" if result["hand_detected"] else "no"}  Sequence: {len(recognizer.hand_buffer)}/{recognizer.sequence_length}')
                ms = (time.monotonic()-started)*1000
                last_epoch, last_received, last_number = epoch, received, number
                data = dict(number=number, received_at=received, epoch=epoch, mode=mode,
                            decision_label=label, label=result['label'], ready=ready,
                            hand_detected=bool(result['hand_detected']),
                            sequence_frames=len(recognizer.hand_buffer),
                            hand_frames=int(sum(recognizer.hand_valid_buffer)),
                            sequence_length=recognizer.sequence_length,
                            knn_distance=float(result['distance']), inference_ms=round(ms, 1),
                            debug_frame=result['debug_frame'])
                with self.condition:
                    if epoch == self.epoch and mode == self.mode:
                        self.result = data
                        self.completed += 1
                        self.completed_at.append(time.monotonic())
                # A start-to-start rate cap, not an extra cooldown after work.
                next_at = started+self.delay
        except Exception as error:
            with self.condition:
                self.error = f'{type(error).__name__}: {error}'
                self.result = {}
        finally:
            if recognizer is not None:
                recognizer.close()

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = None
            self.condition.notify_all()
        if self.thread.is_alive():
            self.thread.join(timeout=3)
