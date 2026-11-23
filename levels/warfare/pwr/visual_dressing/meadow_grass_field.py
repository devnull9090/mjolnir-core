"""Extend PWR's landscape-grass density field to all natural ground, with patchy variation.

The shipped field (out/pwr/world-art/foliage-r2/density.r8, 1009x1009 over the 2 km map) leaves the
base shoulders and the forest floors beside roads at zero, so the GPU grass never reaches them and
only sparse baked instances grow there. This keeps the shipped weights and adds ground within 3 m of a
saved plant instance (meadow_life.PLANT_POINTS), clear of roads, water and shore, thinner under tree
crowns. Broad noise then varies the density so a meadow does not read as one even carpet.

Natural meadow with no density gets FILL_MIN, patchy, so grass reaches the open ground around the
bases; PWR_LEVEL_JSON names the level whose base terraces stay clear.

  PWR_LEVEL_JSON=<level.json> python meadow_grass_field.py <out-dir>  -> density.png, density.r8, field.json
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from meadow_life import FIELD, ROOT, groundcover_tree, noise, visual_margin
from PIL import Image
from prepare_alpine_verges import Site, sha256

ROAD_CLEAR = 2.5  # metres from the visible driving surface
FILL_MIN = 0.42   # least density on natural meadow ground
SLOPE_MAX = 35.0  # degrees; steeper ground keeps its rock and scree
CLEAR_CORE = 12.0  # metres of bare ground kept round a capture point or the warmup centre
CLEAR_FADE = 4.0   # metres over which grass fades in past that core
CLEAR_THIN = 0.55  # share of FILL_MIN at the core's edge, rising to full at the clearing's rim


def base_terraces():
    """Union of the bases' ground decor outlines (site metres), or None without a level.json."""
    import os
    level = os.environ.get("PWR_LEVEL_JSON")
    if not level:
        return None
    import base_edges as be
    from shapely.ops import unary_union
    lvl = json.loads(Path(level).read_text())
    polys = []
    for d in be.base_decor(lvl):
        name = d["mesh"].split(".")[0].rsplit("/", 1)[-1]
        for tris in be.glb_sections(ROOT / "out/pwr/base-edges/meshes" / f"{name}.glb").values():
            polys += be.polys(be.to_site(tris, d))
    return unary_union(polys).buffer(0.05).buffer(-0.05)

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
site = Site()
w = np.fromfile(FIELD, np.uint8).reshape(1009, 1009).astype(float) / 255
rows, cols = np.mgrid[0:1009, 0:1009]
x = cols * 2000 / 1008 - 1000
y = 1000 - rows * 2000 / 1008
xy = np.column_stack((x.ravel(), y.ravel()))
inside = (np.abs(xy) < 999).all(axis=1)
near = np.zeros(len(xy), bool)
cover = groundcover_tree()
near[inside] = cover.query(xy[inside], workers=-1, distance_upper_bound=3.0)[0] < 3.0
ok = near.copy()
ok[near] &= visual_margin(site, xy[near]) > 0.3
for layer in ("water", "shore"):
    ok[ok] &= site.ground.sample_mask(layer, *xy[ok].T, bounds_error=False) < 0.006
gap = site.trunks.query(xy, workers=-1)[0]
shade = np.exp(-(gap / 7.0) ** 2)
# Forest floor: ground under and between trunks is natural even where no earlier pass planted;
# it gets a lighter carpet (the forest communities add ferns and litter on top).
forest = inside & (gap < 12)
forest[forest] &= visual_margin(site, xy[forest]) > 0.3
for layer in ("water", "shore"):
    forest[forest] &= site.ground.sample_mask(layer, *xy[forest].T, bounds_error=False) < 0.006
added = np.where(ok, 0.85 * (1 - 0.6 * shade), 0.0)
added = np.maximum(added, np.where(forest, 0.45, 0.0))
# Every natural meadow texel gets at least FILL_MIN: zero density left bare green expanses that no grass,
# near or far, could ever reach. Natural = clear of roads, water, shore, steep slopes and the base
# terraces (their exact outlines from the cooked base meshes, base_edges.py; the bases mask is far wider).
fill = inside & ~forest
fill[fill] &= visual_margin(site, xy[fill]) > 0.3
for layer in ("water", "shore"):
    fill[fill] &= site.ground.sample_mask(layer, *xy[fill].T, bounds_error=False) < 0.006
h = np.asarray(site.ground.sample(xy[:, 0], xy[:, 1], bounds_error=False), float).reshape(1009, 1009)
gy, gx = np.gradient(h, 2000 / 1008)
fill &= (np.degrees(np.arctan(np.hypot(gx, gy))) < SLOPE_MAX).ravel()
terraces = base_terraces()
if terraces is not None:
    import shapely
    shapely.prepare(terraces)
    fill[fill] &= ~shapely.contains_xy(terraces.buffer(1.0), xy[fill, 0], xy[fill, 1])
# Gameplay clearings (capture zones, the warmup ground) keep a bare core where the objective sits and
# a thinner carpet out to their rim: a 45 m disc of zero grass read as a mown lawn. Low grass hides no
# one; the discs still keep trees and baked plants out (meadow_life, forest stands).
from prepare_alpine_verges import DISCS
clearing = np.ones(len(xy))
for name, c, r in json.loads(Path(DISCS).read_text())["clearance_discs"]:
    if name.startswith(("capture", "warmup")):
        d = np.hypot(xy[:, 0] - c[0], xy[:, 1] - c[1])
        core = min(CLEAR_CORE, r)
        thin = np.where(d < r, CLEAR_THIN + (1 - CLEAR_THIN) * np.clip((d - core) / (r - core), 0, 1), 1.0)
        thin *= np.clip((d - core) / CLEAR_FADE, 0, 1)
        clearing = np.minimum(clearing, thin)
fill &= clearing > 0
added = np.maximum(added, np.where(fill, FILL_MIN * clearing * (1 - 0.5 * shade), 0.0)).reshape(1009, 1009)
base = np.maximum(w, added)
patch = noise(x, y, 23, 31, 2.2) * 0.6 + noise(x, y, 7, 9, 0.9) * 0.4
field = np.clip(base * (0.55 + 0.6 * patch), 0, 1)
field[base == 0] = 0
# Keep the driving surface clean: a field texel is about 2 m and the grass interpolates between
# vertices, so a vertex needs 2.5 m of margin to put no blades on the track; fade in over the next 1.5 m.
live = (field > 0).ravel()
margin = np.full(len(xy), np.inf)
margin[live] = visual_margin(site, xy[live])
field *= np.clip((margin - ROAD_CLEAR) / 1.5, 0, 1).reshape(1009, 1009)
# No grass on the bases' paved ground. The landscape fades its natural layers out by the bases
# mask (tools/level/alpine_ecology.py: available = 1 - smooth(.05, .65, bases)), so past the
# terrace meshes the ground still reads as paving; the FILL_MIN carpet put tufts across it
# (the blue base's apron, 2026-11-22). The grass follows the same fade as the ground.
paved = np.clip((site.ground.sample_mask("bases", *xy.T, bounds_error=False).reshape(1009, 1009) - 0.05) / 0.6, 0, 1)
field *= 1 - paved * paved * (3 - 2 * paved)
# No grass under the water the map ships (tools/level/flux_ground.py): the masks above come from
# the heightfield, which does not know a lake carved after it.
shipped_map = os.environ.get("PWR_LEVEL_JSON")
if shipped_map:
    sys.path.insert(0, str(ROOT / "tools/level"))
    import flux_ground
    _, under = flux_ground.Shipped(Path(shipped_map).parent).check(xy[:, 0] * 100, -xy[:, 1] * 100, np.zeros(len(xy)), wet=30.0)
    field[under.reshape(1009, 1009)] = 0
weights = np.rint(255 * field).astype(np.uint8)
(out / "density.r8").write_bytes(weights.tobytes())
Image.fromarray(weights).convert("RGBA").save(out / "density.png")
info = dict(source=str(FIELD), source_sha256=sha256(FIELD), nonzero_before=int((w > 0).sum()),
            nonzero_after=int((weights > 0).sum()), added_vertices=int(((w == 0) & (added > 0)).sum()),
            mean_weight=float(field[field > 0].mean()), road_clear_m=ROAD_CLEAR, png_sha256=sha256(out / "density.png"))
info.update(fill_min=FILL_MIN, clear_core_m=CLEAR_CORE, clear_thin=CLEAR_THIN, slope_max_deg=SLOPE_MAX, filled_texels=int(fill.sum()),
            base_terraces_m2=round(terraces.area) if terraces is not None else None)
(out / "field.json").write_text(json.dumps(info, indent=1))
print(json.dumps(info))
