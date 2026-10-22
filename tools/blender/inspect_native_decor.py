"""Check authored native rock surfaces against the source's player envelopes.

Reads a layout-check.json and native-preview.json; does not simulate game physics.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mjolnir_level.native import import_reference
from mjolnir_level.native_scene import rotation_rows,ue_matrix

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native',type=Path,required=True)
parser.add_argument('--layout',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
doc=json.loads(args.native.read_text())
decor=json.loads(Path(doc['authored_decor']['path']).read_text())['decor']
checks=json.loads(args.layout.read_text())['checks']
# The scene is intentionally in metres, independent of authoring unit settings.
bpy.context.scene.unit_settings.scale_length=1
templates={}
for mesh in sorted({d['mesh'] for d in decor}):
    _,objects=import_reference(doc['models'][mesh])
    bpy.context.view_layer.update()
    templates[mesh]=[(BVHTree.FromPolygons([v.co for v in o.data.vertices],
        [tuple(p.vertices) for p in o.data.polygons]),o.matrix_world.copy(),
        [Vector(p) for p in o.bound_box]) for o in objects if o.type=='MESH' and not o.hide_render]
issues=[]
candidates=0
for item in decor:
    rows=rotation_rows(*item.get('rot',[0,0,0]))
    for row,scale in zip(rows,item.get('scale',[1,1,1])):
        for i in range(3): row[i]*=scale
    for bvh,local,bounds in templates[item['mesh']]:
        transform=ue_matrix(rows,item['pos'],1)@local
        inverse=transform.inverted()
        corners=[transform@p for p in bounds]
        low=Vector(tuple(min(p[k] for p in corners) for k in range(3)))
        high=Vector(tuple(max(p[k] for p in corners) for k in range(3)))
        def hit(a,b):
            start,end=inverse@Vector(a),inverse@Vector(b)
            direction=end-start
            return bvh.ray_cast(start,direction.normalized(),direction.length)[0]
        for check in checks:
            x,y,z=check['position_m']; z=check.get('floor_m',z)+.05
            if x+.4<low.x or x-.4>high.x or y+.4<low.y or y-.4>high.y or z+2.35<low.z or z>high.z:
                continue
            candidates+=1
            blocked=hit((x,y,z),(x,y,z+2.35)) is not None
            if not blocked:
                for h in (.3,1.1,1.9):
                    for i in range(16):
                        a=i*math.tau/16
                        if hit((x,y,z+h),(x+.4*math.cos(a),y+.4*math.sin(a),z+h)) is not None:
                            blocked=True; break
                    if blocked: break
            # A wholly enclosed marker does not cross a short surface ray.
            if not blocked:
                start=inverse@Vector((x,y,z+1.1))
                direction=(inverse.to_3x3()@Vector((.139,.277,1))).normalized()
                crossings=0
                for _ in range(512):
                    location=bvh.ray_cast(start,direction,1000)[0]
                    if location is None: break
                    crossings+=1; start=location+direction*.001
                blocked=bool(crossings%2)
            if blocked: issues.append({'marker':check['name'],'decor':item['id'],'mesh':item['mesh']})
report={'scope':'Native authored rock render meshes versus 0.4 m radius / 2.4 m player envelopes; excludes UE collision simplification and simulation',
    'markers':len(checks),'native_instances':len(decor),'broadphase_candidates':candidates,'issues':issues}
args.out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if issues: raise SystemExit(1)
