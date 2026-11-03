"""Brief, explicitly opted-in turn continuation with current corridor evidence."""

import math

import numpy as np

from lane_path import boundary_evidence, near_road_fraction, observed_polyline_boundary


MISSING_DASH_REASONS = frozenset(('insufficient_dashes', 'insufficient_dash_span',
                                'dash_association_failed', 'single_dash_uncorroborated'))


def corridor_observation(result, previous, path):
    if (path.get('valid') or path.get('reason') not in MISSING_DASH_REASONS
            or not path.get('reference_set') or not previous
            or previous.get('source') == 'single_dash_boundary'):
        return {'supported': False}
    points = np.asarray(previous.get('path', []), dtype=float)
    if len(points) < 3 or abs(previous.get('heading_error_degrees', 0)) < 8:
        return {'supported': False}
    height, width = result.frame.shape[:2]
    prior_edge = previous.get('boundary_support') or {}
    if prior_edge.get('method') == 'paint_polyline_normals':
        edge = observed_polyline_boundary(result,np.asarray(previous.get('points',[]),float))
    else:
        coefficients = np.polyfit(points[:, 1]/height, points[:, 0]/width, 2)
        edge = boundary_evidence(result, coefficients, points)
    road = near_road_fraction(result, previous['reference_normalized'])
    supported = bool(edge and edge['samples'] >= 8 and edge['side'] == prior_edge.get('side')
                     and edge['method'] == prior_edge.get('method') and road >= .90)
    if supported:
        old = np.asarray(prior_edge.get('points', []), dtype=float)
        new = np.asarray(edge['points'], dtype=float)
        # Reject large edge displacement rather than attaching a different lane.
        supported = bool(len(old) >= 7 and
                         np.linalg.norm(np.median(old, axis=0)-np.median(new, axis=0)) <= .06*width)
    return dict(supported=supported, boundary=edge, near_road_fraction=road)


class TurnRecovery:
    def __init__(self):
        self.reset()

    def reset(self):
        self.last_good = None
        self.anchor = None
        self.used = False
        self.ready = False
        self.good_since = None
        self.good_count = 0
        self.last_source = None
        self.active = False

    @staticmethod
    def source_time(frame):
        value = frame.get('received_at')
        return value if type(value) in (int, float) and math.isfinite(value) else None

    def observe_valid(self, frame, now, angle, speed, direction):
        self.active = False
        source = frame.get('source_number')
        received = self.source_time(frame)
        if (type(source) is not int or received is None
                or self.last_source is not None and source <= self.last_source):
            return
        self.last_source = source
        full = frame['path'].get('source') != 'single_dash_boundary'
        if not full:
            self.good_since = None
            self.good_count = 0
            return
        if self.good_since is None or now-self.good_since[1] > .2:
            self.good_since = (now, now)
            self.good_count = 0
        self.good_count += 1
        self.good_since = (self.good_since[0], now)
        if self.good_count >= 3 and now-self.good_since[0] >= .30:
            self.ready = True
            self.used = False
        self.last_good = dict(at=received, angle=angle, speed=speed, direction=direction)

    def continue_turn(self, frame, now):
        self.good_since = None
        self.good_count = 0
        received = self.source_time(frame)
        path = frame['path']
        if (not self.ready or not self.last_good or not path.get('reference_set')
                or path.get('reason') not in MISSING_DASH_REASONS
                or received is None or not 0 <= now-received <= .2
                or not frame.get('continuation', {}).get('supported')):
            return None
        if not self.used:
            self.anchor = dict(self.last_good)
            self.used = True
        anchor = self.anchor
        if not anchor or not 0 <= now-anchor['at'] < .20:
            return None
        if self.last_good['direction'] != anchor['direction']:
            return None
        command = dict(anchor, angle=self.last_good['angle'], speed=min(anchor['speed'], self.last_good['speed']))
        sign = -1 if anchor['direction'] == 'left' else 1 if anchor['direction'] == 'right' else 0
        if not sign or sign*command['angle'] < 6:
            return None
        source = frame.get('source_number')
        if type(source) is not int or self.last_source is not None and source <= self.last_source:
            # Duplicate ticks may retain an already active bounded command, but
            # cannot enter recovery, refresh its budget or generate a new write.
            return dict(**command, elapsed=now-anchor['at'], duplicate=True) if self.active else None
        self.last_source = source
        self.active = True
        return dict(**command, elapsed=now-anchor['at'], duplicate=False)
