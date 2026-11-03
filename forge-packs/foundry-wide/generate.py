"""Derive Foundry Wide from the versioned original source; never write Foundry.

Only X and Y coordinates change. Z, topology, materials and cosmetic bevel
widths are preserved. The source fingerprint makes upstream changes explicit.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "foundry" / "source" / "geometry.json"
VERSION = "0.2.0"
BASE_SHA256 = "1067fe7493dc91cf407571cce35d27026e44d7275150851f93a8bfea76133815"
IDS = (
    "block_1x1", "block_1x2", "floor_1x1", "floor_1x2", "floor_2x2",
    "bridge_straight", "bridge_corner", "ramp", "ramp_shallow", "wall",
    "wall_half", "wall_corner", "doorway", "window", "railing", "column",
    "cover", "stairs",
)
LEGACY_PIECES_SHA256 = "5778fe97333551b9b2d5a4eb199fcfcf3bdff5ea0fd5f9cf3c5915821219b86c"
ADDITIONS = (
    "glass_wall", "window_glazed", "doorway_tall", "doorway_vehicle",
    "ramp_wide", "ramp_high", "ramp_wide_high", "ramp_wide_shallow",
    "landing_guarded", "bridge_t", "bridge_cross", "bridge_corner_wide",
    "lift_station", "teleporter_housing", "floor_4x4", "wall_long",
    "glass_corner", "door_panel", "door_vehicle_panel", "teleporter_pad_wide",
)


def primitives():
    spec = importlib.util.spec_from_file_location("foundry_wide_primitives", BASE.parent.parent / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def combine(hulls):
    vertices, triangles = [], []
    for hull in hulls:
        offset = len(vertices)
        vertices.extend(copy.deepcopy(hull["vertices"]))
        triangles.extend([[v + offset for v in tri] for tri in hull["triangles"]])
    return {"hulls": hulls, "vertices": vertices, "triangles": triangles}


def planar_uvs(part, axes=(0, 2)):
    lo = [min(v[k] for v in part["vertices"]) for k in axes]
    hi = [max(v[k] for v in part["vertices"]) for k in axes]
    part["uvs"] = [[round((v[k] - lo[i]) / (hi[i] - lo[i]), 9) for i, k in enumerate(axes)]
                   for v in part["vertices"]]
    return part


def build_additions(legacy):
    g = primitives()
    box, component, clad = g.box, g.component, g.clad_box
    pieces = []

    def add(ident, name, category, dims, hulls, visual=None, notes=""):
        if visual is None:
            visual = [component(copy.deepcopy(h), "gunmetal", 0.015) for h in hulls]
        piece = {"id": ident, "name": "Wide " + name, "category": category,
                 "dimensions_m": dims, "snap_m": 0.5, "origin": "bottom_center",
                 "render_distance_m": 200, "notes": notes,
                 "collision": combine(hulls), "visual": visual}
        pieces.append(piece)
        return piece

    def pane(w, h, z=0):
        # Collision keeps the 0.12 m slab. What shows is one plane of the
        # two-sided glass running 2 cm into the frame: a closed glass box
        # shared its end and edge faces with the jambs, sill and head, and
        # those z-fought (tools/forge/check_overlaps.py --pack).
        geometry = box(w, 0.12, h, z=z)
        x, m = w / 2 + 0.02, 0.02
        surface = g.mesh([(-x, 0, z - m), (x, 0, z - m), (x, 0, z + h + m), (-x, 0, z + h + m)], [(0, 1, 2, 3)])
        surface = planar_uvs(component(surface, "glass"))
        surface["surface"] = "two_sided"
        return geometry, surface

    def glass_frame(w=8):
        solids = [(0.5, 1, 3, -(w-0.5)/2), (0.5, 1, 3, (w-0.5)/2),
                  (w-1, 1, 0.25), (w-1, 1, 0.25, 0, 0, 2.75)]
        hulls = [box(*s) for s in solids]
        visual = [p for s in solids for p in clad(*s, body="gunmetal")]
        glass, surface = pane(w-1, 2.5, 0.25)
        return hulls + [glass], visual + [surface]

    hulls, visual = glass_frame()
    add("glass_wall", "Glass Wall", "walls", [8, 1, 3], hulls, visual,
        "Solid non-breakable glass pane; seven-metre view between structural jambs. Stacks with 3 m walls.")
    window = copy.deepcopy(next(p for p in legacy if p["id"] == "window"))
    glass, surface = pane(4, 1.5, 1)
    add("window_glazed", "Glazed Window", "walls", [8, 1, 3],
        window["collision"]["hulls"] + [glass], window["visual"] + [surface],
        "Existing window frame with a solid non-breakable glass pane in its 4 by 1.5 m opening.")

    def doorway(ident, name, width, height, clear):
        jamb = (width-clear)/2
        solids = [(jamb, 1, height, -(clear+jamb)/2),
                  (jamb, 1, height, (clear+jamb)/2), (clear, 1, 0.5, 0, 0, height-0.5)]
        return add(ident, name, "walls", [width, 1, height], [box(*s) for s in solids],
                   [p for s in solids for p in clad(*s)],
                   f"Clear opening {clear:g} m wide by {height-0.5:g} m high. No threshold or collision in the throat.")

    doorway("doorway_tall", "Tall Doorway", 8, 4, 4)
    doorway("doorway_vehicle", "Vehicle Doorway", 12, 6, 8)
    for ident, name, width, run, rise in (
        ("ramp_wide", "Ramp 8 m / Rise 2 m", 8, 8, 2),
        ("ramp_high", "Ramp 4 m / Rise 4 m", 4, 16, 4),
        ("ramp_wide_high", "Ramp 8 m / Rise 4 m", 8, 16, 4),
        ("ramp_wide_shallow", "Ramp 8 m / Gentle Rise 2 m", 8, 16, 2),
    ):
        visual = []
        for left, right, mat in ((-width/2, -width/2+.2, "gunmetal"),
                                 (-width/2+.2, -width/2+.35, "amber"),
                                 (-width/2+.35, width/2-.35, "deck"),
                                 (width/2-.35, width/2-.2, "amber"),
                                 (width/2-.2, width/2, "gunmetal")):
            strip = g.wedge(right-left, run, rise)
            for point in strip["vertices"]:
                point[0] = round(point[0]+(left+right)/2, 9)
            visual.append(component(strip, mat))
        add(ident, name, "ramps", [width, run, rise], [g.wedge(width, run, rise)], visual,
            f"Low end -Y, high end +Y; zero-height nose, exact {rise:g} m rise over {run:g} m run (1:{run/rise:g}).")

    solids = [(8, 8, 0.5), (0.5, 8, 1.5, -3.75, 0, 0.5), (0.5, 8, 1.5, 3.75, 0, 0.5)]
    add("landing_guarded", "Guarded Landing", "bridges", [8, 8, 2], [box(*s) for s in solids],
        [p for s in solids for p in clad(*s, body="gunmetal")],
        "Deck top 0.5 m; 1.5 m solid side rails. Open +/-Y mouths with 7 m clear width; no overhead obstruction.")
    for ident, name, dims, solids, notes in (
        ("bridge_t", "Bridge T Junction", [12, 12, 0.5],
         [(12, 4, 0.5, 0, 4), (4, 8, 0.5, 0, -2)],
         "4 m paths. Side mouth centres (-6,4) and (6,4); stem mouth (0,-6). Empty lower corners remain open."),
        ("bridge_cross", "Bridge Cross Junction", [12, 12, 0.5],
         [(12, 4, 0.5), (4, 4, 0.5, 0, -4), (4, 4, 0.5, 0, 4)],
         "4 m paths with mouth centres (+/-6,0) and (0,+/-6). Four corner quadrants remain open."),
        ("bridge_corner_wide", "Bridge Corner 8 m", [16, 16, 0.5],
         [(8, 16, 0.5, -4), (8, 8, 0.5, 4, -4)],
         "8 m-wide L-shaped deck; the +X/+Y quadrant stays open."),
    ):
        add(ident, name, "bridges", dims, [box(*s) for s in solids],
            [p for s in solids for p in clad(*s, body="gunmetal")], notes)

    # Walk directly onto the lift from ground level: a central flat deck,
    # four 1:4 approaches, and solid corner housings fill the same 8 m square.
    solids = [(4, 4, 0.5)] + [(2, 2, 1.5, x, y) for x in (-3, 3) for y in (-3, 3)]
    hulls = [box(*s) for s in solids]
    visual = [p for s in solids for p in clad(*s, body="gunmetal")]
    for quarter in range(4):
        def approach(width, x=0):
            wedge = g.wedge(width, 2, .5)
            for point in wedge["vertices"]:
                px, py = point[0]+x, point[1]-3
                for _ in range(quarter):
                    px, py = -py, px
                point[0], point[1] = round(px, 9), round(py, 9)
            return wedge
        hulls.append(approach(4))
        for left, right, mat in ((-2, -1.8, "gunmetal"), (-1.8, -1.65, "amber"),
                                 (-1.65, 1.65, "deck"), (1.65, 1.8, "amber"), (1.8, 2, "gunmetal")):
            visual.append(component(approach(right-left, (left+right)/2), mat))
    lift = add("lift_station", "Lift Station", "utilities", [8, 8, 1.5], hulls, visual,
               "Central 4 by 4 m deck at 0.5 m with four 4 m-wide, 2 m-long 1:4 walk-up ramps from ground level. Corner housings are 1.5 m tall; eight metres of central overhead clearance.")
    lift["visual"].append(component(box(3, 3, 0.004, z=0.496), "light_lens_blue"))
    lift["lift"] = {"offset_m": [0, 0, 0.45], "size_m": [4, 4, 3.5], "direction": [0, 0, 1],
                    "acceleration_m_s2": 20, "max_speed_m_s": 4.5, "negates_gravity": True}

    portal = doorway("teleporter_housing", "Teleporter Housing", 8, 4, 4)
    portal["category"] = "utilities"
    field = g.mesh([(-1.95, 0, 0.05), (1.95, 0, 0.05), (1.95, 0, 3.45), (-1.95, 0, 3.45)], [(0, 1, 2, 3)])
    field = planar_uvs(component(field, "portal_green"))
    field["surface"] = "two_sided"
    portal["visual"].append(field)
    portal["notes"] += " Green field is visual-only, UV-mapped and two-sided; gameplay teleporting uses paired markers."

    for ident, name, dims, category in (("floor_4x4", "Floor 4 x 4", [16, 16, 0.5], "floors"),
                                       ("wall_long", "Wall Long", [16, 1, 3], "walls")):
        add(ident, name, category, dims, [box(*dims)], clad(*dims))

    hulls, visual = glass_frame()
    for part in hulls + visual:
        for point in part["vertices"]:
            point[1] -= 3.5
    side_hulls, side_visual = glass_frame(7)
    for part in side_hulls + side_visual:
        for point in part["vertices"]:
            x, y = point[:2]
            point[0], point[1] = -3.5-y, x+0.5
    add("glass_corner", "Glass Corner", "walls", [8, 8, 3], hulls+side_hulls, visual+side_visual,
        "L-shaped glazed wall on -X/-Y edges, opening toward +X/+Y; solid non-breakable panes.")
    for ident, name, width, height in (("door_panel", "Door Panel", 4, 3.5),
                                       ("door_vehicle_panel", "Vehicle Door Panel", 8, 5.5)):
        add(ident, name, "utilities", [width, 0.5, height], [box(width, 0.5, height)],
            clad(width, 0.5, height, body="gunmetal"),
            "Separate solid lift-up panel matching the doorway opening. Place 0.75 m toward local -Y from its frame to slide clear of the lintel.")
    pad = add("teleporter_pad_wide", "Teleporter Pad", "utilities", [4, 4, 0.5], [box(4, 4, 0.5)],
              clad(4, 4, 0.5, body="gunmetal"),
              "Solid 0.5 m deck; green inset surface is visual-only. Pair with separate gameplay teleport markers.")
    field = g.mesh([(-1.5, -1.5, 0.496), (1.5, -1.5, 0.496), (1.5, 1.5, 0.496), (-1.5, 1.5, 0.496)], [(0, 1, 2, 3)])
    # The inset top plate finishes at .496; replace it with the luminous field
    # so no coplanar opaque face hides the green surface.
    pad["visual"] = [p for p in pad["visual"] if not (p["material"] == "deck")]
    field = planar_uvs(component(field, "portal_green"), (0, 1))
    field["surface"] = "two_sided"
    pad["visual"].append(field)
    for piece in pieces:
        if piece["id"] in ("glass_wall", "window_glazed", "glass_corner"):
            piece["surfaces"] = [{"slot": 7, "profile": "glass_cyan"}]
        elif piece["id"] in ("teleporter_housing", "teleporter_pad_wide"):
            piece["surfaces"] = [{"slot": 8, "profile": "teleporter_green"}]
        if piece["id"] in ("door_panel", "door_vehicle_panel"):
            vehicle = piece["id"] == "door_vehicle_panel"
            piece["door"] = {"travel_m": 6 if vehicle else 4, "speed_m_s": 4,
                             "trigger_size_m": [12, 20, 8] if vehicle else [8, 16, 6], "hold_open_s": 2}
    assert tuple(p["id"] for p in pieces) == ADDITIONS
    return pieces


def source_fingerprint(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_original():
    source = json.loads(BASE.read_text(encoding="utf-8"))
    if source_fingerprint(source) != BASE_SHA256:
        raise ValueError("Foundry 0.2.0 source changed; review the Wide derivation before updating its provenance pin.")
    return source


def scale_mesh(mesh):
    mesh["vertices"] = [[round(x * 2, 9), round(y * 2, 9), z] for x, y, z in mesh["vertices"]]


def build_source():
    base = load_original()
    originals = {piece["id"]: piece for piece in base["pieces"]}
    pieces = []
    for ident in IDS:
        piece = copy.deepcopy(originals[ident])
        piece["name"] = "Wide " + piece["name"]
        x, y, z = piece["dimensions_m"]
        piece["dimensions_m"] = [x * 2, y * 2, z]
        piece["render_distance_m"] = 200
        scale_mesh(piece["collision"])
        for hull in piece["collision"]["hulls"]:
            scale_mesh(hull)
        for part in piece["visual"]:
            scale_mesh(part)
        piece["notes"] = {
            "ramp": "Low end -Y, high end +Y; exact 2 m rise over 8 m run (1:4), zero-height nose.",
            "ramp_shallow": "Low end -Y, high end +Y; exact 2 m rise over 16 m run (1:8), zero-height nose.",
            "doorway": "Clear opening 4 m wide by 2.5 m high; no collision across opening.",
            "window": "Open aperture 4 m wide, from Z=1 m to Z=2.5 m; no glass or collision in aperture.",
            "stairs": "Eight 0.25 m rises and 1 m treads; low end -Y. Collision follows the visible steps.",
        }.get(ident, piece["notes"])
        if ident == "ramp":
            piece["name"] = "Wide Ramp 1 : 4"
        elif ident == "ramp_shallow":
            piece["name"] = "Wide Ramp 1 : 8"
        pieces.append(piece)
    assert source_fingerprint(pieces) == LEGACY_PIECES_SHA256, "Original Wide pieces changed."
    pieces.extend(build_additions(pieces))
    used = {part["material"] for piece in pieces for part in piece["visual"]}
    materials = {name: copy.deepcopy(spec) for name, spec in base["materials"].items() if name in used}
    materials["glass"] = {"base_color": [0.32, 0.72, 0.76, 0.22], "metallic": 0.0,
                          "roughness": 0.12, "transmission_weight": 0.8, "ior": 1.45}
    materials["portal_green"] = {"base_color": [0.05, 0.75, 0.10, 0.45], "metallic": 0.0,
                                 "roughness": 0.3, "emission_color": [0.04, 1, 0.08, 1],
                                 "emission_strength": 2.0}
    return {
        "schema_version": 1, "units": "meters", "axes": "right_handed_z_up",
        "license": "MIT", "module_m": 4,
        "provenance": {"pack_id": "foundry", "version": "0.2.0",
                       "source": "../foundry/source/geometry.json",
                       "canonical_json_sha256": source_fingerprint(base),
                       "transform": {"scale_xyz": [2, 2, 1]}, "piece_ids": list(IDS)},
        "materials": materials,
        "pieces": pieces,
    }


def write_sources():
    source = build_source()
    catalog = {
        "schema_version": 1, "name": "Foundry Wide", "version": VERSION,
        "type": "content", "license": "MIT",
        "summary": "38 modular construction pieces with large platforms, glass walls, doors, ramps and utility housings.",
        "description": "A cohesive 4 m-module construction kit with 20 new pieces and all 18 original Wide structures preserved. Separate door frames and panels, solid glazed walls, broad ramps, a lift station and teleporter housings support larger levels.",
        "forge_pack": {"schema_version": 1, "id": "foundry-wide", "blocks": [
            {"id": p["id"], "name": p["name"], "tag": "objects\\mjolnir\\forge\\foundry-wide\\" + p["id"],
             "category": p["category"], "dimensions_m": p["dimensions_m"], "snap_m": 0.5,
             **{key: p[key] for key in ("lift", "door", "surfaces") if key in p}}
            for p in source["pieces"]]},
    }
    (ROOT / "source").mkdir(parents=True, exist_ok=True)
    (ROOT / "source" / "geometry.json").write_text(json.dumps(source, separators=(",", ":")) + "\n", encoding="utf-8")
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return source


if __name__ == "__main__":
    result = write_sources()
    print(f"Generated {len(result['pieces'])} Foundry Wide pieces; Foundry source was read only.")
