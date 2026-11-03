"""Perspective-tolerant stripe grouping; observations only, never GPIO."""

import cv2
import numpy as np


def _perspective_band(mask, reference):
    """Find a wide stripe row without assuming parallel image-space axes."""
    height, width = mask.shape
    step = max(2, round(height / 200))
    top_row = round(.12 * height)
    scanned = (mask[top_row::step] > 0).astype(np.int8)
    transitions = np.diff(np.pad(scanned, ((0, 0), (1, 1))), axis=1)
    row_ids, starts = np.nonzero(transitions == 1)
    ends = np.nonzero(transitions == -1)[1]
    widths = ends - starts
    keep = (widths >= max(4, .025 * width)) & (widths <= .14 * width)
    row_ids, starts, ends = row_ids[keep], starts[keep], ends[keep]
    run_counts = np.bincount(row_ids, minlength=len(scanned))
    candidate_rows = np.flatnonzero((run_counts >= 4) & (run_counts <= 12))
    if len(candidate_rows) < 8:
        return None
    count, labels = cv2.connectedComponents(mask, 8)
    if count > 257:
        return None
    bands = {}
    best = None
    for row in candidate_rows:
        y = int(top_row + row * step)
        on_row = row_ids == row
        runs = np.column_stack((starts[on_row], ends[on_row]))
        # Contiguous groups only: never skip an inconvenient stripe or gap.
        for size in range(4, min(8, len(runs)) + 1):
            for offset in range(len(runs) - size + 1):
                group = runs[offset:offset + size]
                thickness = group[:, 1] - group[:, 0]
                gaps = group[1:, 0] - group[:-1, 1]
                centres = group.mean(axis=1)
                pitch = np.diff(centres)
                if (thickness.max() > 2.5 * thickness.min()
                        or gaps.min() < .35 * np.median(thickness)
                        or gaps.max() > 3 * np.median(thickness)
                        or pitch.max() > 1.8 * pitch.min()
                        or group[-1, 1] - group[0, 0] < .35 * width
                        or not group[0, 0] <= reference * width <= group[-1, 1]):
                    continue
                ids = tuple(int(labels[y, int(x)]) for x in centres)
                if 0 in ids or len(set(ids)) != size:
                    continue
                first, last, rows = bands.get(ids, (y, y - step, 0))
                if y - last > step:
                    first, rows = y, 0
                rows += 1
                bands[ids] = first, y, rows
                if rows < 8 or y - first < .035 * height:
                    continue
                score = (size, y - first)
                if best is None or score > best[0]:
                    best = score, ids, first, y
    if best is None:
        return None
    _, ids, top, bottom = best
    polygons = []
    for identity in ids:
        ys, xs = np.nonzero(labels[top:bottom + 1] == identity)
        points = np.column_stack((xs, ys + top)).astype(np.int32)
        polygons.append(cv2.convexHull(points).reshape(-1, 2).tolist())
    return dict(detected=True, stable=False, stop=False, stripes=len(ids),
                near=float(bottom / height), polygons=polygons, reliable=True,
                method='perspective_band')


def detect_crosswalk(result, reference=.5):
    mask = getattr(result, 'paint_support', None)
    empty = dict(detected=False, stable=False, stop=False, stripes=0, near=0., polygons=[], reliable=True)
    if mask is None:
        return empty
    height, width = mask.shape
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) > 256:
        return dict(empty, reliable=False, reason='too_many_components')
    perspective = _perspective_band(mask, reference)
    bars = []
    for contour in contours:
        area = cv2.contourArea(contour)
        rect = cv2.minAreaRect(contour)
        long, short = max(rect[1]), min(rect[1])
        if not (.0006*mask.size <= area <= .12*mask.size and short >= 3
                and 1.8 <= long/short <= 20 and area/(long*short) >= .65
                and rect[0][1] > .30*height):
            continue
        box = cv2.boxPoints(rect)
        sides = np.diff(np.vstack((box, box[:1])), axis=0)
        axis = max(sides, key=np.linalg.norm)/long
        bars.append(dict(centre=np.array(rect[0]), axis=axis, length=long,
                         thickness=short, box=box))
        if len(bars) > 64:
            return dict(empty, reliable=False, reason='too_many_stripes')
    best = []
    for anchor in bars:
        group = [anchor]
        for bar in bars:
            if bar is anchor:
                continue
            delta = bar['centre']-anchor['centre']
            axial = abs(np.dot(delta, anchor['axis']))
            lateral = abs(np.cross(delta, anchor['axis']))
            if (abs(np.dot(bar['axis'], anchor['axis'])) >= .95
                    and max(bar['length'], anchor['length'])/min(bar['length'], anchor['length']) <= 2.5
                    and axial <= .35*min(bar['length'], anchor['length'])
                    and lateral >= .8*max(bar['thickness'], anchor['thickness'])):
                group.append(bar)
        if len(group) < 3:
            continue
        normal = np.array([-anchor['axis'][1], anchor['axis'][0]])
        group.sort(key=lambda b: float(np.dot(b['centre'], normal)))
        offsets = np.array([np.dot(b['centre'], normal) for b in group])
        gaps = np.diff(offsets)
        thickness = np.median([b['thickness'] for b in group])
        box = np.vstack([b['box'] for b in group])
        if (np.max(gaps)/max(np.min(gaps), 1) <= 2.5
                and np.max(gaps) <= 5*thickness and np.ptp(box[:, 0]) >= .25*width
                and box[:, 0].min()-.03*width <= reference*width <= box[:, 0].max()+.03*width
                and len(group) > len(best)):
            best = group
    if perspective and len(best) <= perspective['stripes']:
        return perspective
    if not best:
        return empty
    box = np.vstack([b['box'] for b in best])
    return dict(detected=True, stable=False, stop=False, stripes=len(best),
                reliable=True,
                near=float(min(1, box[:, 1].max()/height)),
                polygons=[b['box'].round(1).tolist() for b in best])


def exclude_crosswalk_dashes(result, crossing):
    """Remove only observed stripe paint from lane candidates, not the road."""
    if not crossing.get('detected') or not crossing.get('reliable', False):
        return
    exclusion = np.zeros_like(result.dashes)
    for polygon in crossing['polygons']:
        cv2.fillPoly(exclusion, [np.asarray(polygon, np.int32)], 255)
    excluded = 0
    for mark in result.markings:
        if not mark['dash_candidate']:
            continue
        x, y = np.rint(mark['center']).astype(int)
        if 0 <= y < exclusion.shape[0] and 0 <= x < exclusion.shape[1] and exclusion[y, x]:
            mark['dash_candidate'] = False
            mark['crosswalk_stripe'] = True
            excluded += 1
    result.dashes[exclusion > 0] = 0
    result.metrics['crosswalk_excluded_dashes'] = excluded
    result.metrics['dash_candidate_count'] = sum(m['dash_candidate'] for m in result.markings)


class CrosswalkDetector:
    def __init__(self):
        self.reset()

    def reset(self):
        self.last_number = None
        self.first = self.last = None
        self.count = 0
        self.previous_polygons = []

    def observe(self, result, number, received_at, now, reference=.5, *, stop_on_confirmed=False):
        found = detect_crosswalk(result, reference)
        if (type(number) is not int or self.last_number is not None and number <= self.last_number or received_at is None
                or not 0 <= now-received_at <= .2):
            return found
        self.last_number = number
        if not found['detected']:
            self.first = self.last = None
            self.count = 0
            self.previous_polygons = []
            return found
        centroid = np.mean(np.vstack(found['polygons']), axis=0)
        previous = np.mean(np.vstack(self.previous_polygons), axis=0) if self.previous_polygons else None
        if (self.last is None or received_at-self.last > .2 or received_at <= self.last
                or previous is None or np.linalg.norm(centroid-previous) > .08*result.frame.shape[1]):
            self.first = received_at
            self.count = 0
        self.count += 1
        self.last = received_at
        self.previous_polygons = found['polygons']
        found['stable'] = self.count >= 3 and received_at-self.first >= .12
        found['stop'] = found['stable'] and (stop_on_confirmed or found['near'] >= .70)
        found['stop_on_confirmed'] = stop_on_confirmed
        return found
