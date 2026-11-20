"""Photograph the eroded outlet through the local Halo bridge at registered poses."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
from unittest.mock import patch

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]
sys.path.insert(0,str(WORK.parent/"headwater-lake"))
sys.path.insert(0,str(ROOT/"tools/level"))
import photograph as previous
from heightfield import load_heightfield

b,v=previous.b,previous.v
CONTROL=ROOT/"out/pwr/alpine-target/bench/headwater-lake-33/water"


def terrain_probe(field, stations):
    original=(ROOT/"tools/level/headwater_collision_readback.lua").read_text()
    rows=[f'    {{name="{name}", x={x:.5f}, y={y:.5f}, height={float(field.sample(x,y)):.5f}}},'
          for name,(x,y) in stations.items()]
    body,n=re.subn(r"local probes = \{.*?\n\}", "local probes = {\n"+"\n".join(rows)+"\n}",original,count=1,flags=re.S)
    assert n==1
    return body


def capture(folder,identity,pid,photo,native):
    photo.runlua=lambda code:b.run_lua(photo,code)
    photo.private_world()
    lobby=photo.get_lobby()
    b.check(lobby.get("world")=="PWR" and lobby.get("players")=="1" and lobby.get("public")=="0",
            "Expected a private one-player PWR session")
    photo.dressing()
    settings=b.checked_settings(photo)
    registered=b.read(CONTROL/"photos.json")
    b.check(settings==registered["settings"],"Settings differ from the .33 control session")
    field=load_heightfield(WORK/"terrain/runtime-master.json")
    layout=b.read(WORK/"review-locations.json")
    cameras=dict(registered["views"])
    near=layout["bank_camera"]
    eye=[*near["xy"],float(field.sample(*near["xy"]))+near["height_above_ground_m"]]
    cameras["waterline"]=previous.pose(eye,near["target_m"],near["fov_deg"])
    cameras["river-seam"]=previous.pose((13,-32,121),(-36,1,92.2),68)
    cameras["seam-overhead"]=previous.pose((-36,-5,155),(-36,1,92.2),67)
    cameras["riffle"]=previous.pose((-280,790,142.43),(-297,826,143.15),69)
    probes={"water":((args.water/"river_flux_readback.lua").read_text(),"HEADWATER_TEXEL_ACCEPTANCE PASS"),
            "terrain":(terrain_probe(field,layout["terrain_probes"]),"HEADWATER_LANDSCAPE_ACCEPTANCE PASS")}
    if identity["archive"].endswith(".35.mjolnir"):
        probes["painter"]=((WORK/"junction/verify-painter.lua").read_text(),"JOIN_PAINTER_ACCEPTANCE PASS")
    output=folder/"water"
    output.mkdir()
    frames={}
    join = WORK/"junction/observe.lua"
    if join.is_file():
        (join.parent/"observe.log").write_text(b.run_lua(photo,join.read_text()),encoding="utf-8")
    try:
        b.run_lua(photo,photo.PREP+photo.HIDE)
        for name in ("outlet","waterline","riffle","seam-overhead","basin","east-bank","spring-bank","spring","overhead","river-seam"):
            photo.setpose(cameras[name],True)
            time.sleep(3)
            frames[name]=v.take_image(photo,output,name,cameras[name])
        b.write(output/"photos.json",dict(release=identity,settings=settings,views=cameras,frames=frames))
        photo.setpose(cameras["outlet"],True)
        time.sleep(5)
        start=previous.sample_clock(photo)
        time.sleep(15)
        end=previous.sample_clock(photo)
        frames_n,seconds=end[0]-start[0],end[1]-start[1]
        b.check(frames_n>0 and 14.8<seconds<30,"Invalid timing window")
        b.write(output/"outlet-performance.json",dict(frames=frames_n,seconds=seconds,fps=frames_n/seconds,
                 settings=b.checked_settings(photo),camera=cameras["outlet"]))
        for name,(script,passing) in probes.items():
            log=b.run_lua(photo,script)
            (output/(name+".log")).write_text(log,encoding="utf-8")
            print(name,passing in log,log[-350:],flush=True)
        if args.junction_trial and (join.parent/"visual_trial.py").is_file():
            sys.path.insert(0,str(join.parent))
            import visual_trial
            visual_trial.run(photo,b,v,output,previous.pose((-36,-5,155),(-36,1,92.2),67))
    finally:
        b.run_lua(photo,photo.RESTORE)
    b.write(folder/"benchmark.json",dict(completed=True,release=identity,settings=settings,frames=frames))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("release",type=Path)
    parser.add_argument("label")
    parser.add_argument("--water",type=Path,default=WORK/"water-fix")
    parser.add_argument("--junction-trial",action="store_true")
    args=parser.parse_args()
    with previous.preferences(previous.BENCH/args.label),patch.object(b,"measure",capture):
        b.run_release(args.release,args.label)
