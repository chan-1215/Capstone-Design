"""Export inspection images from a captured Unity RGB frame, using OpenCV."""
from pathlib import Path
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'Auto Driving/With Steering/dataset/UnityDriving'
sys.path.insert(0,str(PROJECT/'Tools'))
from opencv_lane_view import analyze

source=PROJECT/'Diagnostics/runtime_20261111/frame_03/unity_policy_input.png'
out=PROJECT/'Diagnostics/vision_stages_20261111'
out.mkdir(exist_ok=True)
image=cv2.imdecode(np.frombuffer(source.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
smooth=cv2.GaussianBlur(image,(5,5),0)
hsv=cv2.cvtColor(smooth,cv2.COLOR_BGR2HSV)
yellow=cv2.inRange(hsv,(18,75,65),(42,255,255))
white=cv2.inRange(hsv,(0,0,155),(179,65,255))
for mask in (yellow,white):
    mask[:int(image.shape[0]*.1)]=0
    mask[int(image.shape[0]*.94):]=0
yellow=cv2.morphologyEx(yellow,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
overlay,result=analyze(image)
for name,frame in [('yellow_mask.png',yellow),('white_mask.png',white),('tracking.png',overlay)]:
    (out/name).write_bytes(cv2.imencode('.png',frame)[1].tobytes())
import json
(out/'source.json').write_bytes((json.dumps({'source':'../runtime_20261111/frame_03/unity_policy_input.png','method':'offline reprocessing of captured RGB with opencv_lane_view.analyze','result':result},indent=2)+'\n').encode('utf-8'))
print(result)
