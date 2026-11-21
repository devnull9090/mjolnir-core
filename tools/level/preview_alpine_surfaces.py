"""CPU material-weight/sampling proof. This is not an Unreal screenshot."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import gaussian_filter
from alpine_ecology import smooth,load
from alpine_sampling import stochastic,bilinear
from heightfield import load_heightfield


def write_pair(before,after,path,label):
    n=before.shape[0]
    canvas=Image.new('RGB',(before.shape[1]*2,n+28),'#181818')
    for i,values in enumerate((before,after)):
        canvas.paste(Image.fromarray(np.uint8(np.clip(values,0,1)**(1/2.2)*255)),(i*before.shape[1],28))
    draw=ImageDraw.Draw(canvas)
    draw.text((8,8),'Previous | '+label,fill='white')
    draw.text((before.shape[1]+8,8),'Candidate | CPU material proof, not Unreal lighting',fill='white')
    canvas.save(path)


def panel(p,size,joint):
    row=np.floor(p[...,1]/size[1]);q=p.copy();q[...,0]-=(abs(row)%2)*size[0]*.5
    identity=np.floor(q/size);local=(q/size%1-.5)*size
    half=np.asarray(size)*.5;bevel=min(size)*.16
    edge=np.minimum(np.minimum(half[0]-abs(local[...,0]),half[1]-abs(local[...,1])),
                    (half.sum()-bevel-abs(local).sum(-1))*.70710678)
    aa=2.5
    seam=1-smooth(joint*.5-aa,joint*.5+aa,edge)
    inset=1-smooth(7-aa,7+aa,abs(edge-65))
    hashed=np.sin(identity@np.array([127.1,311.7]))*43758.5453%1
    plate=.78+.35*smooth(.15,.85,hashed)
    service=smooth(size[1]*.24-aa,size[1]*.24+aa,local[...,0]*.65+local[...,1])*(1-seam)
    plate*=1-service*(hashed>=.48)*.2
    return plate,seam,inset


def noise(p):
    cell=np.floor(p);f=p-cell;f=f*f*(3-2*f)
    def hashed(q):return np.sin(q@np.array([127.1,311.7]))*43758.5453%1
    return ((1-f[...,0])*(1-f[...,1])*hashed(cell)+f[...,0]*(1-f[...,1])*hashed(cell+[1,0])
            +(1-f[...,0])*f[...,1]*hashed(cell+[0,1])+f[...,0]*f[...,1]*hashed(cell+[1,1]))


def run(master,ecology,geology,textures,out):
    out.mkdir(parents=True,exist_ok=True)
    field=load_heightfield(master);eco,spec=load(ecology,field.manifest_sha256)
    geo=np.load(geology,allow_pickle=False)
    z=field.heights_m;gy,gx=np.gradient(gaussian_filter(z,.6),*field.spacing_m)
    light=np.clip((1.2-.45*gx+.35*gy)/np.sqrt(1+gx*gx+gy*gy),.35,1.35)
    base=np.broadcast_to([.105,.165,.075],(*z.shape,3)).copy()
    old=base.copy();new=base.copy()
    tint=(np.array([1.10,1.03,.84])*(1-eco[...,0,None])+np.array([.62,.88,.72])*eco[...,0,None])
    new*=tint*(1-eco[...,1,None]*.28)
    opening=np.maximum(smooth(.13,.43,eco[...,2])*.85,smooth(.40,.88,eco[...,1])*.18)
    new=new*(1-opening[...,None])+np.array([.14,.117,.085])*opening[...,None]
    results=[]
    for result in (old,new):
        result=result*(1-geo[...,2,None]*.8)+np.array([.14,.117,.085])*geo[...,2,None]*.8
        result=result*(1-geo[...,0,None])+np.array([.27,.28,.27])*geo[...,0,None]
        result=result*(1-geo[...,1,None])+np.array([.78,.81,.84])*geo[...,1,None]
        road=field.masks['road'][...,None];water=field.masks['water'][...,None]
        result=result*(1-road)+np.array([.25,.22,.17])*road
        result=result*(1-water)+np.array([.015,.10,.14])*water
        results.append(result*light[...,None])
    write_pair(results[0][::-1],results[1][::-1],out/'ecology-comparison.png','terrain/tree-derived weights; unchanged heights')
    # Actual native fine maps under original architecture-scale plates.
    d=np.asarray(Image.open(textures/'diagonal-orhg.png').convert('RGB'),float)/255
    y,x=np.mgrid[0:768,0:768];p=np.stack((x,y),-1)*(6000/768)
    scan=bilinear(d,p/400)
    old=np.array([.38,.40,.38])*(.94+.10*scan[...,1,None])
    plate,seam,inset=panel(p,[1000,1500],30)
    new=old*plate[...,None]*(1-inset[...,None]*.16)
    new=new*(1-seam[...,None])+np.array([.38,.40,.38])*.2*seam[...,None]
    write_pair(old,new,out/'paving-comparison.png','60m square, native micro-map plus original 10x15m plates')
    # A road strip with identical24m physical/mask width; this shows the
    # difference between continuous lines and interrupted traffic wear.
    y,x=np.mgrid[0:768,0:384];w=np.stack(((x-192)*12.5,y*12.5),-1)
    lateral=abs(w[...,0]);confidence=np.ones_like(lateral)
    previous=np.maximum(np.exp(-((lateral-300)/55)**2),np.exp(-((lateral-500)/55)**2))
    drift=(noise(w/1900+13.1)-.5)*110
    patch=noise(w/3100+27.9)*.65+noise(w/730+5.2)*.35
    weather=.15+.6*noise(w/4300+19.4)
    width=65+50*weather
    candidate=np.maximum(np.exp(-((lateral-280-drift)/width)**2),np.exp(-((lateral-510-drift)/width)**2))
    candidate*=smooth(.22,.65,patch)*(1-weather*.5)
    alpha=1-smooth(1100,1350,lateral)
    shoulder=alpha*(1-alpha)*4
    breakup=noise(w/650+7.3)*.6+noise(w/180+21.7)*.4
    grass=np.array([.105,.165,.075]);earth=np.array([.23,.18,.12]);gravel=np.array([.29,.27,.22])
    old_gravel=np.clip(.35+previous*.45,0,1)
    new_gravel=np.clip(.28+candidate*.38+smooth(650,1150,lateral)*.28+(patch-.5)*.22,0,1)
    old=(earth*(1-old_gravel[...,None])+gravel*old_gravel[...,None])*(1-previous[...,None]*.10)
    new=(earth*(1-new_gravel[...,None])+gravel*new_gravel[...,None])*(1-candidate[...,None]*.12)
    old=old*alpha[...,None]+grass*(1-alpha[...,None])
    visual_alpha=1-np.clip(1-alpha+(breakup-.5)*shoulder*.65,0,1)
    new=new*visual_alpha[...,None]+grass*(1-visual_alpha[...,None])
    write_pair(old,new,out/'road-comparison.png','48x96m, identical24m road and alpha; material only')
    report={'schema':'pwr-surface-cpu-proof-v1','master_sha256':field.manifest_sha256,
            'trees_sha256':spec['trees_sha256'],'height_changes':False,
            'ecology_soil_opening_weight':float(opening.mean()),
            'paving_dark_joint_fraction':float(seam.mean()),
            'road_mask_changes':False,'road_wear_mean_before':float(previous.mean()),'road_wear_mean_after':float(candidate.mean()),
            'limitations':'CPU albedo/material-weight illustration only; full Unreal cook/live/FPS acceptance pending'}
    (out/'preview.receipt.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('master','ecology','geology','textures','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.master,a.ecology,a.geology,a.textures,a.out)
