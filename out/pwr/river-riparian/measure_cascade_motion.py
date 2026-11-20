"""Measure temporal variation specifically on the projected cascade in its registered game camera."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion,binary_dilation

def measure(work,folder):
    geo=json.loads((work/"cascade/surface.json").read_text())
    pos=(np.asarray(geo["positions"])+np.asarray(geo["origin_cm"]))
    views=json.loads((folder/"photos.json").read_text())["views"]
    x,y,z,pitch,yaw,fov=views["inlet"]
    d=pos-[x,y,z]
    p,a=np.deg2rad([pitch,yaw])
    fwd=np.array([np.cos(p)*np.cos(a),np.cos(p)*np.sin(a),np.sin(p)])
    right=np.array([-np.sin(a),np.cos(a),0.])
    up=np.cross(fwd,right)
    focal=480./np.tan(np.deg2rad(fov/2))
    px=np.c_[480.+focal*(d@right)/(d@fwd),270.-focal*(d@up)/(d@fwd)].round().astype(int)
    mask=Image.new("L",(960,540))
    draw=ImageDraw.Draw(mask)
    for triangle in geo["faces"]:
        draw.polygon([tuple(v) for v in px[triangle]], fill=255)
    core=binary_erosion(np.asarray(mask)>0,iterations=4)
    border=binary_dilation(core,iterations=20)&~binary_dilation(core,iterations=8)
    # Use the drops above the lake surface. The rest includes Fluid Flux's moving shallows.
    top=np.indices(core.shape)[0] < np.percentile(np.where(core)[0],65)
    core &= top
    border &= top
    sequence=sorted((folder/"motion").glob("capture-*.png"))
    if len(sequence)!=32 or core.sum()<200 or border.sum()<200:
        raise ValueError("Cascade sequence or registered region is incomplete")
    delta=[]
    prior=None
    for name in sequence:
        with Image.open(name) as im:
            rgb=np.asarray(im.convert("RGB"),dtype=np.int16)
        if prior is not None:
            change=np.abs(rgb-prior).mean(axis=2)
            delta.append([change[core].mean(), change[border].mean()])
        prior=rgb
    med=np.median(np.array(delta),axis=0)
    result=dict(frames=len(sequence),cascade_pixels=int(core.sum()),surround_pixels=int(border.sum()),
                median_cascade_delta=float(med[0]),median_surround_delta=float(med[1]),units="8-bit channel levels per sampled frame")
    (folder/"motion/cascade-motion.json").write_text(json.dumps(result,indent=2))
    print(result)
    return result
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("water", type=Path)
    measure(Path(__file__).resolve().parent,parser.parse_args().water)
