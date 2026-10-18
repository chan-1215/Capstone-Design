"""Conservative central-dash chain for the first, short P-control pilot."""

import threading

import cv2
import numpy as np


def _row_boundary_evidence(result, coefficients, points):
    """Corroborate a dash path with a separate yellow edge, not a replacement lane."""
    yellow, road = getattr(result, 'yellow', None), getattr(result, 'road', None)
    if yellow is None or road is None:
        return None
    height, width = road.shape
    _, labels = cv2.connectedComponents(yellow, 8)
    rows = np.linspace(max(.25 * height, points[:, 1].min()),
                       min(.90 * height, points[:, 1].max()), 9)
    if rows[-1] - rows[0] < .15 * height:
        return None
    edges = {-1:[], 1:[]}
    supported = 0
    for y in rows:
        x = float(np.polyval(coefficients, y / height) * width)
        if not 2 <= x < width - 2:
            continue
        iy, ix = round(y), round(x)
        supported += bool(np.mean(road[max(0,iy-2):iy+3, max(0,ix-2):ix+3] > 0) >= .8)
        columns = np.flatnonzero(np.any(yellow[max(0,iy-2):iy+3] > 0, axis=0))
        runs = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
        centres = []
        for run in runs:
            if len(run) < 2:
                continue
            component_ids = labels[max(0,iy-2):iy+3, run]
            component_ids = component_ids[component_ids > 0]
            if component_ids.size:
                centres.append((float(np.mean(run)), int(np.bincount(component_ids).argmax())))
        for side in edges:
            choices = [(v,label) for v,label in centres if .04 * width < side * (v - x) < .70 * width]
            if choices:
                edge_x, label = min(choices, key=lambda item:abs(item[0]-x))
                edges[side].append((edge_x, y, x, label))
    if supported < 8:
        return None
    for side, values in sorted(edges.items(), key=lambda item:len(item[1]), reverse=True):
        if len(values) < 7:
            continue
        edge = np.asarray(values)
        component = int(np.bincount(edge[:,3].astype(int)).argmax())
        edge = edge[edge[:,3] == component]
        if len(edge) < 7:
            continue
        fit = np.polyfit(edge[:,1] / height, edge[:,0] / width, 2)
        if np.max(np.abs(np.polyval(fit, edge[:,1]/height) - edge[:,0]/width)) > .025:
            continue
        edge_slope = np.polyfit(edge[:,1] / height, edge[:,0] / width, 1)[0]
        path_slope = np.polyfit(edge[:,1] / height, edge[:,2] / width, 1)[0]
        # A pronounced turn must be independently visible in the yellow edge.
        if abs(path_slope) > .08:
            ratio = edge_slope / path_slope
            if not .25 <= ratio <= 4:
                continue
        elif abs(edge_slope) > .8:
            continue
        return dict(side='left' if side < 0 else 'right', samples=len(edge),
                    points=edge[:,:2].round(1).tolist(), method='image_rows')
    return None


def _normal_boundary_evidence(result, coefficients, points, checks):
    """Check a steep path across its normals when same-row edges leave view."""
    yellow, road = getattr(result, 'yellow', None), getattr(result, 'road', None)
    if yellow is None or road is None:
        checks['normal_reason'] = 'missing_masks'
        return None
    height, width = road.shape
    rows = np.linspace(points[:,1].min(), points[:,1].max(), 9)
    centres = np.column_stack((np.polyval(coefficients, rows/height)*width, rows))
    chord = centres[-1] - centres[0]
    length = np.linalg.norm(chord)
    if length < .18*height or abs(chord[0]) < abs(chord[1]):
        checks['normal_reason'] = 'not_observed_steep_path'
        return None
    direction = chord/length
    _, labels = cv2.connectedComponents(yellow, 8)
    distances = np.arange(round(.04*width), round(.70*width)+1)
    edges = {-1:[], 1:[]}
    supported = 0
    for index, centre in enumerate(centres):
        x, y = np.rint(centre).astype(int)
        if not 2 <= x < width-2 or not 2 <= y < height-2:
            continue
        if np.mean(road[y-2:y+3,x-2:x+3] > 0) < .8:
            continue
        supported += 1
        slope = float(np.polyval(np.polyder(coefficients), rows[index]/height))*width/height
        normal = np.array([1., -slope])
        normal /= np.linalg.norm(normal)
        for side in edges:
            ray = np.rint(centre + side*distances[:,None]*normal).astype(int)
            inside = ((ray[:,0] >= 0) & (ray[:,0] < width) &
                      (ray[:,1] >= 0) & (ray[:,1] < height))
            hits = np.flatnonzero(inside)
            hits = hits[labels[ray[hits,1],ray[hits,0]] > 0]
            if not len(hits):
                continue
            run = np.split(hits, np.flatnonzero(np.diff(hits) > 1)+1)[0]
            if len(run) < 2:
                continue
            hit = run[len(run)//2]
            edge = ray[hit].astype(float)
            corridor = np.rint(centre + np.linspace(.08,.8,9)[:,None]*(edge-centre)).astype(int)
            if np.mean(road[corridor[:,1],corridor[:,0]] > 0) < .8:
                continue
            edges[side].append((index, *edge, int(labels[ray[hit,1],ray[hit,0]]), distances[hit]))
    checks.update(normal_road_samples=supported,
                  normal_edge_samples={str(side):len(values) for side,values in edges.items()},
                  normal_reason='insufficient_road_or_edge_coverage')
    for side, values in sorted(edges.items(), key=lambda item:len(item[1]), reverse=True):
        if len(values) < 8:
            continue
        edge = np.asarray(values)
        component = int(np.bincount(edge[:,3].astype(int)).argmax())
        edge = edge[edge[:,3] == component]
        if len(edge) < 7:
            checks['normal_reason'] = 'fragmented_boundary'
            continue
        fit = np.polyfit(edge[:,0]/8, edge[:,4]/width, 2)
        if np.max(np.abs(np.polyval(fit,edge[:,0]/8)-edge[:,4]/width)) > .025:
            checks['normal_reason'] = 'inconsistent_edge_gap'
            continue
        if np.max(edge[:,4])/np.min(edge[:,4]) > 2:
            checks['normal_reason'] = 'excessive_edge_gap_variation'
            continue
        edge_chord = edge[-1,1:3] - edge[0,1:3]
        projection = float(np.dot(edge_chord,direction))
        if (projection < .5*length or projection > 2.5*length or
                projection/max(np.linalg.norm(edge_chord),1) < .85):
            checks['normal_reason'] = 'edge_direction_mismatch'
            continue
        checks['normal_reason'] = 'supported'
        return dict(side='left' if side < 0 else 'right', samples=len(edge),
                    points=edge[:,1:3].round(1).tolist(), method='path_normals')
    return None


def boundary_evidence(result, coefficients, points, checks=None):
    checks = {} if checks is None else checks
    boundary = _row_boundary_evidence(result, coefficients, points)
    checks['row_boundary_confirmed'] = boundary is not None
    return boundary or _normal_boundary_evidence(result, coefficients, points, checks)


def dash_axes(result):
    mask = getattr(result, 'dashes', None)
    if mask is None:
        return []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rectangles = [cv2.minAreaRect(c) for c in contours if cv2.contourArea(c) >= 8]
    axes = []
    for rect in rectangles:
        box = cv2.boxPoints(rect)
        sides = np.diff(np.vstack((box,box[:1])), axis=0)
        axis = max(sides, key=np.linalg.norm)
        axis = axis / max(np.linalg.norm(axis), 1)
        axes.append((np.asarray(rect[0]), axis))
    return axes


def nearest_axis(axes, point):
    if not axes:
        return None
    centre, axis = min(axes, key=lambda item:np.linalg.norm(item[0]-point))
    return axis if np.linalg.norm(centre-point) <= 5 else None


def aligned_dashes(axes, points, minimum=.7):
    direction = points[-1] - points[0]
    direction /= max(np.linalg.norm(direction), 1)
    for point in points:
        axis = nearest_axis(axes, point)
        if axis is None or abs(np.dot(axis, direction)) < minimum:
            return False
    return True


def near_road_fraction(result, reference):
    road = getattr(result, 'road', None)
    if road is None:
        return 0.0
    height, width = road.shape
    centre = round(reference*width)
    patch = road[round(.82*height):round(.94*height),
                 max(0,centre-round(.08*width)):min(width,centre+round(.08*width))]
    return float(np.mean(patch > 0)) if patch.size else 0.0


def corroborated_local_curve(result, points, axes, global_error, reference, checks):
    """Use only the nearest four points after a bounded global-fit failure."""
    height, width = result.frame.shape[:2]
    checks['local_curve_reason'] = 'outside_bounded_exception'
    if len(points) < 5 or global_error > .065:
        return None
    local = points[:4]
    if (np.ptp(local[:,1]) < .30*height or
            not local[:,1].min() <= .55*height <= local[:,1].max()):
        checks['local_curve_reason'] = 'insufficient_near_support'
        return None
    coefficients = np.polyfit(local[:,1]/height,local[:,0]/width,2)
    error = float(np.max(np.abs(np.polyval(coefficients,local[:,1]/height)-local[:,0]/width)))
    checks['local_fit_error_px'] = round(error*width,2)
    if error > .02:
        checks['local_curve_reason'] = 'inconsistent_near_points'
        return None
    slopes = np.polyval(np.polyder(coefficients),local[:,1]/height)*width/height
    tangents = np.degrees(np.arctan(slopes))
    chord = local[-1]-local[0]
    heading = abs(float(np.degrees(np.arctan2(chord[0],-chord[1]))))
    if heading < 20 or np.ptp(tangents) < 15:
        checks['local_curve_reason'] = 'not_a_sharp_curve'
        return None
    for point, slope in zip(local,slopes):
        axis = nearest_axis(axes,point)
        tangent = np.array([slope,1.])
        tangent /= np.linalg.norm(tangent)
        if axis is None or abs(np.dot(axis,tangent)) < .85:
            checks['local_curve_reason'] = 'paint_tangent_mismatch'
            return None
    if near_road_fraction(result,reference) < .90:
        checks['local_curve_reason'] = 'near_road_unconfirmed'
        return None
    boundary = boundary_evidence(result,coefficients,local,checks)
    if boundary is None:
        checks['local_curve_reason'] = 'boundary_unconfirmed'
        return None
    checks.update(local_curve_reason='supported', omitted_far_points=len(points)-4,
                  global_fit_limit_px=round(.065*width,2))
    return local, coefficients, boundary


class LanePath:
    def __init__(self):
        self.lock = threading.RLock()
        self.reference = None
        self.previous = None
        self.previous_y = .55
        self.previous_heading = None
        self.reference_heading = 0.0
        self.signature = None

    def reset(self):
        with self.lock:
            self.reference = self.previous = None
            self.previous_heading = None
            self.previous_y = .55
            self.reference_heading = 0.0

    def calibrate(self, prediction):
        with self.lock:
            if not prediction.get('valid'):
                raise ValueError('No valid central path')
            if abs(prediction.get('heading_degrees', 0)) > 12:
                raise ValueError('Set the central reference on a straight section, not in a sharp curve')
            self.reference = prediction['target_normalized']
            self.previous = self.reference
            self.previous_y = prediction.get('target_y_normalized', .55)
            self.reference_heading = prediction.get('heading_degrees', 0.0)
            return self.reference

    def predict(self, result, signature=None):
        with self.lock:
            if self.signature != signature:
                self.reset()
                self.signature = signature
            height, width = result.frame.shape[:2]
            reference = self.reference if self.reference is not None else .5
            invalid = dict(valid=False, reason='insufficient_dashes', points=[], path=[],
                           reference_set=self.reference is not None,
                           reference_normalized=reference, normalized_error=None,
                           target_normalized=None, target=None, source=None,
                           heading_degrees=None, forward_direction='unknown', boundary_support=None)
            candidates = [m['center'] for m in result.markings if m['dash_candidate']
                          and .01 * width < m['center'][0] < .99 * width
                          and .20 * height < m['center'][1] < .96 * height]
            invalid['candidate_count'] = len(candidates)
            if len(candidates) < 2:
                self.previous = None
                self.previous_heading = None
                return invalid
            bands = {}
            axes = dash_axes(result)
            for x, y in candidates:
                bands.setdefault(int(y / (height * .12)), []).append((x, y))
            chain = []
            for band in sorted(bands, reverse=True):
                pending = list(bands[band])
                while pending:
                    forward_slope = 0.0
                    if not chain:
                        anchor_x = (self.previous if self.previous is not None else reference) * width
                        anchor_y = 0.0
                    elif len(chain) == 1:
                        anchor_x, anchor_y = chain[-1]
                        axis = nearest_axis(axes, chain[-1])
                        if axis is not None and abs(axis[1]) >= .2:
                            forward_slope = float(np.clip(-axis[0]/axis[1], -3, 3))
                    else:
                        a, b = chain[-2:]
                        forward_slope = float(np.clip((b[0] - a[0]) / max(a[1] - b[1], 1), -3, 3))
                        anchor_x, anchor_y = b

                    def residual(point):
                        return point[0] - (anchor_x + forward_slope * (anchor_y - point[1]))

                    ranked = sorted(pending, key=lambda p: abs(residual(p)))
                    gate = .48 if not chain and getattr(result, 'yellow', None) is not None else .22
                    if abs(residual(ranked[0])) > width * gate:
                        break
                    best = residual(ranked[0])
                    if len(ranked) > 1:
                        other = residual(ranked[1])
                        if abs(abs(best)-abs(other)) < width*.025 and abs(best-other) > width*.05:
                            return {**invalid, 'reason': 'ambiguous_dash_chain'}
                    point = ranked[0]
                    if not chain or chain[-1][1] - point[1] >= height*.035:
                        chain.append(point)
                    # Recompute the local slope after each accepted observation,
                    # including successive dashes inside the same coarse band.
                    pending = [p for p in pending if p[1] < point[1] - height*.035]
            if len(chain) < 2:
                self.previous = None
                self.previous_heading = None
                return {**invalid, 'reason':'dash_association_failed', 'points':[list(p) for p in chain]}
            points = np.asarray(chain, dtype=float)
            span = float(np.ptp(points[:,1]) / height)
            # Oblique paint can have adequate chord length but compressed y-span.
            # Only admit that case below with stronger current-frame evidence.
            short_span = span < .18
            chord = points[-1] - points[0]
            short_geometry = (len(points) == 2 and span >= .15 and
                              np.linalg.norm(chord) >= .20*height and
                              abs(chord[0]) >= np.tan(np.radians(30))*abs(chord[1]) and
                              points[:,1].min() <= .55*height <= points[:,1].max())
            if short_span and not short_geometry:
                return {**invalid, 'reason':'insufficient_dash_span', 'points':points.tolist()}
            degree = 2 if len(points) >= 4 else 1
            coefficients = np.polyfit(points[:, 1] / height, points[:, 0] / width, degree)
            residual = np.abs(np.polyval(coefficients, points[:, 1] / height) - points[:, 0] / width)
            global_error = float(np.max(residual))
            boundary_checks = dict(global_fit_error_px=round(global_error*width,2),
                                   global_fit_limit_px=round(.04*width,2), fit_mode='global')
            local_curve = False
            if global_error > .04:
                fallback = corroborated_local_curve(result,points,axes,global_error,reference,boundary_checks)
                if fallback is None:
                    return {**invalid, 'reason':'inconsistent_dash_chain', 'points':points.tolist(),
                            'checks':boundary_checks}
                points, coefficients, boundary = fallback
                span = float(np.ptp(points[:,1])/height)
                boundary_checks['fit_mode'] = 'local_curve'
                local_curve = True
            else:
                boundary = boundary_evidence(result, coefficients, points, boundary_checks)
            if short_span:
                supported = bool(boundary and boundary['samples'] >= 8 and
                                 aligned_dashes(axes, points, minimum=.85) and
                                 near_road_fraction(result, reference) >= .90)
                boundary_checks['short_span_supported'] = supported
                boundary_checks['observed_span_px'] = round(span*height, 2)
                boundary_checks['observed_chord_px'] = round(float(np.linalg.norm(chord)), 2)
                if not supported:
                    return {**invalid, 'reason':'insufficient_dash_span', 'points':points.tolist(),
                            'checks':boundary_checks}
            complemented = local_curve or len(points) == 2 or span < .22
            # Curved local paint was checked against each fitted tangent above;
            # one end-to-end chord is not its local direction at every point.
            aligned = True if local_curve else aligned_dashes(axes, points) if complemented else False
            if complemented and (boundary is None or not aligned):
                return {**invalid, 'reason':'two_dashes_uncorroborated', 'points':points.tolist(),
                        'checks':dict(paint_aligned=aligned, boundary_confirmed=boundary is not None,
                                      **boundary_checks)}
            target_y = .55
            observed_low, observed_high = points[:,1].min()/height, points[:,1].max()/height
            adaptive_target = False
            if not observed_low - .08 <= target_y <= observed_high + .08:
                proposed_y = float(np.clip(target_y, observed_low, observed_high))
                chord = points[-1] - points[0]
                steep = abs(chord[0]) >= abs(chord[1])
                if not (boundary and steep and .40 <= proposed_y <= .70
                        and aligned_dashes(axes, points)):
                    return {**invalid, 'reason':'target_outside_observed_path', 'points':points.tolist(),
                            'checks':dict(observed_y=[observed_low,observed_high],
                                          boundary_confirmed=boundary is not None, **boundary_checks)}
                target_y, adaptive_target = proposed_y, True
            target = float(np.polyval(coefficients, target_y))
            if not .01 < target < .99:
                return {**invalid, 'reason': 'target_outside_image'}
            previous = self.previous
            if previous is not None:
                # Compare/smooth at one image depth even when look-ahead changes.
                previous += float(np.polyval(coefficients,target_y)-np.polyval(coefficients,self.previous_y))
            if previous is not None and abs(target - previous) > .15:
                self.previous = None
                return {**invalid, 'reason': 'path_jump'}
            smoothed = target if previous is None else .45 * target + .55 * previous
            if not .01 < smoothed < .99:
                self.previous = None
                return {**invalid, 'reason':'target_outside_image'}
            self.previous = smoothed
            self.previous_y = target_y
            far_y = float(np.clip(.30, observed_low, observed_high))
            near_y = float(np.clip(.65, observed_low, observed_high))
            if near_y - far_y < .10:
                far_y, near_y = observed_low, observed_high
            forward_dx = float(np.polyval(coefficients, far_y) - np.polyval(coefficients, near_y)) * width
            heading = float(np.degrees(np.arctan2(forward_dx, max((near_y-far_y)*height, 1))))
            heading = heading if self.previous_heading is None else .45 * heading + .55 * self.previous_heading
            self.previous_heading = heading
            heading_error = heading - self.reference_heading
            direction = 'right' if heading_error > 8 else 'left' if heading_error < -8 else 'straight'
            target_reference = reference - np.tan(np.radians(self.reference_heading))*(target_y-.55)*height/width
            error = round((smoothed - target_reference) * 2, 5)
            near_road = near_road_fraction(result,reference)
            # Large look-ahead error can be a bend, not lateral departure. Only
            # permit it when fresh paint geometry AND the near road corroborate it.
            curve_corridor = bool(boundary and abs(heading_error) > 8 and near_road >= .85
                                  and abs(error) <= 1.05)
            rows = np.linspace(points[:, 1].min(), points[:, 1].max(), 20)
            path = [[round(float(np.polyval(coefficients, y / height) * width), 1), round(float(y), 1)] for y in rows]
            return dict(valid=True, reason='local_curve_corroborated' if local_curve else
                        'dash_boundary_corroborated' if complemented else 'central_dash_chain',
                        points=points.tolist(), path=path,
                        target=[round(smoothed * width, 1), round(target_y * height, 1)],
                        target_y_normalized=target_y, adaptive_target=adaptive_target,
                        reference_at_target_normalized=float(target_reference),
                        checks=boundary_checks,
                        target_normalized=smoothed, reference_normalized=reference,
                        reference_set=self.reference is not None,
                        normalized_error=error,
                        heading_degrees=round(heading, 2), forward_direction=direction,
                        heading_error_degrees=round(heading_error, 2),
                        reference_heading_degrees=round(self.reference_heading, 2),
                        curve_corridor_supported=curve_corridor, near_road_fraction=round(near_road, 3),
                        source='dash_boundary' if complemented else 'dash_chain',
                        boundary_support=boundary,
                        speed_scale=.8 if complemented else .85 if abs(heading) > 8 else 1)


def draw_path(image, prediction):
    if not prediction.get('valid'):
        return
    path = np.asarray(prediction['path'], dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(image, [path], False, (80, 230, 80), 2, cv2.LINE_AA)
    for x, y in (prediction.get('boundary_support') or {}).get('points', []):
        cv2.circle(image, (round(x),round(y)), 3, (0,165,255), -1)
    target = tuple(round(v) for v in prediction['target'])
    cv2.drawMarker(image, target, (255, 160, 40), cv2.MARKER_CROSS, 16, 2)
    reference_x = round(prediction.get('reference_at_target_normalized',
                                      prediction['reference_normalized']) * image.shape[1])
    cv2.line(image, (reference_x, round(image.shape[0] * .48)),
             (reference_x, image.shape[0] - 1), (240, 150, 70), 1)
