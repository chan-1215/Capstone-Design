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


def _normal_boundary_evidence(result, coefficients, points, checks, allow_shallow=False):
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
    if length < .18*height or not allow_shallow and abs(chord[0]) < abs(chord[1]):
        checks['normal_reason'] = 'not_observed_steep_path'
        return None
    slopes = np.polyval(np.polyder(coefficients),rows/height)*width/height
    normals = np.column_stack((np.ones(len(rows)),-slopes))
    normals /= np.linalg.norm(normals,axis=1)[:,None]
    return _normal_corridor_evidence(result,centres,normals,checks)


def _normal_corridor_evidence(result, centres, normals, checks, bridge_small_gaps=False):
    """Verify a current connected edge along independently supplied path normals."""
    yellow,road=result.yellow,result.road
    height,width=road.shape
    chord=centres[-1]-centres[0]
    length=np.linalg.norm(chord)
    if length < .18*height:
        checks['normal_reason']='insufficient_chord'
        return None
    direction = chord/length
    # Closing can link a few-pixel print/crease break for component identity;
    # every ray hit below must still be an actually observed yellow pixel.
    components = (cv2.morphologyEx(yellow,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
                  if bridge_small_gaps else yellow)
    _, labels = cv2.connectedComponents(components, 8)
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
        normal = normals[index]
        for side in edges:
            ray = np.rint(centre + side*distances[:,None]*normal).astype(int)
            inside = ((ray[:,0] >= 0) & (ray[:,0] < width) &
                      (ray[:,1] >= 0) & (ray[:,1] < height))
            hits = np.flatnonzero(inside)
            hits = hits[yellow[ray[hits,1],ray[hits,0]] > 0]
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
                  normal_edge_components={str(side):int(np.sum(np.bincount(
                      np.asarray(values)[:,3].astype(int))>=2)) if values else 0
                      for side,values in edges.items()},
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


def corroborated_observed_curve(result, points, axes, reference, checks, allow_divider=False):
    """Validate an observed polyline; never invent a curve through rejected pixels."""
    checks['polyline_reason']='insufficient_observations'
    if len(points) < 3 or len(points) > 10:
        return None
    height,width=result.frame.shape[:2]
    ordered=points[::-1].copy()
    segments=np.diff(ordered,axis=0)
    lengths=np.linalg.norm(segments,axis=1)
    if np.min(lengths) < .035*height or np.sum(lengths) < .30*height:
        return None
    directions=segments/lengths[:,None]
    angles=np.degrees(np.arccos(np.clip(np.sum(directions[1:]*directions[:-1],axis=1),-1,1)))
    if np.max(angles) > 55:
        checks['polyline_reason']='inconsistent_turns'
        return None
    chord=ordered[-1]-ordered[0]
    if abs(np.degrees(np.arctan2(chord[0],chord[1]))) < 20:
        checks['polyline_reason']='not_a_curve'
        return None
    tangents=np.vstack((directions[0],directions[:-1]+directions[1:],directions[-1]))
    tangents/=np.linalg.norm(tangents,axis=1)[:,None]
    for point,tangent in zip(ordered,tangents):
        axis=nearest_axis(axes,point)
        if axis is None or abs(np.dot(axis,tangent)) < .85:
            checks['polyline_reason']='paint_tangent_mismatch'
            return None
    if near_road_fraction(result,reference,allow_divider=allow_divider) < .90:
        checks['polyline_reason']='near_road_unconfirmed'
        return None
    boundary=observed_polyline_boundary(result,points,checks)
    if boundary is None:
        checks['polyline_reason']='boundary_unconfirmed'
        return None
    checks.update(polyline_reason='supported',observed_arc_px=round(float(np.sum(lengths)),2))
    return boundary


def observed_polyline_boundary(result, points, checks=None):
    """Current edge support for observed points, also used by bounded recovery."""
    checks={} if checks is None else checks
    if len(points)<3:
        return None
    ordered=points[::-1]
    segments=np.diff(ordered,axis=0)
    lengths=np.linalg.norm(segments,axis=1)
    if np.any(lengths<1):
        return None
    directions=segments/lengths[:,None]
    tangents=np.vstack((directions[0],directions[:-1]+directions[1:],directions[-1]))
    norms=np.linalg.norm(tangents,axis=1)
    if np.any(norms<.1):
        return None
    tangents/=norms[:,None]
    cumulative=np.r_[0.,np.cumsum(lengths)]
    distance=np.linspace(0,cumulative[-1],9)
    centres=np.column_stack((np.interp(distance,cumulative,ordered[:,0]),
                             np.interp(distance,cumulative,ordered[:,1])))
    tangent=np.column_stack((np.interp(distance,cumulative,tangents[:,0]),
                             np.interp(distance,cumulative,tangents[:,1])))
    normals=np.column_stack((tangent[:,1],-tangent[:,0]))
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    boundary=_normal_corridor_evidence(result,centres,normals,checks,bridge_small_gaps=True)
    if boundary is None:
        return None
    boundary['method']='paint_polyline_normals'
    return boundary


def boundary_evidence(result, coefficients, points, checks=None, allow_shallow=False,
                      minimum_samples=7):
    checks = {} if checks is None else checks
    boundary = _row_boundary_evidence(result, coefficients, points)
    checks['row_boundary_confirmed'] = boundary is not None
    if boundary is not None and boundary['samples'] >= minimum_samples:
        return boundary
    # A partial row view must not mask a complete path-normal observation.
    normal = _normal_boundary_evidence(result, coefficients, points, checks, allow_shallow)
    return normal if normal is not None and normal['samples'] >= minimum_samples else boundary


def observed_row_corridor(result, coefficients, points, axes, reference, checks):
    """Confirm a visible curved edge without assuming projected parallel slopes."""
    height,width=result.road.shape
    checks['observed_rows_reason']='insufficient_observations'
    if len(points)<3 or np.ptp(points[:,1])<.25*height:
        return None
    if near_road_fraction(result,reference,allow_divider=True)<.90:
        checks['observed_rows_reason']='near_road_unconfirmed'
        return None
    for point in points:
        slope=float(np.polyval(np.polyder(coefficients),point[1]/height)*width/height)
        tangent=np.array([slope,1.]);tangent/=np.linalg.norm(tangent)
        axis=nearest_axis(axes,point)
        if axis is None or abs(np.dot(axis,tangent))<.85:
            checks['observed_rows_reason']='paint_tangent_mismatch'
            return None
    _,labels=cv2.connectedComponents(result.yellow,8)
    rows=np.linspace(max(.25*height,points[:,1].min()),min(.90*height,points[:,1].max()),9)
    if np.ptp(rows)<.20*height:
        return None
    edges={-1:[],1:[]}
    for index,y in enumerate(rows):
        x=float(np.polyval(coefficients,y/height)*width)
        ix,iy=round(x),round(y)
        if not 2<=ix<width-2 or np.mean(result.road[iy-2:iy+3,ix-2:ix+3]>0)<.9:
            continue
        columns=np.flatnonzero(result.yellow[iy]>0)
        runs=np.split(columns,np.flatnonzero(np.diff(columns)>1)+1)
        for side in edges:
            candidates=[run for run in runs if len(run)>=2 and
                        .04*width<side*(np.mean(run)-x)<.70*width]
            if not candidates:
                continue
            run=min(candidates,key=lambda v:abs(np.mean(v)-x))
            # A bend can make yellow paint very wide in a horizontal scan.
            # The road corridor ends at its road-facing edge, not its centre.
            edge=int(run[-1] if side<0 else run[0])
            corridor=np.rint(np.linspace(x,edge,17)[2:-2]).astype(int)
            if np.mean(result.road[iy,corridor]>0)<.9:
                continue
            edges[side].append((index,edge,y,int(labels[iy,edge]),abs(edge-x)))
    for side,values in sorted(edges.items(),key=lambda item:len(item[1]),reverse=True):
        if len(values)<8:
            continue
        edge=np.asarray(values)
        component=int(np.bincount(edge[:,3].astype(int)).argmax())
        edge=edge[edge[:,3]==component]
        if len(edge)<8 or np.max(edge[:,4])/np.min(edge[:,4])>2.5:
            continue
        segments=np.diff(edge[:,1:3],axis=0)
        lengths=np.linalg.norm(segments,axis=1)
        directions=segments/lengths[:,None]
        turns=np.degrees(np.arccos(np.clip(np.sum(directions[1:]*directions[:-1],axis=1),-1,1)))
        if np.max(lengths)>.25*width or np.max(turns)>55:
            continue
        checks['observed_rows_reason']='supported'
        return dict(side='left' if side<0 else 'right',samples=len(edge),
                    points=edge[:,1:3].round(1).tolist(),method='observed_rows')
    checks['observed_rows_reason']='edge_or_corridor_unconfirmed'
    return None


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


def near_road_fraction(result, reference, allow_divider=False):
    road = getattr(result, 'road', None)
    if road is None:
        return 0.0
    height, width = road.shape
    centre = round(reference*width)
    top,bottom=round(.82*height),round(.94*height)
    left,right=max(0,centre-round(.08*width)),min(width,centre+round(.08*width))
    patch = road[top:bottom,left:right].copy()
    yellow=getattr(result,'yellow',None)
    if allow_divider and yellow is not None:
        # Only bridge narrow paint with independently classified road on BOTH
        # sides. An outer yellow edge next to floor is never drivable evidence.
        margin=max(3,round(.008*width));strip=max(8,round(.03*width))
        for y in range(top,bottom):
            columns=np.flatnonzero(yellow[y]>0)
            for run in np.split(columns,np.flatnonzero(np.diff(columns)>1)+1):
                if not 2<=len(run)<=.12*width or run[-1]<left or run[0]>=right:
                    continue
                a,b=int(run[0]),int(run[-1])+1
                if a-margin-strip<0 or b+margin+strip>width:
                    continue
                sides=(road[y,a-margin-strip:a-margin],road[y,b+margin:b+margin+strip])
                if all(np.mean(side>0)>=.9 for side in sides):
                    patch[y-top,max(0,a-margin-left):min(right-left,b+margin-left)]=255
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


def corroborated_near_path(result, points, axes, reference, checks, completion_priority=False,
                           target_band=False):
    """Validate the observed near centres independently of an unfittable far bend."""
    height, width = result.frame.shape[:2]
    local = points[points[:,1] >= .40*height]
    if target_band:
        local=local[local[:,1]<=.78*height]
    checks['near_path_reason'] = 'insufficient_near_centres'
    if (len(local) < 2 or len(local) == len(points) or
            np.ptp(local[:,1]) < .18*height or
            not local[:,1].min() <= .55*height <= local[:,1].max()):
        return None
    degree = 2 if len(local) >= 3 else 1
    coefficients = np.polyfit(local[:,1]/height,local[:,0]/width,degree)
    residual = local[:,0]/width - np.polyval(coefficients,local[:,1]/height)
    coefficients[-1] += np.median(residual)
    error = np.max(np.abs(np.polyval(coefficients,local[:,1]/height)-local[:,0]/width))
    checks['near_fit_error_px'] = round(float(error)*width,2)
    if error > .02:
        checks['near_path_reason'] = 'inconsistent_near_centres'
        return None
    slopes = np.polyval(np.polyder(coefficients),local[:,1]/height)*width/height
    for point,slope in zip(local,slopes):
        axis = nearest_axis(axes,point)
        tangent = np.array([slope,1.]); tangent /= np.linalg.norm(tangent)
        if axis is None or abs(np.dot(axis,tangent)) < .85:
            checks['near_path_reason'] = 'paint_tangent_mismatch'
            return None
    if near_road_fraction(result,reference,allow_divider=completion_priority) < .90:
        checks['near_path_reason'] = 'near_road_unconfirmed'
        return None
    prior_components=checks.get('normal_edge_components',{})
    boundary = boundary_evidence(result,coefficients,local,checks,allow_shallow=completion_priority)
    if boundary is None:
        checks['near_path_reason'] = 'boundary_unconfirmed'
        return None
    side='-1' if boundary['side']=='left' else '1'
    if target_band and prior_components.get(side,0)>1:
        checks['near_path_reason']='fragmented_near_boundary'
        return None
    if target_band:
        _,labels=cv2.connectedComponents(result.yellow,8)
        probes=np.rint(boundary['points']).astype(int)
        ids=labels[probes[:,1],probes[:,0]]
        ids=ids[ids>0]
        component=int(np.bincount(ids).argmax()) if len(ids) else 0
        near=int(round(points[:,1].max()))
        margin=max(2,round(.02*height))
        rows=labels[max(0,near-margin):min(height,near+margin+1)]
        connected=bool(component and len(rows) and np.mean(np.any(rows==component,axis=1))>=.8)
        checks['target_band_near_edge_connected']=connected
        if not connected:
            checks['near_path_reason']='fragmented_near_boundary'
            return None
    checks.update(near_path_reason='supported', omitted_far_points=len(points)-len(local),
                  target_band=target_band)
    return local,coefficients,boundary


def supported_side_mark(result, marking, axes):
    """A long partial stripe needs two intact aligned forward observations."""
    height,width=result.frame.shape[:2]
    point=np.asarray(marking['center'],float)
    if (marking.get('length_px',0)<.12*height or marking.get('fill_ratio',0)<.65 or
            marking.get('aspect_ratio',0)<2 or marking.get('thickness_px',0)<.02*height or
            not .03*width<point[0]<.97*width or point[1]>.90*height):
        return False
    axis=nearest_axis(axes,point)
    if axis is None:
        return False
    neighbours=0
    for other in result.markings:
        if not other['dash_candidate'] or other.get('side_clipped',False):
            continue
        direction=np.asarray(other['center'],float)-point
        length=np.linalg.norm(direction)
        if (.035*height<=-direction[1]<=.40*height and length>=.06*height and
                abs(np.dot(direction/length,axis))>=.85):
            neighbours+=1
    return neighbours>=2


def near_reflection_candidate(result, mark, axes=None, reference=None):
    """Reject tiny weak near blobs only with independent larger forward paint."""
    height,width=result.frame.shape[:2]
    y=mark['center'][1]
    if (y<.70*height or mark.get('side_clipped',False) or
            mark.get('length_px',float('inf'))>=.10*height or
            mark.get('fill_ratio',1)>=.70 or mark.get('area_px',float('inf'))>.001*height*width):
        return False
    thickness=mark.get('thickness_px',float('inf'))
    rows=[]
    for other in result.markings:
        dy=y-other['center'][1]
        if (other.get('dash_candidate') and not other.get('side_clipped',False) and
                .08*height<=dy<=.65*height and other.get('fill_ratio',0)>=.75 and
                other.get('thickness_px',0)>=1.8*thickness and
                other.get('length_px',0)>=.06*height):
            rows.append(other['center'][1])
    if len(rows)>=2 and np.ptp(rows)>=.06*height:
        return True
    if reference is None or axes is None:
        return False
    # A lateral glint must not anchor a chain ahead of independently confirmed
    # straight paint. This exception never invents paint across a missing frame.
    centre=np.asarray(mark['center'],float)
    axis=nearest_axis(axes,centre)
    if (axis is None or abs(centre[0]-reference*width)<.15*width or
            abs(axis[1])>.35):
        return False
    forward=[other['center'] for other in result.markings
             if other.get('dash_candidate') and not other.get('side_clipped',False)
             and .20*height<other['center'][1]<y-.08*height
             and abs(other['center'][0]-reference*width)<=.10*width
             and other.get('fill_ratio',0)>=.75
             and other.get('length_px',0)>=.02*height+.03*other['center'][1]]
    if not 3<=len(forward)<=10:
        return False
    points=np.asarray(sorted(forward,key=lambda p:-p[1]),float)
    chord=points[-1]-points[0]
    if (np.ptp(points[:,1])<.18*height or np.any(-np.diff(points[:,1])<.035*height)
            or abs(chord[0])>np.tan(np.radians(15))*abs(chord[1])
            or abs(np.dot(axis,chord/np.linalg.norm(chord)))>.35
            or not aligned_dashes(axes,points,minimum=.90)):
        return False
    coefficients=np.polyfit(points[:,1]/height,points[:,0]/width,1)
    if (np.max(np.abs(np.polyval(coefficients,points[:,1]/height)*width-points[:,0]))>.015*width
            or near_road_fraction(result,reference)<.90):
        return False
    boundary=boundary_evidence(result,coefficients,points,{},minimum_samples=8)
    return bool(boundary and boundary['samples']>=8)


def observed_paint_target(result, coefficients, points, axes, boundary, checks):
    """Use actual near paint beyond its centre, never an unobserved extension."""
    height,width=result.frame.shape[:2]
    anchor=points[np.argmin(points[:,1])]
    if not .70*height < anchor[1] <= .78*height or not aligned_dashes(axes,points,.85):
        return None
    mask=getattr(result,'dashes',None)
    if mask is None or boundary is None:
        return None
    targets=[]
    for y in range(max(2,int(np.ceil(anchor[1]-.08*height))),int(.70*height)+1):
        x=round(float(np.polyval(coefficients,y/height)*width))
        if (not 2<=x<width-2 or np.linalg.norm(np.array([x,y])-anchor)>.20*height or
                np.mean(mask[y-2:y+3,x-2:x+3]>0)<.8):
            continue
        targets.append((x,y))
    if not targets:
        return None
    _,labels=cv2.connectedComponents(result.yellow,8)
    # Bound extra corridor work even if a crease breaks the extended edge.
    for index in sorted({0,len(targets)//2,len(targets)-1}):
        x,y=targets[index]
        extended=np.vstack((points,[x,y]))
        evidence=boundary_evidence(result,coefficients,extended,checks,
                                   allow_shallow=True,minimum_samples=8)
        if evidence is None or evidence['samples']<8 or evidence['side']!=boundary['side']:
            continue
        components=[]
        for edge in (boundary,evidence):
            probes=np.rint(edge['points']).astype(int)
            ids=labels[probes[:,1],probes[:,0]]
            ids=ids[ids>0]
            components.append(int(np.bincount(ids).argmax()) if len(ids)>=7 else 0)
        if not components[0] or components[0]!=components[1]:
            continue
        checks['target_on_observed_paint']=True
        return y/height,evidence
    return None


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
            if prediction.get('source') == 'single_dash_boundary':
                raise ValueError('Set the central reference using multiple observed dashes')
            if abs(prediction.get('heading_degrees', 0)) > 12:
                raise ValueError('Set the central reference on a straight section, not in a sharp curve')
            self.reference = prediction['target_normalized']
            self.previous = self.reference
            self.previous_y = prediction.get('target_y_normalized', .55)
            self.reference_heading = prediction.get('heading_degrees', 0.0)
            return self.reference

    def predict(self, result, signature=None, completion_priority=False):
        with self.lock:
            if self.signature != signature:
                self.reset()
                self.signature = signature
            height, width = result.frame.shape[:2]
            reference = self.reference if self.reference is not None else .5
            invalid = dict(valid=False, reason='insufficient_dashes', points=[], path=[],
                           reference_set=self.reference is not None,
                           reference_normalized=reference, normalized_error=None,
                           reference_heading_degrees=self.reference_heading,
                           target_normalized=None, target=None, source=None,
                           heading_degrees=None, forward_direction='unknown', boundary_support=None)
            axes = dash_axes(result)
            noise={tuple(m['center']) for m in result.markings
                   if completion_priority and m.get('dash_candidate') and
                   near_reflection_candidate(result,m,axes,self.reference)}
            supported_sides={tuple(m['center']) for m in result.markings
                             if completion_priority and m['dash_candidate'] and m.get('side_clipped',False)
                             and supported_side_mark(result,m,axes)}
            candidates = [m['center'] for m in result.markings if m['dash_candidate']
                          and tuple(m['center']) not in noise
                          and (not m.get('side_clipped', False) or tuple(m['center']) in supported_sides)
                          and .01 * width < m['center'][0] < .99 * width
                          and .20 * height < m['center'][1] < .96 * height
                          and m.get('length_px',float('inf')) >= .02*height+.03*m['center'][1]]
            invalid['candidate_count'] = len(candidates)
            single_dash = False
            if len(candidates) == 1 and self.reference is not None:
                centre = np.asarray(candidates[0],float)
                axis = nearest_axis(axes,centre)
                marking = next(m for m in result.markings if m['center'] == candidates[0])
                length = marking.get('length_px',0)
                if axis is not None and length >= .18*height:
                    ends = np.array([centre-axis*length/2,centre+axis*length/2])
                    full_target = (np.ptp(ends[:,1]) >= .18*height and
                                   ends[:,1].min() <= .55*height <= ends[:,1].max())
                    oblique_target = (completion_priority and length >= .20*height and
                                      np.ptp(ends[:,1]) >= .08*height and
                                      abs(axis[0]) >= abs(axis[1]) and
                                      marking.get('fill_ratio',0) >= .75 and
                                      marking.get('aspect_ratio',0) >= 2.5 and
                                      marking.get('thickness_px',0) >= .02*height and
                                      ends[:,1].min() <= .70*height and
                                      ends[:,1].max() >= .40*height)
                    if ((full_target or oblique_target) and
                            np.all((ends[:,0] > .01*width) & (ends[:,0] < .99*width)) and
                            np.all((ends[:,1] > .20*height) & (ends[:,1] < .96*height))):
                        candidates = sorted(ends.tolist(),key=lambda p:-p[1])
                        single_dash = True
            if len(candidates) < 2:
                self.previous = None
                self.previous_heading = None
                return invalid
            bands = {}
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
            low_target,high_target=(.40,.70) if completion_priority else (.52,.58)
            observed_window=(points[:,1].min()<=round(high_target*height,1) and
                             points[:,1].max()>=round(low_target*height,1))
            short_geometry = (len(points) == 2 and span >= .08 and
                              np.linalg.norm(chord) >= .20*height and
                              abs(chord[0]) >= np.tan(np.radians(30))*abs(chord[1]) and
                              observed_window)
            if short_span and not short_geometry and not (completion_priority and len(points) >= 3):
                return {**invalid, 'reason':'insufficient_dash_span', 'points':points.tolist()}
            degree = 2 if len(points) >= 4 else 1
            coefficients = np.polyfit(points[:, 1] / height, points[:, 0] / width, degree)
            residual = np.abs(np.polyval(coefficients, points[:, 1] / height) - points[:, 0] / width)
            global_error = float(np.max(residual))
            boundary_checks = dict(global_fit_error_px=round(global_error*width,2),
                                   global_fit_limit_px=round(.04*width,2), fit_mode='global')
            if noise:
                boundary_checks['near_reflections_rejected']=len(noise)
            local_curve = False
            polyline = False
            if global_error > .04 or short_span and not short_geometry:
                fallback = corroborated_local_curve(result,points,axes,global_error,reference,boundary_checks)
                near_reasons = ('outside_bounded_exception','not_a_sharp_curve','insufficient_near_support')
                if completion_priority:
                    # The near fit repeats paint-tangent, current road and
                    # connected-edge checks; it is not an unchecked fit waiver.
                    near_reasons += ('inconsistent_near_points',)
                if fallback is None and boundary_checks.get('local_curve_reason') in near_reasons:
                    fallback = corroborated_near_path(result,points,axes,reference,boundary_checks,completion_priority)
                if fallback is None and completion_priority:
                    fallback=corroborated_near_path(result,points,axes,reference,boundary_checks,
                                                    True,target_band=True)
                if fallback is None and completion_priority:
                    boundary=corroborated_observed_curve(result,points,axes,reference,boundary_checks,
                                                         allow_divider=True)
                    polyline=boundary is not None
                if fallback is None and not polyline:
                    return {**invalid, 'reason':'inconsistent_dash_chain', 'points':points.tolist(),
                            'checks':boundary_checks}
                if fallback is not None:
                    points, coefficients, boundary = fallback
                span = float(np.ptp(points[:,1])/height)
                boundary_checks['fit_mode'] = ('observed_polyline' if polyline else
                                               'near_path' if boundary_checks.get('near_path_reason') == 'supported'
                                               else 'local_curve')
                local_curve = True
            else:
                boundary = boundary_evidence(result, coefficients, points, boundary_checks,
                                             allow_shallow=completion_priority,
                                             minimum_samples=8 if short_span else 7)
                if boundary is None and completion_priority:
                    boundary=observed_row_corridor(result,coefficients,points,axes,reference,boundary_checks)
            if short_span:
                supported = bool(boundary and boundary['samples'] >= 8 and
                                 (polyline or single_dash or aligned_dashes(axes, points, minimum=.85)) and
                                 near_road_fraction(result, reference,allow_divider=completion_priority) >= .90)
                boundary_checks['short_span_supported'] = supported
                boundary_checks['observed_span_px'] = round(span*height, 2)
                boundary_checks['observed_chord_px'] = round(float(np.linalg.norm(chord)), 2)
                if not supported:
                    return {**invalid, 'reason':'insufficient_dash_span', 'points':points.tolist(),
                            'checks':boundary_checks}
            complemented = local_curve or len(points) == 2 or span < .22
            # Curved local paint was checked against each fitted tangent above;
            # one end-to-end chord is not its local direction at every point.
            aligned = (True if local_curve or single_dash else
                       aligned_dashes(axes, points) if complemented else False)
            if single_dash and near_road_fraction(result,reference) < .90:
                return {**invalid, 'reason':'single_dash_uncorroborated'}
            if complemented and (boundary is None or not aligned):
                fallback=(corroborated_near_path(result,points,axes,reference,boundary_checks,True)
                          if completion_priority else None)
                if fallback is None and completion_priority:
                    fallback=corroborated_near_path(result,points,axes,reference,boundary_checks,
                                                    True,target_band=True)
                if fallback is not None:
                    points,coefficients,boundary=fallback
                    aligned=True
                else:
                    if completion_priority:
                        self.previous=self.previous_heading=None
                    return {**invalid, 'reason':'two_dashes_uncorroborated', 'points':points.tolist(),
                            'checks':dict(paint_aligned=aligned, boundary_confirmed=boundary is not None,
                                          **boundary_checks)}
            evaluate = (lambda y:np.interp(y,points[::-1,1]/height,points[::-1,0]/width)) if polyline else (
                        lambda y:np.polyval(coefficients,y))
            target_y = .55
            observed_low, observed_high = points[:,1].min()/height, points[:,1].max()/height
            adaptive_target = False
            if ((polyline or completion_priority and short_span) and
                    not observed_low <= target_y <= observed_high or
                    not observed_low - .08 <= target_y <= observed_high + .08):
                proposed_y = float(np.clip(target_y, observed_low, observed_high))
                chord = points[-1] - points[0]
                steep = abs(chord[0]) >= abs(chord[1])
                if (completion_priority and not polyline and not single_dash and steep and
                        boundary and self.reference is not None and
                        near_road_fraction(result,reference,allow_divider=True)>=.90 and proposed_y>.70):
                    observed=observed_paint_target(result,coefficients,points,axes,boundary,boundary_checks)
                    if observed is not None:
                        proposed_y,boundary=observed
                if not (boundary and (steep or polyline) and .40 <= proposed_y <= .70
                        and (polyline or single_dash or aligned_dashes(axes, points))):
                    return {**invalid, 'reason':'target_outside_observed_path', 'points':points.tolist(),
                            'checks':dict(observed_y=[observed_low,observed_high],
                                          boundary_confirmed=boundary is not None, **boundary_checks)}
                target_y, adaptive_target = proposed_y, True
            target = float(evaluate(target_y))
            if not .01 < target < .99:
                return {**invalid, 'reason': 'target_outside_image'}
            previous = self.previous
            if previous is not None:
                # Compare/smooth at one image depth even when look-ahead changes.
                previous += float(evaluate(target_y)-evaluate(self.previous_y))
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
            forward_dx = float(evaluate(far_y) - evaluate(near_y)) * width
            heading = float(np.degrees(np.arctan2(forward_dx, max((near_y-far_y)*height, 1))))
            heading = heading if self.previous_heading is None else .45 * heading + .55 * self.previous_heading
            self.previous_heading = heading
            heading_error = heading - self.reference_heading
            direction = 'right' if heading_error > 8 else 'left' if heading_error < -8 else 'straight'
            target_reference = reference - np.tan(np.radians(self.reference_heading))*(target_y-.55)*height/width
            error = round((smoothed - target_reference) * 2, 5)
            near_road = near_road_fraction(result,reference,allow_divider=completion_priority)
            if any(tuple(point) in supported_sides for point in points):
                boundary_checks['partial_paint_corroborated']=bool(boundary and near_road>=.90)
                if not boundary_checks['partial_paint_corroborated']:
                    return {**invalid,'reason':'partial_paint_uncorroborated','checks':boundary_checks}
            # Large look-ahead error can be a bend, not lateral departure. Only
            # permit it when fresh paint geometry AND the near road corroborate it.
            curve_corridor = bool(boundary and abs(heading_error) > 8 and near_road >= .85
                                  and abs(error) <= 1.05)
            rows = np.linspace(points[:, 1].min(), points[:, 1].max(), 20)
            if boundary_checks.get('target_on_observed_paint'):
                rows=np.linspace(min(points[:,1].min(),target_y*height),points[:,1].max(),20)
            path = [[round(float(evaluate(y / height) * width), 1), round(float(y), 1)] for y in rows]
            return dict(valid=True, reason='single_dash_corroborated' if single_dash else
                        'observed_curve_corroborated' if polyline else
                        'near_centres_corroborated' if boundary_checks.get('near_path_reason') == 'supported' else
                        'local_curve_corroborated' if local_curve else
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
                        observed_dash_count=1 if single_dash else len(points),
                        curve_corridor_supported=curve_corridor, near_road_fraction=round(near_road, 3),
                        lap_corridor_supported=bool(boundary and len(points) >= 2 and
                                                   near_road >= .90 and abs(error) <= 1.05),
                        source='single_dash_boundary' if single_dash else
                               'dash_boundary' if complemented else 'dash_chain',
                        boundary_support=boundary,
                        speed_scale=.8 if complemented else 1)


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
