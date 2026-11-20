"""Reprofile the three existing PWR garage exits and remount their route signs.

Each shell, bevel and existing material remains on its original scene object.
The returned receipt maps original physical vertex indices to their new
metre-space positions before decorative bevel evaluation.
"""
from collections import defaultdict
import math

import bpy
from mathutils import Matrix, Vector

from finishing_materials import finish_scene_geometry
from portal_guides import CENTERS
from validate_bases import EvaluatedScene, volume_audit


ARCH = "portal/monolithic outer jamb"
REVEAL = "portal/dark rebated ring"
LINER = "portal/rear inner armored surround"
PREFIX = {"red": "", "blue": "02_BLUE/", "green": "03_GREEN/"}
# Inner profile control stations in design metres, expressed above local Z=0.
STATIONS = ((2.55625, 3.875), (6.0435, 3.60), (7.08025, 3.435))
REAR_ROUTE = {"min": [-5.75, 10.40, .28], "max": [5.75, 32.5, 4.70]}


def reshape(point, kind):
    x, y, z = point
    if kind == "guide":
        return Vector((x + math.copysign(3.875, x), y, z))
    shift = STATIONS[-1][1]
    if z <= STATIONS[0][0]:
        shift = STATIONS[0][1]
    else:
        for (lo, a), (hi, b) in zip(STATIONS, STATIONS[1:]):
            if z <= hi:
                shift = a + (b-a)*(z-lo)/(hi-lo)
                break
    # The outer profile stays seated in the roof and abutting bay walls.
    # Interpolating between the two control contours is monotonic at every Z.
    weight = min(1., max(0., (7.55-abs(x))/(7.55-3.48)))
    x += math.copysign(shift * weight, x)
    if kind == LINER:
        # The aft face seats behind the plate. Carry its dark lining 0.47 m
        # farther into the tunnel so the widened casting has a visible reveal.
        y = 14.716 + (y-14.716)*3.25
    return Vector((x,y,z))


def _names(team):
    for group in (ARCH, REVEAL, LINER):
        for index in range(7):
            yield PREFIX[team] + group + str(index), group
    for side in (-1, 1):
        yield f"{team} | rear vehicle guide {side:+d}", "guide"


def build():
    """Modify named native modules in the open study; return the remap receipt."""
    old, groups, edits = {}, defaultdict(list), []
    relevant = []
    for team, center in CENTERS.items():
        for name,kind in _names(team):
            ob=bpy.data.objects[name]
            if ob.get("pwr_wide_rear_gate"):
                raise ValueError("The rear aperture was already widened: " + name)
            matrix=Matrix.Translation(-Vector(center)) @ ob.matrix_world
            before=[matrix @ v.co for v in ob.data.vertices]
            if kind==ARCH and name.endswith("jamb6"):
                assert abs(min(abs(p.x) for p in before)-2.925) < .002, name
            old[name]=before
            groups[ob.data.as_pointer()].append((team,ob,matrix,kind))
            relevant.append(ob)

    for group in groups.values():
        team,master,frame,kind=group[0]
        mesh=master.data
        if mesh.users!=len(group):
            # Preserve an unrelated consumer of the source data, while retaining
            # the shared mirrored model for every targeted use of this module.
            mesh=mesh.copy()
            for _,ob,_,_ in group:
                ob.data=mesh
        inv=frame.inverted()
        for v,point in zip(mesh.vertices,old[master.name]):
            v.co=inv @ reshape(point,kind)
        mesh.update()
        for team,ob,matrix,role in group:
            after=[matrix @ v.co for v in mesh.vertices]
            before=old[ob.name]
            error=max((reshape(p,role)-q).length for p,q in zip(before,after))
            if error>5e-5:
                raise ValueError(f"Unexpected reflected gate placement on {ob.name}: {error}")
            ob["pwr_wide_rear_gate"]=role
            edits.append({"site":team,"name":ob.name,"old_object":ob.name,
                          "new_object":ob.name,"source_mesh":ob.data.name,
                          "kind":role,"structural":role!="guide",
                          "source_module":ob.get("mirror_source_object",ob.name),
                          "object_to_site_matrix":[list(row) for row in matrix],
                          "site_presentation_center_m":list(CENTERS[team]),
                          "old_local_m":[list(v) for v in before],
                          "new_local_m":[list(v) for v in after]})

    finish_scene_geometry({},objects=[o for o in relevant if " | " not in o.name])
    bpy.context.view_layer.update()
    bpy.context.scene["main_tunnel_clear_m"]=(
        "Main hall floor 16.9 m; entry soffit 7.16 m; rear floor opening 13.6 m, "
        "rear clear rise 6.88 m above floor; covered length 32.5 m")
    return {"schema":"pwr-rear-gate-remap-v1","units":"metres XYZ Z-up, position relative to site center (Blue reflection retained)",
            "geometry":"Indices are unchanged, ordered raw vertices before decorative bevels. Object transforms are unchanged.",
            "target_inside_xz_m":[[6.80,.2],[6.80,2.55625],[6.20,6.0435],[5.32,7.08025]],
            "clearance_box_m":REAR_ROUTE, "objects":sorted(edits,key=lambda r:(r["site"],r["name"]))}


def verify():
    result={}
    for team,center in CENTERS.items():
        prefix={"red":"01_RED","blue":"02_BLUE","green":"03_GREEN"}[team]
        collection=next(c for c in bpy.data.collections if c.name.startswith(prefix))
        scene=EvaluatedScene(collection.all_objects,Matrix.Translation(-Vector(center)))
        route=volume_audit(scene,REAR_ROUTE)
        if not route["passed"]:
            raise ValueError(f"{team} rear vehicle route obstructed: {route}")
        # Prove a solid exists above the lane and beside each clipped haunch.
        # The architectural section of the cast jamb lives at local Y=15.5.
        witnesses={}
        for key,origin,direction in (
            ("soffit",(0,15.50,4.70),(0,0,1)),
            ("west_spring",(-5.75,15.50,2.55625),(-1,0,0)),
            ("east_spring",(5.75,15.50,2.55625),(1,0,0)),
            ("clipped_corner",(5.00,15.50,6.65),(1,0,0)),
        ):
            hit=scene.ray(origin,direction,5)
            if not hit or ARCH not in hit["object"]:
                raise ValueError(f"{team} missing {key} arch witness: {hit}")
            witnesses[key]=dict(origin_m=origin,direction=direction,**hit)
        reads={}
        for z in (1.15,4.65,6.20):
            for x in (-5.73,0,5.73):
                ray=scene.ray((x,10.4,z),(0,1,0),22.1)
                if ray:
                    raise ValueError(f"{team} blocked long view at {(x,z)}: {ray}")
                reads[f"{x}/{z}"]=True
        result[team]={"route":route,"structural_witnesses":witnesses,"long_view_samples_xz_m":reads}
    return result
