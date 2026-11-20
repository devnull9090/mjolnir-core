"""Capture registered native views of the PWR lake with the local Halo bridge."""
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"out/pwr/sweep-polish/qa"))
from lighting_trial import b, v, BENCH, preferences

def pose(eye, target, lens):
    a=[eye[0]*100,-eye[1]*100,eye[2]*100]
    dx,dy,dz=target[0]-eye[0],eye[1]-target[1],target[2]-eye[2]
    return [*a, round(math.degrees(math.atan2(dz,math.hypot(dx,dy))),4),round(math.degrees(math.atan2(dy,dx)),4),lens]

VIEWS={
    "basin":pose((-211,763,252),(-358,890,143.5),58),
    "outlet":pose((-273,785,152),(-321,859,145),73),
    "spring":pose((-449,936,161),(-350,905,144),73),
    "overhead":pose((-354,875,400),(-354,899,143),58)
}
PROBES={"headwater_flux_readback.lua":"HEADWATER_TEXEL_ACCEPTANCE PASS",
        "headwater_collision_readback.lua":"HEADWATER_LANDSCAPE_ACCEPTANCE PASS"}
FRAME_CLOCK = """
local s=StaticFindObject('/Script/Engine.Default__KismetSystemLibrary')
local g=StaticFindObject('/Script/Engine.Default__GameplayStatics')
print(string.format("LAKE_FRAME %d %.7f", s:GetFrameCount(),g:GetRealTimeSeconds(mj.world())))
"""

def sample_clock(photo):
    raw=b.run_lua(photo,FRAME_CLOCK)
    match=re.search(r'LAKE_FRAME (\d+) ([\d.]+)',raw)
    if not match:
        raise ValueError(raw)
    return int(match[1]),float(match[2])

def capture(folder,identifier,pid,photo,native):
    photo.runlua=lambda code:b.run_lua(photo,code)
    photo.private_world()
    lobby=photo.get_lobby()
    b.check(lobby.get("world")=="PWR" and lobby.get("public")=="0" and lobby.get("players")=="1","Private sole-player PWR is required")
    photo.dressing()
    settings=b.checked_settings(photo)
    output=folder/"water";output.mkdir()
    frames={}
    try:
        b.run_lua(photo,photo.PREP+photo.HIDE)
        cameras = dict(VIEWS)
        if identifier["archive"].endswith((".32.mjolnir",".33.mjolnir")):
            cameras["east-bank"] = pose((-280,854,146.24),(-382,914,144.5),73)
        if identifier["archive"].endswith(".33.mjolnir"):
            cameras["spring-bank"] = pose((-352,956,144.35),(-393,970,145.6),65)
        for name,camera in cameras.items():
            photo.setpose(camera,True)
            time.sleep(3.0)
            frames[name]=v.take_image(photo,output,name,camera)
        b.write(output/"photos.json",dict(release=identifier,settings=settings,views=cameras,frames=frames))
        photo.setpose(cameras["outlet"],True)
        time.sleep(5)
        try:
            start=sample_clock(photo)
            time.sleep(15)
            end=sample_clock(photo)
            frames_n,seconds=end[0]-start[0],end[1]-start[1]
            b.check(frames_n>0 and 15<=seconds<30,"Invalid elapsed frames or time")
            b.write(output/"outlet-performance.json",dict(frames=frames_n,seconds=seconds,
                fps=frames_n/seconds,settings=b.checked_settings(photo),camera=cameras["outlet"]))
        except (RuntimeError,ValueError) as ex:
            (output/"frame-clock.log").write_text(str(ex))
        if identifier["archive"].endswith((".32.mjolnir",".33.mjolnir")):
            for filename, marker in PROBES.items():
                result=b.run_lua(photo,(ROOT/"tools/level"/filename).read_text())
                (output/(filename+".log")).write_text(result,encoding="utf-8")
                print(filename,marker in result,result[-250:],flush=True)
    finally:
        b.run_lua(photo,photo.RESTORE)
    b.write(folder/"benchmark.json",dict(completed=True,release=identifier,settings=settings,frames=frames,
                                        purpose="Registered lake photographs only"))
if __name__=="__main__":
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument("release",type=Path);pa.add_argument("label")
    ar=pa.parse_args()
    with preferences(BENCH/ar.label),patch.object(b,"measure",capture):
        b.run_release(ar.release,ar.label)
