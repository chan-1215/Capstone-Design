"""Fresh synthetic joint corridors and fake GPIO; never connect to the robot."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from autonomous import AutoPilot, PilotConfig
from boundary_guidance import boundary_direction, combine_direction, guide_path
from lane_path import LanePath
from turn_recovery import TurnRecovery
import test_pilot


def near_paint(mirror=False, failure=None):
    height,width=360,480
    centre=np.array([200.,300.]);axis=np.array([.8660254,.5])
    normal=np.array([axis[1],-axis[0]])
    ends=np.array([centre-axis*50,centre+axis*50])
    road=np.full((height,width),255,np.uint8)
    yellow=np.zeros_like(road);dashes=np.zeros_like(road)
    edge=ends+normal*90
    cv2.line(yellow,tuple(np.rint(edge[0]-axis*30).astype(int)),
             tuple(np.rint(edge[1]+axis*30).astype(int)),255,9)
    cv2.line(dashes,tuple(np.rint(ends[0]).astype(int)),tuple(np.rint(ends[1]).astype(int)),255,15)
    mark=dict(center=centre.tolist(),length_px=100,thickness_px=15,
              fill_ratio=.85,aspect_ratio=6.6,dash_candidate=True)
    if failure=='edge':yellow[:]=0
    elif failure=='fragment':yellow[214:231]=0
    elif failure=='wrong_edge':
        yellow[:]=0;cv2.line(yellow,(350,90),(120,340),255,9)
    elif failure=='road':road[295:339]=0
    elif failure=='paint':dashes[:]=0
    elif failure=='shape':mark['fill_ratio']=.62
    elif failure=='side':mark['side_clipped']=True
    elif failure=='none':mark['dash_candidate']=False
    elif failure=='outer':
        yy,xx=np.indices(road.shape)
        road[((xx-edge[0,0])*normal[0]+(yy-edge[0,1])*normal[1])>6]=0
    if mirror:
        road,yellow,dashes=(np.fliplr(m).copy() for m in (road,yellow,dashes))
        mark['center'][0]=width-1-mark['center'][0]
    return SimpleNamespace(frame=np.zeros((height,width,3),np.uint8),road=road,
                           yellow=yellow,dashes=dashes,markings=[mark])


class JointPathTests(unittest.TestCase):
    def prediction(self,result,reference=True):
        tracker=LanePath()
        if reference:tracker.reference=.5
        return tracker.predict(result,completion_priority=True)

    def test_current_near_paint_and_edge_replace_missing_fixed_height_target(self):
        for mirror in (False,True):
            result=near_paint(mirror)
            original=self.prediction(result)
            self.assertFalse(original['valid'],original)
            joint=guide_path(result,original)
            self.assertTrue(joint['valid'],joint)
            self.assertEqual(joint['guidance_mode'],'boundary_curve')
            self.assertEqual(joint['source'],'single_dash_boundary')
            self.assertEqual(joint['observed_dash_count'],1)
            self.assertEqual(joint['speed_scale'],.8)
            self.assertGreater(joint['target_y_normalized'],.70)
            self.assertLessEqual(joint['target_y_normalized'],.90)
            x,y=map(round,joint['target'])
            self.assertGreaterEqual(np.mean(result.dashes[y-2:y+3,x-2:x+3]>0),.8)
            self.assertGreaterEqual(joint['boundary_support']['samples'],8)
            self.assertTrue(joint['boundary_turn_agreement'])
            self.assertEqual(joint['forward_direction'],'right' if mirror else 'left')
            with self.assertRaises(ValueError):LanePath().calibrate(joint)

    def test_current_joint_proof_is_required_on_each_frame(self):
        for mirror in (False,True):
            for failure in ('edge','fragment','wrong_edge','road','paint','shape','side','none','reference'):
                result=near_paint(mirror,failure)
                original=self.prediction(result,reference=failure!='reference')
                self.assertFalse(guide_path(result,original)['valid'],(mirror,failure))

    def test_ambiguity_bad_fits_and_jumps_are_not_overridden(self):
        result=near_paint()
        for reason in ('ambiguous_dash_chain','inconsistent_dash_chain','path_jump',
                       'dash_association_failed','two_dashes_uncorroborated','target_outside_image'):
            original=dict(valid=False,reason=reason,reference_set=True,reference_normalized=.5)
            self.assertIs(guide_path(result,original),original)

    def test_outer_edge_and_interior_divider_are_distinct_but_both_can_guide(self):
        for mirror in (False,True):
            for failure,kind in ((None,'divider'),('outer','outer')):
                result=near_paint(mirror,failure)
                guided=guide_path(result,self.prediction(result))
                self.assertTrue(guided['valid'],guided)
                self.assertEqual(guided['boundary_kind'],kind)

    def test_boundary_direction_really_changes_the_direction_term(self):
        result=near_paint()
        joint=guide_path(result,self.prediction(result))
        edge=dict(joint['boundary_support'])
        points=np.asarray(edge['points'],float)
        points[:,0]+=np.linspace(10,-10,len(points))
        edge['points']=points.tolist()
        fused=combine_direction(result,dict(joint,boundary_support=edge))
        self.assertNotEqual(fused['guidance_heading_error_degrees'],joint['heading_error_degrees'])
        self.assertAlmostEqual(fused['guidance_heading_error_degrees'],
            .65*joint['heading_degrees']+.35*fused['boundary_heading_degrees'],places=1)
        reversed_edge=dict(edge,points=points[::-1].tolist())
        self.assertIsNone(boundary_direction(result,reversed_edge,joint['heading_degrees']))

    def test_noninformative_or_opposing_edge_does_not_dilute_a_valid_white_path(self):
        result=near_paint()
        for dx in (0,30):
            points=np.c_[np.linspace(180+dx,180,9),np.linspace(100,260,9)].tolist()
            original=dict(valid=True,heading_degrees=-20,reference_heading_degrees=0,
                          boundary_support=dict(points=points,samples=9,side='right'))
            combined=combine_direction(result,original)
            self.assertEqual(combined['guidance_mode'],'white_path')
            self.assertNotIn('guidance_heading_error_degrees',combined)

    def test_perspective_convergence_cannot_steer_a_straight_white_path(self):
        result=near_paint()
        for mirror in (False,True):
            points=np.c_[np.linspace(128,12,9),np.linspace(98,320,9)]
            if mirror:points[:,0]=479-points[:,0]
            path=dict(valid=True,normalized_error=0,heading_degrees=0,heading_error_degrees=0,
                      reference_heading_degrees=0,boundary_support=dict(points=points.tolist(),
                      samples=9,side='right' if mirror else 'left'))
            combined=combine_direction(result,path)
            self.assertEqual(combined['guidance_mode'],'white_path')
            pilot=object.__new__(AutoPilot)
            pilot.config=PilotConfig(lap_mode=True,continuous=True,boundary_guidance=True)
            self.assertEqual(pilot.wanted_angle(combined),0)

    def test_fallback_is_not_full_evidence_and_cannot_renew_recovery(self):
        result=near_paint();path=guide_path(result,self.prediction(result));recovery=TurnRecovery()
        for i in range(10):
            recovery.observe_valid(dict(path=path,source_number=i,received_at=10+i*.1),
                                   10+i*.1,-40,.24,'left')
        self.assertFalse(recovery.ready)
        self.assertIsNone(recovery.last_good)


class JointControlTests(unittest.TestCase):
    def pilot(self,**settings):
        pilot=object.__new__(AutoPilot)
        pilot.config=PilotConfig(lap_mode=True,continuous=True,boundary_guidance=True,**settings)
        return pilot

    def test_guidance_is_opt_in_and_requires_a_direction_gain(self):
        self.assertFalse(PilotConfig().boundary_guidance)
        for value in (1,None,'true'):
            with self.assertRaises(ValueError):PilotConfig(boundary_guidance=value)
        with self.assertRaises(ValueError):PilotConfig(boundary_guidance=True)
        for value in (0,.1,'bad',float('nan')):
            with self.assertRaises(ValueError):self.pilot(heading_gain=value)

    def test_current_confirmed_bend_cannot_be_cancelled_by_opposite_lateral_offset(self):
        pilot=self.pilot(kp=60,heading_gain=1)
        for sign in (-1,1):
            path=dict(normalized_error=-sign*.6,heading_error_degrees=0,
                      guidance_heading_error_degrees=sign*40,boundary_turn_agreement=True)
            self.assertEqual(pilot.wanted_angle(path),sign*20)
            path['boundary_turn_agreement']=False
            self.assertAlmostEqual(pilot.wanted_angle(path),sign*11.2)
            pilot.config=replace(pilot.config,boundary_guidance=False)
            self.assertAlmostEqual(pilot.wanted_angle(path),-sign*28.8)
            pilot.config=replace(pilot.config,boundary_guidance=True)

    def test_straight_p_control_and_hardware_limits_are_preserved(self):
        pilot=self.pilot(kp=35,heading_gain=1)
        path=dict(normalized_error=.2,heading_error_degrees=0,guidance_heading_error_degrees=0)
        self.assertAlmostEqual(pilot.wanted_angle(path),2.8)
        for error,heading,limit in ((1,80,85),(-1,-80,-105)):
            self.assertEqual(pilot.wanted_angle(dict(path,normalized_error=error,
                guidance_heading_error_degrees=heading)),limit)


class JointSafetyTests(unittest.TestCase):
    setUp=test_pilot.PilotTests.setUp

    def test_joint_mode_starts_disarmed_and_stale_frames_still_stop(self):
        self.pilot.configure(dict(lap_mode=True,continuous=True,boundary_guidance=True,
                                  heading_gain=1,speed=.30))
        self.assertFalse(self.control.armed)
        self.assertEqual(self.servo.commands,[])
        result=near_paint();tracker=LanePath();tracker.reference=.5
        self.monitor.frame['path']=guide_path(result,tracker.predict(result,completion_priority=True))
        self.pilot.start('one');self.now.return_value=1000.1
        self.pilot.heartbeat('one');self.pilot.tick()
        self.assertEqual(self.control.outputs,(.24,.24))
        self.monitor.frame['age']=.25;self.monitor.frame['number']+=1
        self.now.return_value=1000.15;self.pilot.tick()
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))

    def test_joint_mode_does_not_bypass_owner_or_browser_lease(self):
        self.pilot.configure(dict(lap_mode=True,continuous=True,boundary_guidance=True,heading_gain=1))
        self.monitor.frame['path']['boundary_guidance_enabled']=True
        self.pilot.start('one')
        with self.assertRaises(PermissionError):self.pilot.heartbeat('other')
        self.now.return_value=1000.71;self.pilot.tick()
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))

    def test_mode_changes_cannot_start_from_an_old_frame(self):
        self.pilot.configure(dict(lap_mode=True,continuous=True,boundary_guidance=True,heading_gain=1))
        with self.assertRaises(ValueError):self.pilot.start('one')
        self.assertEqual(self.pilot.status()['blocked_reason'],'settings_changed')
        self.assertFalse(self.control.armed)


class JointWebTests(unittest.TestCase):
    setUp=test_pilot.PilotWebTests.setUp
    post=test_pilot.PilotWebTests.post

    def test_mode_toggle_is_disarmed_requires_new_frames_and_straight_reference(self):
        self.monitor.pilot=self.pilot
        self.assertIn('auto-boundary-guidance',self.client.get('/').data.decode())
        self.assertEqual(self.post('reference').status_code,200)
        configured=self.post('settings',settings=dict(lap_mode=True,continuous=True,
                                                      boundary_guidance=True,heading_gain=1))
        self.assertEqual(configured.status_code,200)
        self.assertEqual(self.post('start').status_code,400)
        for _ in range(4):self.monitor.process_frame(test_pilot.sample_track())
        self.assertTrue(self.monitor.prediction['boundary_guidance_enabled'])
        self.assertFalse(self.monitor.prediction['reference_set'])
        self.assertEqual(self.post('reference').status_code,200)
        self.assertEqual(self.control.outputs,(0,0))
        self.assertFalse(self.control.armed)
        self.assertEqual(self.post('start').status_code,200)
        self.assertEqual(self.post('settings',settings={'boundary_guidance':False}).status_code,409)
        stopped=self.client.post('/manual/stop',headers=self.headers,
                                 json={'client':'other','emergency':True})
        self.assertEqual(stopped.status_code,200)
        self.assertFalse(self.pilot.active)
        self.assertFalse(self.control.armed)


if __name__=='__main__':unittest.main()
