"""Rebuild the two ramp walls from the grade to the parapet, using the .7 scene."""
import re

import bpy

from polish_paving_faces import Skin
from finishing_materials import PROFILES


# These families include original structural walls and each later authoring pass.
# The tread, traction plates, deck, turning platform and its rear curb have other names.
REPLACED = {
    "ramp/edge curb": 4,
    "ramp/detailed trim": 4,
    "ramp/armored retaining wall": 4,
    "ramp/interlocking armored shoulder": 12,
    "ramp/shoulder recessed armor field": 12,
    "ramp/landing outer curb": 2,
    "polish/continuous sloping ramp cheeks": 1,
    "polish/fitted ramp coping": 1,
    "polish/ramp sloping fitted fascia": 1,
    "Lookdev / Ramp sill cover plates": 1,
}
CENTERS = ("01_RED", "02_BLUE", "03_GREEN")
FLANK = "ridge_alloy"
CROWN = "ridge_crown"

# Joint footprints. Each entry sets the Y station of its foot, the crest height,
# the offset of the crest along the ramp, and the inward/outward slant of the seam.
# The first section deliberately has a raked, broad face visible at vehicle height.
SLOPE = (
    (-28.65, 2.55, 1.18, .32),
    (-21.20, 4.46, 1.95, -.58),
    (-13.15, 6.86, 2.69, .56),
    (-5.52, 9.45, 2.36, -.46),
)


def replaceable_objects():
    selected = []
    for prefix in CENTERS:
        col = next(c for c in bpy.data.collections if c.name.startswith(prefix))
        found = {family: [] for family in REPLACED}
        for ob in col.objects:
            name = ob.name.removeprefix(prefix + "/")
            family = re.sub(r"(?:\.\d{3})+$", "", name)
            if family in found:
                found[family].append(ob)
        for family, expected in REPLACED.items():
            if len(found[family]) != expected:
                raise ValueError(f"{col.name}: expected {expected} pieces of {family}, found {len(found[family])}")
            selected.extend(found[family])
    return selected


def section(side, inner, row, relief, setback=0., lower=0.):
    foot, crest, rake, skew = row
    ground = .07
    edge = 29.25 if inner else 35.75
    into_wall = -1 if inner else 1
    # The greater inner heel casts into the base shoulder as the grade rises.
    grade = min(1., max(0., (foot + 27.) / 26.))
    width = (2.85 + .43*grade) if inner else (2.03 + .39*grade)
    height = crest - lower - ground
    inset = setback
    heel, head = relief
    outer_heel = width + heel
    outer_shoulder = width + head
    # One broad crest facets directly into each wall face. The solid side
    # runs down to the ground, so there is no continuous open slot under its lip.
    profile = (
        (.035+inset, ground),
        (outer_heel+.16-inset, ground),
        (outer_heel+.10-inset, ground+height*.24),
        (outer_shoulder-.20-inset, ground+height*.77),
        (outer_shoulder-.42-inset, crest-.29-lower),
        (outer_shoulder-.67-inset, crest-.045-lower),
        (.59+inset, crest+.055-lower),
        (.35+inset, crest-.105-lower),
        (.085+inset, ground+.26),
    )
    return [(side*(edge+into_wall*u),
             foot+rake*(z-ground)/(crest-ground)+skew*(u/width-.45), z)
            for u,z in profile]


def toe_planes(batch, start, cap):
    # Form a raked crease between two toe planes. The small bridging triangles
    # are the actual bottom and crown at the toe; all edges remain manifold.
    v = batch.v
    # Use one crease X at both heights. Each half of the raked end face is
    # then a plane, even after the engine triangulates its chamfered outline.
    near,far = v[start][0],v[start+1][0]
    split = .52
    advance = .27
    mid_x = near + split*(far-near)
    def mid(a,b):
        fraction = (mid_x-v[start+a][0])/(v[start+b][0]-v[start+a][0])
        point = [v[start+a][k]*(1-fraction)+v[start+b][k]*fraction for k in range(3)]
        point[1] -= advance
        idx = len(v)
        v.append(tuple(point))
        return idx
    heel = mid(0,1)
    ridge = mid(6,5)
    for j in range(9):
        x,y,z = v[start+j]
        t=(x-near)/(far-near)
        fold=advance*min(t/split,(1-t)/(1-split))
        v[start+j] = (x,y-fold,z)
    def indices(*which):
        return tuple(start+i for i in which)
    batch.f[cap] = (start,heel,ridge,*indices(6,7,8))
    batch.mat[cap] = "ridge_toe_b"
    batch.f.extend([(heel,*indices(1,2,3,4,5),ridge),
                    (start,start+1,heel),(start+5,start+6,ridge)])
    batch.mat.extend(["ridge_toe_c","alloy",CROWN])


def cast_wall(batch, side, inner):
    # Inner wall releases the vehicle before the upper turn. The outside
    # parapet carries straight around the landing beside the end of the ridge.
    if inner:
        rows = (*SLOPE, (-1.75,10.67,.50,.12), (2.84,10.90,.36,-.06),
                (3.83,10.64,.025,0.))
    else:
        rows = (*SLOPE, (-.85,11.14,.62,.12), (3.54,11.66,.34,.20),
                (7.94,11.70,.10,.05), (12.96,11.65,0.,0.))
    rings = []
    faces = []
    # Large facets have slightly different batter between successive stone
    # blocks. The face normal therefore changes at the joint under daylight.
    block_relief = ((.10,-.10),(-.05,.07),(.10,-.19),(-.03,.08),
                    (.07,-.14),(.01,.02),(.03,-.07))
    shell = ["alloy",FLANK,FLANK,FLANK,CROWN,CROWN,CROWN,FLANK,"alloy"]
    joint = ["dark_floor"]*9
    for i,(y,z,rake,skew) in enumerate(rows):
        # In-receding arrises keep each expansion seam visibly narrow on the
        # tread side. The toe and head have real crest breaks against the sky.
        if i in (0,len(rows)-1):
            rings.append(section(side,inner,rows[i],block_relief[min(i,len(block_relief)-1)]))
            if i:
                faces.append(shell)
            continue
        knuckle = (.42 if i==1 and not inner else .22 if i==1 else
                   .32 if i==3 and inner else .20 if i==4 and not inner else .0)
        prev = block_relief[i-1]
        following = block_relief[i]
        if i <= 3:
            # A 4 cm mouth with a flat graphite bed continues across both
            # chamfers. The walls and bed are cut into the full solid mesh.
            for station, depth in ((-.020,0.),(-.016,.034),(.016,.034),(.020,0.)):
                rings.append(section(side,inner,(y+station,z,rake,skew),prev,
                                     setback=depth,lower=depth))
                faces.append(shell if station == -.020 else joint)
        else:
            # Beyond the last joint the landing is one continuous casting.
            rings.append(section(side,inner,(y,z,rake,skew),prev))
            faces.append(shell)
        # The change in end batter and height takes place over a diagonal
        # scarf. A vertical band across the cap would read as a broken rail.
        dy = 1.38 if knuckle else .91
        rise = (rows[i+1][1]-z)*dy/(rows[i+1][0]-y)
        rings.append(section(side,inner,(y+dy,z+knuckle+rise,rake,skew),following))
        faces.append(shell)
    start,cap = len(batch.v),len(batch.f)
    batch.component(rings,"alloy",faces)
    toe_planes(batch,start,cap)


def seat_deck_shoulders():
    # These wing plates used to project 0.715 m over the tread. Pull the outer
    # edge onto the haunch, leaving their top datum and rear turn intact.
    red = next(c for c in bpy.data.collections if c.name.startswith("01_RED"))
    matched = [ob for ob in red.objects if re.sub(r"(?:\.\d{3})+$","",ob.name)
               in ("roof/integrated ramp shoulder","roof/front wing junction armor")]
    if len(matched)!=4:
        raise ValueError("Expected four shared roof-to-ramp wing plates")
    for ob in matched:
        world = ob.matrix_world.copy()
        inverse = world.inverted()
        for vertex in ob.data.vertices:
            p = world @ vertex.co
            x = abs(p.x)
            if x > 26.6 and p.y < 8.0:
                blend = min(1., (8.0-p.y)/6.0)
                inset = (x-26.6)*.74*blend
                p.x = (x-inset)*(1 if p.x>0 else -1)
                vertex.co = inverse @ p
        ob.data.update()
        ob.data["ramp_seated_roof"] = True


def haunch(batch,side):
    # The bottom vertex rows sit inside the existing inboard wall. The upper
    # row seats the roof casting at X27.2, Y-15.1, Z10.53. The tapered face
    # spans the former open triangle without a shelf projecting over the lane.
    rows = []
    for y,lip,cheek,top in ((-20.64,27.24,5.36,10.50),(-12.65,27.55,6.97,10.54),
                            (-6.22,27.68,8.89,10.54),(-2.11,27.83,10.20,10.54),
                            (3.79,28.50,10.38,10.52)):
        pitch = top-cheek
        xz = [(25.79,.11),(28.86,.11),(28.87,cheek-.34),(28.71,cheek+.03),
              (lip+.14,top-max(.09,pitch*.12)),(lip-.17,top),
              (25.79,top)]
        ring=[]
        for x,z in xz:
            station = y
            if y < -20:
                station += .345*min(z,9.32) + 1.92*max(0.,z-9.32)
            ring.append((side*x,station,z))
        rows.append(ring)
    batch.component(rows,"alloy",[["alloy"]*7 for _ in rows[1:]])


def cast_finish(source, key):
    # These castings retain the native normal, mask and tile density. Adjust
    # only the grain in each surface's own material and retain its midtone.
    original = next(m for m in bpy.data.materials if m.get("native_finish_profile") == source)
    finish = original.copy()
    finish.name = "PWR • " + key.replace("_"," ")
    finish["native_finish_profile"] = key
    profile = PROFILES[key]
    nodes = {node.label: node for node in finish.node_tree.nodes}
    field = next(node for label, node in nodes.items() if label.startswith("Mineral changes across"))
    field.inputs["Scale"].default_value = 5.2
    field.inputs["Roughness"].default_value = .72
    color = next(node for label, node in nodes.items() if label.startswith("Broad ±")).color_ramp
    finish["finish_value_variation"] = variation = profile["variance"]
    for element, scale in zip(color.elements, (1.-variation, 1.+variation)):
        element.color = (*[c*scale for c in profile["color"]], 1.)
    grain = nodes["Fine alloy grain over broad mineral finish"]
    grain.inputs["Scale"].default_value = 24.
    grain.inputs["Detail"].default_value = 3.5
    grain_ramp = nodes["Subtle micrograin color variation"].color_ramp
    major = key == FLANK
    for element,tone in zip(grain_ramp.elements,(.86,1.12) if major else (.925,1.065)):
        element.color = (tone,tone,tone,1.)
    bump = nodes["Microscopic non-polished alloy finish"]
    bump.inputs["Distance"].default_value = .013 if major else .008
    bump.inputs["Strength"].default_value = .24 if major else .17


def build():
    """Replace every rail family on all sites, return the new solids and original names."""
    obsolete = replaceable_objects()
    names = [ob.name for ob in obsolete]
    seat_deck_shoulders()
    buttresses = Skin("Faceted ramp buttress castings")
    for side in (-1,1):
        for inner in (True,False):
            cast_wall(buttresses,side,inner)
        haunch(buttresses,side)
    for source,key in (("alloy", FLANK), ("alloy", CROWN),
                       ("apron_finish_v1", "ridge_toe_b"), ("apron_finish_v2", "ridge_toe_c")):
        cast_finish(source,key)
    result = buttresses.publish()
    for ob in result:
        ob["module_role"] = "architectural shell"
        ob["pwr_polish_solid"] = True
        ob["collision"] = "architectural shell"
        ob["clear_tread_width_m"] = 6.5
        ob["ramp_revision"] = "integral solid wedge walls"
    for ob in obsolete:
        bpy.data.objects.remove(ob,do_unlink=True)
    bpy.context.view_layer.update()
    return result, names
