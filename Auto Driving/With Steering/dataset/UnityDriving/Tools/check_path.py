"""Offline check of the same spline and bicycle equations; NOT a Unity render test."""
from pathlib import Path
import json,re,math
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'Assets/Scripts/TrackGeometry.cs').read_text(encoding='utf-8')
k=np.array([(float(x),float(z)) for x,z in re.findall(r'new Vector2\(([-.\d]+)f,([-.\d]+)f\)',source)])
assert len(k)==21,len(k)
p=[]
for j in range(len(k)):
 a,b,c,d=k[(j-1)%len(k)],k[j],k[(j+1)%len(k)],k[(j+2)%len(k)]
 for t in np.arange(30)/30:
  p.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
p=np.array(p);tangent=np.roll(p,-1,axis=0)-np.roll(p,1,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
right=np.c_[tangent[:,1],-tangent[:,0]]
spans=np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1);station=np.r_[0,np.cumsum(spans)[:-1]];length=spans.sum()
def at(s,offset=0):
 s=s%length;i=max(0,np.searchsorted(station,s,side='right')-1);j=(i+1)%len(p);f=(s-station[i])/spans[i]
 r=right[i]*(1-f)+right[j]*f;r/=np.linalg.norm(r)
 return p[i]*(1-f)+p[j]*f+r*offset
def nearest(pos):return np.argmin(np.sum((p-pos)**2,axis=1))
def signed(pos,n):return np.dot(pos-p[n],right[n])
results=[];trails=[]
for lane in range(2):
 for variant in range(3):
  offset=(-1 if lane==0 else 1)*.46/4;s=length-.5
  pos=at(s,offset+(variant-1)*.025);f=at(s+.025,offset)-at(s,offset);yaw=math.atan2(f[0],f[1])+(variant-1)*math.radians(5)
  speed=0;wheel=0;progress=0;prev=s;minmargin=1;maxcte=0;trail=[]
  for step in range(12000):
   n=nearest(pos);s=station[n];f=np.array([math.sin(yaw),math.cos(yaw)]);rear=pos-f*.122/2
   d=at(s+.17,offset)-rear;lx=math.cos(yaw)*d[0]-math.sin(yaw)*d[1]
   target=np.clip(math.degrees(math.atan2(2*.122*lx,max(.001,float(np.dot(d,d))))),-35,35)
   wheel+=np.clip(target-wheel,-140*.02,140*.02);v=.28/(1+abs(target)/70)
   speed+=np.clip(v-speed,-.7*.02,.7*.02);rate=speed/.122*math.tan(math.radians(wheel))
   rear+=np.array([math.sin(yaw+rate*.01),math.cos(yaw+rate*.01)])*speed*.02;yaw+=rate*.02
   f=np.array([math.sin(yaw),math.cos(yaw)]);r=np.array([math.cos(yaw),-math.sin(yaw)]);pos=rear+f*.122/2
   n=nearest(pos);s=station[n];progress+=(s-prev+length/2)%length-length/2;prev=s
   cte=signed(pos,n)-offset;maxcte=max(maxcte,abs(cte))
   for x in [-.146/2,.146/2]:
    for z in [-.189/2,.189/2]:
     corner=pos+r*x+f*z;nn=nearest(corner);minmargin=min(minmargin,.23-abs(signed(corner,nn)))
   trail.append(pos.copy())
   if progress>=length:break
  results.append(dict(lane=lane,variant=variant,lapped=bool(progress>=length),seconds=(step+1)*.02,max_cte_m=float(maxcte),minimum_road_margin_m=float(minmargin)))
  trails.append(np.array(trail))
out=ROOT/'Diagnostics';out.mkdir(exist_ok=True)
(out/'offline_path_check.json').write_text(json.dumps(dict(scope='offline equations only; Unity rendering and capture unverified',track_length_m=float(length),runs=results),indent=2))
im=Image.new('RGB',(900,1050),'#ddd9ce');draw=ImageDraw.Draw(im)
def xy(a):return [(float(450+x*285),float(500-z*285)) for x,z in a]
for off,col in [(0,'#191b20'),(-.23,'#eebd18'),(.23,'#eebd18'),(0,'#eebd18')]:
 if off==0 and col=='#191b20':
  edge=np.vstack([p-right*.23,(p+right*.23)[::-1]]);draw.polygon(xy(edge),fill=col)
 else:draw.line(xy(np.vstack([p+right*off,(p+right*off)[0]])),fill=col,width=4)
for off in [-.115,.115]:
 for s in np.arange(0,length,.15):draw.line(xy(np.array([at(s,off),at(s+.075,off)])),fill='white',width=3)
for trail in trails:draw.line(xy(trail[::8]),fill='#32bf6f',width=1)
draw.text((30,25),'PHOTO-BASED TRACK APPROXIMATION / OFFLINE PATH CHECK',fill='black')
draw.text((30,980),'Green: simulated teacher paths. Track dimensions unmeasured.',fill='black')
im.save(out/'track_layout.png')
print(json.dumps(results,indent=2))
if not all(r['lapped'] and r['minimum_road_margin_m']>0 for r in results):raise SystemExit(2)
