"""Check authored PWR starts, pads, staging and flight points against the exported shell.

Blender --background --factory-startup --python inspect_geometry.py
These geometric checks do not test Havok, network replication or scenery collision.
"""
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import layout

bpy.ops.wm.open_mainfile(filepath=str(ROOT/"pwr.blend"))
obj=bpy.data.objects["PWR_sealed_air_and_terrain"]
tree=BVHTree.FromPolygons([v.co*layout.METRES_PER_WU for v in obj.data.vertices],
                         [tuple(p.vertices) for p in obj.data.polygons])
placements=json.loads((ROOT/"placements.json").read_text())
samples=[]
for index,spawn in enumerate(placements["spawns"]):
    samples.append(("spawn_"+str(index),spawn["position_m"]))
samples += [("capture_"+str(i),[x,y,z+.8]) for i,(x,y,z) in enumerate(layout.CAPTURES)]
samples.append(("warmup",[layout.WARMUP[0],layout.WARMUP[1],layout.WARMUP[2]+.8]))
failures=[]
for name,pos in samples:
    p=Vector(pos)
    hit,_,_,distance=tree.ray_cast(p,Vector((0,0,-1)),3)
    if hit is None or distance > 1.5:
        failures.append({"name":name,"failure":"no near floor support","position_m":pos})
        continue
    origin=hit+Vector((0,0,.05))
    ceiling=tree.ray_cast(origin,Vector((0,0,1)),2.4)[0]
    if ceiling is not None:
        failures.append({"name":name,"failure":"less than 2.4m headroom"})
    for zz in (.4,1.2,2.0):
        for index in range(8):
            angle=index*math.tau/8
            touch=tree.ray_cast(hit+Vector((0,0,zz)),Vector((math.cos(angle),math.sin(angle),0)),.5)[0]
            if touch is not None:
                failures.append({"name":name,"failure":"less than 0.5m radial clearance"})
                break
flight_samples=[]
for team,route in layout.FLIGHTS.items():
    a,b=Vector(route["start"]),Vector(route["end"])
    for index in range(21):
        p=a.lerp(b,index/20)
        for direction in ((0,0,1),(0,0,-1),(0,1,0),(0,-1,0),(1,0,0),(-1,0,0)):
            if tree.ray_cast(p,Vector(direction),15)[0] is not None:
                failures.append({"name":team+"_flight_"+str(index),"failure":"15m transport envelope obstructed"})
        flight_samples.append(list(p))
vehicle_samples=[]
for i,vehicle in enumerate(placements["vehicles"]):
    x,y,z=vehicle["position_m"]
    for dx,dy in ((0,0),(-3,-2),(-3,2),(3,-2),(3,2)):
        hit,_,_,dist=tree.ray_cast(Vector((x+dx,y+dy,z+1)),Vector((0,0,-1)),3)
        if hit is None or dist>2.5:
            failures.append({"name":"vehicle_"+str(i),"failure":"no supporting vehicle footprint"})
        elif tree.ray_cast(hit+Vector((0,0,.1)),Vector((0,0,1)),4)[0] is not None:
            failures.append({"name":"vehicle_"+str(i),"failure":"less than 4 m vehicle headroom"})
        vehicle_samples.append([x+dx,y+dy,z])
crossing_samples=[]
for by in layout.BRIDGES:
    for x in range(-170,171,20):
        for dy in (-10,0,10):
            p=Vector((x,by+dy,37.2))
            hit,_,_,dist=tree.ray_cast(p,Vector((0,0,-1)),2)
            if hit is None or abs(hit.z-36.4)>.06:
                failures.append({"name":"bridge","position_m":list(p),"failure":"bridge surface discontinuity"})
            crossing_samples.append(list(p))
for fy in (-800,800):
    for x in range(-180,181,20):
        for dy in (-10,0,10):
            z=layout.sampled_height(x,fy+dy)
            if layout.WATER_Z-z>.36:
                failures.append({"name":"ford","position_m":[x,fy+dy,z],"failure":"ford deeper than 0.35 m"})
            crossing_samples.append([x,fy+dy,z])
report={"schema":"pwr-authored-geometry-check-v2","player_samples":len(samples),"flight_samples":len(flight_samples),
        "vehicle_footprint_samples":len(vehicle_samples),"crossing_samples":len(crossing_samples),
        "failures":failures,"limits":"Authored shell only; native scenery, Havok, vehicle handling, and multiplayer remain runtime tests."}
(ROOT/"inspection-report.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report))
if failures:
    raise RuntimeError("PWR geometry clearance checks failed")
