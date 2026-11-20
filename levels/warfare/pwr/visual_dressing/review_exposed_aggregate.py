"""Compare matched native Southwest Sweep frames and visibility of fine/mid-scale ground texture."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter

from ground_life_earth import OUT, sha


def compare(old,new):
    clips=[];reads=[]; cameras=[]
    name="glacial-gravel"
    for folder in (old,new):
        frame=folder/"frames"/(name+".png")
        record=json.loads((folder/"frames/frames.json").read_text())["frames"][name]
        cameras.append(np.array(record["frames"][0]["camera_before"][:8],float))
        rgb=np.asarray(Image.open(frame).convert("RGB"))
        h,w=rgb.shape[:2]; clips.append(Image.fromarray(rgb))
        if (w,h)!=(1600,900):raise ValueError("Unexpected screenshot resolution")
        luma=(rgb.astype(np.float32)@np.array([.2126,.7152,.0722],dtype=np.float32))/255
        # All three rectangles are in empty unshadowed dirt, well below the
        # physical stone band. Normalizing by local brightness separates grain
        # contrast from the mean colour of the material.
        windows={"left":[.07,.66,.37,.93],"centre":[.38,.66,.68,.93],"right":[.69,.66,.93,.93]}
        metrics={}
        for key,(x0,y0,x1,y1) in windows.items():
            crop=luma[int(h*y0):int(h*y1),int(w*x0):int(w*x1)]
            low=np.maximum(.06,gaussian_filter(crop,12.,mode="reflect"))
            fine=(gaussian_filter(crop,.65)-gaussian_filter(crop,2.5))/low
            mid=(gaussian_filter(crop,2.5)-gaussian_filter(crop,10))/low
            metrics[key]=dict(mean_luminance=round(float(crop.mean()),5),
                              fine_contrast_rms=round(float(np.sqrt(np.mean(fine[12:-12,12:-12]**2))),6),
                              coarse_contrast_rms=round(float(np.sqrt(np.mean(mid[12:-12,12:-12]**2))),6))
        reads.append(dict(file=str(frame),sha256=sha(frame),metrics=metrics,rectangles_normalized=windows))
    if np.max(np.abs(cameras[0]-cameras[1]))>.01:raise ValueError("The native camera did not match")
    target=OUT.parent/"earth.12";target.mkdir(parents=True,exist_ok=True)
    board=Image.new("RGB",(1440,744),"#172021");draw=ImageDraw.Draw(board)
    font=ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf",23)
    small=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf",18)
    for k,(title,im) in enumerate(zip(("Playtest .11","Playtest .12"),clips)):
        left=720*k
        draw.text((left+16,8),title,font=font,fill="#f2efe0")
        board.paste(im.resize((720,405),Image.Resampling.LANCZOS),(left,47))
        draw.text((left+16,461),"Road shoulder at original pixel scale",font=small,fill="#d1d6ce")
        board.paste(im.crop((375,450,1095,703)),(left,490))
    jpg=target/"southwest-sweep-aggregate.jpg";board.save(jpg,quality=95,subsampling=0,optimize=True)
    result=dict(camera_ue=cameras[0].tolist(),release_11=reads[0],release_12=reads[1],comparison=str(jpg))
    (target/"glacial-gravel-visual-readback.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps([a["metrics"] for a in reads],indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("before",type=Path);p.add_argument("after",type=Path)
    args=p.parse_args();compare(args.before,args.after)
