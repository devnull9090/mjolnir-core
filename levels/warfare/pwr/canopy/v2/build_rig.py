"""Build the deployed parafoil and detachable rig in metres, Spartan feet at the origin.

Run in an empty Blender 5.3 scene. Local -Y is forward and +X is wearer right.
Only the two named export groups go into game assets. Retail fit references stay external.
"""

import bpy
import math
import json
import runpy
from pathlib import Path
from mathutils import Vector

HERE = Path(__file__).resolve().parent
TEXTILE = runpy.run_path(str(HERE / "grip_textile.py"))
PI = math.pi
SPAN = 5.6
CELLS = 7
SAMPLES = 18
GRIP_FORWARD_CM, GRIP_HALF_SPACING_CM, GRIP_HEIGHT_CM = 46, 28, 173
GRIPS = {
    side: [GRIP_FORWARD_CM, sign * GRIP_HALF_SPACING_CM, GRIP_HEIGHT_CM]
    for side, sign in (("grip_l", -1), ("grip_r", 1))
}
PACK_MOUNT = [-29, 0, 122]
PALETTE = {
    "Canopy": ((0.066, 0.079, 0.033), 0.86, 0),
    "Tip": ((0.021, 0.024, 0.020), 0.83, 0),
    "Binding": ((0.078, 0.085, 0.05), 0.68, 0),
    "Webbing": ((0.047, 0.053, 0.038), 0.82, 0),
    "Line": ((0.26, 0.245, 0.17), 0.79, 0),
    "Metal": ((0.26, 0.29, 0.25), 0.31, 0.85),
    "Toggle": ((0.76, 0.34, 0.034), 0.73, 0),
    "Mark": ((0.63, 0.63, 0.49), 0.79, 0),
    "GripTextile": ((0.49, 0.24, 0.045), 0.86, 0),
}
materials = {}
groups = {}


def make_material(name, rgb, rough, metal):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*rgb, 1)
    node.inputs["Roughness"].default_value = rough
    node.inputs["Metallic"].default_value = metal
    return mat


def mesh(name, verts, faces, mat, part, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    groups[part].objects.link(obj)
    obj["dl_part"] = part
    data.materials.append(materials[mat])
    for face in data.polygons:
        face.use_smooth = smooth
    return obj


def tubing(name, points, radius, mat, part, sides=6, flat=1):
    pts = [Vector(p) for p in points]
    verts, faces = [], []
    for i, p in enumerate(pts):
        axis = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        first = Vector((1, 0, 0)) if abs(axis.x) < 0.85 else Vector((0, 1, 0))
        a = (first - axis * first.dot(axis)).normalized()
        b = axis.cross(a)
        for j in range(sides):
            angle = math.tau * j / sides
            verts.append(
                p + radius * (a * math.cos(angle) + b * math.sin(angle) * flat)
            )
        if i:
            for j in range(sides):
                k = (j + 1) % sides
                faces.append(
                    (
                        (i - 1) * sides + j,
                        (i - 1) * sides + k,
                        i * sides + k,
                        i * sides + j,
                    )
                )
    faces.extend(
        [tuple(reversed(range(sides))), tuple(range(len(verts) - sides, len(verts)))]
    )
    return mesh(name, verts, faces, mat, part, True)


def grid(name, cols, rows, fn, mat, part, flip=False, smooth=True):
    vs = [fn(c / cols, r / rows) for r in range(rows + 1) for c in range(cols + 1)]
    fs = []
    for r in range(rows):
        for c in range(cols):
            a = r * (cols + 1) + c
            f = (a, a + 1, a + cols + 2, a + cols + 1)
            fs.append(f[::-1] if flip else f)
    return mesh(name, vs, fs, mat, part, smooth)


def wing(x, d, upper):
    # Inflated cells share a rib line. The lower lip starts aft of the top lip,
    # exposing each intake and the set-back baffle without a black painted face.
    t = abs(x) / (SPAN / 2)
    phase = (x / SPAN + 0.5) * CELLS
    bell = abs(math.sin(PI * phase)) ** 0.58
    chord = 2.08 - 0.38 * t * t - 0.26 * t**9
    depth = d if upper else 0.105 + 0.895 * d
    y = (depth - 0.48) * chord + 0.28 * t**2
    arc = 5.09 - 0.44 * t**3.0
    thickness = math.sin(PI * d) ** 0.72
    # Bias-cut panels pucker diagonally near loaded seams. Their centres
    # stay comparatively taut, with the rolls diminishing toward the tail.
    edge = abs(phase - round(phase))
    wrinkles = math.cos(66 * d + 1.8 * math.sin(7 * d) + 36 * edge)
    wrinkle = 0.024 * wrinkles * math.exp(-7 * edge) * math.sin(PI * d) ** 0.55
    if upper:
        z = (
            arc
            + (0.20 * (1 - d) + (0.56 - 0.17 * t**3) * thickness)
            + (0.094 + 0.072 * thickness) * bell * (1 - d**3)
            + wrinkle
            - 0.24 * t**8
        )
    else:
        z = (
            arc
            - 0.10 * (1 - d)
            - 0.125 * thickness
            - 0.055 * bell * (1 - d)
            - 0.055 * t**8
        )
    return (x, y, z)


def print_uv(u,v,pack=False):
    # Inset by half a texel to keep the atlas boundary out of the print.
    return ((512.5+511*u)/1024,((256 if pack else 0)+.5+255*v)/512)


def build_wing():
    for cell in range(CELLS):
        lo = SPAN * (cell / CELLS - 0.5)
        cw = SPAN / CELLS
        for up in [True, False]:
            skin = grid(
                "Woven cell %02d %s" % (cell + 1, "crown" if up else "belly"),
                SAMPLES,
                32,
                lambda c, d: wing(lo + cw * c, d, up),
                "Canopy",
                "wing",
                not up,
            )
            for mat in ["Tip", "Mark", "Toggle"]:
                skin.data.materials.append(materials[mat])
            for f in skin.data.polygons:
                x = lo + cw * ((f.index % SAMPLES + 0.5) / SAMPLES)
                d = (f.index // SAMPLES + 0.5) / 32
                if abs(x) > 2.60:
                    f.material_index = 1
                elif up and 1.73 < x < 1.87 and d < 0.95:
                    f.material_index = 2
                elif up and 2.02 < x < 2.24 and 0.12 < d < 0.20:
                    f.material_index = 3
            if not up and lo < .4 and lo+cw > -.4:
                faces=[f for f in skin.data.polygons if
                    abs(lo+cw*((f.index%SAMPLES+.5)/SAMPLES))<.4
                    and 7<=f.index//SAMPLES<21]
                if faces:
                    indices=sorted({v for f in faces for v in f.vertices})
                    local={v:i for i,v in enumerate(indices)}
                    # Preserve the complete base skin. Only printed ink draws
                    # over it, conforming to the original cell triangulation.
                    points=[skin.data.vertices[v].co-Vector((0,0,.002)) for v in indices]
                    stencil=mesh("Core underside stencil",points,
                        [[local[v] for v in f.vertices] for f in faces],"GripTextile","wing",True)
                    uv=stencil.data.uv_layers.new(name="UVMap")
                    for loop in stencil.data.loops:
                        v=indices[loop.vertex_index]
                        u=(lo+cw*(v%(SAMPLES+1))/SAMPLES+.8)/1.6
                        uv.data[loop.index].uv=print_uv(u,(21-v//(SAMPLES+1))/14)
        for up in [True, False]:
            tubing(
                "Rolled intake lip",
                [wing(lo + cw * k / 18, 0, up) for k in range(19)],
                0.020,
                "Binding",
                "wing",
                8,
            )
        # Recessed fabric wall, sewn into the cavity.
        grid(
            "Cell interior",
            8,
            4,
            lambda c, r: Vector(wing(lo + c * cw, 0.26, False)).lerp(
                Vector(wing(lo + c * cw, 0.26, True)), r
            ),
            "Tip",
            "wing",
        )
    for i in range(CELLS + 1):
        x = SPAN * (i / CELLS - 0.5)
        grid(
            "Internal fabric rib",
            16,
            3,
            lambda d, h: Vector(wing(x, d, False)).lerp(Vector(wing(x, d, True)), h),
            "Tip" if i in (0, CELLS) else "Binding",
            "wing",
            i == 0,
        )
        for h in [True, False]:
            tubing(
                "Felled rib seam",
                [wing(x, k / 20, h) for k in range(21)],
                0.010,
                "Binding",
                "wing",
            )
        for offset in [-0.021, 0.021]:
            if abs(x + offset) < SPAN / 2:
                tubing(
                    "Raised piping",
                    [wing(x + offset, k / 32, True) for k in range(33)],
                    0.004,
                    "Binding",
                    "wing",
                    5,
                )
    for sign in [-1, 1]:

        def cap(u, d):
            x = sign * (SPAN / 2)
            p = Vector(wing(x, d, True)).lerp(Vector(wing(x, d, False)), u)
            p.x += (
                sign
                * 0.205
                * math.sin(PI * u)
                * (0.25 + 0.75 * math.sin(PI * d) ** 0.55)
            )
            p.z -= 0.065 * math.sin(PI * u)
            return p

        grid("Charcoal end panel", 10, 18, cap, "Tip", "wing", sign == 1)
        tubing(
            "Outer welt",
            [cap(0.5, k / 20) for k in range(21)],
            0.012,
            "Binding",
            "wing",
        )
        tubing(
            "End panel piping",
            [wing(sign * 2.60, k / 32, True) for k in range(33)],
            0.008,
            "Binding",
            "wing",
            6,
        )
    # Narrow spanwise reinforcement tapes conform to the inflated skin.
    for d in [0.45, 0.78]:
        grid(
            "Cross seam",
            CELLS * SAMPLES,
            1,
            lambda c, r: (
                Vector(wing(SPAN * (c - 0.5), d + 0.003 * r, True))
                + Vector((0, 0, 0.003))
            ),
            "Binding",
            "wing",
        )


def hardware(name, x, y, z, w, h, part):
    corners = [
        (-0.41, -0.5),
        (0.41, -0.5),
        (0.5, -0.36),
        (0.5, 0.36),
        (0.41, 0.5),
        (-0.41, 0.5),
        (-0.5, 0.36),
        (-0.5, -0.36),
        (-0.41, -0.5),
    ]
    tubing(
        name, [(x + a * w, y, z + b * h) for a, b in corners], 0.0085, "Metal", part, 8
    )


def textile_strip(name, points, width, thickness, band=0, twist=0, folded=False):
    """A shaped tape with stitched face, bound edges and a dark backing."""
    pts = [Vector(p) for p in points]
    profile = [(-.91,-1),(.91,-1),(1,-.68),(1,.68),(.91,1),(-.91,1),(-1,.68),(-1,-.68)]
    verts, faces, coords, length = [], [], [], 0
    for i, center in enumerate(pts):
        tangent = (pts[min(i+1,len(pts)-1)]-pts[max(i-1,0)]).normalized()
        across = Vector((1,0,0)) if folded else Vector((0,1,0)).cross(tangent).normalized()
        depth = tangent.cross(across)
        angle = twist * i / (len(pts)-1)
        a = across*math.cos(angle)+depth*math.sin(angle)
        b = depth*math.cos(angle)-across*math.sin(angle)
        verts.extend(center+a*xx*width*.5+b*yy*thickness*.5 for xx, yy in profile)
        if i:
            next_length=length+(center-pts[i-1]).length
            for j in range(8):
                k=(j+1)%8
                faces.append(((i-1)*8+j,(i-1)*8+k,i*8+k,i*8+j))
                stripe=band if j==4 or (folded and j==0) else 1
                u1,u2=((profile[v][0]+1)*.5 for v in (j,k)) if j in (0,4) else (.12,.88)
                coords.append([(stripe*.25+.008+u*.234,v/.032) for u,v in ((u1,length),(u2,length),(u2,next_length),(u1,next_length))])
            length=next_length
    faces.extend((tuple(reversed(range(8))),tuple(range(len(verts)-8,len(verts)))))
    coords.extend([[(.37,0)]*8]*2)
    obj=mesh(name,verts,faces,"GripTextile","rig",True)
    uv=obj.data.uv_layers.new(name="UVMap")
    for polygon, pixels in zip(obj.data.polygons, coords):
        if polygon.index % 8 in (0,4):
            polygon.use_smooth=False
        for index,point in zip(polygon.loop_indices,pixels):
            uv.data[index].uv=(point[0]*.5,point[1])
    return obj


def braided(name, points, radius, band=2, sides=10, flat=1):
    obj=tubing(name,points,radius,"GripTextile","rig",sides,flat)
    uv=obj.data.uv_layers.new(name="UVMap")
    length=0
    for i in range(1,len(points)):
        next_length=length+(Vector(points[i])-Vector(points[i-1])).length
        for j in range(sides):
            face=obj.data.polygons[(i-1)*sides+j]
            coords=[(j,length),(j+1,length),(j+1,next_length),(j,next_length)]
            for index,(u,v) in zip(face.loop_indices,coords):
                uv.data[index].uv=((band*.25+.008+.234*u/sides)*.5,v/.032)
        length=next_length
    # Blender assigns a full-disk UV to new cap polygons. Keep these on the
    # cord swatch too, away from the printed atlas half.
    for cap in list(obj.data.polygons)[-2:]:
        for index in cap.loop_indices:
            uv.data[index].uv=((band+.5)/8,.5)
    return obj


def rounded_path(points, steps=3):
    points=[Vector(p) for p in points]
    curve=[]
    for i in range(len(points)-1):
        a,b,c,d=(points[max(0,min(j,len(points)-1))] for j in (i-1,i,i+1,i+2))
        for j in range(steps):
            t=j/steps
            curve.append((2*b+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(3*b-a-3*c+d)*t**3)*.5)
    return [*curve,points[-1]]


def padded_grip(base):
    # A single padded sleeve. Its rolled ends taper into the woven legs;
    # each polygon, including the rounded tips, has an authored textile UV.
    half=[(0,1),(.027,.99),(.041,.97),(.048,.97),(.049,.99),
          (.050,1.035),(.052,1.045),(.055,1.045),(.057,1.01),(.059,.91),
          (.0605,.76),(.062,.55),(.063,.29),(.0635,.12)]
    profile=[(-u,r) for u,r in reversed(half[1:])]+half
    sides=16
    verts,faces,coords=[],[],[]
    for i,(u,r) in enumerate(profile):
        for j in range(sides):
            a=math.tau*j/sides
            verts.append(base+Vector((u,.017*r*math.cos(a),.017*.76*r*math.sin(a))))
        if i:
            u0=profile[i-1][0]
            band=0 if abs((u+u0)/2)>=.049 else 1
            for j in range(sides):
                k=(j+1)%sides
                faces.append(((i-1)*sides+j,(i-1)*sides+k,i*sides+k,i*sides+j))
                coords.append([(band*.25+.008+.234*v/sides,h/.032)
                    for v,h in ((j,u0),(j+1,u0),(j+1,u),(j,u))])
    faces.extend((tuple(reversed(range(sides))),tuple(range(len(verts)-sides,len(verts)))))
    coords.extend([[(.125,.5)]*sides]*2)
    obj=mesh("Toggle grip",verts,faces,"GripTextile","rig",True)
    uv=obj.data.uv_layers.new(name="UVMap")
    for face,pixels in zip(obj.data.polygons,coords):
        for idx,point in zip(face.loop_indices,pixels):
            uv.data[idx].uv=(point[0]*.5,point[1])


def steering_toggle(side,sign,rear_guide):
    forward,right,up=GRIPS[side]
    base=Vector((right/100,-forward/100,up/100))
    def p(dx,dy,dz):
        return base+Vector((sign*dx,dy,dz))
    # Two plies of tape meet at a folded soft eye. The pinched throat is
    # slightly loaded toward the outboard guide. The hand bar stays level.
    eye=p(.020,.018,.176)
    for leg in (-1,1):
        path=[p(leg*.051,.000,-.002),p(leg*.063,.000,.007),
              p(leg*.068,.002,.022),p(leg*.068,.004,.041),
              p(leg*.061+.002,.006,.065),p(leg*.047+.006,.008,.090),
              p(leg*.029+.012,.012,.118),p(leg*.012+.018,.015,.141),
              p(leg*.005+.019,.015,.151)]
        textile_strip("Toggle woven leg",rounded_path(path),.023,.0036,twist=sign*leg*.48)
    # Fold the webbing around a little cord eye, then return the sewn end
    # down the face. Leave an actual opening inside the folded textile.
    tab=[p(.020,.011,.126),p(.020,.011,.150),p(.020,.010,.169),
         p(.020,.013,.175),p(.020,.018,.178),p(.020,.024,.176),
         p(.020,.027,.171),p(.020,.026,.162),p(.020,.022,.135)]
    textile_strip("Doubled toggle eye",rounded_path(tab),.027,.003,3,folded=True)
    for h in (.138,.142,.150,.154):
        # Real thread ends leave the cloth clean at close LOD. The twin
        # longitudinal seams stay baked in the mat at distance.
        for stitch in range(5):
            start=-.0105+.0043*stitch
            face=.022+(h-.135)*.155+.00165
            braided("Throat bar tack",[p(.020+start,face,h),p(.0215+start,face+.00035,h+.00012),
                    p(.023+start,face,h+.0003)], .00047,3,5)
    padded_grip(base)
    # The brake line runs through a separate guide on the rear riser, then
    # up to the trailing edge. The released toggle does not carry a buckle.
    lower=(rear_guide-eye).normalized()
    tail=Vector(wing(sign*2.5,.96,False))
    upper=(tail-rear_guide).normalized()
    normal=(upper+lower).normalized()
    a=Vector((1,0,0))
    a=(a-normal*a.dot(normal)).normalized()
    b=normal.cross(a)
    ring=[rear_guide+.013*(a*math.cos(i*math.tau/24)+b*math.sin(i*math.tau/24)) for i in range(25)]
    tubing("Rear riser brake guide ring",ring,.0022,"Metal","rig",8)
    # The loop enters the soft eye and doubles back into a short splice.
    low=p(.006,.018,.168)
    hitch=rounded_path([low,p(.020,.018,.168),p(.034,.018,.169),p(.036,.019,.174),
        p(.032,.020,.183),eye+lower*.021,eye+lower*.034],2)
    braided("Brake line splice",hitch,.00130,2,10)
    standing=rounded_path([low,p(.003,.018,.171),p(.002,.018,.176),
        p(.007,.018,.183),eye+lower*.017,eye+lower*.035],2)
    braided("Brake control line",[*standing,rear_guide-lower*.014,rear_guide,
        rear_guide+upper*.014,tail],.00155)


def build_lines():
    for side, s in (("grip_l", -1), ("grip_r", 1)):
        front_anchor = Vector((s * .54,-.78,2.32))
        for rear in [False, True]:
            anchor = Vector((s*.415,-.70,2.32)) if rear else front_anchor
            bottom = Vector((s * 0.255, 0.275 if rear else -0.008, 1.58))
            shoulder=Vector((s*.265,-.070,1.67)) if rear else Vector((s*.288,-.10,1.66))
            textile_strip("Rear load riser" if rear else "Front load riser",
                          [bottom,shoulder,anchor],.036 if rear else .030,.005,1)
            if rear:
                attachment=shoulder.lerp(anchor,.62)
                rear_guide=attachment+Vector((-s*.023,.005,0))
                textile_strip("Guide keeper", [attachment+Vector((0,.004,-.018)),
                              attachment+Vector((-s*.013,.008,-.004)),
                              rear_guide+Vector((s*.010,0,0))], .013,.003,1)
            hardware(
                "Riser link", anchor.x, anchor.y, anchor.z + 0.023, 0.077, 0.072, "rig"
            )
            textile_strip("Folded riser cuff",[anchor.lerp(shoulder,.085),anchor.lerp(shoulder,.15)],
                          .040 if rear else .035,.008,1)
            for a, b in [(-0.013, 0.013), (0.013, -0.013)]:
                stitch = [
                    anchor.lerp(shoulder, frac) + Vector((dx, .004, 0))
                    for frac, dx in [(0.18, a), (0.27, b)]
                ]
                tubing("Riser cross stitching", stitch, .0009, "Binding", "rig", 5)
            for n in range(4):
                fork = anchor + Vector(
                    (s * (0.07 + 0.09 * n), 0.045 if rear else -0.045, 0.41 + 0.042 * n)
                )
                tubing(
                    "Suspension cascade",
                    [anchor + Vector((0, 0, 0.045)), fork],
                    0.0056,
                    "Line",
                    "rig",
                )
                for d in [0.53, 0.82] if rear else [0.05, 0.30]:
                    x = s * ((n + 0.5) * SPAN / CELLS - 0.15)
                    top = Vector(wing(x, d, False))
                    tubing("Suspension line", [fork, top], 0.0047, "Line", "rig")
                    tubing(
                        "Anchor webbing",
                        [top - Vector((0, 0, 0.045)), top + Vector((0, 0.022, 0))],
                        0.014,
                        "Binding",
                        "rig",
                    )
        steering_toggle(side,s,rear_guide)


def box(name, loc, dim, mat, bevel, part="pack", rotation=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = dim
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler.x = rotation
    for c in list(o.users_collection):
        c.objects.unlink(o)
    groups[part].objects.link(o)
    o["dl_part"] = part
    o.data.materials.append(materials[mat])
    mod = o.modifiers.new("Rounded edges", "BEVEL")
    mod.width = bevel
    mod.segments = 3
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod = o.modifiers.new("Panel normals", "WEIGHTED_NORMAL")
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return o


def build_pack():
    # A small maker label is sewn between the vertical retention straps.
    # Its backing follows the angle of the pack envelope's outward face.
    def label(u,v):
        z=.162+.053*v
        return (.053-.106*u,.069+.100/math.cos(.13)+math.tan(.13)*(z-.27)+.0012,z)
    tag=grid("Pack maker label",2,2,label,"GripTextile","pack",False,False)
    uv=tag.data.uv_layers.new(name="UVMap")
    for polygon in tag.data.polygons:
        for idx in polygon.loop_indices:
            vertex=tag.data.loops[idx].vertex_index
            uv.data[idx].uv=print_uv((vertex%3)/2,(vertex//3)/2,pack=True)
    # A tapered pad follows the armor profile up toward the shoulder blades.
    box(
        "Padded back panel",
        (0, -0.015, 0.28),
        (0.50, 0.19, 0.56),
        "Webbing",
        0.065,
        rotation=-0.16,
    )
    box(
        "Packed canopy envelope",
        (0, 0.069, 0.27),
        (0.49, 0.20, 0.50),
        "Canopy",
        0.068,
        rotation=-0.13,
    )
    box(
        "Overlapping top flap",
        (0, 0.119, 0.394),
        (0.505, 0.113, 0.24),
        "Canopy",
        0.042,
        rotation=-0.18,
    )
    flap = [
        (-0.222, 0.171, 0.431),
        (-0.222, 0.162, 0.320),
        (-0.207, 0.159, 0.292),
        (-0.175, 0.157, 0.278),
        (0.175, 0.157, 0.278),
        (0.207, 0.159, 0.292),
        (0.222, 0.162, 0.320),
        (0.222, 0.171, 0.431),
    ]
    tubing("Flap bound edge", flap, 0.006, "Binding", "pack", 6)
    for s in [-1, 1]:
        x = s * 0.153
        tubing(
            "Pack side gusset",
            [
                (s * 0.236, 0.079, 0.076),
                (s * 0.246, 0.090, 0.118),
                (s * 0.248, 0.112, 0.249),
                (s * 0.245, 0.123, 0.355),
                (s * 0.229, 0.123, 0.463),
            ],
            0.0075,
            "Binding",
            "pack",
        )
        tubing(
            "Pack retention strap",
            [
                (x, 0.127, 0.065),
                (x, 0.167, 0.18),
                (x, 0.187, 0.31),
                (x, 0.192, 0.44),
                (x, 0.124, 0.503),
            ],
            0.027,
            "Webbing",
            "pack",
            8,
            0.28,
        )
        hardware("Retention buckle", x, 0.183, 0.25, 0.068, 0.059, "pack")
        for a, b in [(-0.013, 0.013), (0.013, -0.013)]:
            tubing(
                "Retainer stitching",
                [(x + a, 0.193, 0.306), (x + b, 0.195, 0.347)],
                0.0019,
                "Line",
                "pack",
                5,
            )
        box("Latch", (x, 0.193, 0.25), (0.057, 0.015, 0.024), "Binding", 0.005)
        tubing(
            "Riser lead from pack",
            [
                (s * 0.19, 0.07, 0.485),
                (s * 0.226, 0.053, 0.54),
                (s * 0.246, 0.004, 0.56),
            ],
            0.028,
            "Webbing",
            "pack",
            8,
            0.38,
        )
    box("ID patch", (0, 0.185, 0.38), (0.135, 0.012, 0.051), "Binding", 0.009)
    for i in range(3):
        box(
            "Embroidered ID bar",
            (-0.036 + i * 0.035, 0.195, 0.38),
            (0.016, 0.004, 0.028),
            "Mark",
            0.002,
        )
    tubing(
        "Release loop",
        [
            (0.23, 0.095, 0.30),
            (0.269, 0.092, 0.25),
            (0.274, 0.073, 0.197),
            (0.248, 0.06, 0.18),
            (0.23, 0.078, 0.23),
        ],
        0.012,
        "Toggle",
        "pack",
        8,
    )


def export(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    duplicates = []
    for part in parts:
        for obj in list(groups[part].objects):
            clone = obj.copy()
            clone.data = obj.data.copy()
            bpy.context.scene.collection.objects.link(clone)
            clone.select_set(True)
            duplicates.append(clone)
    bpy.context.view_layer.objects.active = duplicates[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.calc_loop_triangles()
    count = len(obj.data.loop_triangles)
    bpy.ops.export_scene.gltf(
        filepath=str(HERE / (name + ".gltf")),
        export_format="GLTF_SEPARATE",
        use_selection=True,
        export_yup=True,
        export_materials="EXPORT",
    )
    bpy.data.objects.remove(obj, do_unlink=True)
    return count


def main():
    # The caller supplies a dedicated authoring scene. Reloading factory
    # settings would tear down the MCP add-on while its call is in flight.
    scene = bpy.context.scene
    output = HERE / "pwr_insertion.blend"
    ours = bpy.data.filepath and Path(bpy.data.filepath).resolve() == output.resolve()
    if (bpy.data.filepath and not ours) or (
        not ours and set(o.name for o in scene.objects) - {"Cube", "Camera", "Light"}
    ):
        raise RuntimeError(
            "Open an empty scene or the generated pwr_insertion.blend to rebuild"
        )
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for name in ("deployed", "wing", "rig", "pack"):
        group = bpy.data.collections.get(name)
        if group is not None:
            bpy.data.collections.remove(group)
    for name in PALETTE:
        mat = bpy.data.materials.get(name)
        if mat is not None:
            bpy.data.materials.remove(mat)
    deployed = bpy.data.collections.new("deployed")
    scene.collection.children.link(deployed)
    for part in ("wing", "rig", "pack"):
        group = bpy.data.collections.new(part)
        (scene.collection if part == "pack" else deployed).children.link(group)
        groups[part] = group
    for name, (c, r, m) in PALETTE.items():
        materials[name] = make_material(name, c, r, m)
    build_wing()
    build_lines()
    build_pack()
    scene.unit_settings.system = "METRIC"
    info = {
        "canopy_triangles": export(["wing", "rig"], "pwr_canopy"),
        "pack_triangles": export(["pack"], "pwr_pack"),
        "grip_sockets_ue_cm": GRIPS,
        "pack_mount_ue_cm": PACK_MOUNT,
        "axis": "Blender -Y forward, +X wearer right; metres; deployed mesh origin at biped feet, pack origin at base",
        "width_m": round(
            max(p.co.x for o in groups["wing"].objects for p in o.data.vertices)
            - min(p.co.x for o in groups["wing"].objects for p in o.data.vertices),
            4,
        ),
        "cells": CELLS,
    }
    (HERE / "geometry-report.json").write_text(json.dumps(info, indent=2) + "\n")
    # Keep a separate local pack origin in the export and place its source
    # collection on the armor for the assembled Blender scene.
    for o in groups["pack"].objects:
        o.location += Vector((0, 0.29, 1.22))
    for name, mat in materials.items():
        if name == "GripTextile":
            TEXTILE["write_textures"](HERE)
            TEXTILE["preview"](mat,HERE,bpy)
            continue
        if name in ("Metal", "Mark", "Line"):
            continue
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        coords = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 62
        noise.inputs["Detail"].default_value = 2.3
        links.new(coords.outputs["Object"], noise.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        rgb = PALETTE[name][0]
        for stop, lum in zip(ramp.color_ramp.elements, (0.66, 1.23)):
            stop.color = (*[val * lum for val in rgb], 1)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        bsdf = nodes.get("Principled BSDF")
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        wave = nodes.new("ShaderNodeTexWave")
        wave.inputs["Scale"].default_value = 108
        wave.inputs["Distortion"].default_value = 1.1
        links.new(coords.outputs["Object"], wave.inputs["Vector"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = 0.0006
        bump.inputs["Strength"].default_value = 0.19
        links.new(wave.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bsdf.inputs["Sheen Weight"].default_value = 0.08
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    previous_versions = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(output))
    finally:
        bpy.context.preferences.filepaths.save_version = previous_versions
    print(info)


if __name__ == "__main__":
    main()
