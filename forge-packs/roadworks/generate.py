"""Original Roadworks road kit. Pure Python; metres, right-handed Z-up.

Every asset is anchored at its entry floor, with flow initially along +Y.
Road top is 0.5 m above the origin. Connector forward vectors indicate flow
at BOTH ends (not outward socket normals). Curves turn left about (-20,0).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0"
WIDTH, CLEAR_WIDTH, THICKNESS, RADIUS = 8.8, 8.0, 0.5, 20.0
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
    """4 m rise, flat 2 m ends, 4 m cosine slope easements, max grade 25%."""
    if y <= 2:
        return 0.5
    if y <= 6:
        t = (y-2)/4
        return 0.5 + 0.5*(t - math.sin(math.pi*t)/math.pi)
    if y <= 18:
        return 1.0 + (y-6)*0.25
    if y <= 22:
        t = (y-18)/4
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
            for y in (0,2,3,4,5,6,18,19,20,21,22,24)]


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
    bands = [(-4.4,-4,"gunmetal"), (-4,-3.85,"amber"), (-3.85,-.075,"deck"),
             (-.075,.075,"amber"), (.075,3.85,"deck"), (3.85,4,"amber"),
             (4,4.4,"gunmetal")]
    for a, b in zip(sections, sections[1:]):
        hulls.append(prism(a,b,-WIDTH/2,WIDTH/2,-THICKNESS,0))
        visual.append(component(prism(a,b,-WIDTH/2,WIDTH/2,-THICKNESS,-.035), "concrete"))
        visual.extend(component(prism(a,b,left,right,-.035,0), mat) for left,right,mat in bands)
        if guarded:
            for left, right in ((-4.4,-4),(4,4.4)):
                hulls.append(prism(a,b,left,right,0,1))
                visual.append(component(prism(a,b,left,right,0,.92), "gunmetal"))
                visual.append(component(prism(a,b,left,right,.92,1), "amber"))
    vertices, triangles = [], []
    for hull in hulls:
        offset = len(vertices)
        vertices.extend(hull["vertices"])
        triangles.extend([[index+offset for index in t] for t in hull["triangles"]])
    minimum = [min(v[i] for v in vertices) for i in range(3)]
    maximum = [max(v[i] for v in vertices) for i in range(3)]
    dims = rounded([maximum[i]-minimum[i] for i in range(3)])
    road = {"clear_width_m": CLEAR_WIDTH, "deck_width_m": WIDTH,
            "deck_thickness_m": THICKNESS, "guardrail_height_m": 1 if guarded else 0,
            "connector_convention": "flow_tangent_at_both_ends",
            "connectors": [connector("entry",sections[0]), connector("exit",sections[-1])],
            "sections": sections}
    if kind.startswith("curve"):
        road.update(centerline_radius_m=RADIUS, turn_degrees=int(kind.split("_")[1]),
                    segment_count=len(sections)-1)
        name, category = f"Curve {road['turn_degrees']} / R20", "curves"
        notes = "Left turn; annular convex slices preserve the open inside. Endpoint metadata is authoritative."
    elif kind.startswith("straight"):
        road["run_m"] = int(kind.split("_")[1])
        name, category = f"Straight {road['run_m']} m", "roads"
        notes = "Level road with flush amber lane markings and 0.4 m shoulders."
    else:
        road.update(run_m=24, rise_m=4, flat_end_m=2, max_grade=0.25, easing_run_m=4)
        name, category = "Eased Ramp 24 / +4 m", "ramps"
        notes = "Flat 2 m ends, cosine slope easements, maximum 25% grade. Reverse-connect the high end for descent."
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
                       for kind in ("straight_12", "straight_24", "curve_45", "curve_90", "ramp_24")]}


def write_sources():
    source = build()
    (ROOT / "source").mkdir(parents=True, exist_ok=True)
    (ROOT / "source" / "geometry.json").write_text(json.dumps(source, indent=2)+"\n", encoding="utf-8")
    blocks = [{key: piece[key] for key in ("id", "name", "category", "dimensions_m", "snap_m", "road")}
              | {"tag": "objects\\mjolnir\\forge\\roadworks\\" + piece["id"]}
              for piece in source["pieces"]]
    catalog = {"schema_version": 1, "name": "Roadworks", "version": VERSION, "type": "content",
               "license": "MIT", "summary": "Warthog-scale modular racing roads, curves and eased ramps.",
               "description": "Ten original 8 m clear roads with 12/24 m straights, R20 curves, eased ramps and optional guardrails.",
               "forge_pack": {"schema_version": 1, "id": "roadworks", "blocks": blocks}}
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2)+"\n", encoding="utf-8")
    return source


if __name__ == "__main__":
    result = write_sources()
    print(f"Generated {len(result['pieces'])} original Roadworks pieces")
