"""CE scenery in B30's own assets: boulders, trees, shrubs and plants.

A converted map's scenery (staging/placement.json, kind scenery) is baked
into its terrain mesh as CE drew it: a boulder of 84 triangles, a tree of
crossed cards. This writes, for the natural ones, B30's meshes in their
place (decor entries, sized to the CE model's reach so the Blam collision,
which stays CE's, still matches what is seen) and the CE slots to hide.

    python tools/level/scenery_swap.py recipes <placements.csv> <bounds.json> <out.json>
    python tools/level/scenery_swap.py swap <scene dir> <spec.json> <recipes.json> <bounds.json> <out.json> [--rocks beach|desert]

`recipes`: B30's Maned Kuenovo trees from its World Partition cells
(ue-asset's placements_csv example with the matrix columns, filtered to
"kuenovo") and their parts' bounds (`mjolnir mesh list --filter Kuenovo`):
for each variant the most isolated tree, as its parts' offsets from the
trunk and its height, so a tree can be rebuilt at any spot, yaw and size.

`swap` writes { "decor": [...], "hide": [slot materials...], "count": n,
"effects": {...} } for upgrade_ce_map.py's assemble stage, which appends the
decor, points the hidden slots at M_CE_Hidden and sets the level's effects
(MJOLNIRLevelLoader Effects): with --foliage, the game's ambient life
placed from the map's own scatter (butterflies over the grass, gulls and
surf along the shore, wind along the cliff lips) and leaves falling from
the swapped trees.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import sys

HIDDEN = "/Game/MJOLNIR/CETrial/M_CE_Hidden.M_CE_Hidden"
ULU = "/Game/Env/Bio/Rock/Uluwatu/"
DESERT = "/Game/Env/Bio/Rock/Desert/"
PLANTS = "/Game/Megascans/3D_Plants/"

# Rock meshes by kind of map (their bounds from tools/level/data/
# b30_scenery_bounds.json, `mjolnir mesh list`): B30's beach rocks (the
# cliffs' cladding), or the desert set for a canyon (Blood Gulch).
ROCKS = {
    "beach": [(ULU + "Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A", None),
              (ULU + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B", None),
              (ULU + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C", None)],
    "desert": [(DESERT + "Rock_Desert_Boulder_A/SM_Rock_Desert_Boulder_A", None),
               (DESERT + "Rock_Desert_Boulder_B/SM_Rock_Desert_Boulder_B", None),
               (DESERT + "Rock_Desert_Boulder_C/SM_Rock_Desert_Boulder_C", None)],
}
# The biggest CE boulders (granite gigantic, 10 m and more) as B30's cliff
# rock.
BIG_ROCK = ULU + "Rock_Uluwatu_Cliff_B/SM_Rock_Uluwatu_Cliff_B"
SHRUBS = [PLANTS + "Downy_Willow_wknlfiuqx/Custom_Combinations/SM_Downy_Willow_Combined_A",
          PLANTS + "Downy_Willow_wknlfiuqx/Custom_Combinations/SM_Downy_Willow_Combined_B"]
FERNS = [PLANTS + f"Fern/SM_Fern_0{i}" for i in (1, 2, 3, 4, 5, 6)]
BROADLEAF = [PLANTS + f"Taro/SM_Taro_{i:02d}" for i in (2, 3, 6, 7, 8, 10)]

# CE scenery (substring of the tag path) -> what stands in for it. Tree
# variants by the CE tree's character; the rest by kind.
RULES = [
    ("tree_leafydense_doublewide", ("tree", ["Double_A", "Cluster_A"])),
    ("tree_leafy_doublewide", ("tree", ["Double_A", "YoungDual_A"])),
    ("tree_leafydense", ("tree", ["Lrg_A", "Lrg_B", "Lrg_D"])),
    ("tree_leafy", ("tree", ["Lrg_A", "Lrg_B", "Lrg_C", "Lrg_D"])),
    ("tree_desert_whitebark", ("tree", ["TwistedThick_A", "TwistedThick_B"])),
    ("tree_desert_dead", ("tree", ["TwistedLean_A"])),
    ("boulder_granite_gigantic", ("bigrock", None)),
    ("boulder", ("rock", None)),
    ("rock", ("rock", None)),
    ("shrub", ("mesh", SHRUBS)),
    ("plant fern", ("mesh", FERNS)),
    ("plant_broadleaf", ("mesh", BROADLEAF)),
]


def object_path(package):
    return package + "." + package.rsplit("/", 1)[-1]


def pick(options, key):
    h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    return options[h % len(options)]


def rotator(m):
    """UE rotator (pitch, yaw, roll, degrees) of a row-vector 3 x 3 with
    scale: FMatrix::Rotator."""
    rows = [[v / max(math.sqrt(sum(c * c for c in r)), 1e-9) for v in r] for r in m]
    x, y, z = rows
    pitch = math.atan2(x[2], math.sqrt(x[0] ** 2 + x[1] ** 2))
    yaw = math.atan2(x[1], x[0])
    sy = (-math.sin(yaw), math.cos(yaw), 0.0)
    roll = math.atan2(sum(a * b for a, b in zip(z, sy)), sum(a * b for a, b in zip(y, sy)))
    return math.degrees(pitch), math.degrees(yaw), math.degrees(roll)


LEAVES = "/Game/Env/Bio/Tree/ManedKuenovo/SharedAssets/SM_Tree_Maned_Kuenovo_branch_01"


def mat3(r):
    return [[float(r[f"m{i}{j}"]) for j in range(3)] for i in range(3)]


def mmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def vmul(v, m):
    return [sum(v[k] * m[k][j] for k in range(3)) for j in range(3)]


def minv(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def foliage_pose(m):
    """A row-vector 3 x 3 (rotation and scale) as MJF3's yaw (degrees), scale
    and ground normal (x, y): MJOLNIRLevelLoader's Foliage.rotation turns
    local up to the normal after the yaw. A cluster facing down is mirrored
    up (the normal keeps z positive)."""
    rows = [[v / max(math.sqrt(sum(c * c for c in r)), 1e-9) for v in r] for r in m]
    scale = sum(math.sqrt(sum(c * c for c in r)) for r in m) / 3.0
    n = rows[2] if rows[2][2] >= 0 else [-v for v in rows[2]]
    s2 = n[0] ** 2 + n[1] ** 2
    x = rows[0]
    if s2 > 1e-8:
        # Undo the tilt (about (-ny, nx, 0) by acos(nz)) on the local x axis.
        ang = -math.acos(min(1.0, n[2]))
        k = [-n[1] / math.sqrt(s2), n[0] / math.sqrt(s2), 0.0]
        c, sn = math.cos(ang), math.sin(ang)
        kx = [k[1] * x[2] - k[2] * x[1], k[2] * x[0] - k[0] * x[2], k[0] * x[1] - k[1] * x[0]]
        kd = sum(p * q for p, q in zip(k, x))
        x = [x[i] * c + kx[i] * sn + k[i] * kd * (1 - c) for i in range(3)]
    return math.degrees(math.atan2(x[1], x[0])), scale, n[0], n[1]


def recipes(a):
    bounds = {m["path"].split(".")[0]: m for m in json.load(open(a.bounds, encoding="utf-8"))}
    every = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    rows = [r for r in every if "Tree_Maned_Kuenovo_" in r["mesh"] and "/Meshes/" in r["mesh"]]
    leaf_rows = [r for r in every if r["mesh"] == LEAVES]
    by_variant = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in rows:
        variant = r["mesh"].split("Tree_Maned_Kuenovo_")[1].split("/")[0]
        key = tuple(round(float(r[k]), 3) for k in ("m00", "m01", "m02", "m10", "m11", "m12", "m20", "m21", "m22"))
        by_variant[variant][r["mesh"]].add((float(r["x"]), float(r["y"]), float(r["z"]), key))
    out = {}
    for variant, parts in sorted(by_variant.items()):
        trunks = [m for m in parts if m.endswith("_Trunk")] or [m for m in parts if "_Trunk" in m]
        if not trunks:
            continue
        trunk_mesh = trunks[0]
        trunk_list = sorted(parts[trunk_mesh])
        # The most isolated trunk: no other tree's parts mixed into its own.
        def isolation(t):
            return min((math.hypot(t[0] - o[0], t[1] - o[1]) for o in trunk_list if o != t), default=1e9)
        t = max(trunk_list, key=isolation)
        tx, ty, tz, key = t
        m = [list(key[0:3]), list(key[3:6]), list(key[6:9])]
        scale = math.sqrt(sum(v * v for v in m[0]))
        pitch, yaw, roll = rotator(m)
        recipe = []
        top = 0.0
        for mesh, inst in parts.items():
            same = [p for p in inst if p[3] == key]
            if not same:
                continue
            p = min(same, key=lambda q: math.hypot(q[0] - tx, q[1] - ty))
            if math.hypot(p[0] - tx, p[1] - ty) > 3000:
                continue
            # The offset in the tree's own frame (yaw removed, scale removed).
            dx, dy, dz = p[0] - tx, p[1] - ty, p[2] - tz
            c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
            off = [(dx * c - dy * s) / scale, (dx * s + dy * c) / scale, dz / scale]
            recipe.append({"mesh": mesh, "off": [round(v, 1) for v in off]})
            b = bounds.get(mesh)
            if b:
                top = max(top, off[2] + b["max"][2])
        # Its leaf clusters (SharedAssets, placed beside the tree's own
        # parts, not in them): within the canopy's reach, as offsets and
        # 3 x 3s relative to the trunk's frame.
        inv = minv(m)
        leaves = []
        for r in leaf_rows:
            lx, ly, lz = float(r["x"]), float(r["y"]), float(r["z"])
            if math.hypot(lx - tx, ly - ty) > 1600 or lz < tz:
                continue
            leaves.append({"off": [round(v, 1) for v in vmul([lx - tx, ly - ty, lz - tz], inv)],
                           "m": [[round(v, 5) for v in row] for row in mmul(mat3(r), inv)]})
        out[variant] = {"parts": recipe, "pitch": round(pitch, 2), "roll": round(roll, 2),
                        "height": round(top, 1), "isolation": round(isolation(t)), "leaves": leaves}
        print(f"{variant}: {len(recipe)} parts, {len(leaves)} leaf clusters, {top / 100:.1f} m tall "
              f"(scale 1), {isolation(t) / 100:.0f} m from the next")
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)


def model_shaders(path):
    """A CE model's material (shader) names, lower case."""
    try:
        return [m.get("name", "").lower() for m in json.load(open(path, encoding="utf-8")).get("materials", [])]
    except (OSError, ValueError):
        return []


def model_box(path, cache={}):
    """A CE model's bounds (glTF metres, y up) as UE cm: (x, y, z extents),
    (x, y, z centre)."""
    if path not in cache:
        doc = json.load(open(path, encoding="utf-8"))
        lo, hi = [1e9] * 3, [-1e9] * 3
        for mesh in doc["meshes"]:
            for prim in mesh["primitives"]:
                acc = doc["accessors"][prim["attributes"]["POSITION"]]
                lo = [min(a, b) for a, b in zip(lo, acc["min"])]
                hi = [max(a, b) for a, b in zip(hi, acc["max"])]
        # glTF (x, y up, z) -> UE (x, -z, y) in cm.
        ext = [(hi[0] - lo[0]) * 100, (hi[2] - lo[2]) * 100, (hi[1] - lo[1]) * 100]
        cen = [(hi[0] + lo[0]) * 50, -(hi[2] + lo[2]) * 50, (hi[1] + lo[1]) * 50]
        base = lo[1] * 100
        cache[path] = (ext, cen, base)
    return cache[path]


FX = "/Game/FX/Library/Environment/PNW/"
EFFECTS = {
    "butterflies": FX + "Creatures/Insects/Butterfly/NS_Creature_ButterflySwarm_01",
    "gulls": FX + "Creatures/Birds/Gull/NS_GullFlyCircle",
    "surf": FX + "Liquids/Splashes/SmallWaveSplash/NS_PNW_SmallWaveSplash_01",
    "wind": FX + "Atmospherics/SandBlowing/NS_PNW_WindAlongCliffs",
    "leaves": FX + "Plants/Trees/FallingLeaves/NS_FallingLeaves_Banyan_Lp_01",
    "dust": FX + "Atmospherics/DustMotes/NS_DustMotes_CameraAttached",
}


def foliage_points(json_path, bin_path):
    """{rule: [(x, y, z), ...]} from scatter_foliage's files (MJF3)."""
    import struct
    groups = json.load(open(json_path, encoding="utf-8"))["groups"]
    raw = open(bin_path, "rb").read()
    if raw[:4] != b"MJF3":
        return {}
    _, n = struct.unpack_from("<II", raw, 4)
    pos, out = 12, collections.defaultdict(list)
    for g in range(n):
        (count,) = struct.unpack_from("<I", raw, pos)
        pos += 4
        rule = groups[g].get("rule", "?")
        for _ in range(count):
            x, y, z = struct.unpack_from("<fff", raw, pos)
            out[rule].append((x, y, z))
            pos += 19
    return out


def spaced(points, gap, most, seed):
    """Up to `most` of `points` at least `gap` cm apart, picked in a fixed
    shuffled order."""
    import random
    pts = list(points)
    random.Random(seed).shuffle(pts)
    out = []
    for p in pts:
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= gap * gap for q in out):
            out.append(p)
            if len(out) >= most:
                break
    return out


def make_effects(fol, sea, trees):
    placed = []
    for x, y, z in spaced(fol.get("grass", []) + fol.get("short grass", []), 4500, 8, 3):
        placed.append({"system": object_path(EFFECTS["butterflies"]), "pos": [round(x), round(y), round(z + 80)]})
    shore = fol.get("shells", []) + fol.get("pebbles", [])
    if sea is not None and shore:
        for x, y, z in spaced(shore, 9000, 3, 7):
            placed.append({"system": object_path(EFFECTS["gulls"]), "pos": [round(x), round(y), round(z + 2500)]})
    else:
        grass = fol.get("grass", [])
        for x, y, z in spaced(grass, 12000, 2, 7):
            placed.append({"system": object_path(EFFECTS["gulls"]), "pos": [round(x), round(y), round(z + 3500)]})
    for x, y, z in spaced(fol.get("lip grass", []), 6000, 5, 11):
        placed.append({"system": object_path(EFFECTS["wind"]), "pos": [round(x), round(y), round(z + 100)]})
    for x, y, z, h in trees:
        placed.append({"system": object_path(EFFECTS["leaves"]), "pos": [round(x), round(y), round(z + h * 0.6)]})
    return {"placed": placed, "camera": [object_path(EFFECTS["dust"])]}


def swap(a):
    staging = a.staging or os.path.join(a.scene, "staging")
    placement = json.load(open(os.path.join(staging, "placement.json"), encoding="utf-8"))
    unit = placement.get("world_unit_meters", 3.048) * 100.0
    recipes = json.load(open(a.recipes, encoding="utf-8"))
    bounds = {m["path"].split(".")[0]: m for m in json.load(open(a.bounds, encoding="utf-8"))}
    spec = json.load(open(a.spec, encoding="utf-8"))
    rocks = ROCKS[a.rocks]
    decor, replaced, trees, leaves = [], collections.Counter(), [], []
    hide_shaders = set()
    hide_tokens = set()
    for n, e in enumerate(placement["entries"]):
        if e.get("kind") != "scenery" or not e.get("model"):
            continue
        asset = e["asset"].lower()
        shaders = model_shaders(os.path.join(staging, e["model"]))
        # By its tag path, else by its shaders' names (a protected map's
        # scenery is "protected\scen\175", its shader still the stock
        # boulder's).
        rule = next((r for k, r in RULES if k in asset), None)             or next((r for k, r in RULES if any(k.replace(" ", "_") in sh for sh in shaders)), None)
        if not rule:
            continue
        kind, options = rule
        ext, cen, base = model_box(os.path.join(staging, e["model"]))
        x, y, z = e["pos"][0] * unit, -e["pos"][1] * unit, e["pos"][2] * unit
        yaw = -math.degrees(e["rot"][0])
        key = f"{asset}|{n}"
        width = max(ext[0], ext[1])
        if kind == "tree":
            variant = pick([v for v in options if v in recipes] or list(recipes), key)
            r = recipes[variant]
            s = ext[2] / max(r["height"], 1.0)
            trees.append((x, y, z, ext[2]))
            c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            # The tree's frame here (yaw and size; row vectors), its leaf
            # clusters into it.
            frame = [[s * c, s * sn, 0.0], [-s * sn, s * c, 0.0], [0.0, 0.0, s]]
            for lf in r.get("leaves", []):
                o = vmul(lf["off"], frame)
                fy, fs, fnx, fny = foliage_pose(mmul(lf["m"], frame))
                leaves.append([round(x + o[0], 1), round(y + o[1], 1), round(z + o[2], 1),
                               round(fy, 1), round(fs, 3), round(fnx, 3), round(fny, 3)])
            for part in r["parts"]:
                ox, oy, oz = (v * s for v in part["off"])
                decor.append({"id": f"swap_{n}_{part['mesh'].rsplit('_', 1)[-1]}", "mesh": object_path(part["mesh"]),
                              "pos": [round(x + ox * c - oy * sn, 1), round(y + ox * sn + oy * c, 1), round(z + oz, 1)],
                              "rot": [r["pitch"], round(yaw, 1), r["roll"]], "scale": [round(s, 3)] * 3})
        else:
            if kind == "bigrock":
                mesh = BIG_ROCK
            elif kind == "rock":
                mesh = pick([m for m, _ in rocks], key)
            else:
                mesh = pick(options, key)
            b = bounds.get(mesh)
            if not b:
                print(f"  no bounds for {mesh}; {asset} kept as CE drew it")
                continue
            bx = b["max"][0] - b["min"][0]
            by = b["max"][1] - b["min"][1]
            bz = b["max"][2] - b["min"][2]
            if kind in ("rock", "bigrock"):
                # Its height CE's (the top where CE's was: a CE boulder is
                # mostly buried, and its visible part is what reads), its
                # width fitted within 40% of that so it is not squashed.
                sz = ext[2] / max(bz, 1.0)
                sx, sy = (min(max(t / max(m, 1.0), sz * 0.6), sz * 1.4) for t, m in ((ext[0], bx), (ext[1], by)))
                # Seated: its base a tenth of its height into the ground.
                zc = z + base - b["min"][2] * sz - bz * sz * 0.1
            else:
                # A plant at the CE plant's size, but no plant over 2.5 times
                # its own (CE's broadleaf is 4 m across, a taro 1).
                sx = sy = sz = min(max(width / max(max(bx, by), 1.0), ext[2] / max(bz, 1.0)), 2.5)
                zc = z + base - b["min"][2] * sz
            decor.append({"id": f"swap_{n}", "mesh": object_path(mesh),
                          "pos": [round(x + cen[0], 1), round(y + cen[1], 1), round(zc, 1)],
                          "rot": [0.0, round(yaw, 1), 0.0], "scale": [round(sx, 3), round(sy, 3), round(sz, 3)]})
        replaced[asset.split("\\")[-1]] += 1
        hide_tokens.add(asset.rsplit("\\", 1)[0].replace("\\", "_").replace(" ", "_"))
        hide_shaders.update(shaders)
    # The CE slots of the replaced scenery: the spec's slots named for it.
    hide = []
    for slot in spec["slots"]:
        if any(slot["name"].startswith(t + "_shaders_") for t in hide_tokens)                 or any(slot["name"].startswith(sh + "__") for sh in hide_shaders):
            hide.append(slot["material"])
    effects = None
    if a.foliage:
        fol = foliage_points(a.foliage, os.path.join(os.path.dirname(a.foliage), "foliage.bin"))
        effects = make_effects(fol, a.sea, trees)
        print(f"{len(effects['placed'])} effect(s) placed")
    json.dump({"decor": decor, "hide": hide, "count": sum(replaced.values()), "effects": effects,
               "leaves": {"mesh": object_path(LEAVES), "records": leaves}},
              open(a.out, "w", encoding="utf-8"), indent=1)
    print(f"{len(leaves)} leaf cluster(s) on the trees")
    print(f"{sum(replaced.values())} scenery object(s) in B30's assets ({len(decor)} decor entries, "
          f"{len(hide)} CE slot(s) hidden): {dict(replaced)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recipes")
    r.add_argument("csv"); r.add_argument("bounds"); r.add_argument("out")
    s = sub.add_parser("swap")
    s.add_argument("scene"); s.add_argument("spec"); s.add_argument("recipes"); s.add_argument("bounds")
    s.add_argument("out")
    s.add_argument("--rocks", default="beach", choices=sorted(ROCKS))
    s.add_argument("--foliage", help="the map's foliage.json (its foliage.bin beside it): place the effects")
    s.add_argument("--sea", type=float, help="the sea's height (cm)")
    s.add_argument("--staging", help="the conversion's staging folder (placement.json, models/) when it is not "
                                     "<scene dir>/staging")
    a = ap.parse_args()
    recipes(a) if a.cmd == "recipes" else swap(a)


if __name__ == "__main__":
    main()
