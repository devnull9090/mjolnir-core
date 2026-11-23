"""Grow forest-floor, forest-edge and open-meadow communities across PWR's playable ground.

Stock game meshes only (they resolve from the game's paks), chosen from an in-game audition
(.dream-loop/vegetation/audition-close-*.png). Plants grow in colonies, not an even scatter:
every colony centre takes one community from its zone (distance to the nearest tree) and
layered noise (dryness, flower drifts), then scatters its members around it. The editor PCG
understory graph thins the candidates and draws rotation and variant; the result bakes as
collision-free HISM groups.

The plantable ground is the shipped landscape-grass density field
(out/pwr/world-art/foliage-r2/density.r8), which already excludes roads, water, paving and
gameplay clearances. Tall plants and debris also keep clear of tree trunks, road edges and the
protected discs (player starts, vehicles, capture hills, decor rocks).

  python meadow_life.py prepare <out> [--region map|spike]
  powershell -File tools/ue/run_pwr_pcg.ps1 -Request <out>/request.json
  python meadow_life.py finalize <out>
  python meadow_life.py home <out>      (mirrored home-base shrubs only)
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from build_sweep_banks import pack_groups
from prepare_alpine_verges import ROOT, Site, read, sha256
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree

sys.path.insert(0, str(ROOT / "tools/level"))
import pcg_foliage
from foliage_bake import PAKS, mesh_info

SEED = 26112002
OWNER = "PWR_MeadowLife"
GRAPH = "/Game/MJOLNIR/PCGAuthoring/PWRField/PCG_Understory"
FIELD = ROOT / "out/pwr/world-art/foliage-r2/density.r8"
# Every plant-like instance the earlier passes saved in the level (export_pwr_plant_points.py) marks
# natural ground the grass field leaves out (base shoulders, forest floors, verges); paving carries none.
PLANT_POINTS = ROOT / "out/pwr/meadow-life/plant-points-43.f32"
MS, BIO, MA = "/Game/Megascans/3D_Plants/", "/Game/Env/Bio/", "/Game/Megascans/3D_Assets/"


def m(path):
    return path + "." + path.rsplit("/", 1)[-1]


# Cull (cm) reaches past the near grass (2026-11-21): every kind ships LODs down to a few hundred
# triangles, so distance costs instances, not triangles; leaf litter alone stays short.
# kind -> variants, cull (cm), flags, WPO disable distance (cm), scale range, tall (keeps gameplay clearance)
# flags: 2 static, 32 exact transforms; +1 casts shadow (shrubs and debris only). Flag 4 (grass
# quality tiers) splits a mesh into several components, which the shared verifier does not expect.
KINDS = {
    "windflower": ([m(MS + "WhiteWindflower/SM_WhiteWindflower_02"), m(MS + "WhiteWindflower/SM_WhiteWindflower_05")],
                   (8000, 10000), 34, 2500, (0.9, 1.35), False),
    "periwinkle": ([m(MS + "Periwinkle_tfclbger/SM_Periwinkle_Combined_A30")], (7000, 9000), 34, 2500, (0.75, 1.1), False),
    "seedweed": ([m(MS + "Willowherb_tbfpbbhr/SM_Willowherb_tbfpbbhr_Var1_lod0_Traced"),
                  m(MS + "Willowherb_tbfpbbhr/SM_Willowherb_tbfpbbhr_Var2_lod0_Traced")], (9000, 11000), 34, 3000, (0.8, 1.2), False),
    "lettuce": ([m(MS + "Prickly_Lettuce_tcfobfvr/S_Prickly_Lettuce_tcfobfvr_Var1_lod0"),
                 m(MS + "Prickly_Lettuce_tcfobfvr/S_Prickly_Lettuce_tcfobfvr_Var2_lod0")], (8000, 10000), 34, 3000, (0.55, 0.85), False),
    "burdock": ([m(MS + "Greater_Burdock_xh5pdgiqx/S_Greater_Burdock_xh5pdgiqx_Var1_lod0")], (7000, 9000), 34, 2500, (0.8, 1.1), False),
    "drygrass": ([m(MS + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var1_lod0")], (12000, 15000), 34, 3000, (0.5, 0.85), False),
    "straw": ([m(MS + "Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var15_lod0"),
               m(MS + "Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var1_lod0")], (10000, 13000), 34, 3000, (0.8, 1.2), False),
    "myricaria": ([m(MS + "Myricaria_tfbldaor/S_Myricaria_tfbldaor_Var1_lod0")], (11000, 14000), 34, 3000, (0.8, 1.2), False),
    "greentuft": ([m(BIO + "Grass/GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A")], (7000, 9000), 34, 2500, (0.8, 1.2), False),
    "sagebrush": ([m(BIO + "Plants/Sagebrush/Plants_Sagebrush_A/SM_Plants_Sagebrush_A")], (15000, 19000), 35, 4000, (0.55, 0.9), True),
    "rabbitbrush": ([m(MS + "Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var1_lod0")], (15000, 19000), 35, 4000, (0.5, 0.8), True),
    "elderberry": ([m(MS + "Elderberry_wfzobb2ia/S_Elderberry_wfzobb2ia_Var3_lod0")], (16000, 20000), 35, 4000, (0.8, 1.25), True),
    "blackberry": ([m(MS + "Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var1_lod0")], (15000, 19000), 35, 4000, (0.8, 1.3), True),
    "willow": ([m(BIO + "Shrub/Shrub_Willow_Arctic/SM_Willow_Arctic_Leaf_Cluster_A")], (15000, 19000), 35, 4000, (0.8, 1.2), True),
    "dwarfbirch": ([m(MS + "Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var3_lod0")], (11000, 14000), 34, 3000, (0.9, 1.3), False),
    "whitebirch": ([m(BIO + "Shrub/BetulaRotundifolia/Shrub_BetulaRotundifolia_B/SM_Shrub_BetulaRotundifolia_B")], (15000, 19000), 35, 4000, (0.7, 1.0), True),
    "fern": ([m(MS + "Fern/SM_Fern_01")], (10000, 13000), 34, 3000, (0.9, 1.4), False),
    "ladyfern": ([m(MS + "Lady_Fern_wdvlditia/SM_Lady_Fern_wdvlditia_01")], (8000, 10000), 34, 2500, (0.9, 1.4), False),
    "litter": ([m(MS + "DeadLeaves/SM_DeadLeaves_13")], (3000, 4000), 34, 0, (0.9, 1.5), False),
    "log": ([m(MA + "Fallen_Tree_Log_xiclaj1r/S_Fallen_Tree_Log_xiclaj1r_lod0_Var1"),
             m(MA + "Mossy_Tree_Log_rdkeg/S_Mossy_Tree_Log_rdkeg_high")], (18000, 24000), 35, 0, (0.8, 1.1), True),
    "stump": ([m(BIO + "Tree/Mossy_Wood_Stump/SM_Mossy_Wood_Stump_rgtan")], (16000, 21000), 35, 0, (0.55, 0.8), True),
    "stone": ([m(MA + "Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_01"),
               m(MA + "Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_02"),
               m(MA + "Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_04")], (18000, 24000), 35, 0, (0.6, 1.3), True),
    # Young firs: the map's own mature pine (about 25 m) scaled to 2-3 m.
    "youngfir": (["/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A.SM_PWR_MaturePine_A"], (15000, 22000), 35, 0, (0.08, 0.12), True),
    # Low, spreading arctic willow mats stand in for juniper (no juniper ships).
    "mat": ([m(BIO + "Shrub/Shrub_Willow_Arctic/SM_Willow_Arctic_Leaf_Cluster_A")], (13000, 17000), 35, 4000, (0.45, 0.65), True),
}
# Communities: members (kind, weight), member count range, spread (m), probability per member.
COMMUNITIES = {
    "fernbed": ([("fern", 4), ("ladyfern", 2), ("litter", 2), ("periwinkle", 1)], (5, 10), 2.2, 0.65),
    "thicket": ([("blackberry", 3), ("fern", 2), ("periwinkle", 1), ("litter", 1)], (3, 7), 2.2, 0.6),
    "deadwood": ([("log", 2), ("stump", 1), ("litter", 2), ("fern", 2)], (2, 4), 2.4, 0.5),
    "edgeshrub": ([("blackberry", 3), ("willow", 3), ("dwarfbirch", 2), ("whitebirch", 1),
                   ("lettuce", 1), ("drygrass", 1)], (6, 12), 2.8, 0.75),
    "dry": ([("drygrass", 5), ("straw", 3), ("myricaria", 1), ("seedweed", 1), ("sagebrush", 1)], (5, 11), 2.4, 0.6),
    "drift": ([("windflower", 6), ("periwinkle", 2), ("dwarfbirch", 1)], (8, 18), 1.7, 0.7),
    "weeds": ([("seedweed", 3), ("lettuce", 2), ("burdock", 1)], (3, 7), 1.8, 0.55),
    "scrub": ([("sagebrush", 2), ("rabbitbrush", 2), ("drygrass", 3), ("myricaria", 1)], (2, 6), 2.6, 0.5),
    "mats": ([("willow", 2), ("drygrass", 2)], (2, 5), 1.8, 0.65),
    "stones": ([("stone", 3), ("drygrass", 2), ("windflower", 1)], (2, 5), 1.6, 0.7),
}
REGIONS = {"map": None, "spike": ((-641.0, -152.0), 70.0)}


def noise(x, y, sx, sy, phase):
    a = np.sin(x / sx + phase + 1.3 * np.cos(y / (sy * 1.7) - phase))
    b = np.cos(y / sy - 0.7 * phase + 0.9 * np.sin(x / (sx * 1.4)))
    return np.clip(0.5 + 0.5 * a * b, 0.0, 1.0)


def field_weight(xy):
    import os
    source = Path(os.environ.get("MEADOW_FIELD", FIELD))
    w = np.fromfile(source, np.uint8).reshape(1009, 1009).astype(float) / 255
    rows = (1000 - xy[:, 1]) * 1008 / 2000
    cols = (xy[:, 0] + 1000) * 1008 / 2000
    return map_coordinates(w, [rows, cols], order=1, mode="constant", cval=0)


def groundcover_tree():
    xy = np.fromfile(PLANT_POINTS, "<f4").reshape(-1, 2) * [0.01, -0.01]
    return cKDTree(xy)


def plantable(xy, cover):
    """1 on the grass field or within 3 m of a saved plant instance, else the field weight."""
    w = field_weight(xy)
    near = cover.query(xy, workers=-1, distance_upper_bound=3.0)[0] < 3.0
    return np.where(near, np.maximum(w, 0.7), w)


def road_margin(site, xy):
    pts, half = [], []
    for road in site.roads:
        line = np.array(road["centreline_m"])[:, :2]
        for a, b in zip(line[:-1], line[1:]):
            n = max(2, int(np.linalg.norm(b - a) / 0.5))
            pts.append(a + (b - a) * np.linspace(0, 1, n)[:, None])
            half.append(np.full(n, road["width_m"] / 2))
    d, i = cKDTree(np.concatenate(pts)).query(xy, workers=-1)
    return d - np.concatenate(half)[i]


ROAD_ATLAS = ROOT / "out/pwr/base-approaches/roads/road-network.png"
_ATLAS = None
_ASPHALT_GAP = None


def visual_margin(site, xy):
    """Metres from the visible driving surface. Asphalt keeps its true edge (road geometry); on a dirt
    track the graded shoulder looks like bare ground, so the edge is the rut band, 4 m either side of
    the centreline (road atlas: red = road footprint, green = asphalt, blue = lateral offset +-16 m)."""
    global _ATLAS, _ASPHALT_GAP
    if _ATLAS is None:
        from PIL import Image
        from scipy.ndimage import distance_transform_edt
        with Image.open(ROAD_ATLAS) as img:
            _ATLAS = np.asarray(img.convert("RGBA"), dtype=float) / 255
        # Metres to the atlas's asphalt. The approach roads (stage_sweep_roads.py and its kin) are
        # painted as asphalt in the atlas but are not in the terrain geometry's road list, so
        # road_margin alone took them for meadow and the field and the plants grew across them
        # (the blue base's approach, shot 8 of 2026-11-22).
        _ASPHALT_GAP = distance_transform_edt(_ATLAS[:, :, 1] <= 0.5) * (2000 / len(_ATLAS))
    n = len(_ATLAS)
    coords = [(1000 - xy[:, 1]) * n / 2000 - 0.5, (xy[:, 0] + 1000) * n / 2000 - 0.5]
    red, green, blue = (map_coordinates(_ATLAS[:, :, c], coords, order=1, mode="nearest", prefilter=False) for c in range(3))
    asphalt = map_coordinates(_ASPHALT_GAP, coords, order=1, mode="nearest", prefilter=False)
    geometric = np.minimum(road_margin(site, xy), asphalt)
    dirt = (red > 0.3) & (green < 0.5 * red)
    return np.where(dirt, np.abs((blue - 0.5) * 32) - 4.0, geometric)


def protected_gap(site, xy):
    gap = np.full(len(xy), np.inf)
    for c, r in site.protected:
        gap = np.minimum(gap, np.linalg.norm(xy - c, axis=1) - r)
    return gap


# Low shrubs inside the two team home discs, grown on one side and reflected onto the other so both
# teams get the same cover. Kept below about 1 m and collision-free (the bake has no collision).
VEHICLE_ROOM = 4.0  # metres kept clear around a vehicle spawn for low home shrubs
LANDING_ROOM = 8.0  # metres kept clear around an insertion landing centre
HOME_KINDS = {"blackberry": (0.6, 0.85), "dwarfbirch": (0.9, 1.15), "sagebrush": (0.5, 0.75), "willow": (0.5, 0.7)}


def home_discs():
    """(home_red, home_blue, skip): skip = the home discs and the wide vehicle_* and insertion_* clearances
    (the natural ground inside a home disc lies in them; low collision-free shrubs block neither a vehicle
    nor a landing, and home_ok keeps VEHICLE_ROOM / LANDING_ROOM around their centres)."""
    from prepare_alpine_verges import DISCS
    named = [(n, np.array(c, float), float(r)) for n, c, r in read(DISCS)["clearance_discs"]]
    by = {n: (c, r) for n, c, r in named}
    skip = [(c, r) for n, c, r in named if n.startswith(("home_", "vehicle_", "insertion_"))]
    return by["home_red"], by["home_blue"], skip


def reflect(xy, a, b):
    """Reflect points across the perpendicular bisector of home centres a and b."""
    mid, u = (a + b) / 2, (b - a) / np.linalg.norm(b - a)
    return xy - 2 * ((xy - mid) @ u)[:, None] * u


def home_ok(site, cover, xy, homes, skip):
    """Masks for a home shrub: inside a home disc, on natural ground (within 1.5 m of a plant the earlier
    passes saved: the base pad itself carries none), clear of every protected disc except `skip` (the home
    discs and the wide vehicle clearances; the vehicle markers' own 12 m discs still apply)."""
    inside = np.zeros(len(xy), bool)
    for c, r in homes:
        inside |= np.linalg.norm(xy - c, axis=1) < r - 3
    gap = np.full(len(xy), np.inf)
    vehicles = [sc for sc, sr in skip if sr < 30]
    for sc, sr in skip:
        if 30 <= sr < 50:  # an insertion landing zone: keep its centre open
            gap = np.minimum(gap, np.linalg.norm(xy - sc, axis=1) - LANDING_ROOM)
    for c, r in site.protected:
        if any(np.allclose(c, sc) and r == sr for sc, sr in skip):
            continue
        if any(np.allclose(c, v, atol=0.5) for v in vehicles):
            r = VEHICLE_ROOM  # a vehicle spawn's own marker: room for the vehicle, not its full clearance
        gap = np.minimum(gap, np.linalg.norm(xy - c, axis=1) - r)
    ok = inside & (gap > 1.0) & (cover.query(xy, workers=-1, distance_upper_bound=1.5)[0] < 1.5)
    ok &= site.trunks.query(xy, workers=-1)[0] > 2.2
    ok &= visual_margin(site, xy) > 2.5
    for layer in ("water", "shore"):
        ok &= site.ground.sample_mask(layer, *xy.T, bounds_error=False) < 0.006
    sx = site.height(xy + [0.5, 0]) - site.height(xy - [0.5, 0])
    sy = site.height(xy + [0, 0.5]) - site.height(xy - [0, 0.5])
    return ok & (1 / np.sqrt(1 + sx ** 2 + sy ** 2) > 0.85)


def home_shrubs(site, cover, out):
    rng = np.random.default_rng(SEED + 11)
    red, blue, skip = home_discs()
    (c, r) = red
    centres = c + rng.uniform(-r, r, (1500, 2))
    centres = centres[np.linalg.norm(centres - c, axis=1) < r - 4]
    kinds = list(HOME_KINDS)
    xy, kind = [], []
    for k in centres:
        group = kinds[rng.integers(len(kinds))]
        for _ in range(rng.integers(2, 5)):
            xy.append(k + rng.normal(size=2) * 1.4)
            kind.append(group)
    xy, kind = np.array(xy), np.array(kind)
    mirror = reflect(xy, red[0], blue[0])
    keep = home_ok(site, cover, xy, [red, blue], skip) & home_ok(site, cover, mirror, [red, blue], skip)
    # one shrub per 1.6 m: drop crowded points (a pair is dropped together)
    tree, taken = cKDTree(xy[keep]), np.zeros(int(keep.sum()), bool)
    idx = np.flatnonzero(keep)
    for i in range(len(idx)):
        if not any(taken[j] for j in tree.query_ball_point(xy[idx[i]], 1.6) if j != i):
            taken[i] = True
    idx = idx[taken]
    rows = []
    for i in idx:
        yaw = rng.uniform(0, 360)
        s = float(rng.uniform(*HOME_KINDS[kind[i]]))
        for p, a in ((xy[i], yaw), (mirror[i], 180 - yaw)):
            z = float(site.height(p[None])[0])
            rows.append(dict(kind=str(kind[i]), position=[float(p[0]), float(p[1]), z], yaw=a % 360, scale=s,
                             variant=float(rng.uniform())))
    (out / "home.json").write_text(json.dumps({"pairs": len(idx), "shrubs": rows}, indent=1))
    print(len(idx), "mirrored home shrub pairs")


def candidates(out, region):
    rng = np.random.default_rng(SEED)
    site = Site()
    if REGIONS[region]:
        (cx, cy), radius = REGIONS[region]
        lo, hi = np.array([cx - radius, cy - radius]), np.array([cx + radius, cy + radius])
    else:
        lo, hi = np.array([-1000.0, -1000.0]), np.array([1000.0, 1000.0])
    cover = groundcover_tree()
    step = 5.0
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0], step), np.arange(lo[1], hi[1], step))
    centres = np.column_stack((gx.ravel(), gy.ravel())) + rng.uniform(-step / 2, step / 2, (gx.size, 2))
    if REGIONS[region]:
        centres = centres[np.hypot(*(centres - [cx, cy]).T) < radius]
    centres = centres[(np.abs(centres) < 995).all(axis=1)]
    centres = centres[plantable(centres, cover) > 0.35]
    d = site.trunks.query(centres, workers=-1)[0]
    x, y = centres.T
    dry = noise(x, y, 41, 57, 0.4)
    bloom = noise(x + 300, y - 120, 17, 23, 1.9)
    patch = noise(x - 150, y + 260, 7, 9, 3.1)
    forest, edge = d < 9, (d >= 9) & (d < 22)
    community = np.select(
        [forest & (patch > 0.75), forest & (patch < 0.12), forest & (bloom > 0.55), forest,
         edge & (patch > 0.45), edge & (bloom > 0.6), edge,
         (dry > 0.68) & (patch > 0.6), bloom > 0.64, dry > 0.56, patch > 0.82, patch < 0.06,
         patch > 0.70, patch < 0.22],
        ["thicket", "deadwood", "fernbed", "fernbed",
         "edgeshrub", "drift", "dry",
         "scrub", "drift", "dry", "stones", "mats",
         "weeds", "dry"], default="none")
    use = community != "none"
    centres, community = centres[use], community[use]
    xy, kind, prob = [], [], []
    for c, name in zip(centres, community):
        members, (n0, n1), spread, p = COMMUNITIES[name]
        kinds, weights = zip(*members)
        weights = np.array(weights, float) / sum(weights)
        for _ in range(rng.integers(n0, n1 + 1)):
            k = kinds[rng.choice(len(kinds), p=weights)]
            xy.append(c + rng.normal(size=2) * spread * (0.4 if KINDS[k][5] else 1.0))
            kind.append(k)
            prob.append(p)
    xy, kind, prob = np.array(xy), np.array(kind), np.array(prob)
    tall = np.array([KINDS[k][5] for k in kind])
    keep = (np.abs(xy) < 995).all(axis=1)
    keep[keep] = plantable(xy[keep], cover) > 0.2
    keep &= site.trunks.query(xy, workers=-1)[0] > np.where(tall, 2.2, 0.9)
    keep &= visual_margin(site, xy) > np.where(np.isin(kind, ["log", "stump"]), 7.0, np.where(tall, 2.5, 0.3))
    keep &= ~tall | (protected_gap(site, xy) > 1.5)
    for layer in ("water", "shore"):
        keep &= site.ground.sample_mask(layer, *xy.T, bounds_error=False) < 0.006
    xy, kind, prob = xy[keep], kind[keep], prob[keep]
    z = site.height(xy)
    sx = site.height(xy + [0.5, 0]) - site.height(xy - [0.5, 0])
    sy = site.height(xy + [0, 0.5]) - site.height(xy - [0, 0.5])
    normal = np.column_stack((-sx, -sy, np.ones(len(z))))
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    ok = normal[:, 2] > 0.8
    # The heightfield is stale where the terrain was reshaped after it (the north headwater lake):
    # plants seated on it hung in the air over the water. The map's baked Flux states carry the
    # ground and water as shipped (tools/level/flux_ground.py); PWR_LEVEL_JSON names the map.
    shipped_map = os.environ.get("PWR_LEVEL_JSON")
    dropped = {}
    if shipped_map:
        import flux_ground
        stale, under = flux_ground.Shipped(Path(shipped_map).parent).check(xy[:, 0] * 100, -xy[:, 1] * 100, z * 100)
        dropped = dict(off_shipped_ground=int((ok & stale).sum()), under_water=int((ok & under & ~stale).sum()))
        ok &= ~stale & ~under
    xy, kind, prob, z, normal = xy[ok], kind[ok], prob[ok], z[ok], normal[ok]
    pts = [dict(id=i, position=[float(xy[i, 0]), float(xy[i, 1]), round(float(z[i]), 6)],
                normal=normal[i].round(7).tolist(), density=float(prob[i]), biome_mask=1, kind=str(kind[i]))
           for i in range(len(xy))]
    src = out / "meadow.candidates.json"
    src.write_text(json.dumps({"schema": 1, "align_to_normal": True, "points": pts}, separators=(",", ":")))
    jobs = [dict(input=str(src), output=str(out / f"meadow{s}.pcg.json"), seed=SEED, scale_min=1.0, scale_max=1.0,
                 graph=GRAPH + s) for s in ("", "_repeat")]
    (out / "request.json").write_text(json.dumps({"jobs": jobs}, indent=2))
    counts = {k: int((kind == k).sum()) for k in KINDS}
    comm = {c: int((community == c).sum()) for c in COMMUNITIES}
    (out / "prepare.json").write_text(json.dumps(dict(region=region, seed=SEED, colonies=len(centres), candidates=len(pts),
                                                      by_kind=counts, by_community=comm, shipped_ground=dropped), indent=2))
    print(len(centres), "colonies,", len(pts), "candidates", counts)
    home_shrubs(site, cover, out)


def finalize(out):
    source, first, repeat = (out / s for s in ("meadow.candidates.json", "meadow.pcg.json", "meadow_repeat.pcg.json"))
    proof = pcg_foliage.compare(source, first, repeat)
    points = read(source)["points"]
    selected = sorted(read(first)["points"], key=lambda v: v["id"])
    rng = np.random.default_rng(SEED + 7)
    rows = {}
    for p in selected:
        kind = points[p["id"]]["kind"]
        variants, cull, flags, wpo, (s0, s1), tall = KINDS[kind]
        mesh = variants[min(int(p["asset_draw"] * len(variants)), len(variants) - 1)]
        s = float(rng.uniform(s0, s1))
        pos = list(p["position_cm"])
        pos[2] -= 3.0 if kind in ("log", "stump") else 1.5  # seat roots and debris into the soil
        rows.setdefault(mesh, (kind, []))[1].append([*pos, *p["rotation_xyzw"], s, s, s])
    home = out / "home.json"
    edges = out / "edges.json"   # base_edges.py: the meadow grown over the bases' bed rims and terrace outline
    extra = [h for f in (home, edges) if f.exists() for h in read(f)["shrubs"]]
    for h in extra:
        variants = KINDS[h["kind"]][0]
        mesh = variants[min(int(h["variant"] * len(variants)), len(variants) - 1)]
        x, y, z = h["position"]
        t = np.radians(h["yaw"]) / 2
        s = h["scale"]
        rows.setdefault(mesh, (h["kind"], []))[1].append([x * 100, -y * 100, z * 100 - 1.5, 0, 0, np.sin(t), np.cos(t), s, s, s])
    # Last gate before the bake, for every source (colonies, home shrubs, base edges): nothing is
    # planted off the ground the map ships or under its water (tools/level/flux_ground.py).
    shipped_map = os.environ.get("PWR_LEVEL_JSON")
    removed = dict(off_shipped_ground=0, under_water=0)
    if shipped_map:
        import flux_ground
        shipped = flux_ground.Shipped(Path(shipped_map).parent)
        for mesh, (kind, data) in list(rows.items()):
            a = np.asarray(data, float)
            lift = 3.0 if kind in ("log", "stump") else 1.5      # undo the seating above
            stale, under = shipped.check(a[:, 0], a[:, 1], a[:, 2] + lift)
            removed["off_shipped_ground"] += int(stale.sum())
            removed["under_water"] += int((under & ~stale).sum())
            keep = ~stale & ~under
            if keep.any():
                rows[mesh] = (kind, a[keep].tolist())
            else:
                del rows[mesh]
    # And nothing on a road, by the same margins candidates() keeps, measured again here so a set
    # prepared before visual_margin knew the approach roads' asphalt can be finalized without
    # re-running its PCG pass (rows are UE cm: site x = x / 100, site y = -y / 100).
    site = Site()
    removed["on_road"] = 0
    for mesh, (kind, data) in list(rows.items()):
        a = np.asarray(data, float)
        clear = 7.0 if kind in ("log", "stump") else (2.5 if KINDS[kind][5] else 0.3)
        keep = visual_margin(site, np.column_stack((a[:, 0] / 100, -a[:, 1] / 100))) > clear
        removed["on_road"] += int((~keep).sum())
        if keep.any():
            rows[mesh] = (kind, a[keep].tolist())
        else:
            del rows[mesh]
    cli = str(ROOT / "target/release/mjolnir.exe")
    entries = []
    for mesh, (kind, data) in sorted(rows.items()):
        _, cull, flags, wpo, _, _ = KINDS[kind]
        # Map-owned meshes (/Game/MJOLNIR) are real assets in the editor project: no stand-in needed.
        info = (dict(origin=[0, 0, 0], extent=[100, 100, 100], slots=["Slot0"]) if mesh.startswith("/Game/MJOLNIR/")
                else mesh_info(cli, PAKS, mesh))
        definition = dict(key=f"{kind}{KINDS[kind][0].index(mesh) + 1}", mesh=mesh, cull=list(cull), flags=flags, wpo=wpo,
                          material=None, origin=info["origin"], extent=info["extent"], standin_slots=info["slots"])
        entries.append((definition, np.asarray(data, dtype="<f4")))
    pack_groups(out, OWNER, entries)
    survey = dict(actor=OWNER, seed=SEED, graph=read(first)["graph"], deterministic_repeat=proof,
                  editor_receipt=read(out / "request.receipt.json"), source_count=len(points), count=len(selected),
                  home_shrubs=len(read(home)["shrubs"]) if home.exists() else 0,
                  edge_plants=len(read(edges)["shrubs"]) if edges.exists() else 0, shipped_ground=removed,
                  groups={d["key"]: dict(count=len(r), mesh=d["mesh"], cull=d["cull"]) for d, r in entries},
                  verges_sha256=sha256(out / "verges.json"))
    (out / "survey.json").write_text(json.dumps(survey, indent=2))
    print(survey["count"], "planted in", len(entries), "groups:", {d["key"]: len(r) for d, r in entries})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["prepare", "home", "finalize"])
    ap.add_argument("out", type=Path)
    ap.add_argument("--region", default="map", choices=sorted(REGIONS))
    a = ap.parse_args()
    o = a.out.resolve()
    o.mkdir(parents=True, exist_ok=True)
    if a.action == "prepare":
        candidates(o, a.region)
    elif a.action == "home":  # (re)grow only the mirrored home shrubs into an existing prepare
        home_shrubs(Site(), groundcover_tree(), o)
    else:
        finalize(o)
