#!/usr/bin/env python3
"""Scatter the game's own plants and rocks over a converted CE map's ground.

    scatter_foliage.py <scene.gltf> <materials.spec.json> <out.json> --bin foliage.bin
        [--sea cm] [--offset x,y,z] [--center x,y --radius r] [--seed 1] [--only rule,...]

CE draws its ground as detail maps: a blended shader_environment (Death
Island's beach) picks between two by its base map's alpha (TEXTURE_PASS_CODE
in build_ce_materials.py), so each point of the terrain is some share sand,
grass or other ground. RULES says what grows or lies on each: the game's
own Megascans meshes, at the densities, scales and heights above the sea
Campaign Evolved's B30 beach uses (its World Partition placements, read
with ue-asset's placements_csv example, 2026-10-11):

- grass: wild grass clumps where CE drew grass (B30 tints them grey for a
  dry beach; CE's grass is green).
- tufts: sea wheatgrass, ribbon grass and dune sedge along the edge of the
  grass, where it gives way to sand.
- rocky ground: Nordic beach rocky-ground slabs (3.5 m across, 24 cm high)
  in clusters on sand from just under the sea to 1.5 m above it.
- stones: B30's Uluwatu rocks, scaled small and set into the sand, among
  the rocky ground.

Nothing taller than knee height goes anywhere a player can walk: the
simulation knows only CE's collision, so a scattered rock is something to
walk and shoot through. B30's own big rocks stay out until they can be
given collision.

Each kept point is turned at random and scaled within its rule's range;
points are random but seeded, so every machine places the same. Clusters
come from a smooth noise over the ground. Points on slopes steeper than a
rule's limit are dropped, and so is anything below `--sea` that a rule
keeps above it; without `--sea`, the rules tied to the shore are left out.

Writes the instances to `--bin` (FOLIAGE_MAGIC: per group a count, then
x, y, z as float32 cm, yaw in 256ths of a turn and scale in hundredths, a
byte each) and out.json, the level file's `foliage` entry for
MJOLNIRLevelLoader: the file, and per group its mesh and optional tint,
material, cull distances and shadow. Unreal cm: the glTF is CE in metres,
y up (Unreal x = x, y = z, z = y), plus the terrain mesh's `--offset`.
"""
import argparse
import json
import math
import os
import random
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from refine_water_gltf import read_accessor  # noqa: E402

FOLIAGE_MAGIC = b"MJFG"
MEGA = "/Game/Megascans/3D_Plants/"
ROCKS = "/Game/Env/Bio/Rock/Uluwatu/"
# CE detail maps by what they are (substrings of the bitmap names).
DETAIL_CLASSES = (("grass", ("detail_grass",)), ("sand", ("detail_sand",)))
# A natural surface without a grass detail can paint its grass into the base
# map: there, flat ground whose base colour is green (green over red and
# blue by GREEN_MARGIN, gamma) counts as grass. Only shaders whose detail
# maps are one of NATURAL_DETAILS, so green metal stays bare.
NATURAL_DETAILS = ("cliff", "rock", "ground", "dirt", "sand")
GREEN_MARGIN = (0.03, 0.10)
GRASS_TINT = [0.38, 0.5, 0.26]
TUFT_TINT = [0.55, 0.6, 0.38]

# Each rule: the ground class it grows on and the share of it it needs
# (`share`: [low, high], thinned linearly between), clumps a square metre,
# slope limit (degrees), height above the sea (m), cluster noise (cell
# size m and threshold: None for none), meshes (with their own scale ranges
# and how far to sink them, cm a unit of scale), and the loader settings.
RULES = [
    {"name": "grass", "on": "grass", "share": [0.3, 0.7], "density": 5.0, "slope": 50, "above": [0.3, None],
     "meshes": [(MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var11_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var12_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var4_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var12_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var19_lod0", 0.9, 1.5, 0)],
     "tint": GRASS_TINT, "cull": [5000, 9000]},
    {"name": "tufts", "on": "grass", "share": [0.12, 0.45], "density": 0.8, "slope": 40, "above": [0.6, None],
     "falloff": True,
     "meshes": [(MEGA + "Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var9_lod0", 0.64, 0.96, 0),
                (MEGA + "Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_Var1_lod0", 0.42, 0.58, 0),
                (MEGA + "Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var2_lod0", 0.53, 0.77, 0),
                (MEGA + "Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var3_lod0", 0.42, 0.58, 0),
                (MEGA + "Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var6_lod0", 0.62, 0.79, 0),
                (MEGA + "Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var7_lod0", 0.62, 0.79, 0)],
     "tint": TUFT_TINT, "cull": [4000, 7000]},
    {"name": "rocky ground", "on": "sand", "share": [0.5, 0.8], "density": 0.06, "slope": 25, "above": [-0.4, 1.5],
     "cluster": [14.0, 0.62],
     "meshes": [("/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ve3qdhmqx/S_Nordic_Beach_Rocky_Ground_Uluwata_B",
                 0.6, 1.0, 6)],
     "cull": [8000, 14000], "shadow": True},
    {"name": "stones", "on": "sand", "share": [0.5, 0.8], "density": 0.25, "slope": 30, "above": [-0.5, 2.5],
     "cluster": [14.0, 0.55],
     "meshes": [(ROCKS + "Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A", 0.06, 0.25, 40),
                (ROCKS + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B", 0.04, 0.14, 60),
                (ROCKS + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C", 0.04, 0.10, 80)],
     "materials": {ROCKS + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B":
                   ROCKS + "Rock_Uluwatu_Med_B/Materials/MI_Rock_Uluwatu_Med_B_Waterline",
                   ROCKS + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C":
                   ROCKS + "Rock_Uluwatu_Med_C/Materials/MI_Rock_Uluwatu_Med_C_Waterline",
                   ROCKS + "Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A":
                   ROCKS + "Rock_Uluwatu_Med_A/Materials/MI_Rock_Uluwatu_Med_A_Waterline"},
     "cull": [5000, 9000], "shadow": True},
]


def object_path(package):
    return package + "." + package.rsplit("/", 1)[-1]


def detail_class(path):
    lower = path.lower()
    for cls, names in DETAIL_CLASSES:
        if any(n in lower for n in names):
            return cls
    return None


def ground_slots(spec):
    """{glTF material name (lower case): (base texture file, primary class,
    secondary class, shader type)} for the shaders whose detail maps are
    sand or grass, or natural ground ("green": its grass in the base)."""
    files = {t["name"]: t["file"] for t in spec["textures"]}
    out = {}
    for s in spec["slots"]:
        m = s["material"]
        tex = m.get("textures") or {}
        base = tex.get("Base", "").rsplit(".", 1)[-1]
        if base not in files or "Environment" not in m.get("parent", ""):
            continue
        primary, secondary = detail_class(tex.get("Primary", "")), detail_class(tex.get("Secondary", ""))
        if not (primary or secondary):
            if not any(n in v.lower() for v in tex.values() for n in NATURAL_DETAILS):
                continue
            primary = "green"
        out[s["pattern"].rstrip("$")] = (files[base], primary, secondary if "Secondary" in tex else None,
                                         (m.get("scalars") or {}).get("Type", 0))
    return out


def class_shares(rgba, primary, secondary, shader_type):
    """{class: share 0..1} at each point: a blended shader picks the primary
    detail where the base alpha is 1; a "green" surface is grass by how
    green its base colour is."""
    n = len(rgba)
    if primary == "green":
        g = rgba[:, 1] - np.maximum(rgba[:, 0], rgba[:, 2])
        return {"grass": np.clip((g - GREEN_MARGIN[0]) / (GREEN_MARGIN[1] - GREEN_MARGIN[0]), 0.0, 1.0)}
    pick = rgba[:, 3] if (shader_type > 0.5 and secondary) else np.ones(n)
    shares = {}
    for cls, w in ((primary, pick), (secondary, 1.0 - pick)):
        if cls:
            shares[cls] = shares.get(cls, np.zeros(n)) + w
    return shares


def sample_rgba(img, uv):
    """The image's RGBA (0..1, gamma) at UVs (wrapping), bilinear."""
    h, w, _ = img.shape
    x = (uv[:, 0] % 1.0) * w - 0.5
    y = (uv[:, 1] % 1.0) * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = (x - x0)[:, None], (y - y0)[:, None]
    g = lambda yy, xx: img[yy % h, xx % w]
    return (g(y0, x0) * (1 - tx) * (1 - ty) + g(y0, x0 + 1) * tx * (1 - ty)
            + g(y0 + 1, x0) * (1 - tx) * ty + g(y0 + 1, x0 + 1) * tx * ty)


def value_noise(x, y, cell, seed):
    """Smooth value noise in 0..1 over world x, y (cm), cells `cell` m."""
    fx, fy = x / (cell * 100.0), y / (cell * 100.0)
    ix, iy = math.floor(fx), math.floor(fy)
    tx, ty = fx - ix, fy - iy
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)

    def h(i, j):
        return random.Random(hash((i, j, seed)) & 0xFFFFFFFF).random()

    return (h(ix, iy) * (1 - tx) + h(ix + 1, iy) * tx) * (1 - ty) + (h(ix, iy + 1) * (1 - tx) + h(ix + 1, iy + 1) * tx) * ty


def keep_share(share, lo, hi, falloff):
    """How likely a point is kept for its share of the rule's class: up from
    `lo` to all at `hi`, or (`falloff`, an edge) up to `lo` and back down by
    `hi`."""
    if falloff:
        mid = (lo + hi) / 2
        return max(0.0, 1.0 - abs(share - mid) / ((hi - lo) / 2))
    return min(1.0, max(0.0, (share - lo) / max(hi - lo, 1e-6)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gltf")
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--bin", required=True, help="the instances' binary file (out.json names it)")
    ap.add_argument("--sea", type=float, help="the sea's height (Unreal cm): the rules' heights are above it")
    ap.add_argument("--offset", default="0,0,0", help="the terrain mesh's offset (cm, build_terrain_meshes --offset)")
    ap.add_argument("--center", help="x,y (Unreal cm): only scatter within --radius of it")
    ap.add_argument("--radius", type=float, default=0.0, help="cm")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--only", help="comma-separated rule names")
    a = ap.parse_args()

    rules = [r for r in RULES if not a.only or r["name"] in a.only.split(",")]
    if a.sea is None:
        # A rule that lives in a band above the sea has no place on a map
        # without one: unbounded, the shore stones would cover every sand.
        rules = [r for r in rules if r["above"][1] is None]
    spec = json.load(open(a.spec, encoding="utf-8"))
    slots = ground_slots(spec)
    doc = json.load(open(a.gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(a.gltf)), doc["buffers"][0]["uri"]), "rb").read()
    center = tuple(float(v) for v in a.center.split(",")) if a.center else None
    off = [float(v) for v in a.offset.split(",")]
    rng = random.Random(a.seed)
    images = {}
    groups = {}  # mesh -> (rule, instances)
    counts = {r["name"]: 0 for r in rules}
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            hit = slots.get(doc["materials"][prim["material"]]["name"].lower())
            if not hit:
                continue
            file, primary, secondary, shader_type = hit
            if file not in images:
                images[file] = np.asarray(Image.open(file).convert("RGBA"), dtype=np.float32) / 255.0
            img = images[file]
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            uv = read_accessor(doc, data, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            for i0, i1, i2 in idx:
                p0, p1, p2 = pos[i0], pos[i1], pos[i2]
                n = np.cross(p1 - p0, p2 - p0)
                area = 0.5 * np.linalg.norm(n)
                if area <= 0:
                    continue
                slope = math.degrees(math.acos(min(1.0, abs(n[1]) / (2 * area))))
                if center:
                    c = (p0 + p1 + p2) / 3.0 * 100.0
                    reach = max(np.linalg.norm(p0 - p1), np.linalg.norm(p1 - p2), np.linalg.norm(p2 - p0)) * 100.0
                    if math.hypot(c[0] - center[0], c[2] - center[1]) > a.radius + reach:
                        continue
                for rule in rules:
                    if slope > rule["slope"]:
                        continue
                    count = area * rule["density"]
                    k = int(count) + (1 if rng.random() < count - int(count) else 0)
                    if not k:
                        continue
                    r1 = np.array([rng.random() for _ in range(k)])
                    r2 = np.array([rng.random() for _ in range(k)])
                    s = np.sqrt(r1)
                    w0, w1, w2 = 1 - s, s * (1 - r2), s * r2
                    pts = np.outer(w0, p0) + np.outer(w1, p1) + np.outer(w2, p2)
                    uvs = np.outer(w0, uv[i0]) + np.outer(w1, uv[i1]) + np.outer(w2, uv[i2])
                    share = class_shares(sample_rgba(img, uvs), primary, secondary, shader_type).get(rule["on"])
                    if share is None:
                        continue
                    lo, hi = rule["share"]
                    for p, sh in zip(pts, share):
                        if rng.random() > keep_share(sh, lo, hi, rule.get("falloff")):
                            continue
                        x, y, z = p[0] * 100.0 + off[0], p[2] * 100.0 + off[1], p[1] * 100.0 + off[2]
                        if center and math.hypot(x - center[0], y - center[1]) > a.radius:
                            continue
                        if a.sea is not None:
                            low, high = rule["above"]
                            h = (z - a.sea) / 100.0
                            if (low is not None and h < low) or (high is not None and h > high):
                                continue
                        cl = rule.get("cluster")
                        if cl and value_noise(x, y, cl[0], a.seed) < cl[1]:
                            continue
                        path, smin, smax, sink = rule["meshes"][rng.randrange(len(rule["meshes"]))]
                        scale = rng.uniform(smin, smax)
                        groups.setdefault(path, (rule, []))[1].append(
                            [x, y, z - sink * scale, rng.uniform(0, 360), scale])
                        counts[rule["name"]] += 1
    ordered = sorted(groups.items(), key=lambda kv: kv[0])
    with open(a.bin, "wb") as f:
        f.write(FOLIAGE_MAGIC + struct.pack("<II", 1, len(ordered)))
        for _, (_, inst) in ordered:
            f.write(struct.pack("<I", len(inst)))
            for x, y, z, yaw, scale in inst:
                f.write(struct.pack("<fffBB", x, y, z, int(yaw / 360.0 * 256) % 256,
                                    max(1, min(255, round(scale * 100))) & 0xFF))
    out_groups = []
    for path, (rule, _) in ordered:
        g = {"mesh": object_path(path), "rule": rule["name"], "cull": rule["cull"]}
        if rule.get("tint"):
            g["tint"] = rule["tint"]
        material = rule.get("materials", {}).get(path)
        if material:
            g["material"] = object_path(material)
        g["shadow"] = bool(rule.get("shadow", True))
        out_groups.append(g)
    json.dump({"file": os.path.basename(a.bin), "groups": out_groups}, open(a.out, "w", encoding="utf-8"), indent=1)
    print(", ".join(f"{v} {k}" for k, v in counts.items()) + f" over {len(slots)} ground slot(s) -> {a.bin}")


if __name__ == "__main__":
    main()
