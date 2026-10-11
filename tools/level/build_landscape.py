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
BAKED = ("Base", "Lightmap", "Bake", "SunShare")
# Where build_ce_landscape.py puts the bakes (T_Land<param>).
FOLDER = "/Game/MJOLNIR/Landscape/LTS"


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
    a = ap.parse_args()
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
    zc = 0.0
    h = np.clip(np.round(32768 + (zf - zc) * 128.0 / 100.0), 0, 65535).astype("<u2")
    h.tofile(os.path.join(a.out, "heights.r16"))
    print(f"heights: {ground.mean() * 100:.0f}% over the ground, z {np.nanmin(z) / 100:.1f}..{np.nanmax(z) / 100:.1f} m")

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
    zl = (zf[i0][:, i0] * np.outer(1 - t, 1 - t) + zf[i0][:, i0 + 1] * np.outer(1 - t, t)
          + zf[i0 + 1][:, i0] * np.outer(t, 1 - t) + zf[i0 + 1][:, i0 + 1] * np.outer(t, t))
    over = on & (zl - z2 > a.lift + ABOVE)
    oy, ox = np.nonzero(over)
    for dy in (0, 1):
        for dx in (0, 1):
            cut[i0[oy] + dy, i0[ox] + dx] = True
    holes = np.where(cut, 255, 0).astype(np.uint8)
    holes.tofile(os.path.join(a.out, "holes.r8"))
    # The same mask as a texture, a texel a vertex: the terrain mesh's
    # ground slots draw only where it is cut (the masked CE master's LandCut).
    Image.fromarray(holes, "L").convert("RGBA").save(os.path.join(a.out, "landmask.png"))
    print(f"holes: {cut.mean() * 100:.0f}% of the vertices ({cliff.sum()} on cliffs or layered ground, "
          f"{over.sum()} texel(s) where the grid rode over the ground)")
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
        "masks": {"LandMask": "landmask.png"},
        # The B30 ground (M_CE_LandscapePBR, the loader's Land.pbr): the base
        # bake says where grass grows, over the same rectangle.
        "pbr": {"base": f"{FOLDER}/T_LandBase.T_LandBase", "lightmap": f"{FOLDER}/T_LandLightmap.T_LandLightmap",
                "rect": [float(origin[0]), float(origin[1]), side, side],
                # Tuned on Death Island's dusk (2026-10-11): normals, grain
                # contrast, CE shade as occlusion, second sand; a warm tint
                # against the purple sky; ripples to 12 m over the sea (at 5 m,
                # most of the beach was flat grain; B30's ripples run up it).
                "look": [5.0, 2.6, 0.6, 0.7], "sand_tint": [0.92, 0.82, 0.72, 1.0], "sea": [1200, 40],
                # B30's ground grass ships desaturated, for its material to tint.
                "grass_tint": [0.62, 0.78, 0.36, 1.0],
                # Parallax: the sand's relief and the footprints 4 cm deep,
                # out to 25 m, 14 ray steps (Death Island at 4K: +0.2 ms GPU).
                "parallax": [4.0, 4.0, 2500, 14],
                # Far sand: drifts of the sand 9 times larger, its normal
                # taking over from 15 to 60 m.
                "macro": [0.6, 1500, 6000, 9],
                # The level's sun and sky light, scaled and tinted (the loader,
                # as it reads the level file): a stronger, warmer sun and warm
                # shade, where the purple dusk sky had turned the sand mauve.
                "light": {"sun": {"scale": 1.5, "tint": [1.0, 0.93, 0.75]},
                          "sky": {"scale": 1.0, "tint": [1.0, 0.78, 0.55]}}},
    }
    json.dump(doc_out, open(os.path.join(a.out, "landscape.json"), "w", encoding="utf-8"), indent=1)
    print(f"bakes {n} x {n} ({step:.0f} cm a texel), {on.mean() * 100:.0f}% on the ground -> {a.out}")


if __name__ == "__main__":
    main()
