"""Completion profile regressions; synthetic images and fake GPIO only."""

from types import SimpleNamespace
from dataclasses import asdict
import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from autonomous import AutoPilot, PilotConfig, steering_step
from lane_path import LanePath, near_road_fraction, boundary_evidence, observed_row_corridor, dash_axes, near_reflection_candidate
from turn_recovery import corridor_observation
import test_pilot


def sharp_bend(mirror=False):
    height,width=360,480
    points=np.array([(396.3,338.2),(320.5,239.4),(244.,172.8),
                     (164.5,138.3),(79.7,121.5)])
    fit=np.polyfit(points[:3,1]/height,points[:3,0]/width,2)
    road=np.full((height,width),255,np.uint8)
    yellow=np.zeros_like(road);dashes=np.zeros_like(road)
    ys=np.arange(90,height)
    edge=np.column_stack((np.polyval(fit,ys/height)*width-140,ys)).round().astype(np.int32)
    cv2.polylines(yellow,[edge],False,255,7)
    marks=[]
    for point in points:
        slope=np.polyval(np.polyder(fit),point[1]/height)*width/height
        axis=np.array([slope,1.]);axis/=np.linalg.norm(axis)
        cv2.line(dashes,tuple((point-axis*13).round().astype(int)),
                 tuple((point+axis*13).round().astype(int)),255,7)
        marks.append(dict(center=point.tolist(),dash_candidate=True,length_px=26))
    if mirror:
        yellow,road,dashes=(np.fliplr(mask).copy() for mask in (yellow,road,dashes))
        for mark in marks:mark['center'][0]=width-1-mark['center'][0]
    return SimpleNamespace(frame=np.zeros((height,width,3),np.uint8),
                           yellow=yellow,road=road,dashes=dashes,markings=marks)


def compressed_bend(mirror=False):
    height,width=360,480
    points=np.array([(252.5,192.2),(172.7,151.1),(86.2,128.6)])
    directions=np.diff(points,axis=0)
    directions/=np.linalg.norm(directions,axis=1)[:,None]
    tangents=np.vstack((directions[0],directions[0]+directions[1],directions[1]))
    tangents/=np.linalg.norm(tangents,axis=1)[:,None]
    normals=np.column_stack((-tangents[:,1],tangents[:,0]))
    yellow=np.zeros((height,width),np.uint8);dashes=np.zeros_like(yellow)
    cv2.polylines(yellow,[(points+normals*75).round().astype(np.int32)],False,255,7)
    marks=[]
    for point,axis in zip(points,tangents):
        cv2.line(dashes,tuple((point-axis*13).round().astype(int)),
                 tuple((point+axis*13).round().astype(int)),255,7)
        marks.append(dict(center=point.tolist(),dash_candidate=True,length_px=26))
    road=np.full_like(yellow,255)
    if mirror:
        yellow,road,dashes=(np.fliplr(mask).copy() for mask in (yellow,road,dashes))
        for mark in marks:mark['center'][0]=width-1-mark['center'][0]
    return SimpleNamespace(frame=np.zeros((height,width,3),np.uint8),
                          yellow=yellow,road=road,dashes=dashes,markings=marks)


class LapPerceptionTests(unittest.TestCase):
    def test_tiny_near_glints_cannot_replace_the_large_actual_paint_anchor(self):
        for mirror in (False,True):
            points=np.array([[296.6,322.9],[247.8,217.3],[216.1,148.7],[195.6,103.4],[178.5,76.5]])
            road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
            fit=np.polyfit(points[:,1]/360,points[:,0]/480,2);ys=np.arange(75,350)
            cv2.polylines(yellow,[np.c_[np.polyval(fit,ys/360)*480+140,ys].round().astype(np.int32)],False,255,9)
            marks=[]
            for i,point in enumerate(points):
                axis=np.array([.45,1]);axis/=np.linalg.norm(axis)
                length=(94,61,40,27,15)[i];thickness=(25,20,16,13,7)[i]
                cv2.line(dashes,tuple(np.rint(point-axis*length/2).astype(int)),
                         tuple(np.rint(point+axis*length/2).astype(int)),255,thickness)
                marks.append(dict(center=point.tolist(),length_px=length,thickness_px=thickness,
                                  fill_ratio=.8,area_px=length*thickness*.8,dash_candidate=True))
            for x,y,length,thickness in ((205.4,342.7,26.3,5.6),(197.,303.5,18.7,4.7)):
                cv2.line(dashes,(round(x),round(y-length/2)),(round(x),round(y+length/2)),255,5)
                marks.append(dict(center=[x,y],length_px=length,thickness_px=thickness,
                                  area_px=96 if y>330 else 54.5,fill_ratio=.64,dash_candidate=True))
            if mirror:
                yellow,dashes=(np.fliplr(mask).copy() for mask in (yellow,dashes))
                for m in marks:m['center'][0]=479-m['center'][0]
                points[:,0]=479-points[:,0]
            result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                   yellow=yellow,dashes=dashes,markings=marks)
            tracker=LanePath();tracker.reference=.51
            prediction=tracker.predict(result,completion_priority=True)
            self.assertTrue(prediction['valid'],prediction)
            self.assertEqual(prediction['checks']['near_reflections_rejected'],2)
            self.assertEqual(prediction['points'][0],points[0].tolist())
            self.assertEqual(len(prediction['points']),5)

    def test_near_reflections_need_two_larger_forward_paint_observations_to_be_rejected(self):
        mark=dict(center=[205.4,342.7],length_px=26.3,thickness_px=5.6,area_px=96,
                  fill_ratio=.649,dash_candidate=True)
        forward=[dict(center=[247.8,217.3],length_px=61.4,thickness_px=19.7,
                      fill_ratio=.86,dash_candidate=True),
                 dict(center=[216.1,148.7],length_px=39.6,thickness_px=16.3,
                      fill_ratio=.84,dash_candidate=True)]
        result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),markings=[mark]+forward)
        self.assertTrue(near_reflection_candidate(result,mark))
        for changes in ({'fill_ratio':.8},{'length_px':50},{'side_clipped':True},
                        {'area_px':500},{'center':[205.4,180.]},{'thickness_px':15}):
            self.assertFalse(near_reflection_candidate(result,dict(mark,**changes)),changes)
        result.markings=[mark]+forward[:1]
        self.assertFalse(near_reflection_candidate(result,mark))

    def test_target_may_use_actual_paint_not_just_its_centre_but_never_an_empty_extension(self):
        for mirror in (False,True):
            for failure in (None,'paint','edge','road','reference'):
                points=np.array([[185.,325.],[57.,253.]])
                road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
                axis=points[0]-points[1];axis/=np.linalg.norm(axis)
                normal=np.array([-axis[1],axis[0]])
                edge=points-normal*100
                cv2.line(yellow,tuple(np.rint(edge[0]+axis*50).astype(int)),
                         tuple(np.rint(edge[1]-axis*50).astype(int)),255,9)
                marks=[]
                for point in points:
                    cv2.line(dashes,tuple(np.rint(point-axis*32).astype(int)),
                             tuple(np.rint(point+axis*32).astype(int)),255,13)
                    marks.append(dict(center=point.tolist(),length_px=64,dash_candidate=True))
                if failure=='paint':dashes[:253]=0
                elif failure=='edge':yellow[:]=0
                elif failure=='road':road[295:339]=0
                if mirror:
                    yellow,dashes,road=(np.fliplr(mask).copy() for mask in (yellow,dashes,road))
                    for mark in marks:mark['center'][0]=479-mark['center'][0]
                result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                       yellow=yellow,dashes=dashes,markings=marks)
                tracker=LanePath()
                if failure!='reference':tracker.reference=.5
                prediction=tracker.predict(result,completion_priority=True)
                self.assertEqual(prediction['valid'],failure is None,(mirror,failure,prediction))
                if prediction['valid']:
                    self.assertTrue(prediction['checks']['target_on_observed_paint'])
                    self.assertLessEqual(prediction['target_y_normalized'],.70)
                    self.assertGreaterEqual(prediction['boundary_support']['samples'],8)

    def test_single_oblique_paint_requires_reference_shape_current_edge_and_road(self):
        for mirror in (False,True):
            for failure in (None,'reference','edge','road','shape','wrong_edge'):
                centre=np.array([175.,240.]);axis=np.array([.9,.43589]);axis/=np.linalg.norm(axis)
                road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
                ends=np.array([centre-axis*45,centre+axis*45])
                normal=np.array([-axis[1],axis[0]])
                edge=ends-normal*90
                if failure=='wrong_edge':edge=np.array([[300,90],[300,340]])
                cv2.line(yellow,tuple(np.rint(edge[0]).astype(int)),tuple(np.rint(edge[1]).astype(int)),255,9)
                cv2.line(dashes,tuple(np.rint(ends[0]).astype(int)),tuple(np.rint(ends[1]).astype(int)),255,13)
                mark=dict(center=centre.tolist(),length_px=90,thickness_px=13,fill_ratio=.85,
                          aspect_ratio=6.9,dash_candidate=True)
                if failure=='edge':yellow[:]=0
                elif failure=='road':road[295:339]=0
                elif failure=='shape':mark['fill_ratio']=.61
                if mirror:
                    yellow,dashes,road=(np.fliplr(mask).copy() for mask in (yellow,dashes,road))
                    mark['center'][0]=479-mark['center'][0]
                result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                       yellow=yellow,dashes=dashes,markings=[mark])
                tracker=LanePath()
                if failure!='reference':tracker.reference=.5
                predicted=tracker.predict(result,completion_priority=True)
                self.assertEqual(predicted['valid'],failure is None,(mirror,failure,predicted))
                strict=LanePath();strict.reference=.5
                self.assertFalse(strict.predict(result)['valid'])
                if predicted['valid']:
                    self.assertEqual(predicted['source'],'single_dash_boundary')
                    self.assertEqual(predicted['observed_dash_count'],1)
                    self.assertEqual(predicted['speed_scale'],.8)
                    self.assertGreaterEqual(predicted['boundary_support']['samples'],8)
                    self.assertTrue(predicted['adaptive_target'])
                    self.assertEqual(predicted['forward_direction'],'right' if mirror else 'left')

    def test_partial_row_evidence_does_not_hide_complete_normal_evidence(self):
        row=dict(samples=7,side='right',method='image_rows')
        normal=dict(samples=9,side='right',method='path_normals')
        for alternative in (normal,None,dict(samples=7,side='right')):
            with patch('lane_path._row_boundary_evidence',return_value=row), patch(
                    'lane_path._normal_boundary_evidence',return_value=alternative) as probe:
                selected=boundary_evidence(None,None,None,{},True,minimum_samples=8)
                self.assertIs(selected,normal if alternative is normal else row)
                probe.assert_called_once()
        with patch('lane_path._row_boundary_evidence',return_value=row), patch(
                'lane_path._normal_boundary_evidence') as probe:
            self.assertIs(boundary_evidence(None,None,None),row)
            probe.assert_not_called()

    def test_quantized_short_span_boundary_is_inclusive_without_widening_it(self):
        for mirror in (False,True):
            for offset in (0,.1):
                points=np.array([(232.3,272.7),(129.8,208.8+offset)])
                road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
                axis=points[0]-points[1];axis/=np.linalg.norm(axis)
                cv2.line(yellow,(300,209),(403,273),255,7)
                marks=[]
                for point in points:
                    cv2.line(dashes,tuple(np.rint(point-axis*25).astype(int)),
                             tuple(np.rint(point+axis*25).astype(int)),255,9)
                    marks.append(dict(center=point.tolist(),dash_candidate=True,length_px=50))
                if mirror:
                    yellow,dashes=np.fliplr(yellow).copy(),np.fliplr(dashes).copy()
                    for mark in marks:mark['center'][0]=479-mark['center'][0]
                result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                       yellow=yellow,dashes=dashes,markings=marks)
                path=LanePath().predict(result)
                self.assertEqual(path['valid'],offset==0,(mirror,offset,path))
                completed=LanePath().predict(result,completion_priority=True)
                self.assertTrue(completed['valid'],completed)
                self.assertTrue(completed['adaptive_target'])
                self.assertGreaterEqual(completed['target'][1],min(p[1] for p in completed['points'])-.1)

    def test_oblique_two_marks_use_only_an_observed_bounded_target_in_completion_mode(self):
        for mirror in (False,True):
            for failure in (None,'edge','axis','road','too_near'):
                points=np.array([(168.4,271.8),(51.2,219.3)])
                if failure=='too_near':points[:,1]+=40
                road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
                fit=np.polyfit(points[:,1]/360,points[:,0]/480,1);ys=np.arange(80,360)
                edge=np.c_[np.polyval(fit,ys/360)*480+240,ys].round().astype(np.int32)
                cv2.polylines(yellow,[edge],False,255,7)
                axis=points[0]-points[1];axis/=np.linalg.norm(axis)
                if failure=='axis':axis=np.array([0.,1.])
                marks=[]
                for point in points:
                    cv2.line(dashes,tuple(np.rint(point-axis*25).astype(int)),
                             tuple(np.rint(point+axis*25).astype(int)),255,9)
                    marks.append(dict(center=point.tolist(),dash_candidate=True,length_px=50))
                if failure=='edge':yellow[:]=0
                elif failure=='road':road[295:339]=0
                if mirror:
                    yellow,dashes,road=(np.fliplr(mask).copy() for mask in (yellow,dashes,road))
                    for mark in marks:mark['center'][0]=479-mark['center'][0]
                result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                       yellow=yellow,dashes=dashes,markings=marks)
                self.assertFalse(LanePath().predict(result)['valid'])
                path=LanePath().predict(result,completion_priority=True)
                self.assertEqual(path['valid'],failure is None,(mirror,failure,path))
                if path['valid']:
                    self.assertTrue(path['adaptive_target'])
                    self.assertLessEqual(path['target_y_normalized'],.70)
                    self.assertGreaterEqual(path['target'][1],min(p[1] for p in path['points'])-.1)
                    self.assertLessEqual(path['target'][1],max(p[1] for p in path['points'])+.1)

    def test_large_side_clipped_paint_needs_intact_neighbours_and_an_independent_edge(self):
        points=np.array([(448.2,196.4),(372.4,133.2),(297.5,102.),(221.1,82.7)])
        for failure in (None,'edge','axis','short_fragment','one_neighbour'):
            road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
            fit=np.polyfit(points[:,1]/360,points[:,0]/480,2)
            ys=np.arange(80,210)
            edge=np.c_[np.polyval(fit,ys/360)*480-150,ys].round().astype(np.int32)
            cv2.polylines(yellow,[edge],False,255,7)
            marks=[]
            for i,point in enumerate(points):
                axis=np.array([.8,.6]) if i==0 else np.array([1.,.5])
                if failure=='axis' and i==0:axis=np.array([0.,1.])
                axis/=np.linalg.norm(axis)
                cv2.line(dashes,tuple(np.rint(point-axis*40).astype(int)),
                         tuple(np.rint(point+axis*40).astype(int)),255,12)
                marks.append(dict(center=point.tolist(),dash_candidate=True,length_px=80,
                                  fill_ratio=.75,aspect_ratio=5,thickness_px=12,side_clipped=i==0))
            if failure=='edge':yellow[:]=0
            elif failure=='short_fragment':marks[0]['length_px']=30
            elif failure=='one_neighbour':marks=marks[:2]
            result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                   yellow=yellow,dashes=dashes,markings=marks)
            path=LanePath().predict(result,completion_priority=True)
            self.assertEqual(path['valid'],failure is None,(failure,path))
            if path['valid']:self.assertTrue(path['checks']['partial_paint_corroborated'])

    def test_observed_row_corridor_accepts_perspective_curve_but_requires_current_evidence(self):
        points=np.array([(371.,244.),(341.,163.),(299.,112.),(250.,80.)])
        fit=np.polyfit(points[:,1]/360,points[:,0]/480,2)
        for failure in (None,'wide_paint','near_road','corridor','fragment','paint'):
            road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
            edge=np.array([(58,90),(135,109),(159,128),(168,148),(169,167),
                           (167,186),(163,205),(157,224),(151,244),(130,359)],np.int32)
            cv2.polylines(yellow,[edge],False,255,31 if failure=='wide_paint' else 7)
            road[yellow>0]=0
            for point in points:
                slope=np.polyval(np.polyder(fit),point[1]/360)*480/360
                axis=np.array([slope,1.]);axis/=np.linalg.norm(axis)
                if failure=='paint':axis=np.array([1.,0.])
                cv2.line(dashes,tuple(np.rint(point-axis*13).astype(int)),
                         tuple(np.rint(point+axis*13).astype(int)),255,7)
            if failure=='near_road':road[295:339]=0
            elif failure=='corridor':road[:,225:280]=0
            elif failure=='fragment':yellow[170:210]=0
            result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                                   yellow=yellow,dashes=dashes)
            evidence=observed_row_corridor(result,fit,points,dash_axes(result),.5,{})
            self.assertEqual(evidence is not None,failure in (None,'wide_paint'),failure)
            if evidence:self.assertGreaterEqual(evidence['samples'],8)

    def test_target_band_keeps_observed_near_path_but_not_a_disconnected_near_edge(self):
        points=[(78.3,329.9),(145.,223.1),(166.8,149.9),(120.5,111.),(45.,97.6)]
        road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road);dashes=np.zeros_like(road)
        cv2.line(yellow,(354,80),(354,359),255,7)
        marks=[]
        for i,point in enumerate(points):
            axis=np.array([-.8 if i==0 else -.3 if i<3 else 2.,1.]);axis/=np.linalg.norm(axis)
            centre=np.array(point)
            cv2.line(dashes,tuple(np.rint(centre-axis*13).astype(int)),
                     tuple(np.rint(centre+axis*13).astype(int)),255,7)
            marks.append(dict(center=list(point),dash_candidate=True,length_px=26))
        result=SimpleNamespace(frame=np.zeros((360,480,3),np.uint8),road=road,
                               yellow=yellow,dashes=dashes,markings=marks)
        path=LanePath().predict(result,completion_priority=True)
        self.assertTrue(path['valid'],path)
        self.assertTrue(path['checks']['target_band'])
        self.assertTrue(path['checks']['target_band_near_edge_connected'])
        self.assertEqual(len(path['points']),2)
        self.assertTrue(min(p[1] for p in path['points'])<=198<=max(p[1] for p in path['points']))
        yellow[300:315]=0
        self.assertFalse(LanePath().predict(result,completion_priority=True)['valid'])

    def test_only_an_internal_yellow_divider_can_bridge_the_near_patch(self):
        for failure in (None,'outer_edge','too_wide','missing_road'):
            road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road)
            yellow[:,224:256]=255;road[:,221:259]=0
            if failure=='outer_edge':road[:,259:]=0
            elif failure=='too_wide':yellow[:,200:280]=255;road[:,197:283]=0
            elif failure=='missing_road':road[:]=0
            result=SimpleNamespace(road=road,yellow=yellow)
            self.assertLess(near_road_fraction(result,.5),.9)
            supported=near_road_fraction(result,.5,allow_divider=True)>=.9
            self.assertEqual(supported,failure is None,failure)

    def test_perspective_convergence_need_not_give_identical_path_and_edge_slope(self):
        road=np.full((360,480),255,np.uint8);yellow=np.zeros_like(road)
        cv2.line(yellow,(160,100),(175,340),255,7)
        points=np.array([(280.,330.),(250.,230.),(230.,150.),(218.,100.)])
        result=SimpleNamespace(road=road,yellow=yellow)
        fit=np.polyfit(points[:,1]/360,points[:,0]/480,1)
        self.assertIsNone(boundary_evidence(result,fit,points))
        evidence=boundary_evidence(result,fit,points,allow_shallow=True)
        self.assertIsNotNone(evidence)
        self.assertGreaterEqual(evidence['samples'],8)
        yellow[210:270]=0
        self.assertIsNone(boundary_evidence(result,fit,points,allow_shallow=True))

    def test_compressed_curved_three_marks_use_observed_polyline_in_both_directions(self):
        for mirror,direction in ((False,'left'),(True,'right')):
            result=compressed_bend(mirror)
            self.assertFalse(LanePath().predict(result)['valid'])
            path=LanePath().predict(result,completion_priority=True)
            self.assertTrue(path['valid'],path)
            self.assertEqual(path['reason'],'observed_curve_corroborated')
            self.assertEqual(path['forward_direction'],direction)
            self.assertTrue(path['checks']['short_span_supported'])
            self.assertEqual(path['boundary_support']['method'],'paint_polyline_normals')
            self.assertTrue(path['adaptive_target'])
            self.assertLessEqual(path['target'][1],max(p[1] for p in path['points'])+.1)

    def test_polyline_cannot_bypass_paint_road_or_fragmented_boundary(self):
        for failure in ('road','edge','axis','fragment'):
            result=compressed_bend()
            if failure=='road':result.road[295:339]=0
            elif failure=='edge':result.yellow[:]=0
            elif failure=='fragment':result.yellow[:,150:177]=0
            else:
                result.dashes[:]=0
                for mark in result.markings:
                    x,y=np.rint(mark['center']).astype(int)
                    cv2.line(result.dashes,(x,y-13),(x,y+13),255,7)
            self.assertFalse(LanePath().predict(result,completion_priority=True)['valid'],failure)

    def test_polyline_recovery_uses_current_boundary_not_an_old_quadratic_fit(self):
        result=compressed_bend()
        path=LanePath().predict(result,completion_priority=True)
        self.assertTrue(path['valid'],path)
        path.update(reference_set=True,reference_normalized=.5)
        invalid=dict(valid=False,reason='insufficient_dashes',reference_set=True)
        self.assertTrue(corridor_observation(result,path,invalid)['supported'])
        result.yellow[:]=0
        self.assertFalse(corridor_observation(result,path,invalid)['supported'])

    def test_side_clipped_fragment_cannot_anchor_a_good_chain(self):
        # Use explicit geometry so segmentation rejection is not the only guard.
        result=sharp_bend()
        result.markings.insert(0,dict(center=[471,344],dash_candidate=True,
                                      length_px=30,side_clipped=True))
        cv2.rectangle(result.dashes,(462,330),(479,359),255,-1)
        path=LanePath().predict(result,completion_priority=True)
        self.assertTrue(path['valid'],path)
        self.assertNotIn([471,344],path['points'])

    def test_segmentation_distinguishes_side_and_bottom_clipping(self):
        from track_vision import _markings
        mask=np.zeros((200,300),np.uint8)
        cv2.rectangle(mask,(0,80),(12,110),255,-1)
        cv2.rectangle(mask,(120,160),(132,199),255,-1)
        marks=_markings(mask)[2]
        side=min(marks,key=lambda m:m['center'][0])
        bottom=max(marks,key=lambda m:m['center'][0])
        self.assertTrue(side['side_clipped'])
        self.assertFalse(bottom['side_clipped'])

    def test_near_curve_fit_can_override_bad_far_fit_only_in_completion_mode(self):
        for mirror,direction in ((False,'left'),(True,'right')):
            result=sharp_bend(mirror)
            self.assertFalse(LanePath().predict(result)['valid'])
            path=LanePath().predict(result,completion_priority=True)
            self.assertTrue(path['valid'],path)
            self.assertEqual(path['reason'],'near_centres_corroborated')
            self.assertEqual(len(path['points']),3)
            self.assertEqual(path['forward_direction'],direction)
            self.assertTrue(path['lap_corridor_supported'])

    def test_completion_near_fit_still_needs_current_road_edge_and_paint_axes(self):
        for failure in ('road','edge','axis','fragmented_edge'):
            result=sharp_bend()
            if failure=='road':result.road[295:339]=0
            elif failure=='edge':result.yellow[:]=0
            elif failure=='fragmented_edge':result.yellow[245:270]=0
            else:
                result.dashes[156:191,225:264]=0
                cv2.line(result.dashes,(230,173),(258,173),255,7)
            self.assertFalse(LanePath().predict(result,completion_priority=True)['valid'],failure)


class LapControlTests(unittest.TestCase):
    def setUp(self):
        test_pilot.PilotTests.setUp(self)
        self.pilot.configure(dict(lap_mode=True,continuous=True,kp=35,heading_gain=1,
                                  max_left_angle=105,max_right_angle=85))

    def test_profile_never_arms_or_moves_on_configuration(self):
        self.assertFalse(self.control.armed)
        self.assertEqual(self.control.outputs,(0,0))
        self.assertEqual(self.servo.commands,[])

    def test_small_centre_error_does_not_cause_constant_corrections(self):
        for error in (-.12,-.05,0,.05,.12):
            self.assertEqual(self.pilot.wanted_angle(dict(normalized_error=error)),0)

    def test_left_curve_is_not_cancelled_by_lateral_centre_error(self):
        self.assertLess(self.pilot.wanted_angle(dict(normalized_error=.53,heading_error_degrees=-40)),-20)
        self.assertGreater(self.pilot.wanted_angle(dict(normalized_error=-.53,heading_error_degrees=40)),20)

    def test_two_lane_tolerance_requires_independent_corridor_and_hard_bound(self):
        path=dict(normalized_error=.8,lap_corridor_supported=True)
        self.assertFalse(self.pilot.excessive_error(path))
        path['lap_corridor_supported']=False
        self.assertTrue(self.pilot.excessive_error(path))
        path.update(normalized_error=1.06,lap_corridor_supported=True)
        self.assertTrue(self.pilot.excessive_error(path))

    def test_profile_does_not_bypass_camera_or_stop(self):
        self.pilot.start('one')
        self.monitor.frame['age']=.21
        self.pilot.tick()
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))
        self.assertFalse(self.control.armed)

    def test_profile_is_explicit_and_requires_continuous_mode(self):
        self.assertFalse(PilotConfig().lap_mode)
        for invalid in (1,'true',None):
            with self.assertRaises(ValueError):PilotConfig(lap_mode=invalid,continuous=True)
        with self.assertRaises(ValueError):PilotConfig(lap_mode=True)
        completed=subprocess.run([sys.executable,'-B','track_web.py','--lap-mode'],
                                 capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,2)
        self.assertIn('--lap-mode',completed.stderr)

    def test_unwind_is_faster_but_turn_entry_and_opposite_sign_are_bounded(self):
        self.assertAlmostEqual(steering_step(-60,-7,60,.04,True),-55.2)
        self.assertAlmostEqual(steering_step(-60,-7,60,.04),-57.6)
        self.assertAlmostEqual(steering_step(-7,-60,60,.04,True),-9.4)
        self.assertEqual(steering_step(-2,40,60,.04,True),0)
        self.assertAlmostEqual(steering_step(0,40,60,.04,True),2.4)
        self.assertEqual(steering_step(2,-40,60,.04,True),0)


class ReferenceResumeTests(unittest.TestCase):
    def setUp(self):
        test_pilot.PilotTests.setUp(self)
        self.pilot.configure(dict(lap_mode=True,continuous=True))
        self.camera=dict(max_side=480,rotation=180)
        self.monitor.status=lambda:dict(settings=self.camera,original_size=[960,720])
        def restore(reference,heading):
            self.monitor.frame['path'].update(reference_normalized=reference,reference_set=True)
            self.monitor.frame['streak']=0
        self.monitor.restore_path_reference=restore
        self.reference=dict(reference=.53,camera=self.camera.copy(),path=dict(
            valid=True,source='dash_chain',observed_dash_count=4,target_y_normalized=.55,
            target_normalized=.53,reference_heading_degrees=-.9))
        self.run=[dict(event='start',reference=.53,settings=asdict(self.pilot.config)),
                  dict(event='stop',angle=5.7)]
        self.write_records()

    def write_records(self):
        directory=self.store.root/'runs';directory.mkdir(exist_ok=True)
        (directory/'reference_test.json').write_text(json.dumps(self.reference))
        (directory/'run_test.jsonl').write_text('\n'.join(json.dumps(r) for r in self.run))
        # NTFS file timestamps can be just ahead of Python's wall-clock sample.
        stamp=time.time()-1
        for name in ('reference_test.json','run_test.jsonl'):
            os.utime(directory/name,(stamp,stamp))

    def restore(self):
        return self.pilot.restore_reference('reference_test.json','run_test.jsonl')

    def test_resume_is_explicit_disarmed_and_retains_the_last_command_not_fake_neutral(self):
        self.restore()
        self.assertFalse(self.control.armed)
        self.assertFalse(self.pilot.active)
        self.assertEqual(self.control.outputs,(0,0))
        self.assertEqual(self.servo.commands,[])
        with self.assertRaises(ValueError):self.pilot.start('one')
        self.monitor.frame['streak']=3
        self.pilot.start('one')
        self.assertEqual(self.pilot.angle,5.7)
        self.assertEqual(self.servo.commands,[])

    def test_changed_camera_bad_calibration_or_missing_stop_cannot_resume(self):
        original=json.loads(json.dumps(self.reference))
        for failure in ('camera','heading','source','single','target','reference','angle','running'):
            self.reference=json.loads(json.dumps(original))
            self.run=[dict(event='start',reference=.53,settings=asdict(self.pilot.config)),
                      dict(event='stop',angle=5.7)]
            if failure=='camera':self.reference['camera']['rotation']=0
            elif failure=='heading':self.reference['path']['reference_heading_degrees']=30
            elif failure=='source':self.reference['path']['source']='single_dash_boundary'
            elif failure=='single':self.reference['path']['observed_dash_count']=1
            elif failure=='target':self.reference['path']['target_y_normalized']=.7
            elif failure=='reference':self.run[0]['reference']=.6
            elif failure=='angle':self.run[-1]['angle']=106
            else:self.run[-1]['event']='frame'
            self.write_records()
            with self.assertRaises(ValueError,msg=failure):self.restore()
            self.assertFalse(self.control.armed)

    def test_a_new_manual_neutral_command_supersedes_the_saved_command(self):
        self.restore()
        self.control.arm('manual')
        self.control.input('manual',1,dict(w=False,s=False,a=True,d=True),0,1,1)
        self.control.stop()
        self.monitor.frame['streak']=3
        self.pilot.start('one')
        self.assertEqual(self.pilot.angle,0)

    def test_paths_old_records_and_active_control_are_rejected(self):
        import os,time
        for name in ('../reference_test.json','reference_missing.json','run_test.jsonl'):
            with self.assertRaises(ValueError):self.pilot.restore_reference(name,'run_test.jsonl')
        path=self.store.root/'runs'/'reference_test.json'
        os.utime(path,(time.time()-7201,time.time()-7201))
        with self.assertRaises(ValueError):self.restore()
        self.control.arm('other')
        with self.assertRaises(PermissionError):self.restore()


if __name__=='__main__':
    unittest.main()
