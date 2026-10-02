#!/usr/bin/env python3
"""Composite a converted CE map's shaders into one texture each, in base-map UV space.

    ce_textures.py <staging dir> <out dir> --prefix textures/bloodgulch [--max 4096]

For every shader the BSP's glTF uses, writes `<out dir>/<shader>.png` and prints
(and writes to `<out dir>/materials.json`) one entry per shader:
`{"shader": key, "diffuse": "<prefix>/<shader>.png", "size": [w, h]}`.

Why composite: Campaign Evolved cannot load new cooked materials, and the
shipped materials a runtime instance can borrow sample one colour texture on
UV0. A classic `shader_environment` draws a base map with up to three detail
maps tiled over it at their own scales (docs/ce_map_conversion.md, "Textures").
Detail scales are whole multiples of the base map's period in practice, so the
product tiles exactly like the base map: one texture, sampled on the base
map's UVs, reproduces the shader wherever it is big enough to give every
detail tile its pixels. `--max` caps that size; past it the detail softens.

The shading rules (re-derived for this tool, see docs/ce_map_conversion.md):
- detail functions: 0 double-biased multiply `c * 2d`, 1 multiply `c * d`,
  2 double-biased add `c + 2d - 1`, all in the bitmaps' own (gamma) space,
  as the fixed-function hardware did;
- blended shaders (type 1, 2) pick between the two detail maps by the base
  map's alpha (1 primary, 0 secondary); normal shaders (type 0) by the
  secondary detail map's own alpha;
- the micro detail map goes on top with its own function and scale.
CE multiplies the result by the lightmap (no 2x); lightmaps live on a second
UV set and are not composited, nor are bump maps. The "rescale detail maps"
flag is not staged by the exporter, so its scales are taken as authored.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

DOUBLE_BIASED_MULTIPLY, MULTIPLY, DOUBLE_BIASED_ADD = 0, 1, 2
SHADER_NORMAL, SHADER_BLENDED, SHADER_BLENDED_BASE_SPECULAR = 0, 1, 2


def load(textures, name):
    """An RGBA float image in [0, 1], or None."""
    if not name:
        return None
    path = os.path.join(textures, name)
    if not os.path.exists(path):
        print(f"  missing {name}", file=sys.stderr)
        return None
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0


def fit(img, w, h):
    """Resample to w x h (box filter when shrinking, bicubic when growing)."""
    if img.shape[1] == w and img.shape[0] == h:
        return img
    shrink = w < img.shape[1] or h < img.shape[0]
    method = Image.Resampling.BOX if shrink else Image.Resampling.BICUBIC
    # Channel by channel: PIL premultiplies an RGBA image's colour by its alpha
    # to resample it, which blacks out every texel whose alpha is zero, and CE
    # alpha channels are masks (a blended ground's alpha picks its detail map).
    bytes_ = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    planes = [np.asarray(Image.fromarray(bytes_[..., c], "L").resize((w, h), method)) for c in range(img.shape[2])]
    return np.stack(planes, axis=-1).astype(np.float32) / 255.0


def tiled(img, w, h, scale):
    """`img` repeated `scale` times across a w x h canvas (wrapping), each tile
    resampled to its share of the canvas first so nothing aliases."""
    tw = max(1, round(w / scale))
    th = max(1, round(h / scale))
    tile = fit(img, tw, th)
    reps_y = math.ceil(h / th) + 1
    reps_x = math.ceil(w / tw) + 1
    big = np.tile(tile, (reps_y, reps_x, 1))
    if tw * scale == w and th * scale == h:
        return big[:h, :w]
    # A scale that does not divide the canvas: resample the repeated strip so
    # exactly `scale` tiles span it (a seam at the base map's edge remains).
    span = big[: math.ceil(th * scale), : math.ceil(tw * scale)]
    return fit(span, w, h)


def apply(color, detail, function):
    if function == MULTIPLY:
        return color * detail
    if function == DOUBLE_BIASED_ADD:
        return color + 2.0 * detail - 1.0
    return color * 2.0 * detail


def canvas_size(base, scales, details, cap):
    """The smallest power-of-two canvas (per axis) that gives each detail tile
    its full resolution, capped."""
    bh, bw = base.shape[:2]
    need_w, need_h = bw, bh
    for img, s in zip(details, scales):
        if img is None or s <= 0:
            continue
        need_w = max(need_w, img.shape[1] * s)
        need_h = max(need_h, img.shape[0] * s)
    pow2 = lambda n: 1 << max(0, math.ceil(math.log2(max(1, n))))
    return min(cap, pow2(need_w)), min(cap, pow2(need_h))


def composite_environment(textures, s, cap):
    base = load(textures, s["base_map"])
    if base is None:
        return None
    d = s["detail"]
    primary = load(textures, d["primary"])
    secondary = load(textures, d["secondary"])
    micro = load(textures, d["micro"])
    # The micro detail is subtle and very finely tiled; it does not drive the
    # canvas size, or every surface would hit the cap.
    w, h = canvas_size(base, [d["primary_scale"], d["secondary_scale"]], [primary, secondary], cap)
    b = fit(base, w, h)
    color = b[..., :3]
    kind = s.get("shader_type", SHADER_NORMAL)
    if primary is not None:
        p = tiled(primary, w, h, d["primary_scale"])[..., :3]
        if secondary is not None:
            q4 = tiled(secondary, w, h, d["secondary_scale"])
            q = q4[..., :3]
            blended = kind in (SHADER_BLENDED, SHADER_BLENDED_BASE_SPECULAR)
            a = b[..., 3:4] if blended else q4[..., 3:4]
            detail = q + (p - q) * a
        else:
            detail = p
        color = apply(color, detail, d["function"])
    if micro is not None:
        m = tiled(micro, w, h, d["micro_scale"])[..., :3]
        color = apply(color, m, d["micro_function"])
    return np.clip(color, 0.0, 1.0)


def first_map(textures, s):
    base = load(textures, s["base_map"])
    return None if base is None else base[..., :3]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("out")
    ap.add_argument("--prefix", required=True, help="path the level file names the textures by, under the mod folder")
    ap.add_argument("--max", type=int, default=4096, help="largest canvas side (default 4096)")
    a = ap.parse_args()

    textures = os.path.join(a.staging, "textures")
    materials = json.load(open(os.path.join(a.staging, "materials.json")))
    gltf = json.load(open(os.path.join(a.staging, "bsp", "bsp_0.gltf")))
    used = sorted({m["extras"]["halo"]["material"] for m in gltf["materials"]})
    os.makedirs(a.out, exist_ok=True)

    table = []
    for key in used:
        entry = materials.get(key)
        if not entry:
            print(f"  {key}: not in materials.json", file=sys.stderr)
            continue
        s = entry["shader"]
        if s["shader_class"] == "senv":
            rgb = composite_environment(textures, s, a.max)
        else:
            rgb = first_map(textures, s)
        if rgb is None:
            print(f"  {key}: no base map, left to the fallback material", file=sys.stderr)
            continue
        img = Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB")
        img.save(os.path.join(a.out, key + ".png"))
        table.append({"shader": key, "diffuse": f"{a.prefix}/{key}.png", "size": list(img.size)})
        print(f"  {key}: {s['shader_class']} -> {img.size[0]}x{img.size[1]}")
    json.dump(table, open(os.path.join(a.out, "materials.json"), "w"), indent=2)
    print(f"{len(table)} shader(s) composited into {a.out}")


if __name__ == "__main__":
    main()
