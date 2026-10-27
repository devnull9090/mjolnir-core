"""Build TST in Blender 5.1 with Halo Toolset 425; export classic CE JMS.

Run blender --background --factory-startup --python build_geometry.py.
Coordinates in this script are meters; stored Blender coordinates are CE units.
The generated source .blend and .JMS are checked in, engine build outputs are not.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from amber_light import load_spec as load_amber_spec, mark_material as mark_amber_material
parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out-dir", type=Path, default=ROOT,
                    help="Destination for tst.blend, placements.json and optional data/ export")
parser.add_argument("--no-export", action="store_true",
                    help="Fast Blender geometry iteration; do not load Halo exporter or write JMS")
parser.add_argument("--bundle-textures", action="store_true",
                    help="Copy owned texture images into the new output directory")
args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
OUTPUT = args.out_dir.resolve()
OUTPUT.mkdir(parents=True,exist_ok=True)
ADDON = Path(os.environ.get("HALO_BLENDER_ADDONS", r"C:\haloce\tools\halo-blender-425\addons"))
METERS_PER_CE = 3.048
ARENA_HALF_X, ARENA_HALF_Y = 75, 40
BASE_X = 54
POND_X, POND_Y, WATER_Z = 36, -23, -.18
if not args.no_export:
    sys.path.insert(0, str(ADDON))
    import addon_utils
    assert addon_utils.enable("io_scene_halo", default_set=True, persistent=False)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
if hasattr(scene,"halo"):
    scene.halo.game_title = "halo1"
scene["tst_export_pending"] = args.no_export
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
LIGHT = material("mp lights small strips!", (1.0,.80,.50), .35)
LIGHT["source_shader_tag"] = r"levels\test\bloodgulch\shaders\mp lights small strips"
LIGHT["tst_light_atlas"] = True
AMBER_SPEC = load_amber_spec()
AMBER_LIGHT = material(AMBER_SPEC["material"], AMBER_SPEC["color"], .35)
mark_amber_material(AMBER_LIGHT, AMBER_SPEC)
PORTAL = material("example_tutorial_teleporter!", (.12,.8,.05), .3)
PORTAL["source_shader_tag"] = r"levels\test\tutorial\shaders\example_tutorial_teleporter"
WATER = material("tst_water!", (.055, .22, .23), .15)
SKY = material("+sky", (.27, .50, .70))

# Authoring permissions survive separately from shader names. Face overrides
# painted with the MJOLNIR add-on can refine these material defaults.
for mat in (PANELS, FLOOR, RED, BLUE, LIGHT, AMBER_LIGHT, PORTAL, WATER, SKY):
    mat["mjolnir_pcg_policy"] = "NONE"
GROUND["mjolnir_pcg_policy"] = "GROUND"
CLIFF["mjolnir_pcg_policy"] = "BOTH"  # cliff faces plus turf on suitable tops

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
    if len(mesh.materials)==1 and mesh.materials[0].get('tst_light_atlas'):
        # Blood Gulch's 1024x256 sheet is an atlas. Use one blue-white
        # capsule (top-left pixels 326,2 to 380,23), not the whole sheet.
        # Split long lenses into repeated lamps at the capsule's aspect ratio.
        pixels=tuple(obj.get('light_atlas_pixels',mesh.materials[0].get('light_atlas_pixels',(326,2,380,23))))
        aspect=(pixels[2]-pixels[0])/(pixels[3]-pixels[1])
        vertices,faces=[],[]
        for face in mesh.polygons:
            assert len(face.vertices)==4, obj.name
            points=[mesh.vertices[i].co.copy() for i in face.vertices]
            if (points[1]-points[0]).length < (points[2]-points[1]).length:
                points=points[1:]+points[:1]
            length=(points[1]-points[0]).length
            width=(points[3]-points[0]).length
            count=max(1,round(length/width/aspect))
            for i in range(count):
                a,b=i/count,(i+1)/count
                start=len(vertices)
                vertices += [points[0].lerp(points[1],a),points[0].lerp(points[1],b),
                             points[3].lerp(points[2],b),points[3].lerp(points[2],a)]
                faces.append(tuple(range(start,start+4)))
        mesh.clear_geometry()
        mesh.from_pydata(vertices,[],faces)
        mesh.update()
        obj["light_atlas_pixels"]=pixels
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        mat = mesh.materials[poly.material_index]
        if mat.get('tst_surface_role'):
            project_surface_uv(obj, poly, uv, mat['tst_surface_role'])
            continue
        if mat.get('tst_detail_material'):
            mat=bpy.data.materials[mat['tst_detail_material']]
        dominant = max(range(3), key=lambda k: abs(poly.normal[k]))
        axes = [k for k in range(3) if k != dominant]
        for corner, loop in enumerate(poly.loop_indices):
            co = mesh.vertices[mesh.loops[loop].vertex_index].co * METERS_PER_CE
            if mat == GROUND:
                # The stock beach bitmap paints an entire island; its detail
                # maps provide the small surface texture, not a 6 m base repeat.
                uv.data[loop].uv = (co.x / 300 + .5, co.y / 300 + .5)
            elif mat in (RED, BLUE):
                if obj.get("team_color_band"):
                    # The same stock emblem bitmap has a saturated coloured
                    # patch. Sample it for continuous team-colour inlays.
                    u0, u1, v0, v1 = 126 / 256, 132 / 256, 1 - 290 / 512, 1 - 284 / 512
                    uv.data[loop].uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))[corner]
                else:
                    # One complete emblem on each large doorway panel.
                    uv.data[loop].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[corner]
            elif mat.get('tst_light_atlas'):
                px=obj.get('light_atlas_pixels',mat.get('light_atlas_pixels',(326,2,380,23)))
                width,height=mat.get('light_atlas_size',(1024,256))
                u0,u1,v0,v1=px[0]/width,px[2]/width,1-px[3]/height,1-px[1]/height
                uv.data[loop].uv = ((u0,v0),(u1,v0),(u1,v1),(u0,v1))[corner]
            elif mat == PORTAL:
                # One complete shield mask across the doorway, including its
                # clipped upper corners; this is a non-colliding render face.
                xs=[mesh.vertices[i].co.x for i in poly.vertices]
                zs=[mesh.vertices[i].co.z for i in poly.vertices]
                p=mesh.vertices[mesh.loops[loop].vertex_index].co
                uv.data[loop].uv=((p.x-min(xs))/(max(xs)-min(xs)),(p.z-min(zs))/(max(zs)-min(zs)))
            else:
                period = 2 if mat in (PANELS, FLOOR) else 6
                uv.data[loop].uv = (co[axes[0]] / period, co[axes[1]] / period)

# Shared deterministic landform function also drives scenery placements.
sys.path.insert(0, str(ROOT))
from terrain_form import height, is_rock as terrain_is_rock

# Single sealed playable air volume: terrain, perimeter sky walls and ceiling.
xs = sorted(set(range(-ARENA_HALF_X, ARENA_HALF_X+1,2)) |
            set(range(-75,-67)) | set(range(68,76)))
ys = sorted(set(range(-44, ARENA_HALF_Y+1,2)) |
            set(range(-44,-33)) | set(range(27,41)) | set(range(-35,-10)))
xs = sorted(set(xs) | set(range(20,53)))
nx, ny = len(xs)-1, len(ys)-1
vertices = [(x, y, height(x, y)) for y in ys for x in xs]
faces, indices = [], []
for j in range(ny):
    for i in range(nx):
        a = j * (nx + 1) + i
        b, c, d = a + 1, a + nx + 2, a + nx + 1
        # Alternating diagonals prevent a regular visible ridge pattern.
        faces.extend([(a, b, d), (b, c, d)] if (i+j) % 2 else [(a, b, c), (a, c, d)])
        mx,my=(xs[i]+xs[i+1])/2,(ys[j]+ys[j+1])/2
        is_rock = terrain_is_rock(mx,my)
        indices.extend([1 if is_rock else 0] * 2)
boundary = list(range(nx + 1))
boundary += [j * (nx + 1) + nx for j in range(1, ny + 1)]
boundary += [ny * (nx + 1) + i for i in range(nx - 1, -1, -1)]
boundary += [j * (nx + 1) for j in range(ny - 1, 0, -1)]
upper = []
for index in boundary:
    upper.append(len(vertices))
    vertices.append((vertices[index][0], vertices[index][1], 44))
for i in range(len(boundary)):
    k = (i + 1) % len(boundary)
    faces.append((boundary[i], upper[i], upper[k], boundary[k]))
    indices.append(2)
center = len(vertices)
vertices.append((0, 0, 44))
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

def chamfered_cap(name, plan, inset_plan, z0, shoulder, z1, mat=PANELS):
    """Closed cap with a broad physical top bevel, retaining its lower bounds."""
    n = len(plan)
    vertices = [(x,y,z0) for x,y in plan]
    vertices += [(x,y,shoulder) for x,y in plan]
    vertices += [(x,y,z1) for x,y in inset_plan]
    faces = [tuple(reversed(range(n))),tuple(range(2*n,3*n))]
    for start in (0,n):
        faces += [(start+i,start+(i+1)%n,start+(i+1)%n+n,start+i+n)
                  for i in range(n)]
    return mesh_object(name,vertices,faces,[mat])

def portal_cutter(name, x0, x1, half_width, floor, lintel, chamfer, mat=FLOOR):
    """A player-sized opening with the characteristic clipped upper corners.

    The cutter is an extruded convex Y/Z profile, not an applied bevel, so
    its exact boundary stays reproducible for HEK's collision compiler.
    """
    yz = [(-half_width,floor),(half_width,floor),
          (half_width,lintel-chamfer),(half_width-chamfer,lintel),
          (-half_width+chamfer,lintel),(-half_width,lintel-chamfer)]
    n = len(yz)
    vertices = [(x0,y,z) for y,z in yz] + [(x1,y,z) for y,z in yz]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh_object(name,vertices,faces,[mat])


def side_buttress(name, x, side):
    """Broad angled pier which reads in silhouette from the side lanes."""
    vertices = [(x-.72,9.1,-.2),(x+.72,9.1,-.2),
                (x+.72,12.05,-.2),(x-.72,12.05,-.2),
                (x-.52,8.9,6.85),(x+.52,8.9,6.85),
                (x+.52,10.35,6.85),(x-.52,10.35,6.85)]
    faces = [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    if side == -1:
        vertices = [(xx,-yy,zz) for xx,yy,zz in vertices]
        faces = [tuple(reversed(face)) for face in faces]
    return mesh_object(name,vertices,faces,[FLOOR])

def canted_block(name, y0, y1, back, front0, front1, z0, z1):
    return mesh_object(name,
        [(back,y0,z0),(front0,y0,z0),(front0,y1,z0),(back,y1,z0),
         (back,y0,z1),(front1,y0,z1),(front1,y1,z1),(back,y1,z1)],
        [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [FLOOR])

def front_x(z):
    return 7 - .84 * (z + .4) / 6.6

def side_y(z):
    return 11 - 1.32 * (z + .4) / 6.6

for cx, sign, team, trim in [(-BASE_X, 1, "red", RED), (BASE_X, -1, "blue", BLUE)]:
    plan = [(-7,-8),(-5,-11),(5,-11),(7,-8),(7,8),(5,11),(-5,11),(-7,8)]
    verts = [(x,y,-.4) for x,y in plan] + [(x*.88,y*.88,6.2) for x,y in plan]
    fs = [tuple(reversed(range(8))),tuple(range(8,16))]
    fs += [(i,(i+1)%8,(i+1)%8+8,i+8) for i in range(8)]
    base = mesh_object(f"{team}_base_shell", verts, fs, [PANELS, FLOOR])
    # A stepped overhanging roof and broad side piers change the silhouette;
    # fine surface textures alone cannot make a plain box read as Forerunner.
    boolean(base,chamfered_cap("layered_roof_cap",
        bevel_rectangle(-6.4,-9.95,6.4,9.95,1.25),
        bevel_rectangle(-6.1,-9.65,6.1,9.65,1.07),5.9,6.25,6.55),"UNION")
    for side in (-1,1):
        for x in ((-4.1,3.7) if side == -1 else (-4.1,0,3.7)):
            boolean(base,side_buttress("canted_side_pier",x,side),"UNION")
    # The side vestibule gives a second attack/escape direction. Its doorway
    # is rotated with the base, retaining rotationally balanced geometry.
    boolean(base, prism("side_vestibule", bevel_rectangle(-4,-13.4,2.5,-7,.65),
                        -.4,4.9), "UNION")
    boolean(base, box("chamber_cut", (-4.8,-7.8,.45),(5.3,7.8,4.5)))
    boolean(base, portal_cutter("entrance_cut",4.5,9,2.6,.45,3.9,.62))
    # Two overlapping side-entry layers form an alcove with a shadow line.
    boolean(base,prism("side_portal_outer_frame",bevel_rectangle(-4.25,-13.8,2.75,-12.2,.45),
                       -.2,5.35,FLOOR),"UNION")
    side_rebate = portal_cutter("flank_portal_rebate",12.7,14.5,2.4,.45,4.3,.55)
    for vertex in side_rebate.data.vertices:
        xx,yy=vertex.co.x,vertex.co.y
        vertex.co.x=yy-.65/METERS_PER_CE
        vertex.co.y=-xx
    boolean(base,side_rebate)
    # Recut the inner passage after the outer frame union, maintaining the
    # original 3.7 m clear opening and the same floor/spawn elevations.
    side_opening = portal_cutter("flank_portal_inner",6.5,14.6,1.85,.45,3.7,.45)
    for vertex in side_opening.data.vertices:
        xx,yy=vertex.co.x,vertex.co.y
        vertex.co.x=yy-.65/METERS_PER_CE
        vertex.co.y=-xx
    boolean(base,side_opening)
    # Each long deck sits inside a real recessed gasket. The broad pale rim
    # and bevel catch light at arena distance; deck height stays below the
    # existing roof crown and the gasket remains above the interior ceiling.
    for x0, x1 in [(-5.35,-.45),(.45,5.35)]:
        boolean(base, prism("roof_coffer", bevel_rectangle(x0,-8.4,x1,8.4,.6),
                            6.15,7.3,FLOOR))
        boolean(base,chamfered_cap("roof_inset_deck",
            bevel_rectangle(x0+.23,-8.17,x1-.23,8.17,.48),
            bevel_rectangle(x0+.40,-8.0,x1-.40,8.0,.38),
            6.08,6.27,6.40,FLOOR),"UNION")
        # Sparse assembly joints break long armor leaves into intentional
        # panels without turning the roof into another regular tile grid.
        for y in (-3.4,3.4):
            boolean(base,box("roof_deck_joint",(x0+.48,y-.06,6.31),
                             (x1-.48,y+.06,6.48),FLOOR))
    # Thick canted entrance ribs and lintel sit inside the existing maximum
    # footprint. They join the shell, so the BSP still has one sealed boundary.
    for side in (-1,1):
        y0,y1 = (3.25,4.25) if side == 1 else (-4.25,-3.25)
        boolean(base, canted_block("door_buttress",y0,y1,5.7,7.85,6.85,.1,6.7),"UNION")
    boolean(base,canted_block("door_header",-4.25,4.25,5.7,7.25,6.75,4.45,6.35),"UNION")
    # A larger shallow rebate around the original entrance gives the frame
    # depth without changing the walkable opening or chamber dimensions.
    boolean(base,portal_cutter("door_rebate",6.0,9,3.16,.45,4.4,.72))
    # Shallow bays, lower plinth and an upper groove articulate the side walls.
    for side in (-1, 1):
        for u in (-3.0, .1, 3.2):
            if side == -1 and abs(u) < 1:
                # The vestibule covers this bay; carving through it creates
                # a coincident edge at the inner portal's clipped corner.
                continue
            ymin,ymax = (10.02,11.5) if side == 1 else (-11.5,-10.02)
            boolean(base, box("panel_recess", (u-1.10,ymin,1.15),(u+1.10,ymax,3.45)))
        ymin,ymax = (9.85,11.5) if side == 1 else (-11.5,-9.85)
        boolean(base,box("upper_side_channel",(-4.1,ymin,4.70),(4.1,ymax,4.98),FLOOR))
    # Interior wall recesses catch placed light and demonstrate the material
    # scale without adding tiny collision ledges to the traversable floor.
    for yy in (-5.8, 5.8):
        boolean(base,box("interior_wall_niche",(-5.15,yy-1.3,1.1),(-4.65,yy+1.3,3.4),FLOOR))
    # Interior construction is joined to the shell, not floating decorative
    # intersections. All intrusions stay against walls or above 4.1 m, leaving
    # the 2.4 m player clearance envelope and both existing doors unchanged.
    # The bevelled ribs divide broad panels without noisy, tiny BSP cuts.
    for y in (-7.35,-3.1,3.1,7.35):
        for x in (-4.72,5.22):
            boolean(base,prism("interior_vertical_rib",
                bevel_rectangle(x-.20,y-.22,x+.20,y+.22,.07),.34,4.59,FLOOR),"UNION")
    for x in (-2.65,2.55):
        for y in (-7.75,7.75):
            # Side entrance is centred on x=-.65 and remains fully clear.
            boolean(base,prism("interior_side_rib",
                bevel_rectangle(x-.22,y-.20,x+.22,y+.20,.07),.34,4.59,FLOOR),"UNION")
    for y in (-5.1,0,5.1):
        # Faceted beam undersides echo the clipped portal corners.
        yz=[(y-.22,4.58),(y+.22,4.58),(y+.22,4.30),
            (y+.10,4.18),(y-.10,4.18),(y-.22,4.30)]
        n=len(yz)
        beam=mesh_object("interior_ceiling_beam",
            [(-4.95,yy,z) for yy,z in yz]+[(5.45,yy,z) for yy,z in yz],
            [tuple(reversed(range(n))),tuple(range(n,2*n))]+
            [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],[FLOOR])
        # The profile above is clockwise; make its solid outward-facing.
        bm=bmesh.new(); bm.from_mesh(beam.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(beam.data); bm.free()
        boolean(base,beam,"UNION")
    boolean(base,box("interior_longitudinal_ceiling_rib",
                    (-.02,-7.95,4.29),(.28,7.95,4.60),FLOOR),"UNION")
    # Broad skirting stops short of every door. It extends only 16 cm into
    # the chamber, well away from starts, flag stands and fixture positions.
    boolean(base,box("interior_rear_skirting",(-4.95,-7.9,.32),(-4.64,7.9,.68),FLOOR),"UNION")
    for y0,y1 in [(-7.9,-2.72),(2.72,7.9)]:
        boolean(base,box("interior_front_skirting",(5.14,y0,.32),(5.45,y1,.68),FLOOR),"UNION")
    boolean(base,box("interior_north_skirting",(-4.9,7.64,.32),(5.4,7.95,.68),FLOOR),"UNION")
    for x0,x1 in [(-4.9,-2.60),(1.3,5.4)]:
        boolean(base,box("interior_south_skirting",(x0,-7.95,.32),(x1,-7.64,.68),FLOOR),"UNION")
    # Recessed panel divisions are intentionally centimetres wide, not
    # zero-thickness decals. They remain larger than the final 2.7 cm weld.
    for zz in (1.85,3.18):
        boolean(base,box("rear_panel_joint",(-4.91,-7.15,zz),(-4.73,7.15,zz+.08),FLOOR))
        boolean(base,box("front_panel_joint",(5.23,-7.15,zz),(5.42,7.15,zz+.08),FLOOR))
        boolean(base,box("north_panel_joint",(-4.4,7.73,zz),(4.9,7.92,zz+.08),FLOOR))
        boolean(base,box("south_panel_joint",(-4.4,-7.92,zz),(4.9,-7.73,zz+.08),FLOOR))
    for x in (-2.4,2.4):
        boolean(base,box("ceiling_panel_joint",(x-.04,-7.3,4.46),(x+.04,7.3,4.60),FLOOR))
    # Elevated copies of the existing floor fixture sit on real shallow
    # shelves. Their placements below drive actual scenario light fixtures.
    for y in (-5.3,5.3):
        boolean(base,prism("upper_fixture_shelf",
            bevel_rectangle(4.67,y-.85,5.45,y+.85,.10),3.62,3.82,FLOOR),"UNION")
        boolean(base,box("upper_fixture_hood",(4.70,y-.90,4.06),(5.48,y+.90,4.60),FLOOR),"UNION")
    ramp = mesh_object(f"{team}_entry_ramp", [(6.4,-3.5,-.3),(11,-3.5,-.3),(11,3.5,-.3),(6.4,3.5,-.3),
                      (6.4,-3.5,.45),(11,-3.5,.10),(11,3.5,.10),(6.4,3.5,.45)],
                       [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], [FLOOR])
    boolean(base, ramp, "UNION")
    flank_ramp = mesh_object(f"{team}_flank_ramp",
        [(-3.2,-12.8,-.3),(1.9,-12.8,-.3),(1.9,-17,-.3),(-3.2,-17,-.3),
         (-3.2,-12.8,.45),(1.9,-12.8,.45),(1.9,-17,.12),(-3.2,-17,.12)],
        [(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],[FLOOR])
    boolean(base, flank_ramp, "UNION")
    # A long rear ramp reaches the roof. The low end is outside both door
    # funnels, so it offers a flank without landing in a respawn position.
    # Bury the toe below terrain: a 6 cm exposed vertical lip was collapsed
    # by HEK intermediate plane welding, leaving open collision edges.
    def ramp_solid(name,x0,x1,profile,material):
        n=len(profile)
        obj=mesh_object(name,[(x,y,z) for x in (x0,x1) for y,z in profile],
            [tuple(reversed(range(n))),tuple(range(n,2*n))]+
            [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],[material])
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
        return obj
    # The slope ends at y=4. The final four metres are a level landing, flush
    # with the inset roof deck at 6.40 m, with a broad left turn onto the roof.
    boolean(base,ramp_solid(f'{team}_roof_access',-10,-5.5,
        [(-13,-.4),(8,-.4),(8,6.4),(4,6.4),(-13,-.15)],FLOOR),'UNION')
    # Clear the raised roof rim before joining the deck, avoiding a curb or
    # jump at the last step. The platform bridges the old inset-deck gasket.
    boolean(base,box('roof_landing_rim_opening',(-6.7,3.95,6.4),(-3.55,8.05,7.4),FLOOR))
    boolean(base,box('roof_access_level_landing',(-10,4,5.98),(-3.6,8,6.4),FLOOR),'UNION')
    boolean(base,ramp_solid('roof_ramp_outer_kerb',-10,-9.72,
        [(-13,-.15),(4,6.4),(8,6.4),(8,6.65),(4,6.65),(-13,.10)],PANELS),'UNION')
    boolean(base,prism('roof_landing_end_kerb',
        bevel_rectangle(-10,7.78,-5.65,8.10,.10),6.35,6.65,PANELS),'UNION')
    # An inset structural panel under the landing breaks up the exposed solid
    # support without carving into the walking surface or interior chamber.
    boolean(base,ramp_solid('roof_landing_support_recess',-10.1,-9.72,
        [(4.48,.65),(7.50,.65),(7.50,5.68),(4.48,5.68)],FLOOR))
    for poly in base.data.polygons:
        if poly.normal.z > .85 and poly.center.z*METERS_PER_CE < 5.85:
            poly.material_index = 1
    transform_base(base, cx, sign)
    # Thin non-colliding inlays reference existing CE shader materials. They
    # lie on the authored skirting, stop at doors/ribs, and do not affect the
    # sealed collision boundary. Emission colour in Blender is only a study;
    # actual engine appearance is resolved by these existing shader tags.
    inlays = []
    for y0,y1 in [(-6.9,-3.5),(-2.7,2.7),(3.5,6.9)]:
        inlays.append([(-4.625,y0,.50),(-4.625,y1,.50),(-4.625,y1,.63),(-4.625,y0,.63)])
    for y0,y1 in [(-6.9,-3.5),(3.5,6.9)]:
        inlays.append([(5.125,y1,.50),(5.125,y0,.50),(5.125,y0,.63),(5.125,y1,.63)])
    for x0,x1 in [(-4.3,-3.0),(-2.3,2.1),(3.0,4.7)]:
        inlays.append([(x1,7.625,.50),(x0,7.625,.50),(x0,7.625,.63),(x1,7.625,.63)])
    for x0,x1 in [(-4.3,-3.0),(1.6,2.1),(3.0,4.7)]:
        inlays.append([(x0,-7.625,.50),(x1,-7.625,.50),(x1,-7.625,.63),(x0,-7.625,.63)])
    for index,vertices in enumerate(inlays):
        inset = mesh_object(f"{team}_interior_team_inlay_{index}",vertices,[(0,1,2,3)],[trim])
        inset["team_color_band"] = True
        transform_base(inset,cx,sign)
    for index,y in enumerate((-5.3,5.3)):
        lens = mesh_object(f"{team}_upper_light_lens_{index}",
            [(4.73,y-.72,4.045),(4.73,y+.72,4.045),
             (5.10,y+.72,4.045),(5.10,y-.72,4.045)],[(0,1,2,3)],[LIGHT])
        lens["authored_light_lens"] = True
        lens["source_shader_tag"] = LIGHT["source_shader_tag"]
        transform_base(lens,cx,sign)
    # Team emblems are large enough to identify the base from across the arena.
    # Every accent is render-only and follows the actual sloped facade.
    for side in (-1,1):
        y0,y1 = (4.5,6.35) if side == 1 else (-6.35,-4.5)
        panel = mesh_object(f"{team}_team_emblem_{side}",
            [(front_x(.85)+.025,y0,.85),(front_x(.85)+.025,y1,.85),
             (front_x(3.75)+.025,y1,3.75),(front_x(3.75)+.025,y0,3.75)],[(0,1,2,3)],[trim])
        transform_base(panel,cx,sign)
        # A broad team-colour stripe along each long wall reads from oblique
        # views, where the front-facing emblem otherwise disappears.
        band = mesh_object(f"{team}_side_colour_{side}",
            [(-4.2,side*(side_y(4.08)+.025),4.08),(4.2,side*(side_y(4.08)+.025),4.08),
             (4.2,side*(side_y(4.42)+.025),4.42),(-4.2,side*(side_y(4.42)+.025),4.42)],
            [(0,1,2,3) if side == -1 else (3,2,1,0)],[trim])
        band["team_color_band"] = True
        transform_base(band,cx,sign)
        # Canted vertical accents make the entrance ribs legible at a distance.
        y0,y1 = (3.57,3.93) if side == 1 else (-3.93,-3.57)
        def rib_x(z):
            return 7.85 + (6.85-7.85)*(z-.1)/(6.7-.1) + .025
        band = mesh_object(f"{team}_door_colour_{side}",
            [(rib_x(.5),y0,.5),(rib_x(.5),y1,.5),(rib_x(5.65),y1,5.65),(rib_x(5.65),y0,5.65)],
            [(0,1,2,3)],[trim])
        band["team_color_band"] = True
        transform_base(band,cx,sign)

# Low octagonal control platform: the continuous battered perimeter is
# walkable, and the entire platform is backed by the gameplay BSP.
# Preserve the original radius/elevation and battered approach while adding
# a shallow inset gasket between the octagonal edge armor and center deck.
# All rings form one closed solid; the 13 cm recess has no raised obstruction.
platform_rings = [(7,-.5),(5,.6),(4.60,.6),(4.42,.47),(4.14,.47),(3.96,.6)]
platform_verts = [(radius*math.cos(i*math.tau/8),radius*math.sin(i*math.tau/8),z)
                  for radius,z in platform_rings for i in range(8)]
platform_faces = [tuple(reversed(range(8))),tuple(range(40,48))]
platform_indices = [0,0]
for ring, material_index in enumerate((0,1,1,0,1)):
    start = ring*8
    platform_faces += [(start+i,start+(i+1)%8,start+(i+1)%8+8,start+i+8)
                       for i in range(8)]
    platform_indices += [material_index]*8
platform = mesh_object("midfield_control_gameplay_solid",platform_verts,platform_faces,
                       [FLOOR,PANELS],platform_indices)
for x in (-2.1,0,2.1):
    boolean(platform,box("control_pad_long_joint",(x-.06,-2.65,.52),(x+.06,2.65,.75),FLOOR))
boolean(platform,box("control_pad_cross_joint",(-3.65,-.06,.52),(3.65,.06,.75),FLOOR))

from perimeter_architecture import build as build_perimeter, ARRIVALS
wall=build_perimeter(mesh_object,box,prism,bevel_rectangle,boolean,PANELS,FLOOR,LIGHT,PORTAL)
from facility_architecture import build as build_facility
build_facility(wall,mesh_object,box,prism,bevel_rectangle,boolean,LIGHT,RED,BLUE,AMBER_LIGHT)

from facility_edge_wear import prepare as prepare_facility_edge_wear, apply as apply_facility_edge_wear
detail_collection=bpy.data.collections.new("DETAIL - Forerunner precision armor (render only)")
scene.collection.children.link(detail_collection)
for obj in list(scene.objects):
    if obj.get('mjolnir_render_detail'):
        bpy.context.view_layer.objects.active=obj
        bevel=obj.modifiers.new('Precision armor edge chamfer','BEVEL')
        bevel.width=obj.get('precision_bevel_m',.045)/METERS_PER_CE; bevel.segments=1
        bevel.affect='EDGES'; bevel.limit_method='ANGLE'
        prepare_facility_edge_wear(obj,bevel,METERS_PER_CE)
        bpy.ops.object.modifier_apply(modifier=bevel.name)
        apply_facility_edge_wear(obj,METERS_PER_CE)
        detail_mesh=bmesh.new(); detail_mesh.from_mesh(obj.data)
        bad_edges=sum(not edge.is_manifold for edge in detail_mesh.edges)
        detail_mesh.free()
        if bad_edges:
            raise RuntimeError(f'Render detail {obj.name} has {bad_edges} non-manifold edges')
        if obj.get('engraved_armor') and not any(
                obj.data.materials[face.material_index].get('tst_detail_material')==FLOOR.name
                for face in obj.data.polygons):
            raise RuntimeError(f'Engraving cut did not create recessed faces on {obj.name}')
        for collection in list(obj.users_collection): collection.objects.unlink(obj)
        detail_collection.objects.link(obj)

from architecture_surfaces import assign as assign_surfaces, project_uv as project_surface_uv
assign_surfaces(scene)

# Keep readable, individually editable source meshes in a hidden collection.
# The exported result is the single merged air boundary, while a community
# member can unhide these construction sources to study each component.
source_collection = bpy.data.collections.new("SOURCE - terrain and base construction")
scene.collection.children.link(source_collection)
for obj in list(scene.objects):
    if obj == terrain or obj.name.endswith(("_base_shell", "_gameplay_solid")):
        source = obj.copy()
        source.data = obj.data.copy()
        source.name = "SOURCE_" + obj.name
        source.parent = None
        source_collection.objects.link(source)
        source.hide_render = True
        source.hide_set(True)
        source["authoring_note"] = "Study/edit source copy; regenerate exported boundary with build_geometry.py."

# Cut architecture out of the enclosed playable air volume. Exporting
# intersecting ground and base shells independently leaves coincident BSP
# surfaces at their seams; one boolean result has the actual room boundary.
bm = bmesh.new()
bm.from_mesh(terrain.data)
bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
bm.to_mesh(terrain.data)
bm.free()
from terrain_form import FACILITY_AIR_EXTENSION
# The original outdoor air volume ends at y=40. Extend air only inside the
# new facility's closed outer envelope, then subtract its walls/floor/roof
# below. This exposes the deeper indoor branches without opening rear sky.
boolean(terrain,box('facility_contained_air_extension',*FACILITY_AIR_EXTENSION,PANELS),'UNION')
for obj in list(scene.objects):
    if not obj.name.startswith("SOURCE_") and obj.name.endswith(("_base_shell", "_gameplay_solid")):
        boolean(terrain, obj)
bm = bmesh.new()
bm.from_mesh(terrain.data)
bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
# Exact Boolean intersections against the terrain grid can leave millimetre
# slivers which compile structurally but have near-zero lightmap UV area.
# Weld below four centimetres, then retriangulate coplanar patches as a whole.
# HEK also rejects 1â€“2 cm slivers whose world-space area looks reasonable but
# whose UV area is tiny under the map-wide 150 m beach projection.
# Material delimiters retain floor/wall and cliff/ground boundaries.
bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.012)
bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.012)
bmesh.ops.dissolve_limit(bm, angle_limit=0.0001, verts=list(bm.verts),
                        edges=list(bm.edges), delimit={"MATERIAL"})
bmesh.ops.triangulate(bm, faces=list(bm.faces))
# Dissolving a zero-area Boolean sliver can leave a wire edge with no linked
# faces. Remove that debris without touching the closed surface: boundary
# edges (one face) and non-manifold junctions (three or more) still fail below.
wire_edges = [edge for edge in bm.edges if not edge.link_faces]
surface_faces = len(bm.faces)
if wire_edges:
    wire_count = len(wire_edges)
    bmesh.ops.delete(bm, geom=wire_edges, context="EDGES")
    loose_vertices = [vertex for vertex in bm.verts if not vertex.link_edges]
    bmesh.ops.delete(bm, geom=loose_vertices, context="VERTS")
    assert len(bm.faces) == surface_faces, "Wire cleanup changed the authored surface"
    print("TST_REMOVED_WIRE_DEBRIS", wire_count, "edges", len(loose_vertices), "vertices")
bad_edges = [edge for edge in bm.edges if not edge.is_manifold]
if bad_edges:
    print("TST_NONMANIFOLD_EDGES_METRES",[[tuple(round(c*METERS_PER_CE,5) for c in v.co) for v in e.verts] for e in bad_edges[:20]])
    raise RuntimeError(f"Sealed terrain boundary has {len(bad_edges)} non-manifold edges; source not saved")
bm.to_mesh(terrain.data)
bm.free()

# A water render plane, not a solid cap. The shallow basin is real terrain.
count = 48
verts = [(POND_X,POND_Y,WATER_Z)] + [(POND_X+16.5*math.cos(i*math.tau/count),POND_Y+12.6*math.sin(i*math.tau/count),WATER_Z) for i in range(count)]
pond = mesh_object("pond_surface",verts,[(0,i+1,(i+1)%count+1) for i in range(count)],[WATER])
for obj in list(scene.objects):
    if obj.type == "MESH" and not obj.name.startswith("SOURCE_"):
        uv_project(obj)
        obj.select_set(True)

# Produce placements from the very same height field used for the BSP.
def pos(x,y,lift=0):
    return [x,y,round(height(x,y)+lift,5)]
placements = {
    "sky": "sky\\clear afternoon\\clear afternoon",
    "scenery": [{"tag":"scenery\\trees\\tree_leafy_medium\\tree_leafy_medium", "position_m":pos(x,y), "yaw_degrees":0, "permutation":0}
                # Keep the full native canopy south of the balcony metalwork,
                # not merely its trunk outside the player route markers.
                for x,y in [(-17,-15),(-24,12),(32,1)]],
    "vehicles": [{"tag":"vehicles\\warthog\\mp_warthog","position_m":pos(-46,-18,.3),"yaw_degrees":0,"team":0},
                 {"tag":"vehicles\\warthog\\mp_warthog","position_m":pos(38,10,.3),"yaw_degrees":180,"team":1}],
    "spawns": [], "flags": [], "pickups": [],
    "teleporters": [
        {"channel":0,"from_m":pos(-46,14,.05),"to_m":pos(-12,21.5,.05),"from_yaw_degrees":0,"to_yaw_degrees":0},
        {"channel":1,"from_m":pos(46,-14,.05),"to_m":pos(12,-26,.05),"from_yaw_degrees":180,"to_yaw_degrees":180}],
    "lights": [],
    # Authoring intent only. These become supported modes only when their
    # runtime variants and objective placements have passed actual matches.
    "objective_markers": {
        "oddball": {"position_m":[0,0,.8],"status":"planned"},
        "king": {"positions_m":[[0,0,.8],pos(-24,15,.2),pos(24,-15,.2)],"status":"planned"}
    }
}
for channel, arrival in enumerate(ARRIVALS,2):
    side = -1 if arrival[0] < 0 else 1
    placements["teleporters"].append({"channel":channel,
        "from_m":pos(side*44,22,.05),"to_m":list(arrival),
        "from_yaw_degrees":90,"to_yaw_degrees":270,
        "to_scenery":False,
        "authoring_note":"Ground-to-balcony arrival in front of the walk-through return shield"})
    placements["teleporters"].append({"channel":channel+2,
        "from_m":[arrival[0],30.85,7.25],"to_m":pos(side*44,19,.05),
        "from_yaw_degrees":90,"to_yaw_degrees":270,"scenery":False,"shield_return":True,
        "authoring_note":"Walk into the green shield to return; separate landing avoids bounce-back"})
placements["structure_review_points"] = [
    {"name":f"balcony_walk_{x}","position_m":[x,24.0,7.25]}
    for x in range(-66,67,3)] + [
    {"name":f"tower_passage_{cx}_{dx}_{y}","position_m":[cx+dx,y,7.25]}
    for cx in (-33.0,0,33.0) for dx in range(-6,7,2) for y in (27.0,28.8,30.5)] + [
    {"name":f"exit_step_{x}_{z}","position_m":[x,y,z+.05]}
    for x in (-33,33) for y,z in ((20,4.8),(16.5,2.4))]
placements['structure_review_points'] += [
    {'name':f'{team}_roof_ramp_{y}',
     'position_m':[cx-sign*7.75,sign*y,.05+min(6.4,-.15+6.55*(y+13)/17)]}
    for cx,sign,team in ((-BASE_X,1,'red'),(BASE_X,-1,'blue')) for y in range(-12,8,2)]
placements['structure_review_points'] += [
    {'name':f'{team}_roof_landing_{x}_{y}','position_m':[cx+sign*x,sign*y,6.45]}
    for cx,sign,team in ((-BASE_X,1,'red'),(BASE_X,-1,'blue'))
    for x in (-8.9,-7.75,-6.7,-5.6,-4.5,-3.7) for y in (4.6,6.0,7.2)]
for x,y in [(-20,-27),(20,21),(-12,8),(12,-8),(-38,10),(38,-10),(-35,-30),(25,21)]:
    placements["scenery"].append({"tag":"scenery\\rocks\\boulder_granite_medium\\boulder_granite_medium","position_m":pos(x,y),"yaw_degrees":30})
for team,side in [(0,-1),(1,1)]:
    cx, facing = side*BASE_X, -side
    yaw = 0 if team == 0 else 180
    placements["flags"].append({"position_m":[cx-facing*2,0,.65],"yaw_degrees":yaw,"team":team})
    for local_x in (-2,1.5):
        for local_y in (-5.2,5.2):
            placements["spawns"].append({"position_m":[cx+facing*local_x,facing*local_y,.65],
                "yaw_degrees":yaw,"team":team,"modes":["ctf","slayer"]})
    for local_x in (-3,4):
        for local_y in (-20,20):
            placements["spawns"].append({"position_m":pos(cx+facing*local_x,facing*local_y,.65),
                "yaw_degrees":yaw,"team":team,"modes":["ctf","slayer"]})
    for tag,local_y in [("item collections\\single weapons\\assault rifle",-3.5),
                        ("item collections\\single weapons\\pistol",3.5)]:
        placements["pickups"].append({"tag":tag,"position_m":[cx+facing*3,facing*local_y,.60],"yaw_degrees":yaw})
    for local_x,local_y in [(-4.1,-6.8),(-4.1,6.8),(4,3.8),(0,-11.9)]:
        placements["lights"].append({"tag":"levels\\test\\deathisland\\devices\\light fixtures\\light fixture floor1",
            "position_m":[cx+facing*local_x,facing*local_y,.50],"yaw_degrees":yaw})
    for local_y in (-5.3,5.3):
        placements["lights"].append({"tag":"levels\\test\\deathisland\\devices\\light fixtures\\light fixture floor1",
            "position_m":[cx+facing*4.94,facing*local_y,3.83],"yaw_degrees":yaw,
            "authoring_note":"Existing floor fixture supported by upper wall shelf; no custom light tag"})
    placements["pickups"].append({"tag":"item collections\\powerups\\powerup health pack",
        "position_m":pos(cx+facing*13,side*18,.2),"yaw_degrees":yaw})
for x,y in [(-34,-20),(34,12),(-24,18),(24,-18),(-10,-20),(10,20),(-42,10),(42,-10)]:
    # Neutral starts support FFA; they must not be selected as a CTF team's
    # initial base starts. The scenario reader explicitly accepts team -1.
    placements["spawns"].append({"position_m":pos(x,y,.65),"yaw_degrees":0 if x<0 else 180,
                                 "team":-1,"modes":["all"]})
(OUTPUT / "placements.json").write_text(json.dumps(placements,indent=2)+"\n")
from perimeter_dressing import document as perimeter_dressing_document
(OUTPUT / "perimeter_dressing.json").write_text(json.dumps(perimeter_dressing_document(),indent=2)+"\n")

# Keep the actual submerged pond bed bare in the runtime scatter as well as
# the preview. The render water plane itself does not exclude grass below it.
policy_attribute=terrain.data.attributes.get('mjolnir_pcg_policy') or terrain.data.attributes.new('mjolnir_pcg_policy','INT','FACE')
from terrain_form import facility_contains
for face in terrain.data.polygons:
    center=face.center*METERS_PER_CE
    if facility_contains(center.x,center.y,.5) and center.z < 6.4:
        policy_attribute.data[face.index].value=1  # NONE: no PCG in enclosed rooms.
    elif center.z < WATER_Z and ((center.x-POND_X)/16.5)**2+((center.y-POND_Y)/12.6)**2<1:
        policy_attribute.data[face.index].value=1  # NONE
    elif center.y < -36 and center.z > 8 and terrain.data.materials[face.material_index] == CLIFF:
        # Exposed southern crown: rock cladding is allowed, grass is not.
        # This explicit face override avoids a continuous turf stripe on the
        # foreground fracture and demonstrates permissions independent of UVs.
        policy_attribute.data[face.index].value=3  # CLIFF

# Save the authored source, then export only frame-parented BSP meshes.
bpy.context.view_layer.objects.active = terrain
bpy.context.view_layer.update()
# Keep authored images portable beside the source, including --out-dir runs.
for image in bpy.data.images:
    if image.source == 'FILE' and image.filepath:
        if args.bundle_textures:
            from bundle_textures import copy_owned_image
            image.filepath = copy_owned_image(bpy.path.abspath(image.filepath), ROOT, OUTPUT)
        else:
            image.filepath = bpy.path.relpath(bpy.path.abspath(image.filepath), start=str(OUTPUT)).replace('\\','/')
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "tst.blend"), relative_remap=False)
print("TST_GEOMETRY_SAVED", OUTPUT / "tst.blend")
sys.path.insert(0, str(ROOT.parents[2] / "tools" / "blender"))
from mjolnir_level.surface import write_surface_policy
policy_path = OUTPUT / "tst.surfaces.json"
policy_temporary = OUTPUT / "tst.surfaces.json.tmp"
policy = write_surface_policy(scene, policy_temporary)
for attempt in range(5):
    try:
        policy_temporary.replace(policy_path)
        break
    except PermissionError:
        # Windows indexers/viewers can briefly hold the destination open.
        # Keep the previous complete policy if the sharing lock persists.
        if attempt==4: raise
        time.sleep(.1*(2**attempt))
print("TST_SURFACE_POLICY", policy["counts"])
if args.no_export:
    print("TST_NO_EXPORT: source geometry updated; existing JMS/game build unchanged")
    raise SystemExit(0)
out = OUTPUT / "data" / "levels" / "test" / "tst" / "models"
out.mkdir(parents=True,exist_ok=True)
result = bpy.ops.export_scene.jms(filepath=str(out / "tst.jms"), game_title="halo1", jms_version="8200",
    folder_type="1", folder_structure=False, scale_enum="1", use_scene_properties=False,
    export_render=True, export_collision=False, export_physics=False, hidden_geo=False, nonrender_geo=False,
    apply_modifiers=True, triangulate_faces=True, loop_normals=True, edge_split=False,
    clean_normalize_weights=False, fix_rotations=False, write_textures=False, generate_checksum=True)
assert result == {"FINISHED"}, result
print("TST_GEOMETRY_EXPORTED", out / "tst.JMS")
