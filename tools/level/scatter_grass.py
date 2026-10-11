#!/usr/bin/env python3
"""Scatter the game's own grass over a converted CE map's grassy ground.

    scatter_grass.py <scene.gltf> <materials.spec.json> <out.json>
        [--density 5] [--min-z cm] [--offset x,y,z] [--bin foliage.bin]
        [--center x,y --radius r] [--seed 1]

CE draws its grass as a detail map: a blended shader_environment (Death
Island's beach) picks between two detail maps by its base map's alpha, so
where the picked one is a grass detail (GRASS_DETAILS) is where CE meant
grass. Every terrain triangle drawn with such a shader gets points at
`--density` clumps a square metre (random, seeded: every machine places the
same grass), each kept by how much grass the base map gives it there
(bilinear on the triangle's UV0) and dropped on slopes steeper than
MAX_SLOPE. Each clump is one of the game's Megascans grass meshes (the
ones Campaign Evolved's B30 beach scatters on its landscape, LG_B30_grass_
assets), upright, turned and scaled at random.

Writes {"grass": [{"mesh": path, "instances": [[x, y, z, yaw, scale], ...]}]}
in Unreal centimetres (the glTF is CE in metres, y up: Unreal x = x, y = z,
z = y, plus the terrain mesh's `--offset`). With `--bin`, the instances go
into that file instead (FOLIAGE_MAGIC: per group a count, then x, y, z as
float32 cm, yaw in 256ths of a turn and scale in hundredths, one byte
each; 14 bytes a clump, where Death Island's 300,000 made 37 MB of JSON)
and out.json is the level file's `foliage` entry for MJOLNIRLevelLoader.
`--min-z` drops clumps below it (the sea: CE's grassy ground runs on under
the water).
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

GRASS_DETAILS = ("detail_grass",)
MAX_SLOPE = math.radians(35.0)
FOLIAGE_MAGIC = b"MJFG"
# B30's grass is tinted grey for a dry beach (its instances' Color Overlay,
# 0.286); CE's grass is green.
GRASS_TINT = [0.38, 0.5, 0.26]
GRASS_MESHES = [
    "/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var11_lod0",
    "/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var12_lod0",
    "/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var4_lod0",
    "/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var12_lod0",
    "/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var19_lod0",
]


def object_path(package):
    return package + "." + package.rsplit("/", 1)[-1]


def grass_slots(spec):
    """{glTF material name (lower case): (base texture file, which detail is
    grass: "Primary" or "Secondary", shader type)} for the slots whose
    detail maps include a grass one."""
    files = {t["name"]: t["file"] for t in spec["textures"]}
    out = {}
    for s in spec["slots"]:
        m = s["material"]
        tex = m.get("textures") or {}
        which = [k for k in ("Primary", "Secondary") if any(g in tex.get(k, "") for g in GRASS_DETAILS)]
        base = tex.get("Base", "").rsplit(".", 1)[-1]
        if which and base in files:
            out[s["pattern"].rstrip("$")] = (files[base], which[0], (m.get("scalars") or {}).get("Type", 0))
    return out


def grass_weight(alpha, which, shader_type):
    """How much CE's blend shows the grass detail: a blended shader picks the
    primary detail where the base alpha is 1 (TEXTURE_PASS_CODE)."""
    if shader_type < 0.5:
        return np.ones_like(alpha) if which == "Primary" else np.zeros_like(alpha)
    return alpha if which == "Primary" else 1.0 - alpha


def sample_alpha(img, uv):
    """The image's alpha (0..1) at UVs (wrapping), bilinear."""
    h, w = img.shape
    x = (uv[:, 0] % 1.0) * w - 0.5
    y = (uv[:, 1] % 1.0) * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = x - x0, y - y0
    g = lambda yy, xx: img[yy % h, xx % w]
    return (g(y0, x0) * (1 - tx) * (1 - ty) + g(y0, x0 + 1) * tx * (1 - ty)
            + g(y0 + 1, x0) * (1 - tx) * ty + g(y0 + 1, x0 + 1) * tx * ty)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gltf")
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--density", type=float, default=5.0, help="clumps a square metre where it is all grass")
    ap.add_argument("--min-z", type=float, help="no clumps below this (Unreal cm): the sea")
    ap.add_argument("--offset", default="0,0,0", help="the terrain mesh's offset (cm, build_terrain_meshes --offset)")
    ap.add_argument("--bin", help="write the instances to this binary file (out.json names it)")
    ap.add_argument("--center", help="x,y (Unreal cm): only scatter within --radius of it")
    ap.add_argument("--radius", type=float, default=0.0, help="cm")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    slots = grass_slots(spec)
    doc = json.load(open(a.gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(a.gltf)), doc["buffers"][0]["uri"]), "rb").read()
    center = tuple(float(v) for v in a.center.split(",")) if a.center else None
    off = [float(v) for v in a.offset.split(",")]
    rng = random.Random(a.seed)
    images = {}
    per_mesh = [[] for _ in GRASS_MESHES]
    total = 0
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            hit = slots.get(name)
            if not hit:
                continue
            file, which, shader_type = hit
            if file not in images:
                images[file] = np.asarray(Image.open(file).convert("RGBA"), dtype=np.float32)[:, :, 3] / 255.0
            img = images[file]
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            uv = read_accessor(doc, data, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            for i0, i1, i2 in idx:
                p0, p1, p2 = pos[i0], pos[i1], pos[i2]
                n = np.cross(p1 - p0, p2 - p0)
                area = 0.5 * np.linalg.norm(n)
                if area <= 0 or math.acos(min(1.0, abs(n[1]) / (2 * area))) > MAX_SLOPE:
                    continue
                if center:
                    c = (p0 + p1 + p2) / 3.0 * 100.0
                    reach = max(np.linalg.norm(p0 - p1), np.linalg.norm(p1 - p2), np.linalg.norm(p2 - p0)) * 100.0
                    if math.hypot(c[0] - center[0], c[2] - center[1]) > a.radius + reach:
                        continue
                count = area * a.density
                k = int(count) + (1 if rng.random() < count - int(count) else 0)
                if not k:
                    continue
                r1 = np.array([rng.random() for _ in range(k)])
                r2 = np.array([rng.random() for _ in range(k)])
                s = np.sqrt(r1)
                w0, w1, w2 = 1 - s, s * (1 - r2), s * r2
                pts = np.outer(w0, p0) + np.outer(w1, p1) + np.outer(w2, p2)
                uvs = np.outer(w0, uv[i0]) + np.outer(w1, uv[i1]) + np.outer(w2, uv[i2])
                weight = grass_weight(sample_alpha(img, uvs), which, shader_type)
                for p, wgt in zip(pts, weight):
                    # Thin out where the blend is part grass, all of it where none.
                    if rng.random() > (wgt - 0.3) / 0.4:
                        continue
                    x, y, z = p[0] * 100.0 + off[0], p[2] * 100.0 + off[1], p[1] * 100.0 + off[2]
                    if center and math.hypot(x - center[0], y - center[1]) > a.radius:
                        continue
                    if a.min_z is not None and z < a.min_z:
                        continue
                    per_mesh[rng.randrange(len(GRASS_MESHES))].append(
                        [round(x, 1), round(y, 1), round(z, 1), round(rng.uniform(0, 360), 1),
                         round(rng.uniform(0.9, 1.5), 2)])
                    total += 1
    groups = [(object_path(m), inst) for m, inst in zip(GRASS_MESHES, per_mesh) if inst]
    if a.bin:
        with open(a.bin, "wb") as f:
            f.write(FOLIAGE_MAGIC + struct.pack("<II", 1, len(groups)))
            for _, inst in groups:
                f.write(struct.pack("<I", len(inst)))
                for x, y, z, yaw, scale in inst:
                    f.write(struct.pack("<fffBB", x, y, z, int(yaw / 360.0 * 256) % 256, min(255, int(scale * 100))))
        out = {"file": os.path.basename(a.bin), "groups": [{"mesh": m, "tint": GRASS_TINT} for m, _ in groups]}
    else:
        out = {"grass": [{"mesh": m, "instances": inst} for m, inst in groups]}
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
    print(f"{total} grass clump(s) over {len(slots)} grassy slot(s) -> {a.out}")


if __name__ == "__main__":
    main()
