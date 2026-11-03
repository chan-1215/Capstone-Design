from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from crosswalk import CrosswalkDetector, detect_crosswalk, exclude_crosswalk_dashes
from interaction import CrossingGate
from turn_recovery import TurnRecovery, corridor_observation
from lane_path import LanePath
from test_curve_path import two_dashes, oblique_near_curve


def crossing_frame(shift=0):
    mask = np.zeros((400, 600), np.uint8)
    for x in (170, 250, 330, 410):
        cv2.rectangle(mask, (x+shift, 205), (x+shift+28, 330), 255, -1)
    return SimpleNamespace(paint_support=mask, frame=np.zeros((400, 600, 3), np.uint8))


def distant_crossing():
    result = crossing_frame()
    result.paint_support[:] = 0
    for top, bottom in zip((210, 264, 318, 372, 426), (140, 225, 310, 395, 480)):
        polygon = np.array([[top, 82], [top+27, 82],
                            [bottom+40, 135], [bottom, 135]], np.int32)
        cv2.fillPoly(result.paint_support, [polygon], 255)
    return result


class CrosswalkTests(unittest.TestCase):
    def test_distant_fanned_roi_clipped_stripes_form_one_crosswalk(self):
        found = detect_crosswalk(distant_crossing())
        self.assertTrue(found['detected'])
        self.assertEqual(found['stripes'], 5)
        self.assertEqual(found['method'], 'perspective_band')
        self.assertLess(found['near'], .4)
        self.assertFalse(found['stop'])

    def test_distant_confirmation_is_not_a_near_stop_or_duplicate_confirmation(self):
        detector = CrosswalkDetector()
        frame = distant_crossing()
        for number, at in enumerate((10., 10.07, 10.14)):
            found = detector.observe(frame, number, at, at)
        self.assertTrue(found['stable'])
        self.assertFalse(found['stop'])
        self.assertFalse(detector.observe(frame, 2, 10.14, 10.15)['stable'])
        self.assertFalse(detector.observe(frame, 3, 10.16, 10.5)['stable'])

    def test_opt_in_interaction_stops_on_fresh_confirmation_before_near_threshold(self):
        detector = CrosswalkDetector()
        frame = distant_crossing()
        for number, at in enumerate((10., 10.07, 10.14)):
            found = detector.observe(frame, number, at, at, stop_on_confirmed=True)
            self.assertEqual(found['stop'], number == 2)
        self.assertLess(found['near'], .4)
        self.assertTrue(found['stop'])
        self.assertFalse(detector.observe(frame, 2, 10.14, 10.15, stop_on_confirmed=True)['stop'])
        self.assertFalse(detector.observe(frame, 3, 10.16, 10.5, stop_on_confirmed=True)['stop'])

    def test_fan_requires_four_distinct_regular_persistent_bars_across_reference(self):
        for failure in ('two_lanes', 'glare', 'thin_band', 'wrong_lane',
                        'uneven_spacing', 'connected_paint'):
            result = distant_crossing()
            mask = result.paint_support
            if failure == 'two_lanes':
                mask[:] = 0
                for y in (90, 180, 270):
                    for x in (180, 400):
                        cv2.rectangle(mask, (x, y), (x+20, y+30), 255, -1)
            elif failure == 'glare':
                mask[82:136, 120:540] = 255
            elif failure == 'thin_band':
                mask[90:] = 0
            elif failure == 'wrong_lane':
                result.paint_support = cv2.resize(mask, (180, 400))
                result.paint_support = np.pad(result.paint_support, ((0, 0), (0, 420)))
            elif failure == 'uneven_spacing':
                mask[:] = 0
                for x in (100, 145, 300, 480):
                    cv2.rectangle(mask, (x, 82), (x+28, 135), 255, -1)
            else:
                mask[82, 140:521] = 255
            self.assertFalse(detect_crosswalk(result)['detected'], failure)

    def test_crosswalk_candidates_do_not_become_lane_points_and_masks_are_preserved(self):
        result = distant_crossing()
        result.dashes = result.paint_support.copy()
        result.markings = [dict(center=[327., 110.], dash_candidate=True),
                           dict(center=[250., 250.], dash_candidate=True)]
        result.metrics = {}
        result.dashes[240:260, 240:260] = 255
        paint = result.paint_support.copy()
        crossing = detect_crosswalk(result)
        exclude_crosswalk_dashes(result, crossing)
        self.assertFalse(result.markings[0]['dash_candidate'])
        self.assertTrue(result.markings[1]['dash_candidate'])
        self.assertEqual(result.metrics['crosswalk_excluded_dashes'], 1)
        self.assertEqual(result.dashes[110, 327], 0)
        self.assertEqual(result.dashes[250, 250], 255)
        np.testing.assert_array_equal(result.paint_support, paint)

    def test_unconfirmed_or_unreliable_shapes_do_not_remove_lane_paint(self):
        result = distant_crossing()
        result.dashes = result.paint_support.copy()
        result.markings = [dict(center=[327., 110.], dash_candidate=True)]
        result.metrics = {}
        before = result.dashes.copy()
        for crossing in (dict(detected=False), dict(detected=True, reliable=False)):
            exclude_crosswalk_dashes(result, crossing)
            self.assertTrue(result.markings[0]['dash_candidate'])
            np.testing.assert_array_equal(result.dashes, before)

    def test_parallel_side_by_side_stripes_not_only_horizontal_bars(self):
        result = detect_crosswalk(crossing_frame())
        self.assertTrue(result['detected'])
        self.assertEqual(result['stripes'], 4)
        self.assertGreater(result['near'], .7)
        self.assertFalse(result['stop'])

    def test_perspective_rotation_preserves_group(self):
        result = crossing_frame()
        matrix = cv2.getRotationMatrix2D((300, 260), 25, 1)
        result.paint_support = cv2.warpAffine(result.paint_support, matrix, (600, 400))
        self.assertTrue(detect_crosswalk(result)['detected'])

    def test_blank_lane_dashes_single_patch_and_unrelated_lane_are_negative(self):
        for shape in ('blank', 'lane', 'one', 'other_lane'):
            result = crossing_frame()
            result.paint_support[:] = 0
            if shape == 'lane':
                for y in (100, 190, 280):
                    cv2.rectangle(result.paint_support, (290, y), (310, y+35), 255, -1)
            elif shape == 'one':
                cv2.rectangle(result.paint_support, (100, 210), (450, 330), 255, -1)
            elif shape == 'other_lane':
                for x in (25, 70, 115):
                    cv2.rectangle(result.paint_support, (x, 200), (x+15, 320), 255, -1)
            self.assertFalse(detect_crosswalk(result)['detected'], shape)

    def test_unique_fresh_frames_required_and_stop_only_when_near(self):
        detector = CrosswalkDetector()
        frame = crossing_frame()
        for number, at in enumerate((10., 10.07, 10.14)):
            found = detector.observe(frame, number, at, at)
        self.assertTrue(found['stable'])
        self.assertTrue(found['stop'])
        self.assertFalse(detector.observe(frame, 2, 10.14, 10.15)['stop'])
        self.assertFalse(detector.observe(frame, 3, 10.16, 10.5)['stop'])
        frame.paint_support[:] = 0
        self.assertFalse(detector.observe(frame, 4, 10.6, 10.6)['stop'])
        frame = crossing_frame()
        self.assertFalse(detector.observe(frame, 5, 10.7, 10.7)['stable'])

    def test_excess_components_fail_closed_instead_of_unbounded_pairwise_work(self):
        frame = crossing_frame()
        frame.paint_support[:] = 0
        for x in range(0,600,12):
            for y in range(0,400,12): frame.paint_support[y:y+3,x:x+3] = 255
        found = detect_crosswalk(frame)
        self.assertFalse(found['reliable'])
        self.assertFalse(found['stop'])


class CrossingGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = CrossingGate()
        self.gate.observe_crosswalk({'stop': True, 'detected': True}, 1, 10.)

    def gesture(self, number, at, **changes):
        return dict(mode='wait', ready=True, hand_detected=True, received_at=at,
                    decision_label='go', epoch=1, number=number, **changes)

    def test_requires_new_results_and_half_second_then_latches_departure(self):
        self.assertTrue(self.gate.waiting)
        for i in range(6):
            at = 10.1+i*.11
            released = self.gate.authorize(self.gesture(i, at), at, True)
            self.assertEqual(released, i == 5)
        self.assertEqual(self.gate.state, 'depart')
        for i in range(10):
            self.gate.observe_crosswalk({'detected': True, 'stop': True}, i+2, 11+i*.1)
        self.assertEqual(self.gate.state, 'depart')
        for i in range(8):
            self.gate.observe_crosswalk({'detected': False}, i+20, 13+i*.1)
        self.assertEqual(self.gate.state, 'follow')

    def test_held_display_pre_wait_stale_unknown_stop_and_missing_hand_cannot_release(self):
        for kind in ('display', 'pre_wait', 'stale', 'unknown', 'stop', 'no_hand', 'preview', 'not_ready'):
            self.setUp()
            for i in range(10):
                at = 10.1+i*.1
                result = self.gesture(i, at)
                result['label'] = 'go'
                if kind == 'display': result['decision_label'] = 'unknown'
                if kind == 'pre_wait': result['received_at'] = 9.9
                if kind == 'stale': result['received_at'] = at-.3
                if kind in ('unknown', 'stop'): result['decision_label'] = kind
                if kind == 'no_hand': result['hand_detected'] = False
                if kind == 'preview': result['mode'] = 'preview'
                if kind == 'not_ready': result['ready'] = False
                self.assertFalse(self.gate.authorize(result, at, True), kind)
            self.assertTrue(self.gate.waiting)

    def test_duplicate_go_does_not_accumulate_and_no_path_never_releases(self):
        result = self.gesture(1, 10.1)
        for i in range(6):
            self.assertFalse(self.gate.authorize(result, 10.1+i*.01, True))
        self.assertEqual(self.gate.go_count, 1)
        for i in range(10):
            at = 11+i*.1
            self.assertFalse(self.gate.authorize(self.gesture(i+2, at), at, False))
        self.assertTrue(self.gate.waiting)

    def test_unknown_resets_go_epoch_and_cannot_reuse_authorization_after_reset(self):
        for i in range(4):
            self.gate.authorize(self.gesture(i, 10.1+i*.1), 10.1+i*.1, True)
        result = self.gesture(5, 10.5); result['decision_label'] = 'unknown'
        self.gate.authorize(result, 10.5, True)
        self.assertEqual(self.gate.go_count, 0)
        self.gate.reset()
        self.assertFalse(self.gate.authorize(self.gesture(6, 10.6), 10.6, True))


class TurnRecoveryTests(unittest.TestCase):
    def frame(self, n, at, valid=True, reason='insufficient_dashes', **changes):
        return dict(source_number=n, received_at=at,
                    path=dict(valid=valid, source='dash_chain', reference_set=True, reason=reason),
                    continuation=dict(supported=True), **changes)

    def prepared(self, angle=-30, direction='left'):
        state = TurnRecovery()
        for i, at in enumerate((10., 10.1, 10.2, 10.31)):
            state.observe_valid(self.frame(i, at), at, angle, .255, direction)
        return state

    def test_both_directions_hold_only_previous_command_and_expire(self):
        for angle, direction in ((-30, 'left'), (30, 'right')):
            state = self.prepared(angle, direction)
            decision = state.continue_turn(self.frame(5, 10.4, False), 10.4)
            self.assertEqual(decision['angle'], angle)
            self.assertEqual(decision['speed'], .255)
            self.assertIsNone(state.continue_turn(self.frame(6, 10.52, False), 10.52))

    def test_missing_road_stale_reference_jump_ambiguity_and_straight_do_not_recover(self):
        for failure in ('support', 'stale', 'reference', 'path_jump', 'ambiguous_dash_chain', 'straight'):
            state = self.prepared()
            frame = self.frame(5, 10.4, False)
            if failure == 'support': frame['continuation']['supported'] = False
            elif failure == 'stale': frame['received_at'] = 10.
            elif failure == 'reference': frame['path']['reference_set'] = False
            elif failure == 'straight': state.last_good['direction'] = 'straight'
            else: frame['path']['reason'] = failure
            self.assertIsNone(state.continue_turn(frame, 10.4), failure)

    def test_single_good_flicker_cannot_renew_budget(self):
        state = self.prepared()
        self.assertIsNotNone(state.continue_turn(self.frame(5, 10.4, False), 10.4))
        state.observe_valid(self.frame(6, 10.45), 10.45, -31, .255, 'left')
        self.assertEqual(state.continue_turn(self.frame(7,10.46,False),10.46)['angle'], -31)
        self.assertIsNone(state.continue_turn(self.frame(7, 10.52, False), 10.52))

    def test_opposite_valid_turn_cannot_resume_old_turn_episode(self):
        state = self.prepared()
        state.continue_turn(self.frame(5,10.4,False),10.4)
        state.observe_valid(self.frame(6,10.44),10.44,8,.255,'right')
        self.assertIsNone(state.continue_turn(self.frame(7,10.46,False),10.46))

    def test_never_recover_without_source_time_or_initial_good_streak(self):
        state = TurnRecovery()
        state.observe_valid(self.frame(1, 10.), 10., -30, .255, 'left')
        self.assertIsNone(state.continue_turn(self.frame(2, 10.1, False), 10.1))
        state = self.prepared()
        frame = self.frame(5, 10.4, False); frame['received_at'] = None
        self.assertIsNone(state.continue_turn(frame, 10.4))

    def test_out_of_order_source_cannot_enter_or_replenish_recovery(self):
        state = self.prepared()
        state.observe_valid(self.frame(1,10.36),10.36,-60,.3,'left')
        self.assertEqual(state.last_good['angle'],-30)
        self.assertIsNone(state.continue_turn(self.frame(1,10.4,False),10.4))

    def test_geometry_never_supported_without_prior_or_current_masks(self):
        result = SimpleNamespace(frame=np.zeros((400,600,3),np.uint8))
        self.assertFalse(corridor_observation(result, None, {'valid':False})['supported'])

    def test_current_geometry_supports_both_turns_without_using_missing_paint(self):
        for factory in (two_dashes,oblique_near_curve):
            for mirror in (False,True):
                result = factory(mirror=mirror)
                previous = LanePath().predict(result)
                result.dashes[:] = 0
                result.markings = []
                current = dict(valid=False,reference_set=True,reason='insufficient_dashes')
                self.assertTrue(corridor_observation(result,previous,current)['supported'])

    def test_boundary_loss_fragmentation_displacement_and_road_loss_are_not_recovery(self):
        for failure in ('edge','fragmented','displaced','road'):
            result = two_dashes()
            previous = LanePath().predict(result)
            if failure == 'edge': result.yellow[:] = 0
            elif failure == 'road': result.road[:] = 0
            elif failure == 'fragmented': result.yellow[295:320] = 0
            else: result.yellow = np.roll(result.yellow,70,axis=1)
            current = dict(valid=False,reference_set=True,reason='insufficient_dashes')
            self.assertFalse(corridor_observation(result,previous,current)['supported'],failure)


if __name__ == '__main__':
    unittest.main()
