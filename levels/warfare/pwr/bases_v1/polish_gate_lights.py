"""Vehicle-visible Forerunner lenses recessed into the ceiling and angled arch facets."""
import bpy
from mathutils import Vector
from polish_home import Assembly


def cast(ob, point, direction):
    world = ob.matrix_world
    inverse = world.inverted()
    hit, point, _, _ = ob.ray_cast(inverse @ Vector(point),
                                    (inverse.to_3x3() @ Vector(direction)).normalized())
    if not hit:
        raise ValueError(f"Gate fixture has no support on {ob.name}")
    return world @ point


def ceiling_bar(frame, glass, host, y, half_width):
    # The front window tilts towards the approach. Its top flange enters the
    # actual underside of the casting, including the sloping entrance lip.
    z = cast(host, (0, y, 4.9), (0, 0, 1)).z
    def ring(x, section):
        return [(x, y + dy, z + dz) for dy, dz in section]
    housing = [(-.34,-.04),(-.31,-.18),(.02,-.41),(.34,-.38),(.42,.10),(-.29,.10)]
    window = [(-.303,-.203),(-.061,-.375),(-.026,-.360),(-.274,-.183)]
    frame.loft([ring(-half_width, housing), ring(half_width, housing)], "graphite")
    glass.loft([ring(-half_width+.24, window), ring(half_width-.24, window)], "lens")


def shoulder_bar(frame, glass, host, sign, y):
    # Wrap the luminaire over the leading inner arris. Each sampled profile
    # follows the actual slope of this arch, which differs at the threshold.
    def section(z, profile):
        edge = cast(host, (0,y,z), (sign,0,0))
        face = cast(host, (edge.x + sign*.13, y-2, z), (0,1,0))
        return [(edge.x + sign*dx, face.y + dy, z) for dx,dy in profile]
    trim = [(-.11,-.065),(.005,-.15),(.34,-.15),(.37,.045),(.018,.17),(-.11,.14)]
    lens = [(-.102,-.08),(.014,-.164),(.211,-.164),(.212,-.151),
            (.020,-.152),(-.095,-.066)]
    frame.loft([section(6.20,trim),section(7.22,trim)], "graphite")
    glass.loft([section(6.32,lens),section(7.11,lens)], "lens")


def build():
    graph = bpy.context.evaluated_depsgraph_get()
    def evaluated(name):
        return bpy.data.objects[name].evaluated_get(graph)
    frame = Assembly("threshold and rib lamp casings", .014)
    glass = Assembly("threshold and rib opal windows", 0)
    ceiling_bar(frame, glass, evaluated("facade/gateway/deep inner splay-2"), -17.06, 1.95)
    for suffix, y in (("",-10.4), (".002",2.6)):
        ceiling_bar(frame, glass, evaluated("tunnel/structural rib2" + suffix), y, 1.42)
    for sign, arch in ((-1,"1"),(1,"3")):
        shoulder_bar(frame, glass, evaluated("tunnel/deep entrance soffit"+arch), sign, -13.64)
        for suffix,y in (("",-10.4),(".002",2.6)):
            shoulder_bar(frame, glass, evaluated("tunnel/structural rib"+arch+suffix),sign,y)
    red, blue = (next(c for c in bpy.data.collections if c.name.startswith(prefix))
                 for prefix in ("01_RED","02_BLUE"))
    pieces = frame.objects(red,blue) + glass.objects(red,blue)
    from finishing_materials import finish_scene_geometry
    finish_scene_geometry({}, objects=pieces)
    return pieces
