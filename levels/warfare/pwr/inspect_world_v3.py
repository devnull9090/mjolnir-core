"""Read-only Blender BVH checks for finalized source architecture and placements.

Execute through the existing Blender MCP session. No scene objects are changed.
This checks authored support/clearance; it does not certify native physics.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/"tools/level"))
from heightfield import load_heightfield

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--source",type=Path,required=True)
    p.add_argument("--master",type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index("--")+1:])
    source=a.source;field=load_heightfield(a.master)
    arch=json.loads((source/"architecture-collision-extra.json").read_text())
    points=np.asarray(arch["triangles"],dtype=float).reshape(-1,3)*3.048
    tree=BVHTree.FromPolygons(points.tolist(),np.arange(len(points)).reshape(-1,3).tolist())
    layout=json.loads((source/"layout.json").read_text());placements=json.loads((source/"placements.json").read_text())
    failures=[];samples=[]
    def support(x,y,z):
        floor=float(field.sample(x,y))
        hit=tree.ray_cast(Vector((x,y,z)),Vector((0,0,-1)),8)[0]
        if hit is not None:floor=max(floor,hit.z)
        return floor
    def check(name,position,clearance,radius):
        x,y,z=position;floor=support(x,y,z+.05)
        if z<floor-.05 or z-floor>2.6:failures.append({"name":name,"reason":"bad floor support","z":z,"floor":floor})
        origin=Vector((x,y,floor+.05))
        if tree.ray_cast(origin,Vector((0,0,1)),clearance)[0] is not None:
            failures.append({"name":name,"reason":"headroom obstructed"})
        for angle in np.linspace(0,np.pi*2,8,endpoint=False):
            hit=tree.ray_cast(Vector((x,y,floor+.8)),Vector((np.cos(angle),np.sin(angle),0)),radius)[0]
            if hit is not None:failures.append({"name":name,"reason":"radial clearance obstructed"});break
        samples.append({"name":name,"position_m":position,"support_z_m":floor})
    for i,spawn in enumerate(placements["spawns"]):check("spawn_"+str(i),spawn["position_m"],2.4,.5)
    for i,pos in enumerate(layout["captures_m"]):check("capture_"+str(i),[*pos[:2],pos[2]+.8],2.4,.5)
    q=layout["warmup_m"];check("warmup",[*q[:2],q[2]+.8],2.4,.5)
    for i,v in enumerate(placements["vehicles"]):check("vehicle_"+str(i),v["position_m"],4,2.5)
    for team,route in layout["flights_m"].items():
        for i,t in enumerate(np.linspace(0,1,41)):
            q=np.array(route["start"])*(1-t)+np.array(route["end"])*t
            if q[2]-float(field.sample(*q[:2]))<25:failures.append({"name":team+"_flight_"+str(i),"reason":"terrain envelope obstructed"})
            if tree.find_nearest(Vector(q),25)[0] is not None:failures.append({"name":team+"_flight_"+str(i),"reason":"architecture envelope obstructed"})
    report={"schema":"pwr-source-clearance-v3","master_manifest_sha256":field.manifest_sha256,
            "samples":samples,"flight_samples":82,"failures":failures,"native_runtime_validated":False}
    (source/"inspection-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"samples":len(samples),"flight_samples":82,"failures":failures}))
    if failures:raise RuntimeError("Source clearance checks failed")

if __name__=="__main__":main()
