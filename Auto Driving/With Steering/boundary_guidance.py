"""Current-frame white targets with independently observed yellow direction."""

import math

import numpy as np

from lane_path import boundary_evidence, dash_axes, nearest_axis, near_road_fraction


FALLBACK_REASONS = frozenset(('insufficient_dashes', 'insufficient_dash_span',
                              'target_outside_observed_path', 'single_dash_uncorroborated'))


def boundary_direction(result, boundary, white_heading):
    """Edge samples are ordered far-to-near by the existing corridor validators."""
    if not boundary or boundary.get('samples', 0) < 8:
        return None
    points = np.asarray(boundary.get('points', []), float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 8 or not np.isfinite(points).all():
        return None
    height, width = result.frame.shape[:2]
    forward = points[0] - points[-1]
    length = np.linalg.norm(forward)
    if length < .18*height or forward[1] >= -.04*height:
        return None
    white = np.array([math.sin(math.radians(white_heading)), -math.cos(math.radians(white_heading))])
    if np.dot(forward/length, white) < .8:
        return None
    heading = math.degrees(math.atan2(forward[0], -forward[1]))
    if abs(heading-white_heading) > 35:
        return None
    if ((heading*white_heading < 0 and min(abs(heading), abs(white_heading)) >= 8)
            or abs(heading) < 5 and abs(white_heading) >= 12):
        return None
    # Classify only when road is actually observed on both probe sides.
    right = np.array([-white[1], white[0]])
    side = 1 if boundary['side'] == 'right' else -1
    fractions = []
    for sign in (-1, 1):
        probes = np.rint(points[:, None, :] + sign*side*right *
                         np.linspace(.04*width, .08*width, 5)[None, :, None]).astype(int)
        inside = ((probes[:, :, 0] >= 0) & (probes[:, :, 0] < width) &
                  (probes[:, :, 1] >= 0) & (probes[:, :, 1] < height))
        hits=probes[inside]
        fractions.append(float(np.mean(result.road[hits[:, 1], hits[:, 0]] > 0))
                         if np.count_nonzero(inside) >= 30 else None)
    inner, outer = fractions
    kind = ('divider' if inner is not None and outer is not None and min(inner, outer) >= .9
            else 'outer' if inner is not None and outer is not None and inner >= .9 and outer <= .2
            else 'unknown')
    return dict(heading_degrees=heading, kind=kind)


def combine_direction(result, prediction):
    if not prediction.get('valid'):
        return prediction
    white_heading = prediction['heading_degrees']
    reference_heading = prediction.get('reference_heading_degrees', 0.)
    if abs(white_heading-reference_heading) < 12:
        # Straight edges converge in perspective even when the centre is straight.
        # Raw edge slope alone must never initiate a turn.
        return dict(prediction, guidance_mode='white_path', boundary_guidance_enabled=True)
    evidence = boundary_direction(result, prediction.get('boundary_support'), white_heading)
    if evidence is None:
        return dict(prediction, guidance_mode='white_path', boundary_guidance_enabled=True)
    heading = .65*white_heading + .35*evidence['heading_degrees']
    white_error = white_heading-reference_heading
    edge_error = evidence['heading_degrees']-reference_heading
    agreement = bool(white_error*edge_error > 0 and min(abs(white_error), abs(edge_error)) >= 12)
    return dict(prediction, guidance_mode='white_yellow', boundary_guidance_enabled=True,
                guidance_heading_error_degrees=round(heading-reference_heading, 2),
                boundary_heading_degrees=round(evidence['heading_degrees'], 2),
                boundary_kind=evidence['kind'], boundary_turn_agreement=agreement)


def guide_path(result, prediction, reference_heading=0.):
    """Never replace ambiguous/jumping paths, or invent a path without visible paint."""
    if prediction.get('valid'):
        return combine_direction(result, prediction)
    if (prediction.get('reason') not in FALLBACK_REASONS or not prediction.get('reference_set')
            or near_road_fraction(result, prediction['reference_normalized'], allow_divider=True) < .9):
        return prediction
    height, width = result.frame.shape[:2]
    axes = dash_axes(result)
    choices = []
    selected = np.asarray(prediction.get('points', []), float)
    for mark in result.markings:
        centre = np.asarray(mark['center'], float)
        length = mark.get('length_px', 0)
        if (not mark.get('dash_candidate') or mark.get('side_clipped') or length < .20*height
                or mark.get('fill_ratio', 0) < .75 or mark.get('aspect_ratio', 0) < 2.5
                or mark.get('thickness_px', 0) < .02*height):
            continue
        if len(selected) >= 2 and np.min(np.linalg.norm(selected-centre, axis=1)) > 5:
            continue
        axis = nearest_axis(axes, centre)
        if axis is None:
            continue
        ends = np.array([centre-axis*length/2, centre+axis*length/2])
        ends = ends[np.argsort(ends[:, 1])]
        if (np.ptp(ends[:, 1]) < .08*height or
                np.any((ends[:, 0] <= .01*width) | (ends[:, 0] >= .99*width)) or
                np.any((ends[:, 1] <= .20*height) | (ends[:, 1] >= .96*height))):
            continue
        fit = np.polyfit(ends[:, 1]/height, ends[:, 0]/width, 1)
        checks = {}
        edge = boundary_evidence(result, fit, ends, checks, allow_shallow=True, minimum_samples=8)
        if not edge or edge['samples'] < 8:
            continue
        heading = math.degrees(math.atan2(ends[0, 0]-ends[1, 0], ends[1, 1]-ends[0, 1]))
        if abs(heading-reference_heading) < 12:
            continue
        target = None
        # A near paint target is allowed only in this opt-in, edge-guided mode.
        # Every selected pixel is current observed paint, not a fitted extension.
        for y in range(max(round(.40*height), math.ceil(ends[0, 1])+2),
                       min(round(.90*height), math.floor(ends[1, 1])-2)+1):
            x = round(float(np.polyval(fit, y/height)*width))
            if 2 <= x < width-2 and np.mean(result.dashes[y-2:y+3, x-2:x+3] > 0) >= .8:
                target = [float(x), float(y)]
                break
        if target is None:
            continue
        reference = prediction['reference_normalized']
        target_reference = reference-math.tan(math.radians(reference_heading))*(target[1]/height-.55)*height/width
        error = 2*(target[0]/width-target_reference)
        if abs(error) > 1.05:
            continue
        candidate = dict(valid=True, reason='boundary_guided_curve',
            reference_set=True, reference_normalized=reference,
            reference_heading_degrees=reference_heading, reference_at_target_normalized=target_reference,
            target=target, target_normalized=target[0]/width, target_y_normalized=target[1]/height,
            adaptive_target=True, normalized_error=round(error, 5),
            heading_degrees=round(heading, 2), heading_error_degrees=round(heading-reference_heading, 2),
            forward_direction='left' if heading < reference_heading else 'right',
            points=ends[::-1].round(1).tolist(), path=ends.round(1).tolist(),
            boundary_support=edge, checks=dict(checks, target_on_observed_paint=True),
            curve_corridor_supported=True, lap_corridor_supported=True, near_road_fraction=1.,
            observed_dash_count=1, candidate_count=prediction.get('candidate_count', 0),
            source='single_dash_boundary', speed_scale=.8)
        fused = combine_direction(result, candidate)
        if fused.get('guidance_mode') != 'white_yellow':
            continue
        fused['guidance_mode'] = 'boundary_curve'
        fused['near_road_fraction'] = round(near_road_fraction(result, reference, allow_divider=True), 3)
        score = abs(target[0]/width-reference) + .1*target[1]/height
        choices.append((score, fused))
    if not choices:
        return dict(prediction, guidance_failure='no_current_joint_corridor')
    choices.sort(key=lambda item: item[0])
    if len(choices) > 1 and choices[1][0]-choices[0][0] < .03:
        first, second = choices[0][1], choices[1][1]
        if (abs(first['target_normalized']-second['target_normalized']) > .10 or
                abs(first['heading_degrees']-second['heading_degrees']) > 15):
            return dict(prediction, guidance_failure='ambiguous_joint_corridor')
    return choices[0][1]
