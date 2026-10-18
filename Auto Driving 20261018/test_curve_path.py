import unittest
import json
from types import SimpleNamespace

import cv2
import numpy as np

from lane_path import LanePath, boundary_evidence, corroborated_local_curve, dash_axes
import test_pilot


def two_dashes(*, mirror=False, reverse_edge=False, horizontal=False, road_visible=True, offset=0,
               slope=.6, intercept=60, gap=140, rows_of_dashes=(250,370), dash_half_length=20):
    height, width = 480, 640
    yellow = np.zeros((height, width), np.uint8)
    road = np.zeros_like(yellow)
    dashes = np.zeros_like(yellow)
    rows = np.arange(96, height)
    edge_x = (600 - slope * rows) if reverse_edge else (intercept + gap + slope * rows)
    edge = np.column_stack((edge_x, rows)).astype(np.int32)
    cv2.polylines(yellow, [edge], False, 255, 9)
    if road_visible:
        for y, x in zip(rows, edge_x):
            road[y, :int(x)-6] = 255
    markings = []
    for y in rows_of_dashes:
        x = round(intercept + slope * y + offset)
        direction = np.array([1, 0] if horizontal else [slope, 1], dtype=float)
        direction /= np.linalg.norm(direction)
        a, b = np.array([x,y]) - direction * dash_half_length, np.array([x,y]) + direction * dash_half_length
        cv2.line(dashes, tuple(a.round().astype(int)), tuple(b.round().astype(int)), 255, 11)
        markings.append(dict(center=[x,y], dash_candidate=True))
    if mirror:
        yellow, road, dashes = (np.fliplr(mask).copy() for mask in (yellow,road,dashes))
        for marking in markings:
            marking['center'][0] = width - 1 - marking['center'][0]
    return SimpleNamespace(frame=np.zeros((height,width,3), np.uint8),
                           yellow=yellow, road=road, dashes=dashes, markings=markings)


def oblique_near_curve(*, mirror=False, far_y=313, near_y=404, offset=0):
    """Geometry of the user's displayed two-dash failure, not raw segmentation."""
    frame = np.zeros((480,640,3),np.uint8)
    yellow, road, dashes = (np.zeros((480,640),np.uint8) for _ in range(3))
    edge = np.array([(0,130),(180,175),(380,230),(639,340)],np.int32)
    cv2.polylines(yellow,[edge],False,255,9)
    cv2.fillPoly(road,[np.vstack((edge,[(639,479),(0,479)]))],255)
    markings = []
    axis = np.array([180,near_y-far_y],float)
    axis /= np.linalg.norm(axis)
    for centre in (np.array([78+offset,far_y]),np.array([256+offset,near_y])):
        cv2.line(dashes,tuple((centre-axis*30).round().astype(int)),
                 tuple((centre+axis*30).round().astype(int)),255,12)
        markings.append(dict(center=centre.tolist(),dash_candidate=True))
    if mirror:
        yellow,road,dashes = (np.fliplr(mask).copy() for mask in (yellow,road,dashes))
        for marking in markings:
            marking['center'][0] = 639-marking['center'][0]
    return SimpleNamespace(frame=frame,yellow=yellow,road=road,dashes=dashes,markings=markings)


def sharp_five_point_curve(*, mirror=False):
    points = np.array([(425,320),(362,231),(288,176),(201,141),(20,110)],float)
    coefficients = np.polyfit(points[:4,1]/480,points[:4,0]/640,2)
    frame = np.zeros((480,640,3),np.uint8)
    yellow,road,dashes = (np.zeros((480,640),np.uint8) for _ in range(3))
    road[:] = 255
    rows = np.arange(96,480)
    edge = np.column_stack((232+1.25*rows,rows)).astype(np.int32)
    cv2.polylines(yellow,[edge],False,255,9)
    markings = []
    for point in points:
        slope = np.polyval(np.polyder(coefficients),point[1]/480)*640/480
        axis = np.array([slope,1.]);axis /= np.linalg.norm(axis)
        cv2.line(dashes,tuple((point-axis*16).round().astype(int)),
                 tuple((point+axis*16).round().astype(int)),255,9)
        markings.append(dict(center=point.tolist(),dash_candidate=True))
    if mirror:
        yellow,road,dashes = (np.fliplr(mask).copy() for mask in (yellow,road,dashes))
        for marking in markings:marking['center'][0] = 639-marking['center'][0]
    return SimpleNamespace(frame=frame,yellow=yellow,road=road,dashes=dashes,markings=markings)


class CurvePathTests(unittest.TestCase):
    def test_compressed_oblique_chord_requires_stronger_current_support(self):
        for mirror in (False,True):
            result=two_dashes(slope=1,intercept=-190,gap=220,rows_of_dashes=(241,321),mirror=mirror)
            prediction=LanePath().predict(result)
            self.assertTrue(prediction['valid'],prediction)
            self.assertTrue(prediction['checks']['short_span_supported'])
            self.assertEqual(prediction['speed_scale'],.8)
        for failure in ('edge','road','axis','span','target','chord','vertical'):
            result=two_dashes(slope=1,intercept=-190,gap=220,rows_of_dashes=(241,321))
            if failure=='edge':result.yellow[:]=0
            elif failure=='road':result.road[394:452]=0
            elif failure=='axis':
                result.dashes[:]=0
                for marking in result.markings:
                    x,y=marking['center'];cv2.line(result.dashes,(x,y-15),(x,y+15),255,9)
            elif failure=='span':
                result=two_dashes(slope=1,intercept=-170,gap=220,rows_of_dashes=(241,300))
            elif failure=='target':
                result=two_dashes(slope=1,intercept=-220,gap=220,rows_of_dashes=(300,380))
            elif failure=='chord':
                result=two_dashes(slope=.6,intercept=-90,gap=220,rows_of_dashes=(241,321))
            else:result=two_dashes(slope=0,intercept=200,gap=220,rows_of_dashes=(241,321))
            self.assertFalse(LanePath().predict(result)['valid'],failure)

    def test_relaxed_curve_fit_requires_near_four_and_boundary_in_both_directions(self):
        for mirror,direction in ((False,'left'),(True,'right')):
            prediction = LanePath().predict(sharp_five_point_curve(mirror=mirror))
            self.assertTrue(prediction['valid'],prediction)
            self.assertEqual(prediction['reason'],'local_curve_corroborated')
            self.assertEqual(prediction['forward_direction'],direction)
            self.assertEqual(len(prediction['points']),4)
            self.assertEqual(prediction['checks']['omitted_far_points'],1)
            self.assertGreater(prediction['checks']['global_fit_error_px'],25.6)
            self.assertLessEqual(prediction['checks']['global_fit_error_px'],41.6)
            self.assertLessEqual(prediction['checks']['local_fit_error_px'],12.8)
            self.assertEqual(prediction['speed_scale'],.8)

    def test_local_curve_relaxation_rejects_missing_edge_or_near_road(self):
        for missing in ('yellow','near_road'):
            result = sharp_five_point_curve()
            if missing == 'yellow':result.yellow[:] = 0
            else:result.road[394:452] = 0
            prediction = LanePath().predict(result)
            self.assertFalse(prediction['valid'],prediction)
            self.assertEqual(prediction['reason'],'inconsistent_dash_chain')
            self.assertNotEqual(prediction['checks']['local_curve_reason'],'supported')

    def test_local_curve_rejects_misaligned_near_paint(self):
        result = sharp_five_point_curve()
        result.dashes[150:202,260:316] = 0
        cv2.line(result.dashes,(288,160),(288,192),255,9)
        prediction = LanePath().predict(result)
        self.assertFalse(prediction['valid'],prediction)
        self.assertEqual(prediction['checks']['local_curve_reason'],'paint_tangent_mismatch')

    def test_local_fit_exception_has_hard_cap_and_cannot_relax_straight_paths(self):
        result = sharp_five_point_curve()
        points = np.array([m['center'] for m in result.markings],float)
        checks = {}
        self.assertIsNone(corroborated_local_curve(result,points,dash_axes(result),.066,.5,checks))
        points[:4,0] = 320
        checks = {}
        self.assertIsNone(corroborated_local_curve(result,points,dash_axes(result),.05,.5,checks))
        self.assertEqual(checks['local_curve_reason'],'not_a_sharp_curve')

    def test_local_fit_cannot_hide_bad_near_points(self):
        result = sharp_five_point_curve()
        points = np.array([m['center'] for m in result.markings],float)
        points[1,0] += 100
        checks = {}
        self.assertIsNone(corroborated_local_curve(result,points,dash_axes(result),.05,.5,checks))
        self.assertEqual(checks['local_curve_reason'],'inconsistent_near_points')

    def test_lookahead_transition_reprojects_previous_target_but_keeps_jump_guard(self):
        result = oblique_near_curve(offset=100)
        points = np.array([marking['center'] for marking in result.markings],float)
        coefficients = np.polyfit(points[:,1]/480,points[:,0]/640,1)
        tracker = LanePath()
        tracker.previous = float(np.polyval(coefficients,.55))
        prediction = tracker.predict(result)
        self.assertTrue(prediction['valid'],prediction)
        self.assertTrue(prediction['adaptive_target'])
        self.assertAlmostEqual(prediction['target_normalized'],178/640)
        tracker.previous -= .2
        prediction = tracker.predict(result)
        self.assertFalse(prediction['valid'],prediction)
        self.assertEqual(prediction['reason'],'path_jump')

    def test_target_reference_accounts_for_straight_camera_heading_at_new_depth(self):
        tracker = LanePath()
        tracker.reference = .5
        tracker.reference_heading = 5
        prediction = tracker.predict(oblique_near_curve())
        self.assertTrue(prediction['valid'],prediction)
        reference = .5-np.tan(np.radians(5))*(313/480-.55)*480/640
        self.assertAlmostEqual(prediction['reference_at_target_normalized'],reference)
        self.assertAlmostEqual(prediction['normalized_error'],2*(78/640-reference),places=4)

    def test_oblique_two_dash_curve_uses_normal_edge_and_observed_lookahead(self):
        for mirror, direction in ((False,'left'),(True,'right')):
            prediction = LanePath().predict(oblique_near_curve(mirror=mirror))
            self.assertTrue(prediction['valid'],prediction)
            self.assertEqual(prediction['boundary_support']['method'],'path_normals')
            self.assertTrue(prediction['adaptive_target'])
            self.assertAlmostEqual(prediction['target_y_normalized'],313/480)
            self.assertEqual(prediction['forward_direction'],direction)
            self.assertGreater(abs(prediction['heading_degrees']),50)
            self.assertEqual(prediction['speed_scale'],.8)

    def test_normal_boundary_needs_road_corridor_not_only_paint_on_road(self):
        result = oblique_near_curve()
        result.road[160:290] = 0
        prediction = LanePath().predict(result)
        self.assertFalse(prediction['valid'],prediction)
        self.assertEqual(prediction['reason'],'two_dashes_uncorroborated')

    def test_normal_boundary_rejects_disconnected_yellow_and_missing_road(self):
        for failure in ('yellow_missing','yellow_fragments','road_missing'):
            result = oblique_near_curve()
            if failure == 'yellow_missing':
                result.yellow[:] = 0
            elif failure == 'yellow_fragments':
                result.yellow[:,210:235] = 0
            else:
                result.road[:] = 0
            prediction = LanePath().predict(result)
            self.assertFalse(prediction['valid'],failure)
            self.assertIn('normal_reason',prediction['checks'])

    def test_normal_boundary_rejects_crossing_edge_and_unaligned_strokes(self):
        result = oblique_near_curve()
        result.yellow[:] = 0
        cv2.line(result.yellow,(150,100),(150,479),255,9)
        self.assertFalse(LanePath().predict(result)['valid'])
        result = oblique_near_curve()
        result.dashes[:] = 0
        for marking in result.markings:
            x,y = marking['center']
            cv2.line(result.dashes,(x,y-25),(x,y+25),255,12)
        prediction = LanePath().predict(result)
        self.assertFalse(prediction['valid'])

    def test_adaptive_lookahead_rejects_path_visible_only_too_close(self):
        result = oblique_near_curve(far_y=340,near_y=440)
        prediction = LanePath().predict(result)
        self.assertFalse(prediction['valid'],prediction)

    def test_heading_uses_ordered_observed_rows_for_near_only_curve(self):
        prediction = LanePath().predict(oblique_near_curve())
        self.assertLess(prediction['heading_degrees'],-50)
        prediction = LanePath().predict(oblique_near_curve(mirror=True))
        self.assertGreater(prediction['heading_degrees'],50)

    def test_curving_successive_dashes_in_same_band_update_the_local_prediction(self):
        result = two_dashes(rows_of_dashes=())
        result.markings = []
        for x, y, slope in ((317,293,1.4), (195,220,2.1), (80,174,2.9)):
            direction = np.array([slope,1], dtype=float)
            direction /= np.linalg.norm(direction)
            centre = np.array([x,y])
            cv2.line(result.dashes, tuple((centre-direction*15).round().astype(int)),
                     tuple((centre+direction*15).round().astype(int)), 255, 8)
            result.markings.append(dict(center=[x,y], dash_candidate=True))
        prediction = LanePath().predict(result)
        self.assertTrue(prediction['valid'], prediction)
        self.assertEqual(len(prediction['points']), 3)

    def test_compressed_three_point_curve_requires_independent_boundary_support(self):
        result = two_dashes(rows_of_dashes=(220,265,310), dash_half_length=12)
        prediction = LanePath().predict(result)
        self.assertTrue(prediction['valid'], prediction)
        self.assertEqual(prediction['source'], 'dash_boundary')
        result.yellow[:] = 0
        self.assertFalse(LanePath().predict(result)['valid'])

    def test_steep_curve_association_uses_paint_axis_not_vertical_neighbour_guess(self):
        for mirror in (False,True):
            result = two_dashes(slope=1.5, intercept=-125, gap=150, mirror=mirror)
            prediction = LanePath().predict(result)
            self.assertTrue(prediction['valid'], prediction)
            self.assertEqual(prediction['source'], 'dash_boundary')
            self.assertGreater(abs(prediction['heading_degrees']), 50)

    def test_successive_dashes_in_one_row_band_are_not_competing_lanes(self):
        result = two_dashes()
        result.markings = [dict(center=[310,y], dash_candidate=True) for y in (390,252,172,118)]
        prediction = LanePath().predict(result)
        self.assertTrue(prediction['valid'], prediction)
        self.assertEqual(len(prediction['points']), 4)

    def test_actual_lateral_competitors_still_reject(self):
        result = two_dashes()
        result.markings = [dict(center=[x,y], dash_candidate=True)
                           for x in (270,370) for y in (390,252,172,118)]
        self.assertEqual(LanePath().predict(result)['reason'], 'ambiguous_dash_chain')

    def test_two_dashes_require_matching_edge_and_return_both_turn_directions(self):
        for mirror, direction in ((False,'left'), (True,'right')):
            with self.subTest(direction=direction):
                prediction = LanePath().predict(two_dashes(mirror=mirror))
                self.assertTrue(prediction['valid'], prediction)
                self.assertEqual(prediction['source'], 'dash_boundary')
                self.assertEqual(prediction['forward_direction'], direction)
                self.assertIsNotNone(prediction['boundary_support'])
                self.assertEqual(prediction['speed_scale'], .8)

    def test_opposing_edge_not_enough_road_or_crosswalk_like_axes_rejected(self):
        for values in (dict(reverse_edge=True), dict(road_visible=False), dict(horizontal=True)):
            with self.subTest(values=values):
                prediction = LanePath().predict(two_dashes(**values))
                self.assertFalse(prediction['valid'])
                self.assertEqual(prediction['reason'], 'two_dashes_uncorroborated')

    def test_single_dash_or_boundary_alone_cannot_continue(self):
        for count in (0, 1):
            result = two_dashes()
            result.markings = result.markings[:count]
            self.assertFalse(LanePath().predict(result)['valid'])

    def test_missing_edge_cannot_continue_on_two_dashes(self):
        result = two_dashes()
        result.yellow[:] = 0
        self.assertFalse(LanePath().predict(result)['valid'])

    def test_turning_dashes_near_either_image_edge_are_not_discarded_by_fixed_crop(self):
        for mirror in (False, True):
            prediction = LanePath().predict(two_dashes(offset=-180, mirror=mirror))
            self.assertTrue(prediction['valid'], prediction)
            self.assertTrue(prediction['curve_corridor_supported'])
            self.assertGreater(abs(prediction['normalized_error']), .55)

    def test_separate_yellow_fragments_cannot_fake_a_continuous_edge(self):
        result = two_dashes()
        result.yellow[294:324] = 0
        self.assertFalse(LanePath().predict(result)['valid'])

    def test_reference_cannot_be_reset_to_zero_inside_a_sharp_curve(self):
        tracker = LanePath()
        curve = tracker.predict(two_dashes())
        with self.assertRaises(ValueError):
            tracker.calibrate(curve)
        self.assertIsNone(tracker.reference)

    def test_curve_corridor_requires_near_road_not_just_a_yellow_edge(self):
        result = two_dashes()
        self.assertTrue(LanePath().predict(result)['curve_corridor_supported'])
        result.road[394:452,269:371] = 0
        prediction = LanePath().predict(result)
        self.assertTrue(prediction['valid'])
        self.assertFalse(prediction['curve_corridor_supported'])


class CurvePilotTests(unittest.TestCase):
    setUp = test_pilot.PilotTests.setUp

    def test_relaxed_local_curve_still_obeys_pilot_caps_and_slow_output(self):
        prediction = LanePath().predict(sharp_five_point_curve())
        prediction['reference_set'] = True
        self.monitor.frame['path'] = prediction
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertTrue(self.pilot.active)
        self.assertLessEqual(abs(self.pilot.angle),3.001)
        self.assertLessEqual(abs(self.pilot.wanted_angle(prediction)),20)
        self.assertAlmostEqual(self.control.outputs[0],.143)
        self.assertAlmostEqual(self.control.outputs[1],.143)

    def test_new_oblique_route_keeps_motor_reduction_and_steering_limits(self):
        prediction = LanePath().predict(oblique_near_curve())
        prediction['reference_set'] = True
        self.monitor.frame['path'] = prediction
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertTrue(self.pilot.active)
        self.assertAlmostEqual(abs(self.pilot.angle),3)
        self.assertLessEqual(abs(self.pilot.wanted_angle(prediction)),20)
        self.assertAlmostEqual(self.control.outputs[0],.26*.55)
        self.assertAlmostEqual(self.control.outputs[1],.26*.55)

    def test_diagnostic_io_failure_does_not_prevent_motor_stop(self):
        self.monitor.diagnostic_pair = lambda number:(np.zeros((20,20,3),np.uint8),)*2
        def failed_photo(*args, **kwargs):
            raise OSError('test storage error')
        self.store.photo = failed_photo
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.monitor.frame['path']['valid'] = False
        self.pilot.tick()
        self.assertEqual(self.control.outputs, (0,0))
        self.assertFalse(self.control.armed)
        rows = [json.loads(line) for line in (self.store.root/self.pilot.last_log).read_text().splitlines()]
        self.assertIn('test storage error', rows[-1]['diagnostic']['error'])

    def test_restart_resumes_last_command_instead_of_slewing_from_zero(self):
        self.control.angle = -18
        self.monitor.frame['path']['normalized_error'] = -.3
        self.pilot.start('one')
        self.assertEqual(self.pilot.angle, -18)
        self.assertEqual(self.servo.commands, [])
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertAlmostEqual(self.servo.angle, -18)

    def test_fresh_straight_reference_resets_start_baseline_without_actuating(self):
        self.control.angle = -18
        self.monitor.calibrate_path = lambda:.5
        self.monitor.status = lambda:{'settings':{}}
        self.pilot.calibrate()
        self.pilot.start('one')
        self.assertEqual(self.pilot.angle, 0)
        self.assertEqual(self.servo.commands, [])

    def test_pilot_reduction_does_not_overwrite_manual_preferences(self):
        self.control.speed = .27
        self.control.trims = (.9,1.1)
        self.monitor.frame['path']['speed_scale'] = .8
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertAlmostEqual(self.control.outputs[0], .143)
        self.assertEqual(self.control.speed, .27)
        self.assertEqual(self.control.trims, (.9,1.1))

    def test_heading_is_used_before_large_centre_displacement(self):
        self.monitor.frame['path'].update(normalized_error=0, heading_error_degrees=15,
                                          speed_scale=.8)
        self.assertAlmostEqual(self.pilot.status()['predicted_angle'], 12)
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertAlmostEqual(self.servo.angle, 3)
        self.assertAlmostEqual(self.control.outputs[0], .143)

    def test_large_error_needs_a_fresh_corroborated_corridor_and_stays_limited(self):
        path = self.monitor.frame['path']
        path.update(normalized_error=.8, heading_error_degrees=25)
        with self.assertRaises(ValueError):
            self.pilot.start('one')
        self.assertFalse(self.control.armed)
        path['curve_corridor_supported'] = True
        self.pilot.start('one')
        self.now.return_value = 1000.05
        self.pilot.tick()
        self.assertLessEqual(self.servo.angle, self.pilot.config.max_angle)
        self.assertAlmostEqual(self.control.outputs[0], .143)
        path['curve_corridor_supported'] = False
        self.monitor.frame['number'] += 1
        self.pilot.tick()
        self.assertEqual(self.pilot.reason, 'path_error_large')
        self.assertEqual(self.control.outputs, (0,0))

    def test_extreme_error_is_not_overridden_by_corridor(self):
        self.monitor.frame['path'].update(normalized_error=1.1, curve_corridor_supported=True)
        with self.assertRaises(ValueError):
            self.pilot.start('one')

    def test_curve_still_stops_on_stale_camera(self):
        self.monitor.frame['path'].update(normalized_error=.8, curve_corridor_supported=True)
        self.pilot.start('one')
        self.monitor.frame['age'] = .25
        self.pilot.tick()
        self.assertEqual(self.pilot.reason, 'path_lost')
        self.assertEqual(self.control.outputs, (0,0))


class DiagnosticFrameTests(unittest.TestCase):
    setUp = test_pilot.PilotWebTests.setUp
    post = test_pilot.PilotWebTests.post

    def test_failure_saves_requested_frame_not_a_later_recovered_frame(self):
        self.post('reference')
        self.pilot.start('one')
        failed_observation = self.monitor.control_snapshot()
        expected, _ = self.monitor.fresh_pair()
        changed = expected.copy()
        changed[:40,:40] = 255 if np.mean(expected[10,10]) < 128 else 0
        self.monitor.process_frame(changed)
        self.monitor.process_frame(changed)
        self.pilot.stop('path_lost', failed_observation)
        rows = [json.loads(line) for line in (self.store.root/self.pilot.last_log).read_text().splitlines()]
        files = rows[-1]['diagnostic']
        saved = cv2.imread(str(self.store.root/files[0]))
        self.assertLess(np.max(np.abs(saved[10,10].astype(int)-expected[10,10].astype(int))), 12)
        metadata = json.loads((self.store.root/files[-1]).read_text())
        self.assertEqual(metadata['observation']['number'], failed_observation['number'])
        self.assertFalse(self.control.armed)
