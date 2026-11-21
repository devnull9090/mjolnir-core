"""Point lights where a level's decor has light fixtures: level.lights for MJOLNIRLevelLoader.

A base mesh draws its lamps as an emissive material slot (PWR: `interior_light`), which glows but
lights nothing: the room stays black under a physically exposed sky. For every decor mesh that
carries a configured slot, the slot's faces are grouped into fixtures (faces within `merge_m` of
each other) and each fixture gets one shadowed point light just off its surface, as bright as the
fixture is large. Any map whose decor carries the same slot gets its lights with no further work.

    python emissive_lights.py <level.json> --meshes <dir of <asset>.glb> --config <vista.json> [--write]

Config key `fixture_lights`: {"slots": {"<slot>": {"colour": [r, g, b], "intensity": cd before the
light scale for a fixture of `area_m2`, "radius_m": reach}}, "merge_m", "offset_m", "area_m2"}.
Packagers call lights(level, glb_of, spec) (PWR's release stage, stage_vista.py).
"""
import argparse
import json
from pathlib import Path

import numpy as np

from coplanar_overlaps import glb_sections, world


def fixtures(tris, merge):
    """Group faces into fixtures: [(centre, mean outward normal, area m2)], largest first."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = np.linalg.norm(n, axis=1) / 2
    keep = area > 0
    tris, n, area = tris[keep], n[keep], area[keep]
    centre = tris.mean(1)
    # Coarse cells first (a fixture is thousands of small faces), then leaders: a cell joins the
    # first fixture whose seed lies within `merge`, biggest cells seeding first.
    cell = np.floor(centre / 50.0).astype(np.int64)
    keys, inverse = np.unique(cell, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    c_area = np.bincount(inverse, area)
    c_pos = np.stack([np.bincount(inverse, centre[:, k] * area) for k in range(3)], 1) / c_area[:, None]
    c_n = np.stack([np.bincount(inverse, n[:, k]) for k in range(3)], 1) / 2      # area-weighted normals
    groups = []
    for i in np.argsort(-c_area):
        for g in groups:
            if np.linalg.norm(c_pos[i] - g["seed"]) <= merge:
                g["cells"].append(i)
                break
        else:
            groups.append({"seed": c_pos[i], "cells": [i]})
    out = []
    for g in groups:
        ids = g["cells"]
        a = c_area[ids].sum()
        out.append(((c_pos[ids] * c_area[ids, None]).sum(0) / a, c_n[ids].sum(0), a / 1e4))
    return sorted(out, key=lambda f: -f[2])


def lights(level, glb_of, spec):
    """level.lights entries for every fixture of the configured slots. `glb_of(asset name)` gives the
    mesh's exported .glb path, or None."""
    merge, offset = spec.get("merge_m", 7.0) * 100, spec.get("offset_m", 0.8) * 100
    # Every decor piece's faces of a slot together: a room's lamps are split over several meshes
    # (the shell's ribs, a polish pass's strips), and one light serves the lamps that sit together.
    faces = {slot: [] for slot in spec["slots"]}
    for d in level.get("decor", []):
        name = (d.get("mesh") or "").rsplit(".", 1)[-1]
        glb = glb_of(name) if name else None
        if not glb:
            continue
        sections = glb_sections(glb)
        for slot in spec["slots"]:
            if slot in sections:
                tris = world(sections[slot], d)
                if tris is not None:
                    # glb_sections swaps two axes (glTF y-up to UE), which mirrors the winding: flip it back.
                    faces[slot].append(tris[:, ::-1])
    out, report = [], {}
    for slot, cfg in spec["slots"].items():
        if not faces[slot]:
            continue
        for centre, normal, area in fixtures(np.concatenate(faces[slot]), merge):
            if area < spec.get("min_area_m2", 0.2):
                continue
            length = np.linalg.norm(normal)
            # Lamps facing each other across a room have no net facing: the light sits among them.
            out_dir = normal / length if length > 0.6 * area * 1e4 else np.zeros(3)
            pos = centre + out_dir * offset
            scale = min(1.6, max(0.5, area / spec.get("area_m2", 0.8)))
            out.append({"pos": [round(float(v), 1) for v in pos], "colour": cfg["colour"],
                        "intensity": round(cfg["intensity"] * scale, 2), "radius": cfg["radius_m"] * 100.0,
                        "source_radius": cfg.get("source_radius_cm", 30), "source": "fixtures/" + slot})
        report[slot] = sum(1 for l in out if l["source"] == "fixtures/" + slot)
    return out, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("level", type=Path)
    ap.add_argument("--meshes", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    level = json.loads(a.level.read_text())

    def glb_of(name):
        p = a.meshes / f"{name}.glb"
        return p if p.is_file() else None
    found, report = lights(level, glb_of, json.loads(a.config.read_text())["fixture_lights"])
    if a.write:
        level["lights"] = [l for l in level.get("lights") or [] if "source" not in l] + found
        a.level.write_text(json.dumps(level, indent=2))
    print(json.dumps({"lights": len(found), "by_decor": report}))
    for l in found[:40]:
        print(l["pos"], l["intensity"], l["source"])


if __name__ == "__main__":
    main()
