"""Train the camera-only NumPy MLP used by Unity VisionPolicy.
Original source trajectories are retained in AlignedDataset/labels.csv.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
from pathlib import Path
import csv,json,math,hashlib,argparse
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
COLS,ROWS,TOP,BOTTOM=12,8,.04,.62

def features(path):
    rgb=np.asarray(Image.open(path).convert('RGB'),dtype=np.float32)
    h,w=rgb.shape[:2];out=[]
    for row in range(ROWS):
        for col in range(COLS):
            a=rgb[math.floor((TOP+(BOTTOM-TOP)*row/ROWS)*h):math.floor((TOP+(BOTTOM-TOP)*(row+1)/ROWS)*h):2,col*w//COLS:(col+1)*w//COLS:2]
            r,g,b=a[:,:,0],a[:,:,1],a[:,:,2];maximum=a.max(2);minimum=a.min(2)
            out.extend([np.mean((maximum<115)&(maximum-minimum<60)),np.mean((minimum>150)&(maximum-minimum<60)),np.mean((r>100)&(g>90)&(b<110)&(r>b*1.35)&(g>b*1.25))])
    return np.asarray(out,dtype=np.float32)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=ROOT/'AlignedDatasetFrontCamera');parser.add_argument('--epochs',type=int,default=400);args=parser.parse_args()
    data=args.data;cache=data/'features.npz'
    rows=list(csv.DictReader((data/'labels.csv').open(encoding='utf-8-sig')))
    signature=hashlib.sha256((data/'labels.csv').read_bytes()+(data/'metadata.json').read_bytes()+str(max((data/r['image']).stat().st_mtime_ns for r in rows)).encode()).hexdigest()
    cached=False
    if cache.exists():
        with np.load(cache) as z:
            if 'signature' in z and str(z['signature'])==signature:
                X,Y,groups=z['x'],z['y'],z['groups'];cached=True
    if not cached:
        X=np.stack([features(data/r['image']) for r in rows]);Y=np.array([[float(r['label_wheel_deg'])/35,float(r['label_speed_m_s'])/.28] for r in rows],dtype=np.float32)
        groups=np.array([r['seed']+'_'+r['lane'] for r in rows]);np.savez_compressed(cache,x=X,y=Y,groups=groups,signature=signature)
    unique,counts=np.unique(groups,return_counts=True);validation=unique[np.argmin(counts)]
    train_mask=groups!=validation;val_mask=~train_mask
    trainX,trainY=X[train_mask],Y[train_mask];valX,valY=X[val_mask],Y[val_mask]
    # Horizontal mirroring changes left/right steering sign, not target speed.
    mirror=trainX.reshape(-1,ROWS,COLS,3)[:,:,::-1,:].reshape(-1,ROWS*COLS*3)
    mirrorY=trainY.copy();mirrorY[:,0]*=-1
    trainX=np.concatenate([trainX,mirror]);trainY=np.concatenate([trainY,mirrorY])
    mean=trainX.mean(0);std=np.maximum(trainX.std(0),.05);trainX=(trainX-mean)/std;valX=(valX-mean)/std
    rng=np.random.default_rng(20261110);sizes=[ROWS*COLS*3,64,32,2]
    params=[]
    for a,b in zip(sizes[:-1],sizes[1:]):params.extend([(rng.standard_normal((a,b))*np.sqrt(2/a)).astype(np.float32),np.zeros(b,dtype=np.float32)])
    moments=[np.zeros_like(v) for v in params];variances=[np.zeros_like(v) for v in params]
    def forward(x):
        a=np.maximum(0,x@params[0]+params[1]);b=np.maximum(0,a@params[2]+params[3]);return a,b,b@params[4]+params[5]
    best=float('inf');best_params=None;best_epoch=0;step=0
    for epoch in range(args.epochs):
        order=rng.permutation(len(trainX))
        for start in range(0,len(order),128):
            ids=order[start:start+128];x=trainX[ids];y=trainY[ids];a,b,out=forward(x)
            dy=2*(out-y)*np.array([1,.2],dtype=np.float32)/len(x)
            db=(dy@params[4].T)*(b>0);da=(db@params[2].T)*(a>0)
            grads=[x.T@da,da.sum(0),a.T@db,db.sum(0),b.T@dy,dy.sum(0)]
            step+=1
            for j,(v,g) in enumerate(zip(params,grads)):
                if j%2==0:g=g+1e-5*v
                moments[j]=.9*moments[j]+.1*g;variances[j]=.999*variances[j]+.001*g*g
                v-=.001*(moments[j]/(1-.9**step))/(np.sqrt(variances[j]/(1-.999**step))+1e-8)
        pred=forward(valX)[2];mae=float(np.abs(pred[:,0]-valY[:,0]).mean()*35)
        if mae<best:best=mae;best_params=[v.copy() for v in params];best_epoch=epoch
        if epoch%25==0:print(f'epoch={epoch} validation steering MAE={mae:.3f} deg',flush=True)
        if epoch-best_epoch>65:break
    params[:]=best_params
    pred=forward(valX)[2]
    report={'model':'RGB mask-grid MLP 288-64-32-2','source':'existing Unity trajectories, current-camera rerenders and relabelled recovery perturbations','validation_group':str(validation),'train_scenario_groups':[str(v) for v in unique if v!=validation], 'source_scenario_groups':len(unique),'train_images_before_mirroring':int(train_mask.sum()),'training_examples':len(trainX),'validation_images':int(val_mask.sum()),'best_epoch':best_epoch,'validation_steering_mae_deg':best,'validation_speed_mae_m_s':float(np.abs(pred[:,1]-valY[:,1]).mean()*.28),'independent_test':'closed-loop Unity checks required; no independent image test set with only three source scenarios'}
    cfg=json.loads((data/'render_config.json').read_text(encoding='utf-8-sig'))
    report.update(dataset=data.name,camera_mount_revision=3)
    model={'columns':COLS,'rows':ROWS,'cropTop':TOP,'cropBottom':BOTTOM,'cameraMountRevision':3,'cameraHeight':cfg['cameraHeight'],'cameraZ':cfg['cameraForward'],'cameraPitch':cfg['cameraPitch'],'verticalFov':cfg['cameraVerticalFov'],'yEdges':[math.floor((TOP+(BOTTOM-TOP)*r/ROWS)*240) for r in range(ROWS+1)],'hidden1':64,'hidden2':32,'mean':mean.tolist(),'std':std.tolist()}
    for name,p in zip(['w1','b1','w2','b2','w3','b3'],params):model[name]=p.ravel().tolist()
    out=ROOT/'Assets/Resources';out.mkdir(exist_ok=True)
    (out/'VisionPolicy.json').write_text(json.dumps(model,separators=(',',':')),encoding='utf-8')
    (ROOT/'Diagnostics/vision_training.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
