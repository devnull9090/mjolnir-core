from pathlib import Path
import json
import sys
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,'levels/warfare/pwr/terrain')
import outlet_apron as a
import headwater_dressing as d
w=Path('out/pwr/river-riparian/cutbank')
images=Path('out/pwr/alpine-target/bench/riparian-shore-42/water')
proof={}
geo=json.loads((w/'surface.json').read_bytes())
v=(np.array(geo['positions'])+geo['origin_cm'])/[100.,-100.,100.]
f=np.array(geo['faces'])
tris=v[f]
ct=tris.mean(axis=1)
area=np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0])
n=area/np.linalg.norm(area,axis=1)[:,None]
colors=np.array(geo['colors'])[f].mean(axis=1)
line=np.array(d.read(Path('out/pwr/river-apron/terrain/terrain.geometry.json'))['watercourses'][0]['erosion_reach']['centreline_m'])
water=a.surface(ct[:,:2],line)
for name in ['outlet','cutbank']:
    cam=json.loads((images/'photos.json').read_bytes())['frames'][name]['camera_before']
    eye=np.array(cam[:3])/[100,-100,100]
    pitch,yaw=np.deg2rad(cam[3:5]); fw=np.array([np.cos(yaw),-np.sin(yaw)])
    right=np.r_[-np.sin(yaw),-np.cos(yaw),0.]
    forward=np.r_[fw*np.cos(pitch),np.sin(pitch)]
    up=np.r_[-fw*np.sin(pitch),np.cos(pitch)]
    focal=800/np.tan(np.deg2rad(cam[5]/2))
    delta=v-eye
    z=delta@forward
    px=np.stack((800+focal*(delta@right)/z,450-focal*(delta@up)/z),axis=-1).astype(int)
    valid=(np.einsum('ij,ij->i',n,eye-ct)>0)&(z[f].min(axis=1)>.01)&(px[f,0].max(axis=1)>=0)&(px[f,0].min(axis=1)<1600)&(px[f,1].max(axis=1)>=0)&(px[f,1].min(axis=1)<900)&(ct[:,2]>water-.04)
    indices=np.flatnonzero(valid)
    order=indices[np.argsort(-z[f[indices]].mean(axis=1))]
    img=Image.open(images/(name+'.png')).convert('RGB')
    mask=Image.new('L',(1600,900)); tag=ImageDraw.Draw(mask)
    im=ImageDraw.Draw(img)
    light=np.maximum(0,np.dot(n,[.25,-.25,.93]))
    appearance=np.clip(255*(colors[:,:3]*(.32+.68*light[:,None]))**.48,0,255).astype(int)
    classes=np.select([colors[:,3]<.3,colors[:,3]<.9],[1,2],default=3)
    for i in order:
        poly=[(int(x),int(y)) for x,y in px[f[i]]]
        im.polygon(poly,tuple(appearance[i])); tag.polygon(poly,int(classes[i]))
    p=np.asarray(mask)
    proof[name]={'unoccluded_candidate_pixels':{key:int((p==i).sum()) for i,key in enumerate(('background','soil','wood','gravel')) if i}}
    img.resize((960,540)).save(w/(name+'-registered-projection.jpg'))
    if name == "cutbank":
        roi=p[415:735,:750]
        proof[name]["left_close_roi"]={key:int((roi==i).sum()) for i,key in enumerate(('background','soil','wood','gravel')) if i}
print(proof)
(w/'registered-projection.json').write_text(json.dumps(proof,indent=2))
