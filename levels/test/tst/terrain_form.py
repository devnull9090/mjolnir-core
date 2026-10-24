"""Deterministic, metre-scale enclosed basin for the editable TST source.

No Blender dependency: the mesh builder and placement generator share height().
The central playing surface and base foundations retain their original
profile; the pond has an irregular shore and the south apron extends four
metres. Three cliff sides meet the northern infrastructure wall. The rock
boundary is continuous; PCG dresses this foundation rather than closing gaps.
"""
import math

ARENA_HALF_X, ARENA_HALF_Y = 75, 40
BASE_X = 54
POND_X, POND_Y = 36, -23


def _smooth(a, b, value):
    t = max(0.0, min(1.0, (value-a)/(b-a)))
    return t*t*(3.0-2.0*t)


def ground_height(x, y):
    """Original gameplay ground, before perimeter cliffs were added."""
    h = .16*math.sin(x*.14)*math.cos(y*.19)
    h += 3.0*math.exp(-((x/14)**2+((y-18)/10)**2)*1.7)
    for shoulder in (-24, 24):
        h += 1.3*math.exp(-(((x-shoulder)/8)**2+((y-3)/10)**2))
    distance = math.hypot(x, y)
    if distance < 8:
        h *= max(0, (distance-6.5)/1.5)
    pond = math.hypot((x-POND_X)/8.5, (y-POND_Y)/6.2)
    angle=math.atan2((y-POND_Y)/6.2,(x-POND_X)/8.5)
    pond /= 1+.08*math.sin(angle*3+.4)+.055*math.cos(angle*5-.3)
    if pond < 2.2:
        # A metre-scale shallow shelf and soil bank are part of the actual
        # ground, so water intersects an uneven shore instead of a stone ring.
        # Retain the original deep basin; only reshape its outer two metres.
        radius = math.hypot(8.5*math.cos(angle), 6.2*math.sin(angle))
        shore = 1.485+.038*math.sin(7*angle+.8)+.025*math.cos(11*angle)
        distance = (pond-shore)*radius
        bed = -1.3*max(0, 1-(pond/1.6)**2)
        if distance <= -2.0:
            h = min(h, bed)
        elif distance < 0:
            inner = -1.3*(1-((shore-2/radius)/1.6)**2)
            h = inner+(-.18-inner)*((distance+2)/2)
        else:
            width = 1.25+.30*math.sin(3*angle-.4)
            crest = .37+.16*math.sin(angle)+.10*math.cos(5*angle+.7)
            bank = -.18+(crest+.18)*_smooth(0,width,distance)
            blend = _smooth(width, width+1.5, distance)
            h = bank*(1-blend)+h*blend
    for bx in (-BASE_X, BASE_X):
        pad = max(abs(x-bx)/13, abs(y)/15)
        if pad < 1:
            h *= max(0, (pad-.80)/.20)
    return h


def _rock_planes(x, y, cx, cy, width, depth, crown, turn, dip):
    """Intersect tilted roof and fracture planes into an angular rock mass.

    This is a continuous surface brush, not a separate mesh or a pile of
    primitives. Explicit plane intersections give readable metre-scale facets
    rather than adding noise to a smooth cliff curtain.
    """
    angle = math.radians(turn)
    u = (x-cx)*math.cos(angle)+(y-cy)*math.sin(angle)
    v = -(x-cx)*math.sin(angle)+(y-cy)*math.cos(angle)
    return max(0.0, min(
        crown + dip*u-.14*v,
        crown+.7-.17*u+.22*v,
        crown+1.8-.46*abs(u+.35*v),
        2.4*(width-u), 2.1*(width+u),
        3.3*(depth+v), 2.7*(depth-v),
        2.8*(depth+v)+.45*u+1.1,
        2.5*(width+depth*.62-abs(u+.62*v)),
    ))


def height(x, y):
    ground, cliff = ground_height(x, y), perimeter_height(x, y)
    # Zero means no cliff brush here, not a minimum terrain altitude. Preserve
    # the negative pond bed and subtle dips throughout the playable interior.
    ground += north_talus_height(x, y)
    return max(ground,cliff) if cliff > 0 else ground


def north_talus_height(x, y):
    """Joined asymmetric earth/rock shoulders below the northern balcony.

    This continuous field buries the retaining base and the descent sides.
    Its irregular toes reach into the basin; protected saddles preserve the
    actual stair footprints, rear tree and all nearby gameplay approaches.
    """
    if y < 19:
        return 0.0
    toe = 21.8+1.5*math.sin(x*.115+.7)+.8*math.sin(x*.31)
    crest = 4.5+.75*math.sin(x*.09-.5)+.4*math.cos(x*.24)
    run = max(0.0, min(1.0, (y-toe)/(31.2-toe)))
    # Broad pitched faces, with one change in angle rather than horizontal
    # terraces. Irregular crowns still leave balcony deck/headroom untouched.
    rise = crest*run**1.25
    rise += .33*math.sin(x*.47+y*.35)*math.sin(math.pi*run)
    keep = 1.0
    for stair_x in (-33, 33):
        # Protect the complete 7 m wide tread, plus its collision margin.
        keep *= _smooth(4.25, 6.6, abs(x-stair_x))
    for px,py,clear,fade in ((-24,23,3.3,6.6),(-12,26,2.5,5.6),
                             (-44,22,3.0,6.0),(44,22,3.0,6.0),
                             (34,20,2.5,5.0),(10,20,2.5,5.0),
                             (-24,18,2.5,5.0),(-57,20,2.5,5.0),
                             (-50,20,2.5,5.0),(57,20,2.5,5.0),
                             (50,20,2.5,5.0),(46,18,3.0,5.5)):
        keep *= _smooth(clear,fade,math.hypot(x-px,y-py))
    return max(0.0,rise)*keep


def perimeter_height(x, y):
    """Steep connected cliff curtains, with authored fracture planes on top.

    Keep all existing base foundations, spawns, pond and three lanes clear.
    Side toes start beyond the base roof ramps at |x|=65. The pond remains
    below the south cliff toe. No sea-level boundary blending or beach gaps.
    The north side is closed by the BSP infrastructure solid, not this field.
    """
    south_toe = 37.0 + 1.6*math.sin(x*.12) + .65*math.sin(x*.34)
    south_crown = 11.2 + .9*math.sin(x*.12) + .7*math.cos(x*.29)
    south = max(0, min(south_crown, (-y-south_toe)*4.7))
    side_toe = 65.0 + .28*math.cos(y*.23) + 1.1*math.sin(y*.31)*_smooth(18,26,abs(y))
    side_crown = 18.0 + 3.4*math.cos(y*.19) + 1.5*math.sin(y*.37)
    sides = max(0, min(side_crown, (abs(x)-side_toe)*5.1))
    # Distinct tilted slab crowns interrupt the continuous silhouette without
    # making passable valleys. The broad curtain underneath guarantees closure.
    slabs = 0
    for cx, crown, turn in ((-63,13,-8),(-43,12,11),(-21,14,-9),
                             (2,12,8),(25,13,-12),(48,12,9),(68,14,-6)):
        slabs = max(slabs, _rock_planes(x,y,cx,-43,10,4,crown,turn,.12))
    slabs *= _smooth(36.0,39.0,-y)
    # Beyond the enclosing crest, seat the back edge inside the native outer
    # formations. Keeping an equally high open edge made a thin visible shelf
    # when the preview removed sky closure faces. The inner crest stays intact.
    south_mass=max(0,max(south,slabs)-5*_smooth(40,44,-y))
    return max(south_mass,sides)


def is_rock(x, y):
    """Material follows the sculpted faces; benches can retain turf."""
    step = .4
    slope = math.hypot(height(x+step,y)-height(x-step,y),
                       height(x,y+step)-height(x,y-step))/(2*step)
    # Clad the pitched shoulder core; leave its low taper as soil/grass.
    talus = north_talus_height(x,y)
    return perimeter_height(x,y) > .5 or slope > 1.5 or talus > .65
