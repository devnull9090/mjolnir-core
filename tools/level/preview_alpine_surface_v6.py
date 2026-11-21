"""CPU diagnostic weight/albedo previews. These are not Unreal renders."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from alpine_surface_v6 import ROOT,RECIPES,smooth,compose_apron_height
from heightfield import load_heightfield


def srgb(value):
    return np.where(value<=.0031308,value*12.92,1.055*np.maximum(value,0)**(1/2.4)-.055)


def plate_image(size,layout,pattern,old=False):
    x,y=np.meshgrid(np.linspace(-9000,9000,size),np.linspace(9000,-9000,size));p=np.stack([x,y],-1)
    width,length,joint,strength=layout
    row=np.floor(y/length);q=p.copy();q[...,0]-=np.fmod(abs(row),2)*width*.5
    cell=np.floor(q/[width,length]);local=(q/[width,length]-cell-.5)*[width,length]
    bevel=min(width,length)*.16 if old else pattern[0]
    edge=np.minimum(np.minimum(width*.5-abs(local[...,0]),length*.5-abs(local[...,1])),
                    (width*.5+length*.5-bevel-abs(local[...,0])-abs(local[...,1]))*.70710678)
    aa=18000/size
    seam=1-smooth(joint*.5-aa,joint*.5+aa,edge)
    h=np.mod(np.sin(cell[...,0]*127.1+cell[...,1]*311.7)*43758.5453,1)
    plate=.78+.35*smooth(.15,.85,h) if old else 1-pattern[1]+2*pattern[1]*h
    if old:
        service=smooth(length*.24-aa,length*.24+aa,local[...,0]*.65+local[...,1])*(1-seam)
        plate*=1-service*(h>=.48)*.2
    inset=(1-smooth(7-aa if old else 2-aa,7+aa if old else 2+aa,abs(edge-65)))
    if not old:inset*=h>=.72
    color=np.array([.38,.40,.38])*plate[...,None]*(1-inset[...,None]*(.16 if old else .08))
    color=color*(1-seam[...,None]) + np.array([.38,.40,.38])*.2*seam[...,None] if old else color*(1-seam[...,None]*pattern[2])
    return np.uint8(np.clip(srgb(color),0,1)*255)


def title(image,text):
    header=Image.new('RGB',(image.width,image.height+52),'#17202a');header.paste(image,(0,52))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    ImageDraw.Draw(header).text((12,15),text,fill='white',font=font)
    return header


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v6/surface');a=p.parse_args()
    field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/gaea-apron-v4/source.json')
    z,x,y=compose_apron_height(field,np.load(ROOT/'out/pwr/visual-v5/apron-v4/harmonic-field.npz'))
    masks=np.load(a.out/'apron/geology.rgba.npy')
    rock,snow,soil,wet=np.moveaxis(masks,-1,0)
    grass=np.array([.23,.34,.17])*(1-wet[...,None]*.25)
    color=grass*(1-soil[...,None])+np.array([.33,.29,.22])*soil[...,None]
    color=color*(1-rock[...,None])+np.array([.34,.37,.39])*rock[...,None]
    color=color*(1-snow[...,None])+np.array([.84,.88,.91])*snow[...,None]
    gy,gx=np.gradient(z,*field.spacing_m);n=np.stack([-gx,-gy,np.ones_like(z)],-1);n/=np.linalg.norm(n,axis=-1,keepdims=True)
    light=np.array([-.5,.35,.79]);light/=np.linalg.norm(light)
    shade=.35+.65*np.maximum(np.sum(n*light,-1),0);color*=shade[...,None]
    color[np.maximum(abs(x),abs(y))<1000]=[.025,.03,.035]
    image=Image.fromarray(np.uint8(np.clip(srgb(color[::-1]),0,1)*255))
    title(image,'8 km geology weights + source relief | diagnostic, not an Unreal render').save(a.out/'apron-zoning-preview.png')
    old=Image.fromarray(plate_image(900,[1000,1500,30,1],[30,.03,.18,.25],True))
    new=Image.fromarray(plate_image(900,RECIPES['alloy']['PavingLayout'],RECIPES['alloy']['PavingPattern']))
    combined=Image.new('RGB',(1800,952));combined.paste(title(old,'Visual5 macro albedo | 180m square'),(0,0));combined.paste(title(new,'Visual6 macro albedo | same scale; native fine scan omitted'),(900,0))
    combined.save(a.out/'paving-macro-comparison.png')
    eco=np.load(a.out/'ecology/ecology.rgba.npy');soil=smooth(.13,.43,eco[...,2])*.85
    rgb=np.array([.25,.39,.18])*(1-eco[...,:1]*.30)
    rgb=rgb*(1-soil[...,None])+np.array([.35,.29,.21])*soil[...,None]
    title(Image.fromarray(np.uint8(np.clip(srgb(rgb[::-1]),0,1)*255)),'2 km meadow moisture/soil weights | diagnostic, not an Unreal render').save(a.out/'meadow-zoning-preview.png')


if __name__=='__main__':main()
