"""Cast armor, passage luminaires and fin saddles for the mirrored PWR home bases.

The source scene uses metres with its garage facing -Y. Red owns all meshes.
Blue instances the same mesh data at the original base's reflected transform.
"""

import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Matrix


HERE = Path(__file__).resolve().parent
MATERIALS = {
    "shell": "FR • silver satin alloy",
    "graphite": "FR • inset blue graphite",
    "trim": "FR • engraved narrow trim",
    "shadow": "FR • shadow channels",
    "lens": "FR • cool interior light",
    "team": "TEAM • red recessed energy",
    "deck": "FR • dark traffic paving",
}


class Assembly:
    """Build a small, material-indexed group of closed, chamfered castings."""

    def __init__(self, name, bevel):
        self.name = "polish/" + name
        self.bevel = bevel
        self.vertices = []
        self.faces = []
        self.slots = []
        self.used = []

    def loft(self, rings, finish):
        count = len(rings[0])
        if finish not in self.used:
            self.used.append(finish)
        start = len(self.vertices)
        for ring in rings:
            if len(ring) != count:
                raise ValueError("Casting sections must have matching corners")
            self.vertices.extend(ring)
        sides = [tuple(reversed(range(start, start + count)))]
        for step in range(len(rings) - 1):
            i = start + step * count
            for j in range(count):
                k = (j + 1) % count
                sides.append((i+j, i+k, i+count+k, i+count+j))
        i = start + (len(rings)-1)*count
        sides.append(tuple(range(i, i+count)))
        self.faces.extend(sides)
        self.slots.extend([self.used.index(finish)] * len(sides))

    def plate(self, points, front, back, side, finish):
        self.loft([[(side*x, plane(z), z) for x, z in points]
                   for plane in (front, back)], finish)

    def slab(self, points, z0, z1, side, finish):
        self.loft([[(side*x, y, z) for x,y in points] for z in (z0,z1)], finish)

    def objects(self, red, blue):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        for kind in self.used:
            mesh.materials.append(bpy.data.materials[MATERIALS[kind]])
        for face, slot in zip(mesh.polygons, self.slots):
            face.material_index = slot
        editable = bmesh.new()
        editable.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(editable, faces=list(editable.faces))
        editable.to_mesh(mesh)
        editable.free()
        mesh.update()

        master = bpy.data.objects.new(self.name, mesh)
        red.objects.link(master)
        master["module_role"] = "architectural shell"
        master["pwr_polish_site"] = "red"
        master["collision"] = "none"
        if self.bevel:
            bevel = master.modifiers.new("Cast arris", "BEVEL")
            bevel.width = self.bevel
            bevel.segments = 2
            bevel.limit_method = "ANGLE"
            bevel.angle_limit = math.radians(22)
            bevel.harden_normals = True
        normals = master.modifiers.new("Broad planar highlights", "WEIGHTED_NORMAL")
        normals.keep_sharp = True

        peer = master.copy()
        peer.data = mesh
        peer.name = "02_BLUE/" + master.name
        blue.objects.link(peer)
        peer.matrix_world = Matrix.Translation((135, 0, 0)) @ Matrix.Diagonal((-1,1,1,1))
        peer["pwr_polish_site"] = "blue"
        peer["mirror_source_object"] = master.name
        for slot in peer.material_slots:
            if slot.material == bpy.data.materials[MATERIALS["team"]]:
                slot.link = "OBJECT"
                slot.material = bpy.data.materials["TEAM • blue recessed energy"]
        return [master, peer]


def _crown(armor, reveal, side):
    # The outer edge of each casting wraps over the slightly lower next course.
    # The dark reveal is on the vertical return of an otherwise solid eave.
    courses = [
        (6.78, 14.80, 11.42, -.30, .85),
        (14.02, 21.50, 11.22, -.15, .77),
        (20.78, 26.58, 11.02, .00, .70),
    ]
    for lo, hi, top, front_shift, overlap in courses:
        def profile(x, lift, retreat):
            y = -18.02 + front_shift + retreat
            z = top + lift
            # Inclined top, deep leading bevel, undercut nose and seated back.
            section = [(-14.15, 10.49), (-14.15, z-.08), (y+.70, z),
                       (y+.13, z-.17), (y-.18, z-.41),
                       (y-.17, z-.66), (y+.17, z-.75), (y+.52, 10.42)]
            return [(side*(x+.30*(py+18)/3.8), py, pz) for py,pz in section]

        armor.loft([profile(lo, -.13, .29), profile(lo+.49, 0, 0),
                    profile(hi-overlap, 0, 0), profile(hi-.17, -.05, .11),
                    profile(hi, -.18, .29)], "shell")

        # The tongue is exposed past the bright metal lip; its tail continues
        # into the next cap. The underlying roof remains solid throughout.
        x = hi-.43
        y = -18.02 + front_shift
        reveal.slab([(x-.47,y-.095),(x+.16,y-.095),(x+.47,y+.18),
                     (x+.46,y+.63),(x-.60,y+.58)], top-.58, top-.48, side,"graphite")

    # The main garage lintel has two solid splayed shoulders, carrying the
    # outer wing crowns into the blunt protective eyebrow over the doorway.
    def eyebrow(x, y, z):
        return [(side*x,-15.08,10.28),(side*x,-15.08,z-.13),
                (side*x,y+.55,z),(side*x,y+.12,z-.08),
                (side*x,y-.30,z-.46),(side*x,y-.20,z-.69),
                (side*x,y+.40,10.13)]
    armor.loft([eyebrow(.06,-17.87,10.93), eyebrow(5.95,-17.87,10.93),
                eyebrow(6.74,-18.09,11.26),eyebrow(7.43,-18.23,11.44),
                eyebrow(8.38,-18.00,11.29)],"shell")


def _wing_panels(plates, inlay, side):
    # The existing flank inclines backward by 0.241 m per metre of height.
    # All the armor, keyways and lip ends follow that face, including the
    # turns immediately above the small garage portal.
    def plane(offset):
        return lambda z: -17.057 - (10.567-z)*.24138 - offset
    def plate(shape, back_offset, front_offset, finish):
        plates.plate(shape, plane(front_offset), plane(back_offset), side, finish)
    def mark(shape, depth, finish):
        inlay.plate(shape, plane(depth+.014),plane(depth), side,finish)

    upper = [(11.57,9.29),(24.57,9.29),(25.13,8.82),(24.26,7.60),
             (19.57,7.60),(18.74,6.78),(14.13,6.78)]
    plate(upper,.06,.22,"graphite")
    inset = [(13.02,8.94),(23.85,8.94),(24.25,8.66),(23.88,8.23),
             (19.18,8.23),(18.29,7.40),(14.70,7.40)]
    plate(inset,.21,.27,"deck")
    lower = [(13.89,6.42),(18.49,6.42),(19.20,7.18),(23.77,7.18),
             (23.51,6.83),(19.48,6.83),(17.61,4.39),(15.31,4.39)]
    plate(lower,.04,.19,"graphite")
    # Two crisp trimmed rails, separated by broad unmarked areas.
    mark([(13.25,8.88),(17.77,8.88),(18.17,8.52),(18.07,8.43),
          (17.67,8.75),(13.34,8.75)],.27,"trim")
    mark([(14.32,6.34),(17.96,6.34),(19.02,7.12),(19.21,7.12),
          (18.02,6.20),(14.42,6.20)],.19,"trim")
    # Angular paired identifiers sit in one graphite rebate per wing.
    well = [(22.06,8.37),(23.55,8.37),(23.89,8.79),(22.40,8.79)]
    mark(well,.27,"shadow")
    for x in (22.38,22.93):
        mark([(x,8.44),(x+.22,8.44),(x+.43,8.71),(x+.21,8.71)],.289,"team")


def _fin_saddles(armor, fillets, side):
    # Follow the fin's existing outer spine. These folds wrap around the
    # tip and the intermediate shoulder, so their return faces read obliquely.
    def fixed(n): return lambda z: n
    plates = [
        ([(16.05,21.98),(16.96,21.96),(17.59,19.72),(18.66,18.28),
          (18.21,17.79),(16.79,19.29)], 9.62, 13.00),
        ([(17.53,18.45),(18.51,18.78),(19.38,17.19),(20.94,15.86),
          (20.22,15.20),(18.60,16.45)], 9.34, 12.75),
        ([(19.92,15.67),(20.96,15.99),(22.07,14.08),(23.54,12.67),
          (23.88,10.66),(21.67,10.66),(21.53,12.22),(20.55,13.74)], 9.00, 12.88)]
    for shape, front, back in plates:
        armor.plate(shape,fixed(front),fixed(back),side,"shell")
    armor.plate([(13.99,21.28),(14.44,21.99),(16.90,21.99),
                 (17.05,21.62),(16.49,21.32)],fixed(9.47),fixed(15.03),side,"shell")
    for x,z,y in ((17.64,18.30,9.33),(20.11,15.60,8.99)):
        fillets.plate([(x,z),(x+.39,z+.12),(x+.97,z-.63),(x+.88,z-.72)],
                      fixed(y-.016),fixed(y+.04),side,"graphite")
    # The lower third is a structural shoe with a darker chair and bright toe.
    armor.plate([(18.06,10.60),(18.33,11.66),(19.14,12.52),
                 (20.76,12.52),(20.48,11.57),(21.02,10.60)],
                fixed(9.26),fixed(11.65),side,"graphite")


def _gallery_lamps(hardware, optics, side):
    # Face the observer with a chamfer as well as illuminating the tunnel
    # wall. The 4 cm black rim stands proud of the lens on both ends.
    for y in (-17.95,-12.17):
        for wall, into in ((18.85,1),(24.05,-1)):
            def ring(plan, z):
                return [(side*(wall+into*x), y+dy, z) for x,dy in plan]
            casing = [(-.07,-.48),(.08,-.48),(.27,-.22),(.27,.22),
                      (.13,.45),(-.07,.45)]
            cap=[(-.07,-.51),(.12,-.51),(.31,-.25),(.31,.22),
                 (.16,.48),(-.07,.48)]
            hardware.loft([ring(casing,.37),ring(cap,.59),
                           ring(casing,1.91),ring(casing,2.08)], "graphite")
            # Front inclined face and longer side face share a tucked lip,
            # modeled with space between the pearl lens and its side frame.
            well=[(.076,-.491),(.286,-.226),(.286,.19),(.271,.21),
                  (.258,-.211),(.062,-.463)]
            hardware.loft([ring(well,.72),ring(well,1.92)],"shadow")
            lens=[(.132,-.421),(.267,-.248),(.277,-.22),(.269,-.206),
                  (.122,-.407)]
            optics.loft([ring(lens,.82),ring(lens,1.83)],"lens")
            strip=[(.286,-.144),(.288,.106),(.277,.112),(.276,-.153)]
            optics.loft([ring(strip,1.03),ring(strip,1.77)],"lens")
            # An undercut sill casts a small local pool beside each pier.
            sill=[(.25,-.25),(.30,-.17),(.30,.19),(.25,.25)]
            optics.loft([ring(sill,.61),ring(sill,.65)],"lens")



def _approach_tongue(core, paving, side):
    # Two articulated branches depart the garage shoulders on opposite sides
    # of the road. Their slightly oblique cross-joints follow the finger as it
    # bends and narrows. All elevations are relative to the 0.20 m court.
    rows = [
        ((8.52,-23.45), (19.42,-24.94), .27),
        ((8.59,-26.94), (19.16,-28.27), .33),
        ((10.22,-29.43), (18.32,-30.67), .33),
        ((11.18,-32.47), (18.75,-33.44), .32),
        ((12.77,-35.22), (18.36,-35.61), .29),
        ((14.45,-37.31), (16.15,-37.47), .235),
    ]

    def point(row, t, lift=0):
        a,b,z = row
        return (side*(a[0]+(b[0]-a[0])*t), a[1]+(b[1]-a[1])*t, z+lift)

    # One closed running bed supports the smoothly descending road edge.
    # The top of this physical shell is within 2.5 cm of the panel faces.
    sections = []
    for row in rows:
        left, right = point(row,0), point(row,1)
        sections.append([(left[0],left[1],.055),(right[0],right[1],.055),
                         right,left])
    core.loft(sections,"shadow")

    seams = [(0,.27,.77,1),(0,.27,.79,1),(0,.19,.73,1),
             (0,.20,.73,1),(0,.27,.76,1),(0,.27,.76,1)]
    for index,(a,b) in enumerate(zip(rows, rows[1:])):
        for j in range(3):
            quad=[point(a,seams[index][j]),point(a,seams[index][j+1]),
                  point(b,seams[index+1][j+1]),point(b,seams[index+1][j])]
            cx=sum(v[0] for v in quad)/4
            cy=sum(v[1] for v in quad)/4
            # Centre-relative inset makes individually fitted plates and leaves
            # a consistent finger-width dark joint on intersections.
            footprint=[]
            for x,y,z in quad:
                dx,dy=cx-x,cy-y
                distance=math.hypot(dx,dy)
                footprint.append((x+.029*dx/distance,y+.029*dy/distance,z))
            paving.loft([[(x,y,z-.006) for x,y,z in footprint],
                         [(x,y,z+.025) for x,y,z in footprint]],
                        "trim" if j==2 else "shell")


def _ramp_coping(core, armor, side):
    # The same longitudinal section follows both ramp shoulders, outside
    # their 6.5 m tread. The inner cheek stops at the open turning landing.
    stations=[(-27.95,.38),(-26.62,1.82),(-24.70,3.53),(-19.60,5.69),
              (-15.65,7.03),(-10.55,8.77),(-6.49,10.04),(-1.48,11.51),
              (3.70,11.74)]
    for inner,outer,landing in ((26.91,29.02,False),(36.02,38.17,True)):
        run=list(stations)
        if landing:
            run.extend([(7.53,11.75),(10.14,11.65)])
        else:
            run[-1]=(3.73,10.68)
        def ring(y,top,cap):
            # A broad inclined top facet, narrower outside bevel, and
            # pronounced dark skirt carry continuously between the old feet.
            depth=min(2.18,top-.075)
            if cap:
                corners=[(inner+.06,top-.225),(outer-.09,top-.255),
                         (outer-.12,top-.12),(outer-.39,top+.005),
                         (inner+.40,top+.095),(inner+.10,top-.05)]
            else:
                corners=[(inner+.14,top-depth),(outer-.15,top-depth),
                         (outer,top-.27),(outer-.36,top-.060),
                         (inner+.39,top+.008),(inner,top-.17)]
            return [(side*x,y,z) for x,z in corners]
        core.loft([ring(y,z,False) for y,z in run],"graphite")
        for (y0,z0),(y1,z1) in zip(run,run[1:]):
            # Keep the fitted silver caps close, with the graphite continuous
            # through the joints. Their arrises and facets follow grade.
            gap=.035
            slope=(z1-z0)/(y1-y0)
            armor.loft([ring(y0+gap,z0+gap*slope,True),
                        ring(y1-gap,z1-gap*slope,True)],"shell")


def _gallery_shoes(core, side):
    # Foot pads expand away from the 5.2 m lower gallery aperture.
    for left,right,facing in ((16.68,18.76,1),(24.14,26.22,-1)):
        def footprint(x0,x1,front,back,z):
            return [(side*x,y,z) for x,y in
                    ((x0+.25,front),(x1-.25,front),(x1,front+.31),
                     (x1,back-.23),(x1-.16,back),(x0+.16,back),
                     (x0,back-.23),(x0,front+.31))]
        bottom=footprint(left,right,-21.06,-18.26,.20)
        middle=footprint(left+.03,right-.03,-21.03,-18.29,.70)
        # The inside edge rises into the existing portal casing.
        head_left=left+(.67 if facing==1 else .08)
        head_right=right-(.08 if facing==1 else .67)
        top=footprint(head_left,head_right,-20.54,-18.43,1.72)
        core.loft([bottom,middle,top],"shell")

def build():
    """Add the authored home-base pass and return every realized render object."""
    red = next(c for c in bpy.context.scene.collection.children if c.name.startswith("01_RED"))
    blue = next(c for c in bpy.context.scene.collection.children if c.name.startswith("02_BLUE"))
    if any(ob.get("pwr_home_armor") for ob in (*red.objects, *blue.objects)):
        raise ValueError("Home architecture polish is already present in this scene")
    crown = Assembly("overlapping portal crown", .065)
    shadow = Assembly("portal crown return keys", .024)
    panels = Assembly("stepped flank plates", .018)
    grooves = Assembly("flank keyways", 0)
    fins = Assembly("fin shoulder saddles", .066)
    trims = Assembly("fin saddle joints", .013)
    lamps = Assembly("passage beacon housings", 0)
    optics = Assembly("recessed passage lenses", 0)
    roads = Assembly("tapered road tongue beds", 0)
    paving = Assembly("fitted approach tongue slabs", 0)
    cheeks = Assembly("continuous sloping ramp cheeks", .031)
    coping = Assembly("fitted ramp coping", .027)
    shoes = Assembly("gallery surround shoes", .022)
    for side in (-1,1):
        _approach_tongue(roads, paving, side)
        _ramp_coping(cheeks, coping, side)
        _gallery_shoes(shoes, side)
        _crown(crown, shadow, side)
        _wing_panels(panels, grooves, side)
        _fin_saddles(fins, trims, side)
        _gallery_lamps(lamps, optics, side)

    objects = []
    for batch in (crown, shadow, panels, grooves, fins, trims, lamps, optics, roads, paving, cheeks, coping, shoes):
        pair = batch.objects(red, blue)
        if batch in (crown, fins, roads, cheeks, shoes):
            for obj in pair:
                obj["pwr_polish_solid"] = True
                obj["collision"] = "architectural shell"
        objects.extend(pair)
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from finishing_materials import finish_scene_geometry
    finish_scene_geometry({}, objects=objects)
    for obj in objects:
        obj["pwr_home_armor"] = True
    bpy.context.view_layer.update()
    return objects

