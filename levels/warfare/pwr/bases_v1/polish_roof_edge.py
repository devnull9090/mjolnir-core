"""Replace the tiered front cornice with the gatehouse's bevelled roof casting."""

import bmesh
import bpy
from mathutils import Matrix

from finishing_materials import finish_scene_geometry
from polish_home import Assembly


# Section across the right half of the Red gate, in metres. Each station gives
# the X position at the crest and toe, and the two Y/Z positions of the bevel.
# The outward displacement of the toe continues the portal's raked jambs.
STATIONS = (
    (0.00, 0.00, -16.36, 10.63, -17.97, 9.52),
    (6.24, 6.81, -16.36, 10.63, -17.97, 9.52),
    (6.84, 7.50, -16.30, 10.71, -18.08, 9.43),
    (8.34, 8.66, -15.74, 10.84, -18.04, 9.37),
    (8.86, 9.16, -15.79, 10.76, -16.94, 9.42),
    (9.40, 10.28, -15.83, 10.66, -16.97, 9.49),
    (11.52, 12.03, -15.86, 10.64, -17.62, 9.48),
    (12.42, 12.75, -15.86, 10.64, -17.69, 9.51),
    (20.92, 21.24, -15.82, 10.63, -17.69, 9.51),
    (21.69, 22.07, -15.80, 10.63, -17.68, 9.43),
    (23.30, 23.86, -15.74, 10.63, -17.67, 9.51),
    (24.43, 25.09, -15.55, 10.72, -17.96, 9.47),
    (25.60, 25.98, -15.48, 10.71, -17.92, 9.33),
    (26.19, 26.30, -15.42, 10.65, -16.94, 9.47),
    (27.75, 27.82, -15.48, 10.54, -16.94, 9.46),
)


def _section(row, sign, shift=0., *, gasket=False):
    x, toe_x, y, z, toe_y, toe_z = row
    end = .030 if gasket else 0.
    def point(px, py, pz):
        return (sign*(px+shift), py+end, pz-end)
    # Rebate the lintel to expose the engraved band underneath. At either
    # shoulder the same casting returns into the solid pier instead.
    if x <= 6.24:
        lip = point(toe_x, toe_y+.014, toe_z-.044)
        return_toe = point(toe_x, toe_y+.54, toe_z-.08)
        return_z = toe_z-.10
    else:
        outer_shoulder = x >= 24.43
        depth = 1.08 if outer_shoulder else .55
        lip = point(toe_x, toe_y-.015, toe_z-.09)
        # The wing's return leans into the corner pier below the short step.
        return_toe = point(toe_x-(.17 if outer_shoulder else .02),
                           toe_y+(.14 if outer_shoulder else -.035), toe_z-depth)
        return_z = toe_z-depth-.04
    return [
        point(x,-12.80,9.34), point(x,-12.80,10.50),
        point(x,-13.55,10.54), point(x,y,z),
        point(toe_x,toe_y,toe_z), lip, return_toe, point(x,-14.12,return_z),
    ]


def _castings():
    shell = Assembly("integral bevelled roof casting", .020)
    key = Assembly("recessed roof joint beds", .008)
    # One piece spans the main gate. A shoulder, a quiet panel and an outer
    # haunch follow on each side. The wing surfaces share one roof datum.
    shell.loft([_section(STATIONS[1],-1,-.022),_section(STATIONS[0],1),
                _section(STATIONS[1],1,-.022)],"shell")
    for side in (-1,1):
        for i,j in ((1,5),(5,8),(8,11),(11,14)):
            rings = [_section(STATIONS[i],side,.022)]
            rings.extend(_section(row,side) for row in STATIONS[i+1:j])
            rings.append(_section(STATIONS[j],side,-.022 if j!=14 else 0.))
            shell.loft(rings,"shell")
        for i in (1,5,8,11):
            key.loft([_section(STATIONS[i],side,-.12,gasket=True),
                      _section(STATIONS[i],side,.12,gasket=True)],"graphite")
    return shell,key


def _family(ob, collections):
    members = [[o for o in c.objects if o.type == "MESH" and o.data == ob.data]
               for c in collections]
    if any(len(group)!=1 for group in members):
        raise ValueError(f"Ambiguous architecture mesh linkage for {ob.name}")
    return [group[0] for group in members]


def _seat_y(p):
    # The concealed seat follows the diagonal's back. It affects only the
    # existing upper corner, so the entrance columns keep their floor profile.
    if p.z < 9.25 or abs(p.x) > 28.12 or p.y > -12.8:
        return p.y
    section = []
    for x, toe_x, y, z, toe_y, toe_z in STATIONS:
        t = max(0., min(1., (p.z-toe_z)/(z-toe_z)))
        section.append((toe_x+(x-toe_x)*t, toe_y+(y-toe_y)*t, toe_z))
    px = abs(p.x)
    for left,right in zip(section,section[1:]):
        if px <= right[0]:
            u=(px-left[0])/(right[0]-left[0])
            face=left[1]+(right[1]-left[1])*u
            spring=left[2]+(right[2]-left[2])*u
            break
    else:
        _,face,spring = section[-1]
    # A pressed seat backs the physical toe, with enough clearance above it
    # to keep the old diagonal armor from piercing the new mitred face.
    seat = face + min(.64,max(0.,(p.z-spring+.10)*2.4))
    # Leave a positive derivative at the deepest part of the seat. Thin
    # faceplates have separate front and back skins that must stay separate.
    return p.y+.91*max(0.,seat-p.y)


def _seat_existing(ob):
    world = ob.matrix_world
    if not any(_seat_y(p)-p.y > .002 for v in ob.data.vertices
               for p in [world@v.co]):
        return False
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        bm.transform(world)
        zs = [v.co.z for v in bm.verts]
        # Anchor the intact lower section before the first displaced row.
        # Otherwise Blender's triangles stretch the new seat down a tall pier.
        for level in (9.04, 9.25, 9.62, 10.04):
            if min(zs)<level-.005 and max(zs)>level+.005:
                bmesh.ops.bisect_plane(bm, geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                                       dist=.00001, plane_co=(0,0,level), plane_no=(0,0,1))
        for v in bm.verts:
            v.co.y = _seat_y(v.co)
        bm.transform(world.inverted())
        bm.normal_update()
        bm.to_mesh(ob.data)
        ob.data.update()
    finally:
        bm.free()
    return True


def build():
    collections = [next(c for c in bpy.data.collections if c.name.startswith(prefix))
                   for prefix in ("01_RED","02_BLUE","03_GREEN")]
    red,blue,green = collections
    legacy = [o for o in red.objects if o.name.startswith(
        ("roof/interlocking crown armor","facade/roof junction/"))]
    legacy += [red.objects[n] for n in ("polish/overlapping portal crown",
                                        "polish/portal crown return keys","roof/gateway crown")]
    if len(legacy)!=15:
        raise ValueError("Expected the fifteen front crown components from playtest seven")
    removed = []
    for old in legacy:
        for o in _family(old,collections):
            removed.append(o.name)
            bpy.data.objects.remove(o,do_unlink=True)
    trimmed = []
    for ob in list(red.objects):
        if (ob.type!="MESH" or "continuous recessed field" in ob.name or
                not ob.name.startswith(("roof/","facade/gateway/","facade/flanks/"))):
            continue
        if _seat_existing(ob):
            trimmed.extend(_family(ob,collections))
    new = []
    shell,keys = _castings()
    for batch in (shell,keys):
        master,peer = batch.objects(red,blue)
        if batch is shell:
            for ob in (master,peer):
                ob["pwr_polish_solid"] = True
                ob["collision"] = "architectural shell"
        copy = master.copy()
        copy.name = "03_GREEN/"+master.name
        green.objects.link(copy)
        copy.matrix_world = Matrix.Translation((0,150,0)) @ master.matrix_world
        copy["pwr_polish_site"] = "green"
        copy["source_object_name"] = master.name
        new.extend((master,peer,copy))
    finish_scene_geometry({},objects=trimmed+new)
    bpy.context.view_layer.update()
    return {"removed":removed,"reseated":[o.name for o in trimmed],
            "created":[o.name for o in new],"physical_shell":shell.name}
