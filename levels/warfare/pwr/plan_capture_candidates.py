"""Choose candidate spots for PWR's moving capture zones from the terrain masks.

Each site keeps its classic spot as candidate 0 and gains extra candidates on
open, flat, dry, tree-free ground. Fairness is built in: site C's candidates are
mirror images of site A's across the line halfway between the two homes, and
site B's lie on that line, so every draw leaves both teams the same distances.
Writes `capture_candidates_m` into layout.json (with --write) and a preview PNG.

    python levels/warfare/pwr/plan_capture_candidates.py --preview out/pwr/zones/candidates.png [--write]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield  # noqa: E402

TERRAIN = HERE / "terrain/runtime-v3/runtime-master.json"  # the accepted layout-3 runtime terrain
LAYOUT = HERE / "layout.json"
RADIUS = 20.0          # capture radius (m)
CHECK = RADIUS + 6.0   # ground that must be clear around a spot
MAX_RISE = 3.0         # height range allowed inside CHECK (m)
SITE_GAP = 150.0       # from every candidate of another site
SAME_GAP = 100.0       # between a site's own candidates
HOME_GAP = 160.0       # from either home
EXTRA = 3              # extra candidates per site (MAX_CANDIDATES is 6)
STEP = 10.0            # search grid (m)


def disc(field, x, y, radius, step=4.0):
    """Samples of the height and every mask on a disc."""
    pts = []
    r = -radius
    while r <= radius:
        s = -radius
        while s <= radius:
            if r * r + s * s <= radius * radius:
                pts.append((x + r, y + s))
            s += step
        r += step
    xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
    heights = np.array([field.sample(px, py) for px, py in zip(xs, ys)])
    masks = {k: np.array([field.sample_mask(k, px, py) for px, py in zip(xs, ys)]) for k in field.masks}
    return heights, masks


def suitable(field, x, y, bounds):
    (x0, y0), (x1, y1) = bounds
    if not (x0 + CHECK < x < x1 - CHECK and y0 + CHECK < y < y1 - CHECK):
        return None
    heights, masks = disc(field, x, y, CHECK)
    rise = float(heights.max() - heights.min())
    if rise > MAX_RISE:
        return None
    if masks["water"].max() > 0.01 or masks["shore"].max() > 0.25 or masks["bases"].max() > 0.1:
        return None
    if masks["walkable"].min() < 0.99 or masks["forest"].mean() > 0.05 or masks["forest"].max() > 0.3:
        return None
    # Lower is better: flat, open, a little road is welcome (vehicles reach it).
    return rise + 4.0 * float(masks["forest"].mean()) - 0.5 * float(masks["road"].mean())


def plan(layout, field):
    homes = {k: np.array(v[:2]) for k, v in layout["homes_m"].items()}
    mid = (homes["red"] + homes["blue"]) / 2
    axis = (homes["blue"] - homes["red"]) / np.linalg.norm(homes["blue"] - homes["red"])

    def mirror(p):
        d = np.dot(np.array(p[:2]) - mid, axis)
        q = np.array(p[:2]) - 2 * d * axis
        return [float(q[0]), float(q[1])]

    def side(p):  # < 0 red's half, > 0 blue's
        return float(np.dot(np.array(p[:2]) - mid, axis))

    play = layout["play_area_m"]
    bounds = ((play["min"][0], play["min"][1]), (play["max"][0], play["max"][1]))
    classic = [c[:2] for c in layout["captures_m"]]
    chosen = [[], [], []]

    def far_enough(p, site):
        for s in range(3):
            for q in [classic[s]] + chosen[s]:
                gap = SAME_GAP if s == site else SITE_GAP
                if math.dist(p, q) < gap:
                    return False
        return all(math.dist(p, h) >= HOME_GAP for h in homes.values())

    def z(p):
        return round(float(field.sample(p[0], p[1])), 3)

    # A on red's half, beyond the dead centre, mirrored for C; then B on the centre line.
    scored = []
    x = bounds[0][0]
    while x < bounds[1][0]:
        y = bounds[0][1]
        while y < bounds[1][1]:
            p = [x, y]
            d = side(p)
            if -380 < d < -120:
                score = suitable(field, x, y, bounds)
                if score is not None:
                    m = mirror(p)
                    mscore = suitable(field, m[0], m[1], bounds)
                    if mscore is not None:
                        scored.append((max(score, mscore), p, m))
            y += STEP
        x += STEP
    scored.sort(key=lambda t: t[0])
    for _, p, m in scored:
        if len(chosen[0]) >= EXTRA:
            break
        if far_enough(p, 0) and far_enough(m, 2) and math.dist(p, m) >= SITE_GAP:
            chosen[0].append(p); chosen[2].append(m)
    line = []
    t = -1000.0
    while t <= 1000.0:
        p = list(mid + np.array([-axis[1], axis[0]]) * t)
        score = suitable(field, p[0], p[1], bounds)
        if score is not None:
            line.append((score, [float(p[0]), float(p[1])]))
        t += STEP / 2
    line.sort(key=lambda t: t[0])
    for _, p in line:
        if len(chosen[1]) >= EXTRA:
            break
        if far_enough(p, 1):
            chosen[1].append(p)
    out = [[[round(p[0], 2), round(p[1], 2), z(p)] for p in site] for site in chosen]
    report = []
    for s, site in enumerate(out):
        for k, p in enumerate([layout["captures_m"][s]] + site):
            report.append({"site": "ABC"[s], "candidate": k, "pos": p,
                           "red_home_m": round(math.dist(p[:2], homes["red"]), 1),
                           "blue_home_m": round(math.dist(p[:2], homes["blue"]), 1)})
    return out, report


def preview(path, layout, field, candidates):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    (x0, y0), (x1, y1) = field.bounds_m if hasattr(field.bounds_m[0], "__len__") else ((-1000, -1000), (1000, 1000))
    fig, ax = plt.subplots(figsize=(9, 9), dpi=110)
    ax.imshow(field.heights_m, origin="lower", extent=(x0, x1, y0, y1), cmap="terrain")
    for key, colour in (("water", "#1f6fd1"), ("forest", "#0b5d1e")):
        m = np.ma.masked_less(field.masks[key], 0.5)
        ax.imshow(m, origin="lower", extent=(x0, x1, y0, y1), cmap=matplotlib.colors.ListedColormap([colour]), alpha=0.45)
    for name, colour in (("red", "#d23"), ("blue", "#26d")):
        hx, hy = layout["homes_m"][name][:2]
        ax.plot(hx, hy, "s", ms=12, color=colour, mec="white")
    for s, colour in enumerate(("#ffb000", "#ffffff", "#ff5cf0")):
        for k, p in enumerate([layout["captures_m"][s]] + candidates[s]):
            ax.add_patch(plt.Circle(p[:2], RADIUS, fill=False, lw=2, color=colour))
            ax.text(p[0] + 22, p[1] + 22, f"{'ABC'[s]}{k}", color=colour, fontsize=10, weight="bold")
    p = layout["play_area_m"]
    ax.add_patch(plt.Rectangle(p["min"][:2], p["max"][0] - p["min"][0], p["max"][1] - p["min"][1], fill=False, ls="--", color="w"))
    ax.set_title("PWR capture candidates (0 = classic; C mirrors A, B on the centre line)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--write", action="store_true", help="store the result in layout.json")
    args = parser.parse_args()
    layout = json.loads(LAYOUT.read_text(encoding="utf-8-sig"))
    field = load_heightfield(TERRAIN)
    candidates, report = plan(layout, field)
    for row in report:
        print(json.dumps(row))
    if args.preview:
        preview(args.preview, layout, field, candidates)
        print("preview:", args.preview)
    if args.write:
        raw = LAYOUT.read_bytes()
        out = {}
        for k, v in layout.items():
            if k != "capture_candidates_m":
                out[k] = v
            if k == "capture_radius_m":
                out["capture_candidates_m"] = candidates
        newline = "\r\n" if b"\r\n" in raw else "\n"
        LAYOUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline=newline)
        print("wrote", LAYOUT)


if __name__ == "__main__":
    main()
