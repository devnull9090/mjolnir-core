"""Generate the original Foundry modular geometry without third-party dependencies.

All coordinates are metres, right-handed Z-up. Each piece has its bounding
footprint centred on X/Y and its lowest collision point at Z=0. The authored
convex hulls are independent closed solids, never an enclosing box around a
doorway. Run with Python, then build_blender.py with Blender to export visuals.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "0.2.0"
MATERIALS = {
    "concrete": {"base_color": [0.37, 0.40, 0.39, 1], "metallic": 0.05, "roughness": 0.78},
    "gunmetal": {"base_color": [0.075, 0.105, 0.12, 1], "metallic": 0.72, "roughness": 0.38},
    "deck": {"base_color": [0.21, 0.255, 0.27, 1], "metallic": 0.5, "roughness": 0.55},
    "amber": {"base_color": [1.0, 0.48, 0.045, 1], "metallic": 0.25, "roughness": 0.4},
    "light_lens": {"base_color": [1.0, 0.83, 0.52, 1], "metallic": 0.0, "roughness": 0.24,
                   "emission_color": [1.0, 0.72, 0.32, 1], "emission_strength": 3.0},
    "light_lens_red": {"base_color": [1.0, 0.05, 0.03, 1], "metallic": 0.0, "roughness": 0.24,
                       "emission_color": [1.0, 0.05, 0.03, 1], "emission_strength": 3.0},
    "light_lens_blue": {"base_color": [0.04, 0.2, 1.0, 1], "metallic": 0.0, "roughness": 0.24,
                        "emission_color": [0.04, 0.2, 1.0, 1], "emission_strength": 3.0},
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

    # The threshold stays empty: a separate half-metre pad can be placed inside
    # this frame, leaving 3 m of headroom and 2.5 m of width for landing tests.
    # The receiver preflight raises its ~1.98 m player hull by ~0.61 m.
    portal_solids = [(0.75, 1, 4, -1.625), (0.75, 1, 4, 1.625), (2.5, 1, 0.5, 0, 0, 3.5)]
    portal_visual = [part for solid in portal_solids for part in clad_box(*solid, body="gunmetal")]
    for side in (-1, 1):
        for face in (-1, 1):
            portal_visual.extend([
                component(box(0.30, 0.035, 3.05, side*1.625, face*0.4825, 0.3), "deck", 0.012),
                component(box(0.075, 0.025, 2.75, side*1.325, face*0.4875, 0.5), "light_lens", 0.008),
                component(box(0.48, 0.025, 0.13, side*1.625, face*0.4875, 0.16), "amber", 0.008),
            ])
    for face in (-1, 1):
        portal_visual.append(component(box(2.25, 0.025, 0.1, 0, face*0.4875, 3.70), "light_lens", 0.008))
    add("portal_frame", "Portal Frame", "Openings", [4, 1, 4], portal_solids, portal_visual,
        "Open 2.5 m wide by 3.5 m high. With a 0.5 m pad, clear height is 3 m. Pair with a separate teleporter marker; the frame alone does not teleport.")

    pad_visual = clad_box(2, 2, 0.5, body="gunmetal")
    # Flush square landing target and four short lens bars. There are no raised
    # rails or central obstructions to interfere with the receiver's capsule.
    for side in (-1, 1):
        pad_visual.extend([
            component(box(1.40, 0.065, 0.004, 0, side*0.70, 0.496), "amber", 0.001),
            component(box(0.065, 1.27, 0.004, side*0.70, 0, 0.496), "amber", 0.001),
            # Clear of the deck's amber edge strip, whose top it would share.
            component(box(0.55, 0.06, 0.004, 0, side*0.9, 0.496), "light_lens", 0.001),
            component(box(0.06, 0.55, 0.004, side*0.89, 0, 0.496), "light_lens", 0.001),
        ])
    add("teleporter_pad", "Teleporter Pad", "Floors", [2, 2, 0.5], [(2, 2, 0.5)], pad_visual,
        "Flush with floor tiles; top at Z=0.5 m. Place the separate sender/receiver marker just above the top. Channels and facing are gameplay-marker settings.")

    # The housing stops at the amber end caps, and the lens sits 1 cm behind
    # the bars across it: shared faces between parts z-fight.
    strip_visual = [component(box(1.76, 0.44, 0.5, 0, 0.03), "gunmetal", 0.025),
                    component(box(1.68, 0.05, 0.30, 0, -0.215, 0.10), "light_lens", 0.012)]
    for x in (-0.94, 0.94):
        strip_visual.append(component(box(0.12, 0.5, 0.5, x), "amber", 0.012))
    for x in (-0.55, 0, 0.55):
        strip_visual.append(component(box(0.045, 0.04, 0.40, x, -0.23, 0.05), "gunmetal", 0.006))
    add("light_strip", "Light Strip", "Lighting", [2, 0.5, 0.5], [(2, 0.5, 0.5)], strip_visual,
        "Wall/header light housing; illuminated face points -Y. Includes a warm shadowless point light in front of the lens.")
    pieces[-1]["light"] = {"offset_m": [0, -0.35, 0.25], "color_rgb": [1, 0.72, 0.32],
                            "intensity_cd": 2500, "radius_m": 6}

    pylon_solids = [(1, 1, 0.25), (0.4, 0.4, 2.25, 0, 0, 0.25), (1, 1, 0.5, 0, 0, 2.5)]
    pylon_visual = clad_box(1, 1, 0.25, body="gunmetal")
    # The lamp head fills the gap between its two plates rather than sharing
    # their top and bottom faces.
    pylon_visual.extend([component(box(0.4, 0.35, 2.25, 0, 0, 0.25), "gunmetal", 0.025),
                         component(box(0.95, 0.95, 0.3, 0, 0, 2.6), "gunmetal", 0.03),
                         component(box(1, 1, 0.10, 0, 0, 2.5), "gunmetal", 0.015),
                         component(box(1, 1, 0.10, 0, 0, 2.9), "gunmetal", 0.015)])
    for side in (-1, 1):
        pylon_visual.extend([
            component(box(0.74, 0.025, 0.26, 0, side*0.4875, 2.62), "light_lens", 0.012),
            component(box(0.025, 0.74, 0.26, side*0.4875, 0, 2.62), "light_lens", 0.012),
            component(box(0.20, 0.025, 0.5, 0, side*0.1875, 0.48), "amber", 0.01),
        ])
    add("light_pylon", "Light Pylon", "Lighting", [1, 1, 3], pylon_solids, pylon_visual,
        "Freestanding light housing. The narrow post stays a separate collision hull; the lamp head is not an enclosing full-height column.")
    pieces[-1]["light"] = {"offset_m": [0, 0, 3.1], "color_rgb": [1, 0.72, 0.32],
                            "intensity_cd": 7000, "radius_m": 8}
    neutral_pylon = pieces[-1]
    for suffix, color in [("red", [1, 0.05, 0.03]), ("blue", [0.04, 0.2, 1])]:
        variant = copy.deepcopy(neutral_pylon)
        variant["id"] += "_" + suffix
        variant["name"] += " / " + suffix.title()
        variant["light"]["color_rgb"] = color
        variant["notes"] += " Fixed " + suffix + " lens and light identify team routes."
        for part in variant["visual"]:
            if part["material"] == "light_lens":
                part["material"] += "_" + suffix
        pieces.append(variant)
    return pieces


def write_sources():
    pieces = build()
    catalog = {"schema_version": 1, "name": "Foundry", "version": VERSION, "type": "content", "license": "MIT",
               "summary": f"{len(pieces)} original modular construction pieces, including portal and light housings, on a 2 m grid.",
               "description": f"Original modular industrial construction kit: {len(pieces)} pieces on a 2 m module, with concrete, gunmetal, amber and illuminated lens details.",
               "forge_pack": {"schema_version": 1, "id": "foundry", "blocks": [
                   {"id": p["id"], "name": p["name"],
                    "tag": "objects\\mjolnir\\forge\\foundry\\" + p["id"],
                    "category": p["category"], "dimensions_m": p["dimensions_m"], "snap_m": 0.5,
                    **({"light": p["light"]} if "light" in p else {})}
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
