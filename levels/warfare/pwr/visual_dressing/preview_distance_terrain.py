"""Paired plan-view study of the cooked terrain field, shown on the same stock surface swatches."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as nd

from bake_distance_terrain import ROOT, BASELINE, MASKS, MASTER, smooth


def preview(out, paks, cooked):
    source = out/"study-inputs"
    source.mkdir(parents=True,exist_ok=True)
    pbr = json.loads((ROOT/"out/pwr/base-polish/saturday.7/map-input/pwr.level.json").read_text())["landscape"]["pbr"]
    side = 1024
    yy, xx = np.indices((side,side))
    def raster(path):
        return np.asarray(Image.open(path).convert("RGBA"),dtype=np.float32)/255.
    def land(name):
        native = np.load(MASTER/f"runtime-master.{name}.npy")[::-1].copy()
        return np.asarray(Image.fromarray(native).resize((side,side),Image.Resampling.BILINEAR))
    def ground_swatch(name,asset,tile_cm,tint):
        file = source/(name+".png")
        if not file.exists():
            subprocess.run([str(ROOT/"target/release/mjolnir.exe"),"texture","export","--paks",str(paks),
                            "--asset",asset,"--mip","4","--out",str(file)],check=True,capture_output=True)
        data = np.asarray(Image.open(file).convert("RGB").resize((3,3),Image.Resampling.BOX),dtype=np.float32)/255.
        data = np.where(data<.04045,data/12.92,((data+.055)/1.055)**2.4)
        data *= np.array(tint)[:3]
        uv = [3*yy*(200000/side)/tile_cm,3*xx*(200000/side)/tile_cm]
        return np.stack([nd.map_coordinates(data[:,:,k],uv,order=1,mode="grid-wrap")
                         for k in range(3)],axis=-1)
    def blend(a,b,t):
        return a + (b-a)*t[:,:,None]
    soil = ground_swatch("soil",pbr["surfaces"]["SandD"].split("/")[-1],pbr["tiles"][0],pbr["sand_tint"])
    rock = ground_swatch("rock",pbr["surfaces"]["RockD"].split("/")[-1],pbr["steep"][2],pbr["rock_tint"])
    grass = ground_swatch("grass","T_Ground_Grass_tb3nce_Desat_4K_NSVT_D",pbr["tiles"][2],pbr["grass_tint"])
    weights = raster(MASKS/"T_LandBase.png")
    ecology = raster(MASKS/"T_LandEcology.png")
    wet_bed = land("water")
    height = land("heights")
    gy,gx = np.gradient(nd.gaussian_filter(height,1.),2000/side)
    light = (.70*gx - .48*gy + .71)/np.sqrt(1+gx*gx+gy*gy)
    relief = (.72 + .5*np.clip(light,-.5,1))[:,:,None]
    ground = blend(grass,soil,np.maximum(weights[:,:,3],.55*ecology[:,:,2]))
    ground = blend(ground,rock,weights[:,:,0])
    ground = blend(ground,np.array([.70,.73,.76]),weights[:,:,1])
    old = raster(out/"cooked-previous-valley-rgba.png" if cooked else BASELINE/"biome-color.png")
    fresh = raster(out/"cooked-valley-rgba.png" if cooked else out/"biome-color.png")
    def physical(field,water):
        linear = ground * (field[:,:,:3] * 255/128) * relief
        if water:
            earth = (linear @ np.array([.2126,.7152,.0722]))[:,:,None]*np.array([1.09,.89,.66])
            linear = blend(linear,earth,.88*smooth(.07,.78,field[:,:,3]))
        linear = blend(linear,np.array([.031,.13,.14]),wet_bed)
        srgb=np.where(linear<.0031308,12.92*linear,1.055*np.maximum(0,linear)**(1/2.4)-.055)
        return Image.fromarray(np.uint8(np.clip(np.rint(255*srgb),0,255)))
    old_plan, plan = physical(old,False),physical(fresh,True)
    side=650
    bg="#132028"; label="#e7eddf"; soft="#b9c5c1"
    card = Image.new("RGB",(2*side+60,814),bg)
    draw=ImageDraw.Draw(card)
    def font(size):
        return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf",size)
    def title(x,y,text,size,color):
        draw.text((x,y),text,font=font(size),fill=color)
    title(20,9,"Pelican Warfare   /   Valley ground",30,label)
    title(20,55,"Playtest .7",23,soft)
    title(side+40,55,"New terrain",23,soft)
    for i,im in enumerate((old_plan,plan)):
        card.paste(im.resize((side,side),Image.Resampling.LANCZOS),(20+i*(side+20),91))
    title(20,753,("Cooked terrain texture study" if cooked else "Terrain authoring study")+
          "   ·   2 km across   ·   North up",18,label)
    title(20,782,"Both views use the same heightfield, campaign surface swatches and light. Open water is shown in teal.",15,soft)
    save = out/("valley-cooked-ground-study.jpg" if cooked else "valley-ground-study.jpg")
    card.save(save,quality=94)
    return save


if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("out",type=Path)
    arg.add_argument("--paks",type=Path,required=True)
    arg.add_argument("--cooked",action="store_true")
    a=arg.parse_args()
    print(preview(a.out.resolve(),a.paks.resolve(),a.cooked))
