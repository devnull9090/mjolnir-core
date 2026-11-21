"""Final exterior alloy finish, ramp fascia and gallery transitions in the playtest-six scene."""
import bpy
from mathutils import Matrix
from finishing_materials import PROFILES, finish_scene_geometry
from polish_home import Assembly


def pewter_profiles():
    """Shared linear-space finish values for Blender and the native material build."""
    profiles = {}
    for key, base in PROFILES.items():
        if key != "alloy" and key != "ramp_finish" and not key.startswith("apron_finish"):
            continue
        r, g, b = base["color"]
        # Broad armor moves toward warm pewter while narrow trim retains a cool highlight.
        profiles[key] = {**base, "color": (r*.925, g*.866, b*.815),
                         "variance": base["variance"]*.58,
                         "rough": (base["rough"][0]+.025, base["rough"][1]-.035)}
        if key == "ramp_finish" or key.startswith("apron_finish"):
            traffic = profiles[key]
            traffic["color"] = tuple(v*(.55 if key == "ramp_finish" else .66) for v in traffic["color"])
            traffic["metal"] = .29 if key == "ramp_finish" else .36
            traffic["rough"] = tuple(min(.76,v+.12) for v in traffic["rough"])
    return profiles


def apply_finishes():
    profiles = pewter_profiles()
    for material in bpy.data.materials:
        key = material.get("native_finish_profile")
        if key not in profiles:
            continue
        profile = profiles[key]
        material.diffuse_color = (*profile["color"],1)
        material["finish_value_variation"] = profile["variance"]
        material["finish_roughness_range"] = profile["rough"]
        nodes = {node.label:node for node in material.node_tree.nodes}
        nodes["Broad selective metal sheen"].inputs["Metallic"].default_value = profile["metal"]
        ramp = next(n for label,n in nodes.items() if label.startswith("Broad ±")).color_ramp
        for value, step in zip((-1,1), ramp.elements):
            step.color = (*[v*(1+value*profile["variance"]) for v in profile["color"]],1)
        broad = next(n for label,n in nodes.items() if label.startswith("Mineral changes across"))
        broad.inputs["Scale"].default_value = 2.8
        # The existing roughness field is reflected in broad flat faces, so change
        # its range too. Leave native normal-map intensity and metal edges intact.
        reflection = nodes["Soft reflection islands across entire slabs"].color_ramp
        lo, hi = profile["rough"]
        for elem in reflection.elements:
            fraction = min(1.,max(0.,(elem.position-.25)/.5))
            roughness = lo + fraction*(hi-lo)
            elem.color = (roughness, roughness, roughness,1.)
    return profiles


def fascia(batch, sign):
    stations = [(-27.95,.38),(-26.62,1.82),(-24.70,3.53),(-19.60,5.69),
                (-15.65,7.03),(-10.55,8.77),(-6.49,10.04),(-1.48,11.51),
                (3.70,11.74)]
    for inner,outer,outer_wall in ((26.91,29.02,False),(36.02,38.17,True)):
        rows = stations + [(7.53,11.75),(10.14,11.65)] if outer_wall else stations[:-1]+[(3.73,10.68)]
        for (ya,za),(yb,zb) in zip(rows,rows[1:]):
            for x,face in ((inner,-1),(outer,1)):
                def section(t):
                    z = za+(zb-za)*t
                    y = ya+(yb-ya)*t
                    depth = min(2.08,max(.16,z-.15))
                    def vertex(offset,h):
                        return (sign*(x+face*offset),y,max(.06,z-h))
                    return [vertex(-.13,.13),vertex(.028,.19),vertex(.070,.32),
                            vertex(-.005,depth-.07),vertex(-.09,depth),vertex(-.17,depth-.12)]
                gap = min(.04/(yb-ya),.08)
                batch.loft([section(gap),section(1-gap)],"shell")


def gallery(batch, sign):
    def front(z): return -20.80+.256*z
    def back(z): return -19.28+.244*z
    # The lower wings run behind the existing plinths. The upper haunches bite
    # into the flank panel and brow, outside the measured vehicle clear volume.
    for shape in (
        [(14.42,.25),(17.52,.25),(18.53,1.17),(18.57,2.40),(17.98,3.46),
         (17.05,2.08),(15.82,1.58),(14.42,1.56)],
        [(24.41,1.26),(25.26,.25),(28.06,.25),(28.06,1.55),
         (26.96,1.58),(26.05,2.07),(25.02,3.40),(24.44,2.35)],
        [(17.25,2.82),(17.98,2.42),(19.27,5.62),(23.63,5.62),(24.88,2.43),
         (25.62,2.80),(24.50,6.04),(23.78,6.40),(19.16,6.40),(18.41,6.01)],
    ):
        batch.plate(shape, front, back, sign, "shell")


def brow_joints(batch, sign):
    # The joint bridges the horizontal brow to each sloping casting. Attach
    # its profile to the same raked plane as the face of the larger armor.
    for x, dx in ((18.85,.60),(24.05,-.60)):
        shape = [(x-.055,5.72),(x+.055,5.72),(x+dx+.055,6.32),(x+dx-.055,6.32)]
        batch.plate(shape,lambda z:-20.818+.256*z,lambda z:-20.799+.256*z,sign,"shadow")


def apron_faces():
    # The plate sides stay silver. Only the exposed top face of each fitted
    # course gets a traffic finish, so its arris catches a bright narrow line.
    master = bpy.data.objects["polish/fitted approach tongue slabs"]
    mesh = master.data
    traffic = next(m for m in bpy.data.materials if m.get("native_finish_profile") == "apron_finish_v1")
    index = len(mesh.materials)
    mesh.materials.append(traffic)
    for face in mesh.polygons:
        if face.normal.z > .88:
            face.material_index = index


def build():
    profiles = apply_finishes()
    apron_faces()
    red,blue,green = (next(c for c in bpy.data.collections if c.name.startswith(prefix))
                      for prefix in ("01_RED","02_BLUE","03_GREEN"))
    spandrels = Assembly("ramp sloping fitted fascia", .034)
    brow = Assembly("gallery brow and splayed transitions", .047)
    joints = Assembly("gallery brow diagonal joints", 0)
    for sign in (-1,1):
        fascia(spandrels,sign)
        gallery(brow,sign)
        brow_joints(joints,sign)
    result = []
    for batch in (spandrels,brow,joints):
        master,peer = batch.objects(red,blue)
        if batch is brow:
            for ob in (master,peer):
                ob["pwr_polish_solid"] = True
                ob["collision"] = "architectural shell"
        copy = master.copy()
        copy.name = "03_GREEN/" + master.name
        copy["pwr_polish_site"] = "green"
        copy["source_object_name"] = master.name
        green.objects.link(copy)
        copy.matrix_world = Matrix.Translation((0,150,0)) @ master.matrix_world
        result.extend((master,peer,copy))
    finish_scene_geometry({},objects=result)
    bpy.context.view_layer.update()
    return result, profiles
