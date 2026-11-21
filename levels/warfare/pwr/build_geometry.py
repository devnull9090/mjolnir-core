"""Generate the PWR vehicle basin and a sealed CE BSP with the Halo Blender exporter."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import importlib
from pathlib import Path
import sys

import bpy
import bmesh

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import layout
importlib.reload(layout)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out-dir", type=Path, default=ROOT)
parser.add_argument("--no-export", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
out = args.out_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
if not args.no_export:
    sys.path.insert(0, os.environ.get("HALO_BLENDER_ADDONS", r"C:\haloce\tools\halo-blender-425\addons"))
    import addon_utils
    assert addon_utils.enable("io_scene_halo", default_set=True, persistent=False)
for old in list(bpy.data.objects):
    bpy.data.objects.remove(old,do_unlink=True)
for old in list(bpy.data.meshes):
    bpy.data.meshes.remove(old,do_unlink=True)
for old in list(bpy.data.materials):
    bpy.data.materials.remove(old,do_unlink=True)
for old in list(bpy.data.collections):
    if old.name.startswith("PWR reusable"): bpy.data.collections.remove(old)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = layout.METRES_PER_WU
if hasattr(scene, "halo"):
    scene.halo.game_title = "halo1"
scene["pwr_export_pending"] = args.no_export
frame = bpy.data.objects.new("frame", None)
scene.collection.objects.link(frame)


def material(name, rgb, policy="NONE"):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .65
    m["mjolnir_pcg_policy"] = policy
    return m


GROUND = material("beach", (.30, .38, .17), "GROUND")
ROAD = material("blood ground", (.30, .24, .15))
ROAD_RIBBON = material("pwr_road!", (.25, .22, .16))
CLIFF = material("pwr_cliffs", (.37, .40, .39), "CLIFF")
METAL = material("metal panels generic ext", (.42, .47, .48))
FLOOR = material("metal plate floor ext", (.24, .28, .30))
RED = material("dangercanyon_decor_strip_red!", (.62, .035, .02))
BLUE = material("dangercanyon_decor_strip_blue!", (.025, .15, .70))
WATER = material("pwr_water!", (.055, .22, .26))
SKY = material("+sky", (.28, .48, .65))


def mesh(name, verts, faces, materials, indices=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata([tuple(v / layout.METRES_PER_WU for v in p) for p in verts], [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.parent = frame
    for m in materials:
        data.materials.append(m)
    for poly, index in zip(data.polygons, indices or []):
        poly.material_index = index
    return obj


def box(name, lo, hi, mat=METAL):
    x, y, z = lo
    X, Y, Z = hi
    return mesh(name, [(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)],
                [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [mat])


def boolean(obj, cutter, operation="DIFFERENCE"):
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new("Closed architectural solid", "BOOLEAN")
    mod.operation, mod.solver, mod.material_mode = operation, "EXACT", "TRANSFER"
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def ring_solid(name, cx, cy, rings, sides=8, mat=METAL, angle=math.pi/8):
    verts = [(cx + r*math.cos(angle + i*math.tau/sides), cy + r*math.sin(angle + i*math.tau/sides), z)
             for r,z in rings for i in range(sides)]
    faces = [tuple(reversed(range(sides))), tuple(range((len(rings)-1)*sides,len(rings)*sides))]
    for row in range(len(rings)-1):
        for i in range(sides):
            a, b = row*sides+i, row*sides+(i+1)%sides
            faces.append((a,b,b+sides,a+sides))
    return mesh(name, verts, faces, [mat])


def ramp(name, x0, x1, y0, y1, z0, z1, mat=FLOOR):
    return mesh(name, [(x0,y0,min(z0,z1)-2),(x1,y0,min(z0,z1)-2),(x1,y1,min(z0,z1)-2),(x0,y1,min(z0,z1)-2),
                       (x0,y0,z0),(x1,y0,z0),(x1,y1,z1),(x0,y1,z1)],
                [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [mat])


# The world uses one conforming terrain grid, with a closed inward sky boundary.
xs = ys = list(range(-1000,1001,layout.GRID))
nx=ny=len(xs)-1
verts=[(x,y,layout.height(x,y)) for y in ys for x in xs]
faces,slots=[],[]
water_verts,water_faces=[],[]
def clip_water(points):
    clipped=[]
    for a,b in zip(points,points[1:]+points[:1]):
        inside=a[2]<layout.WATER_Z
        if inside: clipped.append((a[0],a[1],layout.WATER_Z))
        if inside != (b[2]<layout.WATER_Z):
            t=(layout.WATER_Z-a[2])/(b[2]-a[2])
            clipped.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]),layout.WATER_Z))
    if len(clipped)>=3:
        start=len(water_verts); water_verts.extend(clipped)
        water_faces.extend((start,start+i,start+i+1) for i in range(1,len(clipped)-1))
for j in range(ny):
    for i in range(nx):
        a=j*(nx+1)+i
        for tri in [(a,a+1,a+nx+2),(a,a+nx+2,a+nx+1)]:
            faces.append(tri)
            x=sum(verts[k][0] for k in tri)/3; y=sum(verts[k][1] for k in tri)/3
            cliff=max(abs(x),abs(y))>860
            slots.append(2 if cliff else 1 if layout.water_distance(x,y)<30 else 0)
            clip_water([verts[k] for k in tri])
boundary=list(range(nx+1))+[j*(nx+1)+nx for j in range(1,ny+1)]
boundary += [ny*(nx+1)+i for i in range(nx-1,-1,-1)]+[j*(nx+1) for j in range(ny-1,0,-1)]
upper=[]
for i in boundary:
    upper.append(len(verts)); verts.append((verts[i][0],verts[i][1],layout.SKY_Z))
for i in range(len(boundary)):
    k=(i+1)%len(boundary); faces.append((boundary[i],upper[i],upper[k],boundary[k])); slots.append(3)
center=len(verts); verts.append((0,0,layout.SKY_Z))
for i in range(len(upper)):
    faces.append((center,upper[(i+1)%len(upper)],upper[i])); slots.append(3)
terrain=mesh("PWR_sealed_air_and_terrain",verts,faces,[GROUND,ROAD,CLIFF,SKY],slots)
mesh("PWR_connected_river_and_lakes",water_verts,water_faces,[WATER])
from road_ribbons import build as road_ribbons
road_verts,road_faces=road_ribbons([[verts[i] for i in face] for face in faces[:nx*ny*2]])
mesh("PWR_precise_24m_vehicle_roads",road_verts,road_faces,[ROAD_RIBBON])
solids=[]
kit=bpy.data.collections.new("PWR reusable Forerunner kit - excluded from CE export")
scene.collection.children.link(kit); kit.hide_render=True; kit.hide_viewport=True
assembly=[]

def keep(obj,kind):
    # Keep an editable source copy. Export geometry stays beneath `frame` only.
    source=obj.copy(); source.data=obj.data.copy(); source.parent=None
    source.name="KIT_"+obj.name; source.data.name="PWR_"+kind
    kit.objects.link(source); source.hide_set(True); source.hide_render=True; source["mjolnir_preview_only"]=True
    from mathutils import Matrix, Vector
    lo=Vector([min(v.co[a] for v in source.data.vertices) for a in range(3)])
    hi=Vector([max(v.co[a] for v in source.data.vertices) for a in range(3)])
    anchor=(lo+hi)*.5
    source.data.transform(Matrix.Translation(-anchor)); source.location=anchor
    source.data.asset_mark(); source.data.asset_data.description="Original Pelican Warfare modular "+kind
    source["module_kind"]=kind; source["seed"]=layout.SEED
    assembly.append({"name":obj.name,"module":kind,"asset":source.data.name,
                     "position_m":[v*layout.METRES_PER_WU for v in anchor],
                     "bounds_m":{"min":[v*layout.METRES_PER_WU for v in lo],"max":[v*layout.METRES_PER_WU for v in hi]},
                     "rotation_degrees":[0,0,0],"vertices":len(obj.data.vertices),"faces":len(obj.data.polygons)})
    solids.append(obj)
    return obj

def garage(name,x,y,z,large=False):
    r=44 if large else 30
    body=ring_solid(name,x,y,[(r,z-2),(r,z+18),(r*.72,z+27)],8)
    boolean(body,box("drive_through",(x-r-3,y-16,z-.2),(x+r+3,y+16,z+12),FLOOR))
    boolean(body,box("infantry_crosscut",(x-5,y-r-3,z-.2),(x+5,y+r+3,z+7),FLOOR))
    keep(body,"drive_through_garage")
    keep(ring_solid(name+"_command_spire",x,y,[(13,z+25),(10,z+37),(3,z+43)],6),"command_spire")
    for dx in (-r*.75,r*.75):
        for dy in (-r*.72,r*.72):
            keep(ring_solid(name+"_buttress",x+dx,y+dy,[(6,z-2),(5,z+17),(2,z+23)],4,angle=math.pi/4),"canted_buttress")
    if large:
        keep(ramp(name+"_roof_ramp",x-6,x+6,y+r*.7,y+r*.7+80,z+18,z),"roof_ramp")

for team,(x,y,z) in layout.HOMES.items():
    garage(team+"_headquarters",x,y,z,True)
    # Separate gateways frame the approach without narrowing the 24 m roadway.
    gx=x+(90 if team=="red" else -90)
    gate=box(team+"_gateway",(gx-4,-25,34),(gx+4,25,58))
    boolean(gate,box("gate_opening",(gx-5,-14,35),(gx+5,14,52)))
    keep(gate,"vehicle_gateway")
    sign=1 if team=="red" else -1
    xx=gx+sign*4.03
    for sy in (-1,1):
        yy=sy*20
        panel=[(xx,yy-2,z+3),(xx,yy+2,z+3),(xx,yy+2,z+14),(xx,yy-2,z+14)]
        if sign<0: panel.reverse()
        mesh(team+"_identity_panel",panel,[(0,1,2,3)],[RED if team=="red" else BLUE])
    for sy in (-1,1):
        keep(ring_solid(team+"_watchtower",x+35,y+sy*78,[(12,z-2),(9,z+20),(14,z+22),(9,z+28)],6),"watchtower")

# Three deck bridges are real native solids, with 24 m clear lanes.
for by in layout.BRIDGES:
    keep(box("bridge_"+str(int(by)),(-175,by-12,33),(175,by+12,36.4),FLOOR),"bridge_deck")
    for side in (-1,1):
        x0,x1=(-195,-175) if side<0 else (175,195)
        z0,z1=(36,36.4) if side<0 else (36.4,36)
        nose=mesh("bridge_eased_entry",[(x0,by-12,34),(x1,by-12,34),(x1,by+12,34),(x0,by+12,34),
                   (x0,by-12,z0),(x1,by-12,z1),(x1,by+12,z1),(x0,by+12,z0)],
                  [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],[FLOOR])
        keep(nose,"bridge_entry_nose")
    for xx in (-145,-65,65,145):
        keep(ring_solid("bridge_pier",xx,by,[(9,4),(7,32),(10,34)],4,angle=math.pi/4),"bridge_pier")
    # Discontinuous edge pylons leave infantry exits and the vehicle lane open.
    for xx in (-120,120):
        for sy in (-1,1):
            keep(ring_solid("bridge_beacon",xx,by+sy*16,[(4,34),(3,46),(1,50)],4),"bridge_beacon")

for i,(x,y,z) in enumerate(layout.CAPTURES):
    keep(ring_solid("objective_"+str(i),x,y,[(27,z-2),(27,z-.4),(24,z)],12,FLOOR),"objective_plinth")
    if i!=1:
        # Headquarters-sized objective areas have open capture pads and offset architecture.
        garage("objective_"+str(i)+"_annex",x,y+42,36)
    else:
        for sx in (-1,1):
            keep(ring_solid("central_signal_spire",sx*39,23,[(7,5),(6,49),(2,65)],6),"signal_spire")
for i,(x,y,z) in enumerate(layout.SATELLITES):
    garage("satellite_"+str(i),x,y,z)

wx,wy,wz=layout.WARMUP
warm=box("warmup_pavilion",(wx-42,wy-27,35),(wx+42,wy+27,wz))
boolean(warm,box("warmup_roof",(wx-43,wy-28,48),(wx+43,wy+28,51)),"UNION")
for dx in (-38,38):
    for dy in (-23,23):
        boolean(warm,ring_solid("pavilion_column",wx+dx,wy+dy,[(4,35),(3,49)],4),"UNION")
keep(warm,"staging_pavilion")
keep(ramp("staging_approach",wx-14,wx+14,wy-45,wy-25,36,37),"staging_ramp")
for dx in (-26,26):
    keep(box("staging_bench",(wx+dx-6,wy+10,37),(wx+dx+6,wy+12,37.6),FLOOR),"bench")

# Seeded infantry cover, with road, water and structure exclusion masks.
rng=random.Random(layout.SEED)
for i in range(28):
    for attempt in range(200):
        x,y=rng.uniform(-800,800),rng.uniform(-760,760)
        if layout.road_distance(x,y)>35 and layout.water_distance(x,y)>65 and layout.foundation_weight(x,y)<.01:
            break
    z=layout.sampled_height(x,y)
    keep(ring_solid("field_cover_%02d"%i,x,y,[(rng.uniform(8,14),z-4),(7,z+4),(3,z+8)],5,CLIFF,angle=rng.random()),"faceted_rock_cover")

# Inward-facing sealed air volume; original modular sources remain in the kit.
bm=bmesh.new(); bm.from_mesh(terrain.data)
bmesh.ops.reverse_faces(bm,faces=list(bm.faces)); bm.to_mesh(terrain.data); bm.free()
for index,obj in enumerate(solids):
    boolean(terrain,obj)
    if index%20==0: print("PWR_SOLIDS",index,len(solids),flush=True)
bm=bmesh.new(); bm.from_mesh(terrain.data)
bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.001)
bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.001)
bmesh.ops.dissolve_limit(bm,angle_limit=.00001,verts=list(bm.verts),edges=list(bm.edges),delimit={"MATERIAL"})
bmesh.ops.triangulate(bm,faces=list(bm.faces))
wire=[e for e in bm.edges if not e.link_faces]
if wire: bmesh.ops.delete(bm,geom=wire,context="EDGES")
bad=[e for e in bm.edges if not e.is_manifold]
if bad: raise RuntimeError(f"PWR boundary has {len(bad)} non-manifold edges")
bm.to_mesh(terrain.data); bm.free()
if len(terrain.data.polygons)>=30000: raise RuntimeError("CE collision budget exceeded")
for obj in scene.objects:
    if obj.type!="MESH" or obj.parent!=frame: continue
    uv=obj.data.uv_layers.new(name="UVMap")
    for poly in obj.data.polygons:
        mat=obj.data.materials[poly.material_index]
        dominant=max(range(3),key=lambda axis:abs(poly.normal[axis]))
        axes=[axis for axis in range(3) if axis!=dominant]
        for loop in poly.loop_indices:
            p=obj.data.vertices[obj.data.loops[loop].vertex_index].co*layout.METRES_PER_WU
            # CE stores UVs at limited precision. A whole-map 2 km projection
            # collapses small Boolean boundary triangles in the radiosity bake.
            period=32 if mat==GROUND else 20 if mat in (ROAD,CLIFF,WATER) else 6
            uv.data[loop].uv=(p[axes[0]]/period,p[axes[1]]/period)
    if obj==terrain:
        policy_attribute=obj.data.attributes.new("mjolnir_pcg_policy","INT","FACE")
        for poly in obj.data.polygons:
            if obj.data.materials[poly.material_index]==GROUND:
                centre=poly.center*layout.METRES_PER_WU
                if layout.road_distance(centre.x,centre.y)<28:
                    policy_attribute.data[poly.index].value=1

placements={"sky":r"sky\clear afternoon\clear afternoon","scenery":[],"vehicles":[],"spawns":[],"flags":[],"pickups":[],"lights":[],"teleporters":[]}
for team,(name,(cx,cy,z)) in enumerate(layout.HOMES.items()):
    sign=1 if team==0 else -1; yaw=0 if team==0 else 180
    placements["flags"].append({"team":team,"position_m":[cx,cy,z+.65],"yaw_degrees":yaw})
    for dx,dy in [(-18,-8),(-18,8),(18,-8),(18,8),(-65,-30),(65,-30),(-65,30),(65,30)]:
        placements["spawns"].append({"team":team,"position_m":[cx+sign*dx,cy+dy,z+.8],"yaw_degrees":yaw,"modes":["ctf","slayer"]})
    fleet=[("warthog",dx,dy) for dx,dy in [(48,-55),(65,-55),(-48,-55),(-65,-55)]]
    fleet += [("scorpion",dx,55) for dx in (-65,65)]+[("banshee",dx,85) for dx in (-65,65)]
    tags={"warthog":r"vehicles\warthog\mp_warthog","scorpion":r"vehicles\scorpion\scorpion_mp","banshee":r"vehicles\banshee\banshee_mp"}
    for kind,dx,dy in fleet:
        placements["vehicles"].append({"tag":tags[kind],"team":team,"position_m":[cx+sign*dx,cy+dy,z+.8],"yaw_degrees":yaw})
    for tag,dx,dy in [(r"item collections\single weapons\assault rifle",-12,-8),(r"item collections\single weapons\pistol",12,8),(r"item collections\powerups\powerup health pack",-65,0)]:
        placements["pickups"].append({"tag":tag,"position_m":[cx+dx,cy+dy,z+.6],"yaw_degrees":yaw})
placements["warfare"]=layout.document()
(out/"placements.json").write_text(json.dumps(placements,indent=2)+"\n")
(out/"layout.json").write_text(json.dumps(layout.document(),indent=2)+"\n")
(out/"assembly.json").write_text(json.dumps({"schema":"pwr-modular-assembly-v2","seed":layout.SEED,"modules":assembly},indent=2)+"\n")
from export_candidates import export_candidates
export_candidates(out)
bpy.context.view_layer.objects.active=terrain
bpy.ops.wm.save_as_mainfile(filepath=str(out/"pwr.blend"))
sys.path.insert(0,str(ROOT.parents[2]/"tools"/"blender"))
from mjolnir_level.surface import write_surface_policy
policy=write_surface_policy(scene,out/"pwr.surfaces.json")
report={"schema":"pwr-geometry-v2","seed":layout.SEED,"size_m":[2000,2000],"bsp_triangles":len(terrain.data.polygons),"water_triangles":len(water_faces),"road_triangles":len(road_faces),"modular_instances":len(assembly),"boundary":"closed","flight_envelope":"authored; not runtime validated","surface_policy":policy["counts"]}
(out/"geometry-report.json").write_text(json.dumps(report,indent=2)+"\n")
print("PWR_GEOMETRY",json.dumps(report))
if not args.no_export:
    target=out/"data/levels/warfare/pwr/models"; target.mkdir(parents=True,exist_ok=True)
    result=bpy.ops.export_scene.jms(filepath=str(target/"pwr.jms"),game_title="halo1",jms_version="8200",folder_type="1",folder_structure=False,scale_enum="1",use_scene_properties=False,export_render=True,export_collision=False,export_physics=False,hidden_geo=False,nonrender_geo=False,apply_modifiers=True,triangulate_faces=True,loop_normals=True,edge_split=False,clean_normalize_weights=False,fix_rotations=False,write_textures=False,generate_checksum=True)
    assert result=={"FINISHED"},result
    print("PWR_EXPORTED",target/"pwr.JMS")


