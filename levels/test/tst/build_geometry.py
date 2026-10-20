"""Build TST in Blender 5.1 with Halo Toolset 425; export classic CE JMS.

Run blender --background --factory-startup --python build_geometry.py.
Coordinates in this script are meters; stored Blender coordinates are CE units.
The generated source .blend and .JMS are checked in, engine build outputs are not.
"""
import json
import math
import os
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
ADDON = Path(os.environ.get("HALO_BLENDER_ADDONS", r"C:\haloce\tools\halo-blender-425\addons"))
METERS_PER_CE = 3.048
sys.path.insert(0, str(ADDON))
import addon_utils
assert addon_utils.enable("io_scene_halo", default_set=True, persistent=False)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.halo.game_title = "halo1"
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = METERS_PER_CE
frame = bpy.data.objects.new("frame", None)
scene.collection.objects.link(frame)

def material(name, color, roughness=0.8):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    return m

GROUND = material("beach", (0.30, 0.35, 0.13))
CLIFF = material("tst_cliffs", (0.39, 0.38, 0.32))
PANELS = material("metal panels generic ext", (0.31, 0.32, 0.30), .65)
FLOOR = material("metal plate floor ext", (0.22, 0.24, 0.25), .6)
RED = material("dangercanyon_decor_strip_red!", (.55, .035, .015), .5)
BLUE = material("dangercanyon_decor_strip_blue!", (.025, .15, .65), .5)
WATER = material("tst_water!", (.055, .22, .23), .15)
SKY = material("+sky", (.27, .50, .70))

def mesh_object(name, vertices, faces, mats, indices=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v / METERS_PER_CE for v in p) for p in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.parent = frame
    for m in mats:
        mesh.materials.append(m)
    if indices:
        for poly, index in zip(mesh.polygons, indices):
            poly.material_index = index
    return obj

def uv_project(obj):
    mesh = obj.data
    mesh.update()
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        mat = mesh.materials[poly.material_index]
        dominant = max(range(3), key=lambda k: abs(poly.normal[k]))
        axes = [k for k in range(3) if k != dominant]
        for corner, loop in enumerate(poly.loop_indices):
            co = mesh.vertices[mesh.loops[loop].vertex_index].co * METERS_PER_CE
            if mat == GROUND:
                # The stock beach bitmap paints an entire island; its detail
                # maps provide the small surface texture, not a 6 m base repeat.
                uv.data[loop].uv = (co.x / 120 + .5, co.y / 120 + .5)
            elif mat in (RED, BLUE):
                if obj.get("team_color_band"):
                    # The same stock emblem bitmap has a saturated coloured
                    # patch. Sample it for continuous team-colour inlays.
                    u0, u1, v0, v1 = 126 / 256, 132 / 256, 1 - 290 / 512, 1 - 284 / 512
                    uv.data[loop].uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))[corner]
                else:
                    # One complete emblem on each large doorway panel.
                    uv.data[loop].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[corner]
            else:
                period = 2 if mat in (PANELS, FLOOR) else 6
                uv.data[loop].uv = (co[axes[0]] / period, co[axes[1]] / period)

def height(x, y):
    h = .16 * math.sin(x * .14) * math.cos(y * .19)
    h += 2.8 * math.exp(-((x / 11) ** 2 + ((y - 14) / 8) ** 2) * 1.7)
    pond = math.sqrt(((x - 30) / 7) ** 2 + ((y + 17) / 5) ** 2)
    if pond < 1.6:
        h = min(h, -1.3 * max(0, 1 - (pond / 1.6) ** 2))
    # Level build pads, including the ground under the base slabs.
    for bx in (-46, 46):
        pad = max(abs(x - bx) / 11, abs(y) / 12)
        if pad < 1:
            h *= max(0, (pad - .80) / .20)
    if y > 24:
        t = (y - 24) / 6
        h += t ** 1.45 * (10 + .9 * math.sin(x * .27) + .6 * math.sin(x * .71))
    if y < -26:
        h += ((-y - 26) / 4) ** 2 * (2.6 + .35 * math.cos(x * .32))
    if abs(x) > 56:
        h += ((abs(x) - 56) / 4) ** 2 * (3 + .4 * math.sin(y * .33))
    return h

# Single sealed playable air volume: terrain, perimeter sky walls and ceiling.
nx, ny = 60, 30
vertices = [(x, y, height(x, y)) for y in range(-30, 31, 2) for x in range(-60, 61, 2)]
faces, indices = [], []
for j in range(ny):
    for i in range(nx):
        a = j * (nx + 1) + i
        b, c, d = a + 1, a + nx + 2, a + nx + 1
        # Alternating diagonals prevent a regular visible ridge pattern.
        faces.extend([(a, b, d), (b, c, d)] if (i+j) % 2 else [(a, b, c), (a, c, d)])
        indices.extend([1 if j >= 27 else 0] * 2)
boundary = list(range(nx + 1))
boundary += [j * (nx + 1) + nx for j in range(1, ny + 1)]
boundary += [ny * (nx + 1) + i for i in range(nx - 1, -1, -1)]
boundary += [j * (nx + 1) for j in range(ny - 1, 0, -1)]
upper = []
for index in boundary:
    upper.append(len(vertices))
    vertices.append((vertices[index][0], vertices[index][1], 38))
for i in range(len(boundary)):
    k = (i + 1) % len(boundary)
    faces.append((boundary[i], upper[i], upper[k], boundary[k]))
    indices.append(2)
center = len(vertices)
vertices.append((0, 0, 38))
for i in range(len(upper)):
    faces.append((center, upper[(i+1) % len(upper)], upper[i]))
    indices.append(2)
terrain = mesh_object("TST_sealed_terrain_and_sky", vertices, faces, [GROUND, CLIFF, SKY], indices)

def box(name, lo, hi, mat=PANELS):
    x,y,z = lo; X,Y,Z = hi
    return mesh_object(name, [(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)],
                       [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [mat])

def boolean(obj, cutter, operation="DIFFERENCE"):
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("Architectural solid", "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.material_mode = "TRANSFER"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)

def transform_base(obj, cx, sign):
    for v in obj.data.vertices:
        v.co.x = cx / METERS_PER_CE + v.co.x * sign
        v.co.y *= sign

def bevel_rectangle(x0, y0, x1, y1, bevel):
    return [(x0, y0 + bevel), (x0 + bevel, y0), (x1 - bevel, y0),
            (x1, y0 + bevel), (x1, y1 - bevel), (x1 - bevel, y1),
            (x0 + bevel, y1), (x0, y1 - bevel)]

def prism(name, plan, z0, z1, mat=PANELS):
    n = len(plan)
    verts = [(x, y, z0) for x, y in plan] + [(x, y, z1) for x, y in plan]
    fs = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    fs += [(i, (i+1) % n, (i+1) % n + n, i+n) for i in range(n)]
    return mesh_object(name, verts, fs, [mat])

def canted_block(name, y0, y1, back, front0, front1, z0, z1):
    return mesh_object(name,
        [(back,y0,z0),(front0,y0,z0),(front0,y1,z0),(back,y1,z0),
         (back,y0,z1),(front1,y0,z1),(front1,y1,z1),(back,y1,z1)],
        [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [FLOOR])

def front_x(z):
    return 6 - .72 * (z + .4) / 5.7

def side_y(z):
    return 9 - 1.08 * (z + .4) / 5.7

for cx, sign, team, trim in [(-46, 1, "red", RED), (46, -1, "blue", BLUE)]:
    plan = [(-6,-7),(-4,-9),(4,-9),(6,-7),(6,7),(4,9),(-4,9),(-6,7)]
    verts = [(x,y,-.4) for x,y in plan] + [(x*.88,y*.88,5.3) for x,y in plan]
    fs = [tuple(reversed(range(8))),tuple(range(8,16))]
    fs += [(i,(i+1)%8,(i+1)%8+8,i+8) for i in range(8)]
    base = mesh_object(f"{team}_base_shell", verts, fs, [PANELS, FLOOR])
    boolean(base, box("chamber_cut", (-3.8,-5.9,.45),(4.7,5.9,4.1)))
    boolean(base, box("entrance_cut", (3.5,-2.5,.45),(7,2.5,3.65)))
    # Two roof coffers leave a broad raised rim and a central structural rib.
    # Their floors remain above the original 4.1 m interior ceiling.
    for x0, x1 in [(-4.55,-.4),(.4,4.55)]:
        boolean(base, prism("roof_coffer", bevel_rectangle(x0,-6.85,x1,6.85,.55),
                            4.98,6.0,FLOOR))
    # Thick canted entrance ribs and lintel sit inside the existing maximum
    # footprint. They join the shell, so the BSP still has one sealed boundary.
    for side in (-1,1):
        y0,y1 = (3.15,3.95) if side == 1 else (-3.95,-3.15)
        boolean(base, canted_block("door_buttress",y0,y1,5.0,5.98,5.65,.2,5.18),"UNION")
    boolean(base,canted_block("door_header",-3.95,3.95,5.0,5.8,5.50,4.15,5.05),"UNION")
    # A larger shallow rebate around the original entrance gives the frame
    # depth without changing the walkable opening or chamber dimensions.
    boolean(base,box("door_rebate",(5.0,-3.08,.45),(7,3.08,4.13),FLOOR))
    # Shallow bays, lower plinth and an upper groove articulate the side walls.
    for side in (-1, 1):
        for u in (-2.6, .1, 2.8):
            ymin,ymax = (8.12,9.5) if side == 1 else (-9.5,-8.12)
            boolean(base, box("panel_recess", (u-1.05,ymin,1.15),(u+1.05,ymax,3.45)))
        ymin,ymax = (7.95,9.5) if side == 1 else (-9.5,-7.95)
        boolean(base,box("upper_side_channel",(-3.35,ymin,4.20),(3.35,ymax,4.46),FLOOR))
    ramp = mesh_object(f"{team}_entry_ramp", [(5.5,-3.2,-.3),(10,-3.2,-.3),(10,3.2,-.3),(5.5,3.2,-.3),
                      (5.5,-3.2,.45),(10,-3.2,.10),(10,3.2,.10),(5.5,3.2,.45)],
                       [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [FLOOR])
    boolean(base, ramp, "UNION")
    for poly in base.data.polygons:
        if poly.normal.z > .85:
            poly.material_index = 1
    transform_base(base, cx, sign)
    # Team emblems are large enough to identify the base from across the arena.
    # Every accent is render-only and follows the actual sloped facade.
    for side in (-1,1):
        y0,y1 = (4.08,5.78) if side == 1 else (-5.78,-4.08)
        panel = mesh_object(f"{team}_team_emblem_{side}",
            [(front_x(.85)+.025,y0,.85),(front_x(.85)+.025,y1,.85),
             (front_x(3.75)+.025,y1,3.75),(front_x(3.75)+.025,y0,3.75)],[(0,1,2,3)],[trim])
        transform_base(panel,cx,sign)
        # A broad team-colour stripe along each long wall reads from oblique
        # views, where the front-facing emblem otherwise disappears.
        band = mesh_object(f"{team}_side_colour_{side}",
            [(-3.4,side*(side_y(3.62)+.025),3.62),(3.4,side*(side_y(3.62)+.025),3.62),
             (3.4,side*(side_y(3.94)+.025),3.94),(-3.4,side*(side_y(3.94)+.025),3.94)],
            [(0,1,2,3) if side == -1 else (3,2,1,0)],[trim])
        band["team_color_band"] = True
        transform_base(band,cx,sign)
        # Canted vertical accents make the entrance ribs legible at a distance.
        y0,y1 = (3.39,3.71) if side == 1 else (-3.71,-3.39)
        def rib_x(z):
            return 5.98 + (5.65-5.98)*(z-.2)/(5.18-.2) + .025
        band = mesh_object(f"{team}_door_colour_{side}",
            [(rib_x(.5),y0,.5),(rib_x(.5),y1,.5),(rib_x(4.65),y1,4.65),(rib_x(4.65),y0,4.65)],
            [(0,1,2,3)],[trim])
        band["team_color_band"] = True
        transform_base(band,cx,sign)

# Cut architecture out of the enclosed playable air volume. Exporting
# intersecting ground and base shells independently leaves coincident BSP
# surfaces at their seams; one boolean result has the actual room boundary.
bm = bmesh.new()
bm.from_mesh(terrain.data)
bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
bm.to_mesh(terrain.data)
bm.free()
for obj in list(scene.objects):
    if obj.name.endswith("_base_shell"):
        boolean(terrain, obj)
bm = bmesh.new()
bm.from_mesh(terrain.data)
bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.001)
bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.001)
bmesh.ops.triangulate(bm, faces=list(bm.faces))
bm.to_mesh(terrain.data)
bm.free()

# A water render plane, not a solid cap. The shallow basin is real terrain.
count = 48
verts = [(30,-17,-.18)] + [(30+9.5*math.cos(i*math.tau/count),-17+6.8*math.sin(i*math.tau/count),-.18) for i in range(count)]
pond = mesh_object("pond_surface",verts,[(0,i+1,(i+1)%count+1) for i in range(count)],[WATER])
for obj in list(scene.objects):
    if obj.type == "MESH":
        uv_project(obj)
        obj.select_set(True)

# Produce placements from the very same height field used for the BSP.
def pos(x,y,lift=0):
    return [x,y,round(height(x,y)+lift,5)]
placements = {
    "sky": "sky\\clear afternoon\\clear afternoon",
    "scenery": [{"tag":"scenery\\trees\\tree_leafy_medium\\tree_leafy_medium", "position_m":pos(x,y), "yaw_degrees":0, "permutation":0}
                for x,y in [(-12,-12),(-22,20),(25,0)]],
    "vehicles": [{"tag":"vehicles\\warthog\\mp_warthog","position_m":pos(-37,-12,.3),"yaw_degrees":0,"team":0}],
    "spawns": [], "flags": [], "pickups": [],
    "teleporters": [{"channel":0,"from_m":pos(-35,9,.05),"to_m":pos(35,9,.05),"from_yaw_degrees":0,"to_yaw_degrees":180}],
    "lights": [{"tag":"levels\\test\\deathisland\\devices\\light fixtures\\light fixture floor1","position_m":[-40,-3.5,.5],"yaw_degrees":0}]
}
for x,y in [(-12,-21),(0,8),(15,-9)]:
    placements["scenery"].append({"tag":"scenery\\rocks\\boulder_granite_medium\\boulder_granite_medium","position_m":pos(x,y),"yaw_degrees":30})
for team,sign in [(0,-1),(1,1)]:
    placements["flags"].append({"position_m":[sign*47,0,.55],"yaw_degrees":0 if team==0 else 180,"team":team})
    for y in [-4,4]:
        placements["spawns"].append({"position_m":[sign*45,y,.65],"yaw_degrees":0 if team==0 else 180,"team":team,"modes":["ctf","slayer"]})
    for tag,y in [("item collections\\single weapons\\assault rifle",-3),("item collections\\single weapons\\pistol",3)]:
        placements["pickups"].append({"tag":tag,"position_m":[sign*44,y,.60],"yaw_degrees":0})
placements["pickups"].append({"tag":"item collections\\powerups\\powerup health pack","position_m":pos(0,-5,.2),"yaw_degrees":0})
(ROOT / "placements.json").write_text(json.dumps(placements,indent=2)+"\n")

# Save the authored source, then export only frame-parented BSP meshes.
bpy.context.view_layer.objects.active = terrain
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "tst.blend"))
out = ROOT / "data" / "levels" / "test" / "tst" / "models"
out.mkdir(parents=True,exist_ok=True)
result = bpy.ops.export_scene.jms(filepath=str(out / "tst.jms"), game_title="halo1", jms_version="8200",
    folder_type="1", folder_structure=False, scale_enum="1", use_scene_properties=False,
    export_render=True, export_collision=False, export_physics=False, hidden_geo=False, nonrender_geo=False,
    apply_modifiers=True, triangulate_faces=True, loop_normals=True, edge_split=False,
    clean_normalize_weights=False, fix_rotations=False, write_textures=False, generate_checksum=True)
assert result == {"FINISHED"}, result
print("TST_GEOMETRY_EXPORTED", out / "tst.JMS")
