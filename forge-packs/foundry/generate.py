"""Generate the original Foundry modular geometry without third-party dependencies.

All coordinates are metres, right-handed Z-up. Each piece has its bounding
footprint centred on X/Y and its lowest collision point at Z=0. The authored
convex hulls are independent closed solids, never an enclosing box around a
doorway. Run with Python, then build_blender.py with Blender to export visuals.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATERIALS = {
    "concrete": {"base_color": [0.37, 0.40, 0.39, 1], "metallic": 0.05, "roughness": 0.78},
    "gunmetal": {"base_color": [0.075, 0.105, 0.12, 1], "metallic": 0.72, "roughness": 0.38},
    "deck": {"base_color": [0.21, 0.255, 0.27, 1], "metallic": 0.5, "roughness": 0.55},
    "amber": {"base_color": [1.0, 0.48, 0.045, 1], "metallic": 0.25, "roughness": 0.4},
}


def mesh(vertices, faces):
    triangles = [[face[0], face[i], face[i + 1]] for face in faces for i in range(1, len(face) - 1)]
    return {"vertices": [[round(v, 6) for v in p] for p in vertices], "triangles": triangles}


def box(w, d, h, x=0.0, y=0.0, z=0.0):
    vertices = [(x + a * w / 2, y + b * d / 2, z + c * h)
                for a, b, c in [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),
                                (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
    return mesh(vertices, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                           (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])


def wedge(w, d, h):
    return mesh([(-w/2, -d/2, 0), (w/2, -d/2, 0), (w/2, d/2, 0),
                 (-w/2, d/2, 0), (w/2, d/2, h), (-w/2, d/2, h)],
                [(0, 3, 2, 1), (0, 1, 4, 5), (1, 2, 4), (2, 3, 5, 4), (3, 0, 5)])


def component(geometry, material, bevel=0.0):
    return {**geometry, "material": material, "bevel_m": bevel}


def clad_box(w, d, h, x=0.0, y=0.0, z=0.0, body="concrete"):
    """Recessed deck panels, flush trim and an amber strip inside nominal bounds."""
    if min(w, d, h) < 0.3:
        return [component(box(w, d, h, x, y, z), "gunmetal", min(w, d, h) * 0.08)]
    inset, skin = 0.07, 0.025
    parts = [component(box(w, d-0.05, h - skin, x, y, z), body, min(0.028, h / 8)),
             component(box(w - 2*inset, d - 2*inset, skin - 0.004, x, y, z + h - skin), "deck", 0.008)]
    for sx in (-1, 1):
        parts.append(component(box(inset, d, skin, x + sx*(w-inset)/2, y, z+h-skin), "gunmetal", 0.006))
    for sy in (-1, 1):
        parts.append(component(box(w-2*inset, inset, skin, x, y+sy*(d-inset)/2, z+h-skin), "gunmetal", 0.006))
    parts.append(component(box(max(0.1, w - 0.4), 0.045, 0.004, x, y-d/2+0.15, z+h-0.004), "amber", 0.001))
    # Recessed front armor panel, with the panel surface flush with the nominal
    # face. Its depth overlaps the body intentionally; exports remain solids.
    if h >= 0.7 and d >= 0.4 and w >= 1:
        for sign in (-1, 1):
            parts.append(component(box(w-0.24, 0.025, h*0.46, x, y+sign*(d/2-0.0125), z+h*0.26), "gunmetal", 0.012))
            parts.append(component(box(w-0.4, 0.025, 0.055, x, y+sign*(d/2-0.0125), z+h*0.72), "amber", 0.004))
    return parts


def build():
    pieces = []

    def add(ident, name, category, dims, solids, visual=None, notes=""):
        hulls = [box(*s) for s in solids] if solids else [wedge(*dims)]
        if visual is None:
            visual = [part for solid in solids for part in clad_box(*solid)]
        vertices, triangles = [], []
        for hull in hulls:
            offset = len(vertices)
            vertices.extend(hull["vertices"])
            triangles.extend([[i+offset for i in triangle] for triangle in hull["triangles"]])
        pieces.append({"id": ident, "name": name, "category": category.lower(),
                       "dimensions_m": dims, "snap_m": 0.5, "origin": "bottom_center",
                       "notes": notes, "collision": {"hulls": hulls, "vertices": vertices, "triangles": triangles},
                       "visual": visual})

    add("block_1x1", "Block 1 x 1", "Blocks", [2, 2, 2], [(2, 2, 2)])
    add("block_1x2", "Block 1 x 2", "Blocks", [2, 4, 2], [(2, 4, 2)])
    add("floor_1x1", "Floor 1 x 1", "Floors", [2, 2, 0.5], [(2, 2, 0.5)])
    add("floor_1x2", "Floor 1 x 2", "Floors", [2, 4, 0.5], [(2, 4, 0.5)])
    add("floor_2x2", "Floor 2 x 2", "Floors", [4, 4, 0.5], [(4, 4, 0.5)])
    add("bridge_straight", "Bridge Straight", "Bridges", [2, 4, 0.5], [(2, 4, 0.5)],
        clad_box(2, 4, 0.5, body="gunmetal") +
        [component(box(0.08, 3.6, 0.004, x, 0, 0.496), "amber") for x in (-0.84, 0.84)])
    add("bridge_corner", "Bridge Corner", "Bridges", [4, 4, 0.5],
        [(2, 4, 0.5, -1, 0), (2, 2, 0.5, 1, -1)],
        notes="L-shaped footprint; the upper-right quadrant stays open.")
    for ident, name, length in [("ramp", "Ramp 1 : 2", 4), ("ramp_shallow", "Ramp 1 : 4", 8)]:
        # Adjacent closed wedges make a flush deck with no coplanar overlay.
        visual = []
        for left, right, material in [(-1,-0.9,"gunmetal"), (-0.9,-0.825,"amber"),
                                      (-0.825,0.825,"deck"), (0.825,0.9,"amber"), (0.9,1,"gunmetal")]:
            strip = wedge(right-left, length, 2)
            for point in strip["vertices"]:
                point[0] += (left+right)/2
            visual.append(component(strip, material))
        add(ident, name, "Ramps", [2, length, 2], [], visual,
            "Low end faces -Y, high end +Y. Zero-height nose; exact rise 2 m.")
    add("wall", "Wall Full", "Walls", [4, 0.5, 3], [(4, 0.5, 3)])
    add("wall_half", "Wall Half", "Walls", [4, 0.5, 1.5], [(4, 0.5, 1.5)])
    add("wall_corner", "Wall Corner", "Walls", [2, 2, 3],
        [(2, 0.5, 3, 0, -0.75), (0.5, 1.5, 3, -0.75, 0.25)],
        notes="L-shaped corner; open towards +X/+Y.")
    add("doorway", "Doorway", "Openings", [4, 0.5, 3],
        [(1, 0.5, 3, -1.5), (1, 0.5, 3, 1.5), (2, 0.5, 0.5, 0, 0, 2.5)],
        notes="Clear opening 2 m wide by 2.5 m high; no collision across opening.")
    add("window", "Window Wall", "Openings", [4, 0.5, 3],
        [(1, 0.5, 3, -1.5), (1, 0.5, 3, 1.5), (2, 0.5, 1), (2, 0.5, 0.5, 0, 0, 2.5)],
        notes="Open aperture 2 m wide, from Z=1 m to Z=2.5 m. No glass or collision in aperture.")
    add("railing", "Railing", "Trim", [4, 0.25, 1],
        [(0.15, 0.25, 0.9, -1.925), (0.15, 0.25, 0.9, 1.925),
         (4, 0.25, 0.1, 0, 0, 0.9), (3.7, 0.1, 0.15, 0, 0, 0.4)])
    add("column", "Column", "Supports", [1, 1, 4], [(1, 1, 4)])
    add("cover", "Low Cover", "Cover", [2, 0.75, 1], [(2, 0.75, 1)])
    add("stairs", "Stairs", "Ramps", [2, 4, 2],
        [(2, 0.5, (step+1)*0.25, 0, -1.75+step*0.5) for step in range(8)],
        notes="Eight 0.25 m rises and 0.5 m treads; low end -Y. Gameplay collision is the visible steps.")
    return pieces


def write_sources():
    pieces = build()
    catalog = {"schema_version": 1, "name": "Foundry", "version": "0.1.0", "type": "content", "license": "MIT",
               "summary": "18 original modular construction pieces on a 2 m grid, with concrete, gunmetal and amber accents.",
               "description": "Original modular industrial construction kit: 18 pieces on a 2 m module.",
               "forge_pack": {"schema_version": 1, "id": "foundry", "blocks": [
                   {"id": p["id"], "name": p["name"],
                    "tag": "objects\\mjolnir\\forge\\foundry\\" + p["id"],
                    "category": p["category"], "dimensions_m": p["dimensions_m"], "snap_m": 0.5}
                   for p in pieces]}}
    source = {"schema_version": 1, "units": "meters", "axes": "right_handed_z_up",
              "license": "MIT", "module_m": 2, "materials": MATERIALS, "pieces": pieces}
    (ROOT / "source").mkdir(exist_ok=True)
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    (ROOT / "source" / "geometry.json").write_text(json.dumps(source, separators=(",", ":")) + "\n", encoding="utf-8")
    return source


if __name__ == "__main__":
    result = write_sources()
    print(f"Generated {len(result['pieces'])} Foundry pieces in {ROOT / 'source' / 'geometry.json'}")
