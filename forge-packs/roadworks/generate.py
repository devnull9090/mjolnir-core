"""Original Roadworks road kit. Pure Python; metres, right-handed Z-up.

Every asset is anchored at its entry floor, with flow initially along +Y.
Road top is 0.5 m above the origin. Connector forward vectors indicate flow
at BOTH ends (not outward socket normals). Curves turn left about (-40,0).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "0.2.0"
WIDTH, CLEAR_WIDTH, THICKNESS, RADIUS = 17.6, 16.0, 0.5, 40.0
RAIL_HEIGHT = 1.5
MATERIALS = {
    "concrete": {"base_color": [0.37, 0.40, 0.39, 1], "metallic": 0.05, "roughness": 0.78},
    "gunmetal": {"base_color": [0.075, 0.105, 0.12, 1], "metallic": 0.72, "roughness": 0.38},
    "deck": {"base_color": [0.21, 0.255, 0.27, 1], "metallic": 0.5, "roughness": 0.55},
    "amber": {"base_color": [1.0, 0.48, 0.045, 1], "metallic": 0.25, "roughness": 0.4},
}


def rounded(point):
    return [round(v, 9) if abs(v) > 1e-10 else 0.0 for v in point]


def mesh(vertices, faces):
    return {"vertices": [rounded(p) for p in vertices],
            "triangles": [[face[0], face[i], face[i+1]]
                          for face in faces for i in range(1, len(face)-1)]}


def section(center, right):
    return {"center_m": rounded(center), "right": rounded(right)}


def point_at(s, lateral, vertical=0):
    return [s["center_m"][i] + lateral*s["right"][i] + (vertical if i == 2 else 0)
            for i in range(3)]


def prism(a, b, left, right, bottom, top):
    """Closed convex road slice; bottom/top are offsets from travel surface."""
    vertices = [point_at(s, side, height)
                for height in (bottom, top)
                for s, side in ((a, left), (a, right), (b, right), (b, left))]
    return mesh(vertices, [(0,3,2,1), (4,5,6,7), (0,1,5,4),
                           (1,2,6,5), (2,3,7,6), (3,0,4,7)])


def box(w, d, h, x=0, y=0, z=0):
    return prism(section([x,y-d/2,z], [1,0,0]), section([x,y+d/2,z], [1,0,0]),
                 -w/2, w/2, 0, h)


def component(geometry, material):
    return {**geometry, "material": material, "bevel_m": 0.0}


def ramp_height(y):
    """4 m rise, flat 4 m ends, 8 m cosine slope easements, max grade 12.5%."""
    if y <= 4:
        return 0.5
    if y <= 12:
        t = (y-4)/8
        return 0.5 + 0.5*(t - math.sin(math.pi*t)/math.pi)
    if y <= 36:
        return 1.0 + (y-12)*0.125
    if y <= 44:
        t = (y-36)/8
        return 4.0 + 0.5*(t + math.sin(math.pi*t)/math.pi)
    return 4.5


def path(kind):
    if kind.startswith("straight"):
        run = int(kind.split("_")[1])
        return [section([0,y,0.5], [1,0,0]) for y in (0,run)]
    if kind.startswith("curve"):
        degrees = int(kind.split("_")[1])
        segments = degrees*24//90
        return [section([RADIUS*(math.cos(t)-1), RADIUS*math.sin(t), .5],
                        [math.cos(t), math.sin(t), 0])
                for t in (math.radians(degrees)*i/segments for i in range(segments+1))]
    return [section([0,y,ramp_height(y)], [1,0,0])
            for y in (0,4,6,8,10,12,36,38,40,42,44,48)]


def connector(ident, s):
    right = s["right"]
    return {"id": ident, "position_m": s["center_m"],
            "forward": rounded([-right[1], right[0], 0]), "up": [0,0,1],
            "clear_width_m": CLEAR_WIDTH,
            "edge_points_m": [rounded(point_at(s,-WIDTH/2)), rounded(point_at(s,WIDTH/2))]}


def build_piece(kind, guarded):
    sections = path(kind)
    hulls, visual = [], []
    # Flush, continuous lane/shoulder stripes share the exact travel plane.
    bands = [(-8.8,-8,"gunmetal"), (-8,-7.7,"amber"), (-7.7,-.15,"deck"),
             (-.15,.15,"amber"), (.15,7.7,"deck"), (7.7,8,"amber"),
             (8,8.8,"gunmetal")]
    for a, b in zip(sections, sections[1:]):
        hulls.append(prism(a,b,-WIDTH/2,WIDTH/2,-THICKNESS,0))
        visual.append(component(prism(a,b,-WIDTH/2,WIDTH/2,-THICKNESS,-.035), "concrete"))
        visual.extend(component(prism(a,b,left,right,-.035,0), mat) for left,right,mat in bands)
        if guarded:
            for left, right in ((-8.8,-8),(8,8.8)):
                hulls.append(prism(a,b,left,right,0,RAIL_HEIGHT))
                visual.append(component(prism(a,b,left,right,0,RAIL_HEIGHT-.08), "gunmetal"))
                visual.append(component(prism(a,b,left,right,RAIL_HEIGHT-.08,RAIL_HEIGHT), "amber"))
    vertices, triangles = [], []
    for hull in hulls:
        offset = len(vertices)
        vertices.extend(hull["vertices"])
        triangles.extend([[index+offset for index in t] for t in hull["triangles"]])
    minimum = [min(v[i] for v in vertices) for i in range(3)]
    maximum = [max(v[i] for v in vertices) for i in range(3)]
    dims = rounded([maximum[i]-minimum[i] for i in range(3)])
    road = {"clear_width_m": CLEAR_WIDTH, "deck_width_m": WIDTH,
            "deck_thickness_m": THICKNESS, "guardrail_height_m": RAIL_HEIGHT if guarded else 0,
            "connector_convention": "flow_tangent_at_both_ends",
            "connectors": [connector("entry",sections[0]), connector("exit",sections[-1])],
            "sections": sections}
    if kind.startswith("curve"):
        road.update(centerline_radius_m=RADIUS, turn_degrees=int(kind.split("_")[1]),
                    segment_count=len(sections)-1)
        name, category = f"Curve {road['turn_degrees']} / R40", "curves"
        notes = "Left turn; annular convex slices preserve the open inside. Endpoint metadata is authoritative."
    elif kind.startswith("straight"):
        road["run_m"] = int(kind.split("_")[1])
        name, category = f"Straight {road['run_m']} m", "roads"
        notes = "Level road with flush amber lane markings and 0.8 m shoulders."
    else:
        road.update(run_m=48, rise_m=4, flat_end_m=4, max_grade=0.125, easing_run_m=8)
        name, category = "Eased Ramp 48 / +4 m", "ramps"
        notes = "Flat 4 m ends, cosine slope easements, maximum 12.5% grade. Reverse-connect the high end for descent."
    return {"id": kind + ("_guarded" if guarded else ""),
            "name": name + (" + Rails" if guarded else ""), "category": category,
            "dimensions_m": dims, "snap_m": 0.5, "origin": "entry_floor",
            "render_distance_m": 300,
            "notes": notes, "road": road,
            "collision": {"hulls": hulls, "vertices": vertices, "triangles": triangles}, "visual": visual}


def build():
    return {"schema_version": 1, "units": "meters", "axes": "right_handed_z_up",
            "license": "MIT", "module_m": 0.5, "materials": MATERIALS,
            "pieces": [build_piece(kind, guarded)
                       for guarded in (False, True)
                       for kind in ("straight_24", "straight_48", "curve_45", "curve_90", "ramp_48")]}


def write_sources():
    source = build()
    (ROOT / "source").mkdir(parents=True, exist_ok=True)
    (ROOT / "source" / "geometry.json").write_text(json.dumps(source, indent=2)+"\n", encoding="utf-8")
    blocks = [{key: piece[key] for key in ("id", "name", "category", "dimensions_m", "snap_m", "road")}
              | {"tag": "objects\\mjolnir\\forge\\roadworks\\" + piece["id"]}
              for piece in source["pieces"]]
    catalog = {"schema_version": 1, "name": "Roadworks", "version": VERSION, "type": "content",
               "license": "MIT", "summary": "Warthog-scale modular racing roads, curves and eased ramps.",
               "description": "Ten original 16 m clear roads with 24/48 m straights, R40 curves, eased ramps and optional 1.5 m guardrails.",
               "forge_pack": {"schema_version": 1, "id": "roadworks", "blocks": blocks}}
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2)+"\n", encoding="utf-8")
    return source


if __name__ == "__main__":
    result = write_sources()
    print(f"Generated {len(result['pieces'])} original Roadworks pieces")
