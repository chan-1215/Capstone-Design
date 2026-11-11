"""Image-only OpenCV diagnostics; never reads simulator coordinates or controls it.

Unity pipes base64 PNG frames to stdin. Each response contains a JPEG overlay
and detected points. Also supports --image INPUT --output OUTPUT for inspection.
"""
import base64
import json
import sys
import argparse
from pathlib import Path
import cv2
import numpy as np

cv2.setNumThreads(1)


def analyze(image):
    h, w = image.shape[:2]
    smooth = cv2.GaussianBlur(image, (5, 5), 0)
    hsv = cv2.cvtColor(smooth, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (18, 75, 65), (42, 255, 255))
    white = cv2.inRange(hsv, (0, 0, 155), (179, 65, 255))
    # Ignore sky and the tiny near edge; no world-space lane/path information.
    top, bottom = int(h * .10), int(h * .94)
    for mask in (white, yellow):
        mask[:top] = 0
        mask[bottom:] = 0
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    overlay = image.copy()
    yellow_contours, _ = cv2.findContours(yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    yellow_contours = [c for c in yellow_contours if cv2.contourArea(c) >= 8]
    cv2.drawContours(overlay, yellow_contours, -1, (0, 230, 255), 2)
    white_contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates, accepted = [], []
    for c in white_contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        # Large white mat components and long crosswalk bars are not dashes.
        if area < 4 or area > w * h * .06 or bw > w * .28 or bh > h * .5:
            continue
        if x <= 1 or x + bw >= w - 1:
            continue
        m = cv2.moments(c)
        if not m['m00']:
            continue
        point = [int(m['m10'] / m['m00']), int(m['m01'] / m['m00'])]
        # A dash must have dark road around it; this rejects isolated white mat.
        border = hsv[max(0, y-3):min(h, y+bh+3), max(0, x-3):min(w, x+bw+3), 2]
        if np.mean(border < 145) < .18:
            continue
        candidates.append(point)
        accepted.append(c)
    cv2.drawContours(overlay, accepted, -1, (255, 230, 0), 1)
    # Follow one visible sequence from near to far, avoiding jumps to lane 2.
    path = []
    remaining = list(candidates)
    if remaining:
        near = [p for p in remaining if p[1] >= max(q[1] for q in remaining) - h * .15]
        current = min(near, key=lambda p: abs(p[0]-w/2))
        path.append(current)
        while True:
            def same_corridor(p):
                if not (3 < current[1]-p[1] < h*.4 and abs(p[0]-current[0]) < w*.32):
                    return False
                points = np.linspace(current, p, 40).astype(int)
                return np.count_nonzero(yellow[points[:, 1], points[:, 0]]) <= 1
            options = [p for p in remaining if same_corridor(p)]
            if not options:
                break
            current = min(options, key=lambda p: (p[1]-current[1])**2 + (p[0]-current[0])**2)
            path.append(current)
    for p in candidates:
        cv2.circle(overlay, tuple(p), 2, (255, 230, 0), -1)
    if len(path) >= 2:
        cv2.polylines(overlay, [np.array(path, np.int32)], False, (70, 255, 70), 2, cv2.LINE_AA)
    cv2.line(overlay, (w//2, top), (w//2, bottom), (160, 160, 160), 1)
    cv2.putText(overlay, f'OpenCV | dashes {len(candidates)} | path {len(path)}', (5, 14), cv2.FONT_HERSHEY_SIMPLEX, .34, (50, 255, 80), 1, cv2.LINE_AA)
    return overlay, {'dashes': len(candidates), 'boundaries': len(yellow_contours), 'pathPoints': len(path), 'path': path, 'valid': len(path) >= 2}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.image:
        image = cv2.imdecode(np.frombuffer(args.image.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        overlay, result = analyze(image)
        if args.output:
            args.output.write_bytes(cv2.imencode('.png', overlay)[1].tobytes())
        print(json.dumps(result))
        return
    print(json.dumps({'ready': True, 'opencv': cv2.__version__}), flush=True)
    for line in sys.stdin:
        try:
            image = cv2.imdecode(np.frombuffer(base64.b64decode(line), np.uint8), cv2.IMREAD_COLOR)
            overlay, result = analyze(image)
            result['jpeg'] = base64.b64encode(cv2.imencode('.jpg', overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]).decode('ascii')
            print(json.dumps(result, separators=(',', ':')), flush=True)
        except Exception as exc:
            print(json.dumps({'error': str(exc)}), flush=True)


if __name__ == '__main__':
    main()
