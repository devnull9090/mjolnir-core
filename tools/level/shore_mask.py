"""Bake a map's shore mask from its baked Fluid Flux water: where the water's edge is, for the
landscape shader's shore band (wet line, gravel and damp earth along every lake and river).

    python tools/level/shore_mask.py LEVEL.json OUT.png [--size 2048] [--json OUT.json]

LEVEL is a level.json whose folder holds the `flux_state/<domain>/` the level names
(`flux.domains[].state`), with `landscape.pbr.rect` [x, y, w, h] in Unreal cm. Every map with
baked Flux states gets a mask from its own water; nothing here is per map.

The PNG covers the rect, row 0 at its smallest Unreal y, one texel per rect/size:
  R  signed metres from the water's edge, -8..+24 as 0..1 (0.25 at the edge, under it in water)
  G  metres above the water's own level at the nearest edge, -4..+12 as 0..1
  B  1 inside a Flux domain, 0 outside (the shader draws no band where B is 0)
  A  1
Flux encodings (as the bake tools write them): surface z cm = height.R + capture;
terrain z cm = centre z - ground.R; texel (row, col) sits at Unreal
(centre x + (col - n/2 + 0.5) cell, centre y + (row - n/2 + 0.5) cell).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flux_wrap_safe import read  # noqa: E402

WET_M = 0.03
DIST_RANGE = (-8.0, 24.0)
LEVEL_RANGE = (-4.0, 12.0)
BORDER = 4          # texels at each domain's edge left to its neighbour


def domain_fields(root, state):
    surf = (read(root / "height.exr")[..., 0] + state["capture"]) / 100.0
    ground = (state["centre"][2] - read(root / "ground.exr")[..., 0]) / 100.0
    wet = (surf - ground) > WET_M
    cell = state["cell"] / 100.0
    out_d = ndimage.distance_transform_edt(~wet) * cell
    in_d = ndimage.distance_transform_edt(wet) * cell
    signed = np.where(wet, -in_d, out_d)
    _, (ri, ci) = ndimage.distance_transform_edt(~wet, return_indices=True)
    above = ground - surf[ri, ci]
    return signed, above, wet.any()


def bake(level_path, size):
    level_path = Path(level_path)
    level = json.loads(level_path.read_text(encoding="utf-8"))
    rx, ry, rw, rh = level["landscape"]["pbr"]["rect"]
    xs = rx + (np.arange(size) + 0.5) * rw / size
    ys = ry + (np.arange(size) + 0.5) * rh / size
    X, Y = np.meshgrid(xs, ys)
    dist = np.full((size, size), np.inf, np.float32)
    above = np.full((size, size), LEVEL_RANGE[1], np.float32)
    cover = np.zeros((size, size), np.float32)
    report = []
    for dom in (level.get("flux") or {}).get("domains", []):
        root = level_path.parent / "flux_state" / dom["id"]
        if not (root / "state.json").is_file():
            report.append({"domain": dom.get("id"), "skipped": "no baked state"})
            continue
        state = json.loads((root / "state.json").read_text())
        signed, high, any_wet = domain_fields(root, state)
        if not any_wet:
            report.append({"domain": dom["id"], "skipped": "dry"})
            continue
        n = signed.shape[0]
        col = np.rint((X - state["centre"][0]) / state["cell"] + n / 2 - 0.5).astype(int)
        row = np.rint((Y - state["centre"][1]) / state["cell"] + n / 2 - 0.5).astype(int)
        # Skip the border band: flux_wrap_safe writes it as dry water, a false edge where two
        # domains meet; the neighbouring domain's overlap covers it.
        inside = (col >= BORDER) & (col < n - BORDER) & (row >= BORDER) & (row < n - BORDER)
        d = np.where(inside, signed[np.clip(row, 0, n - 1), np.clip(col, 0, n - 1)], np.inf)
        h = high[np.clip(row, 0, n - 1), np.clip(col, 0, n - 1)]
        take = inside & (np.abs(d) < np.abs(dist))   # overlapping domains: the nearer edge wins
        dist = np.where(take, d, dist)
        above = np.where(take, h, above)
        cover = np.where(inside, 1.0, cover)
        report.append({"domain": dom["id"], "texels": int(inside.sum()), "wet_texels": int((inside & (d < 0)).sum())})
    r = (np.clip(dist, *DIST_RANGE) - DIST_RANGE[0]) / (DIST_RANGE[1] - DIST_RANGE[0])
    g = (np.clip(above, *LEVEL_RANGE) - LEVEL_RANGE[0]) / (LEVEL_RANGE[1] - LEVEL_RANGE[0])
    rgba = np.stack([r, g, cover, np.ones_like(r)], -1)
    return (rgba * 255 + 0.5).astype(np.uint8), report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("level")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--json")
    a = ap.parse_args()
    rgba, report = bake(a.level, a.size)
    Image.fromarray(rgba, "RGBA").save(a.out)
    info = {"schema": "mjolnir-shore-mask-v1", "size": a.size, "dist_range_m": DIST_RANGE,
            "level_range_m": LEVEL_RANGE, "domains": report}
    if a.json:
        Path(a.json).write_text(json.dumps(info, indent=1))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
