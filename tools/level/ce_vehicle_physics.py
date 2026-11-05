"""The numbers a Custom Edition vehicle's clone wears, for tools/level/ce_vehicle.py.

Nothing here touches a file: tags come in as `mjolnir values --json` trees and
edits go out as `path=value` lines for `new-tag --set-file`.

Physics model. The donor's shapes are stretched axis by axis until they fill
the CE hull's box, which keeps the second, proxy body and every mass
distribution. A stretch breaks the donor's mopp, so the driven body goes onto
the shape list directly, as the shipped Ghost's is.

Handling. A shipped value becomes value x (CE vehicle / CE baseline), the
baseline being the donor's own CE self.

Ride height. A wheel's friction point is a sphere at its marker, so the ground
sits at marker z - radius in the object's space (Warthog: 0.222678 - 0.25 =
-0.0273 wu, -8.3 cm; the drawn tyres reach -9 cm). The clone keeps that ground
and takes the drawn tyre's radius, which puts the marker on the drawn tyre's
centre.
"""
import math
import re

JEEP = "physics types.type-human_jeep[0]"
HAVOK = "havok vehicle physics"
# Who gets on where, and the shipped hud_messages line for each of the
# Warthog's seats: driver, passenger, the two boardings, the back seat.


def flatten(fields, prefix=""):
    """A `values --json` tree as {path: displayed value}."""
    out = {}
    for f in fields:
        name = prefix + f["name"].strip()
        if f["kind"] == "field":
            out[name] = f["value"].strip(chr(34))
        elif f["kind"] == "block":
            for i, element in enumerate(f.get("children", [])):
                out.update(flatten(element["children"], f"{name}[{i}]."))
        elif "children" in f:
            out.update(flatten(f["children"], name + "."))
    return out


def vec(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", text)]


def fmt(v):
    return "(" + ", ".join(f"{x:.6f}" for x in v) + ")"


def count(flat, block):
    pattern = re.compile(re.escape(block) + r"\[(\d+)\]")
    return 1 + max((int(m.group(1)) for m in map(pattern.match, flat) if m), default=-1)


class Stretch:
    """p -> scale * p + offset, axis by axis, between two boxes."""

    def __init__(self, src_lo, src_hi, dst_lo, dst_hi):
        self.scale = [(dst_hi[k] - dst_lo[k]) / (src_hi[k] - src_lo[k]) for k in range(3)]
        self.offset = [dst_lo[k] - self.scale[k] * src_lo[k] for k in range(3)]
        self.mean = math.prod(self.scale) ** (1 / 3)

    def point(self, p):
        return [self.scale[k] * p[k] + self.offset[k] for k in range(3)]

    def size(self, v):
        return [abs(self.scale[k]) * v[k] for k in range(3)]

    def plane(self, n, d):
        """n.p + d = 0 after the stretch, its normal unit length again."""
        m = [n[k] / self.scale[k] for k in range(3)]
        w = d - sum(m[k] * self.offset[k] for k in range(3))
        length = math.sqrt(sum(x * x for x in m))
        return [x / length for x in m], w / length

    def inertia(self, rows):
        """A unit mass's tensor: I = tr(C) - C for the second moments C, which
        stretch as S C S."""
        trace = (rows[0][0] + rows[1][1] + rows[2][2]) / 2
        second = [[(trace if i == j else 0.0) - rows[i][j] for j in range(3)] for i in range(3)]
        second = [[self.scale[i] * self.scale[j] * second[i][j] for j in range(3)] for i in range(3)]
        trace = second[0][0] + second[1][1] + second[2][2]
        return [[(trace if i == j else 0.0) - second[i][j] for j in range(3)] for i in range(3)]


def shape_box(flat):
    """The box round both rigid bodies' shapes, in object space."""
    centre, half = vec(flat["lists[0].aabb center"]), vec(flat["lists[0].aabb half extents"])
    lo = [centre[k] - half[k] for k in range(3)]
    hi = [centre[k] + half[k] for k in range(3)]
    for i in range(count(flat, "boxes")):
        if vec(flat[f"boxes[{i}].convex transform shape.rotation i"]) != [1, 0, 0]:
            continue
        c = vec(flat[f"boxes[{i}].convex transform shape.translation"])
        h = vec(flat[f"boxes[{i}].half extents"])
        lo = [min(lo[k], c[k] - h[k]) for k in range(3)]
        hi = [max(hi[k], c[k] + h[k]) for k in range(3)]
    return lo, hi


def list_centre_of_mass(flat):
    """The centre of the shape list's volume, each child at its distribution:
    the boxes' come first, then the polyhedra's."""
    boxes = count(flat, "boxes")
    total, moment = 0.0, [0.0, 0.0, 0.0]
    for i in range(count(flat, "list shapes")):
        kind = flat[f"list shapes[{i}].shape reference.shape type"].split()[0]
        index = int(flat[f"list shapes[{i}].shape reference.shape"].lstrip("#"))
        shape = f"boxes[{index}]" if kind == "box" else f"polyhedra[{index}]"
        volume = float(flat[shape + ".base.volume"])
        c = vec(flat[f"mass distributions[{index if kind == 'box' else boxes + index}].center of mass"])
        total += volume
        moment = [moment[k] + volume * c[k] for k in range(3)]
    return [m / total for m in moment]


def physics_sets(flat, stretch, mass, centre_of_mass):
    """The physics model's edits. `centre_of_mass` is where the driven body's
    centre ends up, in object space."""
    sets = [f"mass={mass:.3f}"]
    for i in range(count(flat, "boxes")):
        p = f"boxes[{i}]"
        t = f"{p}.convex transform shape"
        half = vec(flat[p + ".half extents"])
        square = vec(flat[t + ".rotation i"]) == [1, 0, 0]
        # A turned box cannot stretch along another axis: it only grows.
        half = stretch.size(half) if square else [stretch.mean * h for h in half]
        radius = float(flat[p + ".box shape.radius"]) * stretch.mean
        # Shipped boxes keep their smallest half in w, and count the radius in
        # their volume.
        sets += [f"{p}.half extents={fmt(half)}",
                 f"{p}.havok w half extents={min(half):.6f}",
                 f"{p}.box shape.radius={radius:.6f}",
                 f"{t}.convex.radius={radius:.6f}",
                 f"{t}.translation={fmt(stretch.point(vec(flat[t + '.translation'])))}",
                 f"{p}.base.volume={8 * math.prod(h + radius for h in half):.6f}"]
    p = "polyhedra[0]"
    volume = float(flat[p + ".base.volume"]) * math.prod(stretch.scale)
    radius = float(flat[p + ".polyhedron shape.radius"]) * stretch.mean
    sets += [f"{p}.base.volume={volume:.6f}",
             f"{p}.polyhedron shape.radius={radius:.6f}",
             f"{p}.aabb center={fmt(stretch.point(vec(flat[p + '.aabb center'])))}",
             f"{p}.aabb half extents={fmt(stretch.size(vec(flat[p + '.aabb half extents'])))}",
             f"{p}.havok w aabb half extents={radius:.6f}"]
    for i in range(count(flat, "polyhedron four vectors")):
        p = f"polyhedron four vectors[{i}]"
        for k, axis in enumerate("xyz"):
            values = vec(flat[f"{p}.four vectors {axis}"]) + [float(flat[f"{p}.havok w four vectors {axis}"])]
            values = [stretch.scale[k] * v + stretch.offset[k] for v in values]
            sets += [f"{p}.four vectors {axis}={fmt(values[:3])}",
                     f"{p}.havok w four vectors {axis}={values[3]:.6f}"]
    for i in range(count(flat, "polyhedron plane equations")):
        p = f"polyhedron plane equations[{i}]"
        n, d = stretch.plane(vec(flat[p + ".plane equations"]), float(flat[p + ".havok w plane equations"]))
        sets += [f"{p}.plane equations={fmt(n)}", f"{p}.havok w plane equations={d:.6f}"]
    for i in range(count(flat, "mass distributions")):
        p = f"mass distributions[{i}]"
        rows = [vec(flat[f"{p}.inertia tensor {axis}"]) for axis in "ijk"]
        sets.append(f"{p}.center of mass={fmt(stretch.point(vec(flat[p + '.center of mass'])))}")
        sets += [f"{p}.inertia tensor {axis}={fmt(row)}" for axis, row in zip("ijk", stretch.inertia(rows))]
    centre = stretch.point(vec(flat["lists[0].aabb center"]))
    sets += [f"lists[0].aabb center={fmt(centre)}",
             f"lists[0].aabb half extents={fmt(stretch.size(vec(flat['lists[0].aabb half extents'])))}",
             f"lists[0].havok w aabb half extents={radius:.6f}"]

    reach = max(stretch.scale)
    for r in range(count(flat, "rigid bodies")):
        p = f"rigid bodies[{r}]"
        sphere = stretch.point(vec(flat[p + ".bouding sphere offset"]))
        sets += [f"{p}.bouding sphere offset={fmt(sphere)}",
                 f"{p}.bounding sphere radius={float(flat[p + '.bounding sphere radius']) * reach:.6f}"]
    offset = [centre_of_mass[k] - stretch.point(list_centre_of_mass(flat))[k] for k in range(3)]
    sets += [f"rigid bodies[0].center off mass offset={fmt(offset)}",
             "rigid bodies[0].shape reference.shape type=list",
             "rigid bodies[0].shape reference.shape=#0"]
    return sets


def shipped_centre_of_mass(flat):
    offset = vec(flat["rigid bodies[0].center off mass offset"])
    return [c + o for c, o in zip(list_centre_of_mass(flat), offset)]


def ratios(ce):
    v, b = ce["vehicle"], ce["baseline"]
    return {k: v[k] / b[k] for k in ("mass", "forward_speed", "reverse_speed", "steering_left",
                                     "ground_friction", "ground_depth")}


def contact_height(flat_vehicle, marker_z):
    """Where the donor's wheels meet the ground, in the object's space."""
    return marker_z - float(flat_vehicle[f"{HAVOK}.friction points[0].radius"])


def vehicle_sets(flat, ce, radius):
    """The vehicle's edits: handling and tyre sizes."""
    r = ratios(ce)
    sets = []

    def scaled(path, ratio):
        sets.append(f"{path}={float(flat[path]) * ratio:.6f}")

    steering = f"{JEEP}.steering control"
    scaled(f"{steering}.max steering angle at zero", r["steering_left"])
    scaled(f"{steering}.max steering angle at full speed", r["steering_left"])
    scaled(f"{JEEP}.turning control.maximum left turn", r["steering_left"])
    scaled(f"{JEEP}.turning control.maximum right turn (negative)", r["steering_left"])
    scaled(f"{JEEP}.engine.engine moment", r["mass"])
    scaled(f"{JEEP}.engine.engine max angular velocity", r["forward_speed"])
    # Reverse runs off the same engine.
    scaled(f"{JEEP}.engine.gears[0].gear ratio", r["reverse_speed"] / r["forward_speed"])
    scaled(f"{HAVOK}.ground friction", r["ground_friction"])
    scaled(f"{HAVOK}.ground depth", r["ground_depth"])
    shrink = radius / float(flat[f"{HAVOK}.friction points[0].radius"])
    for i in range(count(flat, f"{HAVOK}.friction points")):
        p = f"{HAVOK}.friction points[{i}]"
        sets.append(f"{p}.radius={radius:.6f}")
        scaled(f"{p}.damaged radius", shrink)
    # No seat strings: the game draws <MISSING STRING TABLE ENTRY> for names
    # its Unreal string table lacks, mongoose_enter_driver among them.
    return sets


def pathfinding_sets(flat, scale):
    """The AI's spheres, shrunk with the rig about their own node."""
    sets = []
    for i in range(count(flat, "pathfinding spheres")):
        p = f"pathfinding spheres[{i}]"
        centre = [c * scale for c in vec(flat[p + ".center"])]
        sets += [f"{p}.center={fmt(centre)}", f"{p}.radius={float(flat[p + '.radius']) * scale:.6f}"]
    return sets
