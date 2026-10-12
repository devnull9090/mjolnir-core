#!/usr/bin/env python3
"""Turn a converted CE map's ground into an Unreal Landscape's inputs.

    build_landscape.py <scene.gltf> <materials.spec.json> <out dir> --shader deathbeach,underwater
        [--quad 100] [--components N] [--texture 1024] [--lift 8] [--offset x,y,z]

Campaign Evolved draws B30's beach as a Landscape (footprints, grass, real
terrain detail); a converted map draws its ground as part of one static
mesh. This takes the triangles of the ground shader (`--shader`, a substring
of the CE shader's name; Death Island's beach is `deathbeach`) and writes,
over one square of N x N landscape components of 63 quads (`--quad` cm a
quad), what unreal/MJOLNIRMaterials/Scripts/build_ce_landscape.py builds the
Landscape from:

- heights.r16: (N*63+1)^2 little-endian uint16 heights, row by row from the
  square's -y edge, 32768 the actor's z, 128 a unit of its z scale (100 cm).
  A vertex over the ground takes the ground's height (the lowest, where two
  layers overlap: a plateau's overhanging lip stays the mesh's) plus `--lift`
  cm. Off the ground is a hole (below): a vertex beside the ground takes its
  ground neighbours' mean height, so the half-drawn quads along a hole's edge
  stay level; further out, the ground's heights diffused (only distant LODs
  see them).
- holes.r8: a byte a vertex, 255 where the landscape is cut away (its
  visibility layer): off the ground; on both sides of a step of more than
  2 m between neighbouring vertices (where a plateau's lip overhangs a cliff
  that recedes under it), where two layers of ground overlap, or where the
  ground ends, grown a vertex so no half-cut quad stands up a wall or sticks
  out past one; and around any quad whose surface rides more than 15 cm over the
  ground (checked at the bakes' resolution), where the grid is too coarse for
  a sharp top (Death Island's mossy boulder). The terrain mesh draws those.
- base.png, lightmap.png, bake.png, sunshare.png: the shader's base map and
  its lightmap pages (CE's lightmap, ue-texture's bake, the solver's sun
  shares) as seen from above over the same square, `--texture` texels a
  side, for the landscape master (build_ce_materials.py M_CE_Landscape), which
  reads them by world XY (LandRect). Texels off the ground take the nearest
  ground's value.
- landmask.png: holes.r8 as a texture, for the terrain mesh's ground slots,
  which draw only the holes (`cut` in landscape.json).
- landscape.json: where the actor goes, its scale and components, the
  rectangle (LandRect), the files, and `material`: the ground slot's own
  material with the bakes (as build_ce_landscape.py imports them) in place
  of its lightmap pages, which MJOLNIRLevelLoader sets on the landscape (the
  level file's `landscape.material`).

Unreal cm: the glTF is CE in metres, y up (Unreal x = x, y = z, z = y), plus
the terrain mesh's `--offset`.
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from refine_water_gltf import read_accessor  # noqa: E402

QUADS = 63
STEP = 2.0  # m between neighbouring vertices: a cliff, cut out
ABOVE = 15.0  # cm the landscape may ride over the ground (beyond --lift) before it is cut
SETTLE = 40.0  # cm a vertex may come down to meet the ground before it is cut instead
BAKED = ("Base", "Lightmap", "Bake", "SunShare")
# Where build_ce_landscape.py puts the bakes (T_Land<param>): its
# MJ_LANDSCAPE_NAME's folder (--name, LTS by default, Death Island's).
FOLDER = "/Game/MJOLNIR/Landscape/LTS"


# Each map's look over the defaults, by --name. Blood Gulch (LBG; tuned
# 2026-10-12): its paths are packed earth (Megascans trampled path, stones
# on soil in patches), not beach sand, in the original's reddish brown (its
# CE base map lit, about #af6e3d): CE's colour at 0.5 under an orange tint,
# grain contrast 1.15 (2.6 drew the busy earth texture pink); warmer shade
# (fill 0.6 on flat ground); cliffs at 0.9x CE colour (1.4x drew its red
# cliff map orange), half of it, under a grey-brown tint.
MAP_LOOKS = {
    # Yoyorast Island (LYY, 2026-10-12): its grey island rock took a purple
    # cast from CE's bluish lightmap at the dusk share; CE's light at 0.15,
    # its colour at 1.1x under a warm grey tint.
    "LYY": {
        "cliff": {"ce_tint": [0.15, 0, 0, 0], "tint": [0.85, 0.8, 0.72, 1.0], "mix": [0.6, 1.6, 1.1, 1.0]},
    },
    "LBG": {
        "pbr": {"sand_tint": [0.92, 0.84, 0.64, 1.0], "mix": [0.35, 0.65, 0.5, 0.25], "slope": [0.92, 0.8, 1.0, 0.6],
                "look": [3.0, 1.15, 0.6, 0.5], "tiles": [400, 250, 300, 700],
                "surfaces": {
                    "SandD": "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_D",
                    "SandN": "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_N",
                    "SandO": "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_ORHG",
                    "SandBD": "Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_A30_D",
                    "SandBN": "Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_N"},
                # No sea: earth throughout, in the colour its paths had as sand.
                "inland": [0, 0, 0, 1.0], "dirt_tint": [0.92, 0.84, 0.64, 1.0]},
        "cliff": {"mix": [0.6, 1.6, 0.9, 1.0], "look": [2.2, 0.5, 0.3, 1.5], "tint": [0.85, 0.78, 0.7, 1.0]},
    },
}


def load_image(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)


def sample(img, uv):
    """The image at UVs (wrapping), bilinear; img rows go with v."""
    h, w, _ = img.shape
    x = (uv[:, 0] % 1.0) * w - 0.5
    y = (uv[:, 1] % 1.0) * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = (x - x0)[:, None], (y - y0)[:, None]
    g = lambda yy, xx: img[yy % h, xx % w]
    return (g(y0, x0) * (1 - tx) * (1 - ty) + g(y0, x0 + 1) * tx * (1 - ty)
            + g(y0 + 1, x0) * (1 - tx) * ty + g(y0 + 1, x0 + 1) * tx * ty)


def raster(tris, origin, step, size, fields, highest=False):
    """Each triangle (Unreal cm, xy over z) seen from above at the points
    origin + (i, j) * step of a size x size grid: the lowest triangle's z
    and its interpolated `fields` (per-vertex arrays, by triangle). Returns
    z (nan off the ground) and each field's grid. The lowest, because where
    a plateau's grass overhangs the beach the beach is the ground a player
    walks; taking the plateau stood a wall up in front of the cliff.
    `highest` takes the top layer instead (to find where layers overlap)."""
    z = np.full((size, size), -np.inf if highest else np.inf)
    out = [np.zeros((size, size, f.shape[-1])) for f in fields]
    for t in range(len(tris)):
        p = tris[t]
        lo = np.floor((p[:, :2].min(0) - origin) / step).astype(int)
        hi = np.ceil((p[:, :2].max(0) - origin) / step).astype(int)
        lo, hi = np.clip(lo, 0, size - 1), np.clip(hi, 0, size - 1)
        if (hi < lo).any():
            continue
        xs = origin[0] + np.arange(lo[0], hi[0] + 1) * step
        ys = origin[1] + np.arange(lo[1], hi[1] + 1) * step
        gx, gy = np.meshgrid(xs, ys)
        (x0, y0), (x1, y1), (x2, y2) = p[0, :2], p[1, :2], p[2, :2]
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-9:
            continue
        w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / d
        w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / d
        w2 = 1.0 - w0 - w1
        eps = -1e-6
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if not inside.any():
            continue
        zz = w0 * p[0, 2] + w1 * p[1, 2] + w2 * p[2, 2]
        sub = z[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
        take = inside & ((zz > sub) if highest else (zz < sub))
        if not take.any():
            continue
        sub[take] = zz[take]
        for f, o in zip(fields, out):
            v = f[t]
            val = w0[..., None] * v[0] + w1[..., None] * v[1] + w2[..., None] * v[2]
            o[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1][take] = val[take]
    z[~np.isfinite(z)] = np.nan
    return z, out


def fill(values, mask, iterations=400):
    """Values off `mask` from their neighbours on it: pushed down a pyramid
    and pulled back up, then smoothed (mask cells stay)."""
    v = np.where(mask[..., None], values, 0.0)
    wgt = mask.astype(float)
    levels = [(v * wgt[..., None], wgt)]
    while min(levels[-1][1].shape) > 2:
        sv, sw = levels[-1]
        h, w = sw.shape
        h2, w2 = (h + 1) // 2, (w + 1) // 2
        pv = np.zeros((h2 * 2, w2 * 2, sv.shape[-1]))
        pw = np.zeros((h2 * 2, w2 * 2))
        pv[:h, :w], pw[:h, :w] = sv, sw
        levels.append((pv.reshape(h2, 2, w2, 2, -1).sum((1, 3)), pw.reshape(h2, 2, w2, 2).sum((1, 3))))
    est = None
    for sv, sw in reversed(levels):
        here = sv / np.maximum(sw, 1e-9)[..., None]
        if est is not None:
            up = np.repeat(np.repeat(est, 2, 0), 2, 1)[:sw.shape[0], :sw.shape[1]]
            here = np.where((sw > 0)[..., None], here, up)
        est = here
    out = np.where(mask[..., None], values, est)
    free = ~mask
    for _ in range(iterations):
        p = np.pad(out, ((1, 1), (1, 1), (0, 0)), mode="edge")
        avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4.0
        out[free] = avg[free]
    return out


def shift_filter(img, radius, op):
    """`op` (np.maximum or np.minimum) of every value within `radius` texels
    (a disc), edges padded with the image's own."""
    out = img.copy()
    p = np.pad(img, radius, mode="edge")
    h, w = img.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                out = op(out, p[radius + dy:radius + dy + h, radius + dx:radius + dx + w])
    return out


def propagate(values, known, steps, op):
    """Grow `values` from the `known` texels outward `steps` texels, each new
    texel taking `op` (np.maximum or np.minimum) of its known neighbours:
    every texel near a seed learns the nearest seed's value."""
    fill_v = -np.inf if op is np.maximum else np.inf
    v = np.where(known, values, fill_v)
    k = known.copy()
    h, w = v.shape
    for _ in range(steps):
        pv = np.pad(v, 1, constant_values=fill_v)
        pk = np.pad(k, 1)
        best = np.full_like(v, fill_v)
        got = np.zeros_like(k)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    nk = pk[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                    nv = pv[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                    best = np.where(nk, op(best, nv), best)
                    got |= nk
        new = got & ~k
        if not new.any():
            break
        v = np.where(new, best, v)
        k |= new
    return v, k


def box_blur(img, radius):
    """A box blur `radius` texels each way, twice (near a gaussian)."""
    for _ in range(2):
        p = np.pad(img, radius, mode="edge")
        c = np.cumsum(np.cumsum(np.pad(p, ((1, 0), (1, 0))), 0), 1)
        k = 2 * radius + 1
        img = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)
    return img


def edge_bake(tris, centres, step, n, z_low, on, out_dir):
    """edge.png over the bakes' square, for where walls and ground meet:
    R the height of the ground at the top of a wall (its nearest lip's,
    within 4 m; 0 for none), over `range`; G the lip
    (ground that drops more than 2 m within 3 m), B the foot (ground a wall
    rises more than 2 m over within 3 m), both softened over metres; A the
    height of the ground at the bottom of a wall (its nearest foot's; 0 for
    none).
    M_CE_CliffPBR drapes turf, earth and moss down from the lip by R;
    M_CE_LandscapePBR wears the grass at a lip and roughens a foot."""
    z_hi, _ = raster(tris, centres, step, n, [], highest=True)
    lo_f = np.where(on, z_low, np.inf)
    hi_f = np.where(np.isfinite(z_hi), z_hi, -np.inf)
    r_edge = max(1, int(round(300.0 / step)))
    # Each wall's lip and foot heights, from the drop itself: the texels
    # where the top surface falls more than 2 m within two texels (a lip)
    # or the lowest rises as much (a foot), spread outward 4 m, so a wall
    # knows the edge right above it and the ground right below it. (The
    # highest ground within 3 m read the beach under a wall standing over
    # it, or the plateau rising behind its lip.)
    tight_lo = shift_filter(np.where(on, hi_f, np.inf), 2, np.minimum)
    tight_hi = shift_filter(np.where(on, lo_f, -np.inf), 2, np.maximum)
    lip_seed = on & (hi_f - tight_lo > 200.0)
    foot_seed = on & (tight_hi - lo_f > 200.0)
    reach = max(1, int(round(400.0 / step)))
    # A lip's height is the plateau's: the highest top surface within two
    # texels (at a 62 cm texel the drop's own texel is partway down the wall,
    # and the drape began a metre under the edge, a thin green line).
    lip_z, lip_k = propagate(shift_filter(hi_f, 2, np.maximum), lip_seed, reach, np.maximum)
    foot_z, foot_k = propagate(lo_f, foot_seed, reach, np.minimum)
    top = np.where(lip_k, lip_z, -np.inf)
    # A lip is where the top surface drops, a foot where the lowest one
    # rises: under an arch (the plateau over the beach) neither does, where
    # mixing the two had both everywhere.
    near_lo = shift_filter(np.where(on, hi_f, np.inf), r_edge, np.minimum)
    near_hi = shift_filter(np.where(on, lo_f, -np.inf), r_edge, np.maximum)
    lip = on & (hi_f - near_lo > 200.0)
    foot = on & (near_hi - lo_f > 200.0)
    soft = max(1, int(round(120.0 / step)))
    lip = np.clip(box_blur(lip.astype(float), soft) * 2.0, 0, 1)
    foot = np.clip(box_blur(foot.astype(float), soft) * 2.0, 0, 1)
    # A: the ground at the bottom of a wall (the lowest within 3 m).
    bottom = np.where(foot_k, foot_z, np.inf)
    finite = np.isfinite(top)
    fb = np.isfinite(bottom)
    # 0 is "none within reach" (the range starts a metre under the lowest):
    # a wall leaning back from the ground under it has no lip the masters
    # may drape from.
    lo = float(min(top[finite].min(), bottom[fb].min())) - 100.0
    hi = float(max(top[finite].max(), bottom[fb].max()))
    t = np.where(finite, (top - lo) / max(hi - lo, 1.0), 0.0)
    b = np.where(fb, (bottom - lo) / max(hi - lo, 1.0), 0.0)
    rgba = np.stack([t, lip, foot, b], -1)
    Image.fromarray(np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8), "RGBA").save(
        os.path.join(out_dir, "edge.png"))
    print(f"edges: lips {(lip > 0.5).mean() * 100:.1f}%, feet {(foot > 0.5).mean() * 100:.1f}% of the square; "
          f"tops {lo / 100:.1f}..{hi / 100:.1f} m")
    return [lo, hi]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gltf")
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--shader", required=True,
                    help="substrings of the ground shaders' names, comma-separated; the first sizes the square")
    ap.add_argument("--quad", type=float, default=100.0, help="cm a quad")
    ap.add_argument("--components", type=int, help="components a side (default: enough for the ground)")
    ap.add_argument("--texture", type=int, default=1024, help="bake texels a side")
    ap.add_argument("--lift", type=float, default=8.0, help="cm above the ground mesh")
    ap.add_argument("--offset", default="0,0,0", help="the terrain mesh's offset (cm)")
    ap.add_argument("--name", default="LTS",
                    help="the landscape's name, one a map (build_ce_landscape.py MJ_LANDSCAPE_NAME): its bakes' folder")
    a = ap.parse_args()
    global FOLDER
    FOLDER = f"/Game/MJOLNIR/Landscape/{a.name}"
    os.makedirs(a.out, exist_ok=True)
    off = np.array([float(v) for v in a.offset.split(",")])

    spec = json.load(open(a.spec, encoding="utf-8"))
    files = {t["name"]: t["file"] for t in spec["textures"]}
    shaders = [x for x in a.shader.split(",") if x]
    slots = {s["pattern"].rstrip("$"): s for s in spec["slots"] if any(x in s["pattern"] for x in shaders)}
    if not slots:
        sys.exit(f"no slot of a shader matching {a.shader!r}")
    doc = json.load(open(a.gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(a.gltf)), doc["buffers"][0]["uri"]), "rb").read()

    # Every ground triangle with its base UVs and its lightmap page's UVs.
    tris, uv0s, uv1s, pages, blended, firsts = [], [], [], [], [], []
    page_files = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            slot = slots.get(doc["materials"][prim["material"]]["name"].lower())
            if not slot:
                continue
            tex = slot["material"]["textures"]
            leaf = lambda k: files[tex[k].rsplit(".", 1)[-1]] if k in tex else None
            key = tuple(leaf(k) for k in BAKED)
            if key not in page_files:
                page_files.append(key)
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1) + off
            uv0 = read_accessor(doc, data, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
            uv1 = read_accessor(doc, data, prim["attributes"]["TEXCOORD_1"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            tris.append(pos[idx])
            uv0s.append(uv0[idx])
            uv1s.append(uv1[idx])
            pages.append(np.full(len(idx), page_files.index(key)))
            # A blended shader picks sand or grass by its base alpha; any other
            # ground (Death Island's sea floor) is plain sand.
            blended.append(np.full(len(idx), 1.0 if (slot["material"].get("scalars") or {}).get("Type", 0) > 0.5 else 0.0))
            firsts.append(np.full(len(idx), shaders[0] in slot["pattern"]))
    tris, uv0s, uv1s, pages, blended, firsts = map(np.concatenate, (tris, uv0s, uv1s, pages, blended, firsts))
    # The square around the first shader's ground (the sea floor runs on for
    # kilometres; the rest of it stays the mesh's).
    lo, hi = tris[firsts][..., :2].reshape(-1, 2).min(0), tris[firsts][..., :2].reshape(-1, 2).max(0)
    span = (hi - lo).max()
    comps = a.components or math.ceil(span / (QUADS * a.quad))
    side = comps * QUADS * a.quad
    origin = (lo + hi) / 2 - side / 2
    size = comps * QUADS + 1
    print(f"{len(tris)} ground triangle(s) over {len(page_files)} lightmap page(s); "
          f"{comps} x {comps} components, {side / 100:.0f} m a side from {origin.round(1).tolist()}")

    # Heights.
    z, _ = raster(tris, origin, a.quad, size, [])
    ground = np.isfinite(z)
    # Off the ground the landscape is a hole: its heights matter only for the
    # half-drawn quads along a hole's edge and for distant LODs. A vertex
    # beside the ground takes its ground neighbours' mean, so an edge quad
    # stays level with the ground (sunk, it opened a crack under the cliff
    # mesh); further out, the ground's heights diffused.
    zf = fill(np.nan_to_num(z)[..., None], ground)[..., 0]
    zg = np.pad(np.where(ground, z, 0.0), 1)
    ng = np.pad(ground.astype(float), 1)
    sums = sum(zg[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    counts = sum(ng[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    ring = ~ground & (counts > 0)
    zf = np.where(ground, z, np.where(ring, sums / np.maximum(counts, 1), zf)) + a.lift
    lowest = np.where(ground, z, np.inf)
    highest = np.where(ground, z, -np.inf)
    pl, ph = np.pad(lowest, 1, constant_values=np.inf), np.pad(highest, 1, constant_values=-np.inf)
    n_lo = np.minimum.reduce([pl[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx]
                              for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
    n_hi = np.maximum.reduce([ph[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx]
                              for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
    step = STEP * 100.0
    cliff = ground & ((z - n_lo > step) | (n_hi - z > step))
    # Where two layers of ground overlap (a plateau's grass over the beach
    # below), the landscape can be only one: it is cut, and the mesh keeps
    # both (cut there, the mesh lost the upper one and a ridge top opened).
    ztop, _ = raster(tris, origin, a.quad, size, [], highest=True)
    layered = ground & (ztop - z > 100.0)
    cliff |= layered
    # Where the ground just ends (a plateau's edge over a wall with no beach
    # at its foot), the landscape stops a vertex short too: its last quad,
    # half drawn level towards the hole, stuck out past the wall as a lip.
    # The mesh draws the edge as CE has it.
    grow = cliff | ~ground
    pc = np.pad(grow, 1)
    cut = ~ground | np.logical_or.reduce([pc[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx]
                                         for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    # The actor's z: the ground's middle height, rounded to the metre. A
    # height is 16 bits, +-256 m about it at z scale 100 (Yoyorast's ground
    # lies at -258 m, which clipped at a fixed 0).
    zc = float(np.round((np.nanmin(z) + np.nanmax(z)) / 2.0 / 100.0) * 100.0)

    # Bakes, one texel's centre at a time over the same square.
    n = a.texture
    step = side / n
    centres = origin + step / 2
    z2, (uv0g, uv1g, pg, bg) = raster(tris, centres, step, n, [uv0s, uv1s, pages[:, None, None].repeat(3, 1),
                                                               blended[:, None, None].repeat(3, 1)])
    plain = np.isfinite(z2) & (bg[..., 0] < 0.5)
    on = np.isfinite(z2)

    # Where the landscape's surface (bilinear between its vertices, a fair
    # stand-in for its two triangles a quad) rides over the ground, cut the
    # quad: the mesh is drawn there.
    fx = (np.arange(n) + 0.5) * step / a.quad
    i0 = np.clip(np.floor(fx).astype(int), 0, size - 2)
    t = (fx - i0)

    def surface():
        return (zf[i0][:, i0] * np.outer(1 - t, 1 - t) + zf[i0][:, i0 + 1] * np.outer(1 - t, t)
                + zf[i0 + 1][:, i0] * np.outer(t, 1 - t) + zf[i0 + 1][:, i0 + 1] * np.outer(t, t))

    # First the grid settles onto the ground: where its surface rides over
    # the ground (a bank's toe, a dip a metre across), the vertices around
    # come down, up to SETTLE cm. Cut there instead, the mesh drew patches
    # whose own normals read the bank flatter, dirt notches with a hard edge
    # in a grass bank (Blood Gulch, 2026-10-12). What a vertex cannot reach
    # (a real ledge) is still cut, below.
    lowered = np.zeros_like(zf)
    keep = ground & ~cut
    for _ in range(8):
        zl = surface()
        excess = np.where(on, zl - z2 - (a.lift + ABOVE * 0.5), 0.0)
        oy, ox = np.nonzero(excess > 0.5)
        if not len(oy):
            break
        need = np.zeros_like(zf)
        for dy in (0, 1):
            for dx in (0, 1):
                np.maximum.at(need, (i0[oy] + dy, i0[ox] + dx), excess[oy, ox] * 0.6)
        need = np.where(keep, np.minimum(need, SETTLE - lowered), 0.0)
        zf -= need
        lowered += need
    print(f"settled {int((lowered > 0.5).sum())} vertices onto the ground (up to {lowered.max():.0f} cm)")
    zl = surface()
    over = on & (zl - z2 > a.lift + ABOVE)
    oy, ox = np.nonzero(over)
    for dy in (0, 1):
        for dx in (0, 1):
            cut[i0[oy] + dy, i0[ox] + dx] = True
    holes = np.where(cut, 255, 0).astype(np.uint8)
    holes.tofile(os.path.join(a.out, "holes.r8"))
    # The lift (the landscape over the mesh where they overlap) tapers to
    # nothing at a hole's edge: a vertex beside a hole sits on the ground,
    # the next half lifted, the rest lifted whole. Lifted to its edge, the
    # landscape stood 8 cm over the mesh it met, and a view along the ground
    # (a base's door, Blood Gulch, 2026-10-12) saw under it through the step.
    near = cut.copy()
    ring = []
    for _ in range(2):
        pn = np.pad(near, 1)
        grown = np.logical_or.reduce([pn[1 + dy:size + 1 + dy, 1 + dx:size + 1 + dx]
                                      for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
        ring.append(grown & ~near)
        near = grown
    share = np.ones_like(zf)
    share[cut] = 0.0  # a hole's own vertices shape the half-drawn quads at its edge
    share[ring[0]] = 0.0
    share[ring[1]] = 0.5
    zh = zf - a.lift * (1.0 - share)
    h = np.clip(np.round(32768 + (zh - zc) * 128.0 / 100.0), 0, 65535).astype("<u2")
    h.tofile(os.path.join(a.out, "heights.r16"))
    print(f"heights: {ground.mean() * 100:.0f}% over the ground, z {np.nanmin(z) / 100:.1f}..{np.nanmax(z) / 100:.1f} m, "
          f"lift tapered over {int(ring[0].sum() + ring[1].sum())} vertices by the holes")
    # The same mask as a texture, a texel a vertex: the terrain mesh's
    # ground slots draw only where it is cut (the masked CE master's LandCut).
    Image.fromarray(holes, "L").convert("RGBA").save(os.path.join(a.out, "landmask.png"))
    print(f"holes: {cut.mean() * 100:.0f}% of the vertices ({cliff.sum()} on cliffs or layered ground, "
          f"{over.sum()} texel(s) where the grid rode over the ground)")
    edge_range = edge_bake(tris, centres, step, n, z2, on, a.out)
    pg = np.round(pg[..., 0]).astype(int)
    images = {}
    written = {}
    for k, name in enumerate(BAKED):
        out = np.zeros((n, n, 4), np.float32)
        for pi, key in enumerate(page_files):
            f = key[k]
            if not f:
                continue
            if f not in images:
                images[f] = load_image(f)
            sel = on & (pg == pi)
            if sel.any():
                out[sel] = sample(images[f], (uv0g if name == "Base" else uv1g)[sel])
        if name == "Base":
            # Plain sand: alpha 1 (sand), and a grey that tints nothing
            # (M_CE_LandscapePBR's CE colour is relative to 0.25 linear).
            out[plain] = [136.0, 136.0, 136.0, 255.0]
        out = fill(out, on, iterations=40)
        file = name.lower() + ".png"
        Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA").save(os.path.join(a.out, file))
        written[name] = file
    rep = next(k for k in slots if shaders[0] in k)
    # The slot's own material, its page textures swapped for the bakes (and
    # their rectangle): the landscape draws with the master itself, and the
    # loader sets these at runtime. (A cooked material instance would have
    # to be retargeted to the game's layout like the world; the master
    # needs nothing.)
    material = dict(slots[rep]["material"])
    material["textures"] = {k: v for k, v in (material.get("textures") or {}).items() if k not in BAKED}
    material["textures"].update({k: f"{FOLDER}/T_Land{k}.T_Land{k}" for k in written})
    # The bake resolved the base map's UVs: CE's own transform of them (a
    # constant -1 in v on Death Island's beach, which a repeating map never
    # shows) would push the clamped bake onto its edge row.
    material["vectors"] = {k: v for k, v in (material.get("vectors") or {}).items()
                           if k not in ("BaseXform", "BaseUAnim", "BaseVAnim", "BaseRAnim", "BaseMisc")}
    material["vectors"]["LandRect"] = [float(origin[0]), float(origin[1]), side, side]
    doc_out = {
        "shader": a.shader, "slot": rep,
        "location": [float(origin[0]), float(origin[1]), zc],
        "scale": [a.quad, a.quad, 100.0],
        "components": comps, "sections": 1, "quads": QUADS,
        "heights": "heights.r16", "holes": "holes.r8", "size": size,
        "rect": [float(origin[0]), float(origin[1]), side, side],
        "textures": written, "lift": a.lift,
        "material": material,
        # The mesh slots of this ground (by their base map) give way to the
        # landscape bar its holes: the loader draws them with the masked
        # master, LandCut on.
        "cut": {"base": slots[rep]["material"]["textures"].get("Base"),
                "bases": sorted({sl["material"]["textures"]["Base"] for sl in slots.values()
                                 if "Base" in sl["material"].get("textures", {})}),
                "mask": f"{FOLDER}/T_LandMask.T_LandMask", "size": size,
                # The mesh draws wherever a hole reaches at all: the landscape
                # cuts its own edge another way (its visibility layer), and
                # at the masters' 0.25 the two left slivers of sky between
                # them. Overlapping, the landscape rides 8 cm (--lift) above.
                "edge": 0.02,
                "rect": [float(origin[0]), float(origin[1]), side, side]},
        "masks": {"LandMask": "landmask.png", "LandEdge": "edge.png"},
        # The cliffs in the game's rock (M_CE_CliffPBR, the loader's
        # Land.cliffs): every slot whose primary detail map is a cliff's.
        "cliff": {"details": sorted({sl["material"]["textures"]["Primary"].rsplit(".", 1)[-1]
                                     for sl in spec["slots"]
                                     if "detail_cliff" in sl["material"].get("textures", {}).get("Primary", "")
                                     and "Lightmap" in sl["material"].get("textures", {})}),
                  # Megascans jagged rock at 5 m and 14 m (rough rock read as a
                  # rubble wall at any scale; Jagged_Rock and the 8K shale drew
                  # far cliffs black);
                  # CE's own colour leading (look.y 0.85, at 1.4x: at 2.6x the
                  # rock went gold) under a brown tint, as the original's
                  # streaky brown walls; the fill
                  # is the sand's bounce, which this sky light alone lacks.
                  "rock_a": {"d": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D",
                             "n": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N",
                             "o": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_ORHG"},
                  "rock_b": {"d": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D",
                             "n": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N",
                             "o": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_ORHG"},
                  "tiles": [500, 1400, 2500, 4], "mix": [0.6, 1.6, 1.4, 1.0], "look": [2.2, 0.85, 0.3, 1.5], "far": [2500, 9000, 0.6, 0],
                  # CE's light colour at 0.5: some of the dusk's purple shade
                  # and warm sun, as on CE's own surfaces beside the rock.
                  "ce_tint": [0.5, 0, 0, 0],
                  "tint": [0.8, 0.66, 0.56, 1.0], "rough": [0.6, 1.0, 0, 0], "fill": [1.0, 0.8, 0.62, 1.0],
                  # Under the lip a ragged turf rim to 35 cm, no earth band (the
                  # damp soil drew black lines along every lip), stains 7 m down;
                  # at the foot only the contact shade over 1.5 m (the banked
                  # sand, foot.w, painted whole leaning walls pale).
                  "drape": [35, 35, 700, 1.0], "foot": [35, 150, 0.45, 0.0]},
        # The B30 ground (M_CE_LandscapePBR, the loader's Land.pbr): the base
        # bake says where grass grows, over the same rectangle.
        "pbr": {"base": f"{FOLDER}/T_LandBase.T_LandBase", "lightmap": f"{FOLDER}/T_LandLightmap.T_LandLightmap",
                "rect": [float(origin[0]), float(origin[1]), side, side],
                # Tuned on Death Island's dusk (2026-10-11): normals, grain
                # contrast, CE shade as occlusion, second sand; ripples to 12 m
                # over the sea (at 5 m most of the beach was flat grain; B30's
                # ripples run up it).
                # Colours matched to the original map side by side
                # (2026-10-11): sand a cool grey tint (the Megascans sand is
                # peach under the warmed light; CE's is grey beige), the grass
                # a deeper green, CE's own colour at 0.4 (mix: its grey sand and darker
                # patches from afar).
                "look": [5.0, 2.6, 0.6, 0.7], "sand_tint": [0.66, 0.74, 0.78, 1.0], "sea": [1200, 80],
                # A damp band 80 cm up from the sea, darker and a little glossy
                # (B30's waterline; 40 cm and gloss 0.35 read as a foil strip).
                "wet": [0.55, 0.55, 0, 0],
                "mix": [0.35, 0.65, 0.4, 0.25],
                # B30's ground grass ships desaturated, for its material to tint.
                "grass_tint": [0.34, 0.62, 0.2, 1.0],
                # Parallax: the sand's relief and the footprints 4 cm deep,
                # out to 25 m, 14 ray steps (Death Island at 4K: +0.2 ms GPU).
                "parallax": [4.0, 4.0, 2500, 14],
                # Where walls and ground meet (edge_bake): the ground and cliff
                # masters read it over the landscape's rectangle, its heights
                # over `range` (cm); edge_look: grass worn at a lip, earth tint
                # there, shade at a foot.
                "edge": {"texture": f"{FOLDER}/T_LandEdge.T_LandEdge", "range": edge_range,
                         "rect": [float(origin[0]), float(origin[1]), side, side]},
                "edge_look": [0.8, 0.5, 0.45],
                # Banks steeper than about 23 degrees turn grass, all grass by
                # 37 (CE's split drew stripes down them; the original is green);
                # the cliffs' fill at a quarter on flat ground (a cliff's shadow
                # on the sand was CE's deep blue sky alone, a navy band).
                "slope": [0.92, 0.8, 1.0, 0.25],
                # Far sand: drifts of the sand 9 times larger, its normal
                # taking over from 15 to 60 m.
                "macro": [0.6, 1500, 6000, 9],
                # Earth inland (2026-10-12): the sand gives way to packed
                # earth from 3 to 9 m over the sea, its edge wandering 4 m;
                # sandy gravel where the two meet and in a quarter of the
                # earth, gravel in patches 18 m across; a map with no sea is
                # earth throughout.
                "inland": [300, 900, 400, 1.0], "dirt": [0.8, 0.35, 1800, 0.25],
                "dirt_tint": [0.85, 0.8, 0.72, 1.0],
                # The level's sun and sky light, scaled and tinted (the loader,
                # as it reads the level file): a stronger sun, both a touch
                # warm against the purple dusk sky (which turned the sand
                # mauve); warmer, everything went gold beside the original.
                # Distance haze (the loader's environment.haze): a thin blue
                # height fog from 25 m, cut off at 800 m (the sky mesh).
                "haze": {"density": 0.02, "falloff": 0.08, "start": 2500, "cutoff": 80000,
                         "max_opacity": 0.7, "color": [0.00168, 0.00192, 0.00248]},
                "light": {"sun": {"scale": 1.5, "tint": [1.0, 1.0, 0.92]},
                          "sky": {"scale": 1.0, "tint": [1.0, 0.95, 0.85]}}},
    }
    # The map's own look over the defaults (tuned on Death Island's dusk).
    for section, fields in MAP_LOOKS.get(a.name, {}).items():
        doc_out[section].update(fields)
    json.dump(doc_out, open(os.path.join(a.out, "landscape.json"), "w", encoding="utf-8"), indent=1)
    print(f"bakes {n} x {n} ({step:.0f} cm a texel), {on.mean() * 100:.0f}% on the ground -> {a.out}")


if __name__ == "__main__":
    main()
