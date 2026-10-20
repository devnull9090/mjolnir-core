"""Take converted CE maps through the B30 pipeline in one run.

    python tools/level/upgrade_ce_map.py BGL YOY [--install] [--stages ...]
    python tools/level/upgrade_ce_map.py TST --stages install --local-install

For each map named in tools/level/ce_upgrade_maps.json this does what was
done by hand per map until 2026-10-12:

  land      build_landscape.py: the ground's heights, holes and bakes
  foliage   scatter_foliage.py: grass, debris and the cliffs' cladding
  swap      scenery_swap.py: the natural CE scenery (boulders, trees,
            shrubs, plants) in B30's own meshes, the CE slots hidden;
            then rock_foliage.py clears the grass inside each B30 rock
  editor    the map's Landscape world in unreal/MJOLNIRMaterials
            (Scripts/build_ce_landscape.py), and once for the run the
            trial masters (Scripts/build_ce_materials.py, chunk 983) and
            the maps' tessellated cliffs (cliff_mesh.py, then
            Scripts/build_ce_cliffs.py, chunk 983 too)
  cook      tools/ue/cook.ps1 with every map's world, once for the run
  bake      bake_editor_world.sh: the map container around the world
  assemble  the map's level file: the conversion's, with the landscape,
            foliage and water entries
  install   (--install, the game closed) the map container over the hub
            copy's, the landscape container, the trial masters, the
            loader, the level and foliage files

Everything lands in <work>/<CODE>/ (default C:/haloce/ce_conversions/
upgrade), so a run can stop at any stage and pick up with --stages. The
editor and the cook take the project's mutex, so one run at a time.

--local-install installs a new, locally converted map without a hub listing.
It requires the CE runtime, loader/native DLL and game variants already
installed. It copies the conversion's mesh/textures and the upgraded world,
then rebuilds the shared registration and menu with `mjolnir level register`.
Set MJOLNIR to the CLI executable when it is not in this checkout's target.
"""
import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CONFIG = os.path.join(HERE, "ce_upgrade_maps.json")
PROJECT = os.path.join(REPO, "unreal", "MJOLNIRMaterials")
STAGED = os.path.join(PROJECT, "Saved", "StagedBuilds", "Windows", "Meteorite", "Content", "Paks")
STAGES = ("land", "foliage", "swap", "collision", "editor", "cook", "bake", "assemble", "install")
# The cliffs' fill (M_CE_CliffPBR CliffFillDir): its share on a wall, and its
# change towards faces that look up. The master's own (0.75, -0.35) is a
# bounce off the sand, strongest on faces looking down: cladding rocks part
# way up a wall in shade drew their undersides brighter than the wall
# (2026-10-13).
CLIFF_FILL_DIR = [0.75, 0.0, 0.0, 0.0]
# Tessellated cliffs (cliff_mesh.py, M_CE_CliffTess) unless a map's config
# says "tess": false: displacement (0..1 of 50 cm either way), whether the
# cladding rocks are tessellated too and theirs: none. The Megascans rocks
# are detailed already; at the walls' 0.6 they folded, backfaces showing as
# lavender patches, and even at 0.2 their triplanar rock smeared into
# streaks down every overhang (Yoyorast, 2026-10-16; 0.06 still streaked).
TESS = {"disp": 0.6, "cladding": True, "clad_disp": 0.0}
# Indoor maps (`indoor`: Rat Race's tunnels): no Landscape, no grass or
# swapped scenery, the conversion's own map container and collision; only
# the cliffs in the game's rock (and the level file's structures, lights,
# decals). INDOOR_CLIFF is the cliff entry build_landscape.py would write
# (Battle Creek's: the same CE cliff shader), under the map's `cliff`, with
# everything that reads the landscape off: the turf, soil and stains at a
# wall's lip (CliffDrape.w), the sand at its foot (CliffFoot.w) and the sand's
# bounce (CliffFill.w), which would light a tunnel from nowhere.
INDOOR_SKIP = ("land", "foliage", "swap", "collision", "bake")
INDOOR_CLIFF = {"tiles": [500, 1400, 2500, 4], "mix": [0.6, 1.6, 1.4, 1.0], "look": [2.2, 0.85, 0.3, 1.5],
                "far": [2500, 9000, 0.6, 0], "ce_tint": [0.5, 0, 0, 0], "tint": [0.8, 0.66, 0.56, 1.0],
                "rough": [0.6, 1.0, 0, 0], "fill": [1.0, 0.8, 0.62, 0.0], "drape": [35, 35, 700, 0.0],
                "foot": [35, 150, 0.45, 0.0]}
GAME =os.environ.get("HCE_GAME", "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved")
PAKS = os.path.join(GAME, "Meteorite", "Content", "Paks")
UE4SS = os.path.join(GAME, "Meteorite", "Binaries", "Win64", "ue4ss")
LAUNCHER_STATE = os.path.join(os.environ.get("APPDATA", ""), "com.devnull9090.mjolnir-launcher", "hub_state.json")
# What a swapped scenery slot draws (scenery_swap.py).
HIDDEN = "/Game/MJOLNIR/CETrial/M_CE_Hidden.M_CE_Hidden"
RIVER_SPLASH = ("/Game/FX/Library/Environment/PNW/Liquids/Splashes/AmbientRiverSplash/"
                "NS_PNW_AmbientRiverSplash_01.NS_PNW_AmbientRiverSplash_01")
# Structures: slots whose CE base map is one of these (metal, panels,
# machinery) draw with the trial environment master's surface section
# (build_ce_materials.py SURFACE_CODE): relief from the base map, roughness
# and specular, the Forerunner kit's scratch wear. Surface: on, relief,
# plate roughness, wear.
STRUCTURE = ("metal", "panel", "tech", "steel", "plate", "strip", "circuit", "generator", "pipe", "grate",
             "girder", "beam", "rivet", "vent")
SURFACE = [0.4, 2.0, 0.55, 0.3]
# The game's Forerunner metal (build_ce_materials.py SURFACE_CODE): its kit's
# greeble map (343 left it under a prototyping folder; a game update may move
# it, and the loader then drops it and the plate draws without scratches)
# and SurfaceMetal: metallic, iridescence, scratch tile (cm), plate
# roughness (the kit's 0.38).
SURFACE_WEAR = "/Game/_Prototyping/Users/ChiyoLai/T_FR_Gen_Metal_01_ORHG.T_FR_Gen_Metal_01_ORHG"
SURFACE_METAL = [0.5, 0.0, 300.0, 0.7]
# Grass sways in one steady wind.
WIND = {"dir": [0.9, 0.4], "strength": 0.4}
# cm the visible ground rides over the mesh, less half the sand's parallax
# depth (scatter_foliage --lift).
FOLIAGE_LIFT = 6


def run(cmd, env=None, cwd=REPO, check=True):
    print("  $", " ".join(str(c) for c in cmd)[:220], flush=True)
    full = dict(os.environ, **(env or {}))
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=full, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        sys.exit(f"failed ({p.returncode}):\n{out[-3000:]}")
    return out


def powershell(script, args, env=None):
    return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script] + args, env=env, check=False)


def bash():
    for b in ("C:/Program Files/Git/bin/bash.exe", "bash"):
        if b == "bash" or os.path.exists(b):
            return b


def sea_height(level):
    """The sea's height (cm) from the level's water decor, as the loader finds it."""
    origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
    for item in level.get("decor") or []:
        if isinstance(item, dict) and "_Water." in str(item.get("mesh", "")) and item.get("pos"):
            return item["pos"][2] + origin[2]
    return None


def paths(code, m, work):
    conv = m["conversion"]
    scene = m.get("scene", conv)
    w = os.path.join(work, code)
    return {"conv": conv, "scene": scene, "work": w, "land": os.path.join(w, "land"),
            "foliage": os.path.join(w, "foliage"), "bake": os.path.join(w, "bake"),
            "level": m.get("base_level") or os.path.join(conv, m["level"]), "out_level": os.path.join(w, "level.json")}


def indoor_landscape(code, m, p):
    """An indoor map's landscape.json (INDOOR_CLIFF): the cliff entry alone,
    its slots every terrain slot whose primary detail map is a cliff's (as
    build_landscape.py finds them), for cliff_mesh.py and the level file."""
    level = json.load(open(p["level"], encoding="utf-8"))
    terrain = next(i for i in level["decor"] if str(i.get("id", "")).endswith("_terrain"))
    details = sorted({t["Primary"].rsplit(".", 1)[-1] for t in
                      (mt.get("textures") or {} for mt in terrain.get("materials") or [] if isinstance(mt, dict))
                      if "detail_cliff" in t.get("Primary", "")})
    cliff = dict(INDOOR_CLIFF, details=details, **(m.get("cliff") or {}))
    os.makedirs(p["land"], exist_ok=True)
    json.dump({"cliff": cliff}, open(os.path.join(p["land"], "landscape.json"), "w", encoding="utf-8"), indent=1)
    print(f"  {code}: indoor, cliffs by {', '.join(details)}")


def staging(p):
    """The conversion's staging folder: placement.json and the CE models
    (the scene folder's own when it has them)."""
    own = os.path.join(p["scene"], "staging")
    return own if os.path.isdir(os.path.join(own, "models")) else os.path.join(p["conv"], "staging")


def sea_zone(code, m, p):
    """tools/level/sea_zone.py for a coast with a wading zone: the distance
    field and the wall, in <work>/<CODE>/zone. Returns the folder."""
    coast = m["flux"]["coast"]
    out = os.path.join(p["work"], "zone")
    cmd = [sys.executable, os.path.join(HERE, "sea_zone.py"), os.path.join(p["scene"], "scene.gltf"), out,
           "--sea", str(coast["water"]), "--wade", str(coast["wade"])]
    if coast.get("zone_ignore"):
        cmd += ["--ignore", ",".join(coast["zone_ignore"])]
    if coast.get("apron"):
        cmd += ["--apron", ",".join(coast["apron"]["shaders"])]
    print("  " + run(cmd).strip().splitlines()[-1])
    return out


def deep_floor(m, p, ids, floor):
    """With a wading zone: CE's own sea floor again, as a copy of its ground
    item with every other slot hidden, lowered to the deep seabed's depth
    (zone_shelf's 25 m, a little under). Past the landscape the sea had no
    floor, and from the water a player saw over the landscape's edge to
    our old sea far below (Yoyorast, 2026-10-16); the copy runs on to the
    horizon (Yoyorast's floor is 3.2 km across). An id without "_terrain":
    plain decor, no terrain shading or shadow copy."""
    coast = m["flux"]["coast"]
    if not coast.get("wade"):
        return []
    import numpy as np
    z = np.load(os.path.join(p["work"], "zone", "zone.npz"))["floor"]
    floor_z = float(np.nanmedian(z))
    target = coast["water"] - 2520.0
    out = []
    for key, slots in floor.items():
        item = ids[key]
        mats = [HIDDEN] * len(item["materials"])
        for i in slots:
            mats[i] = item["materials"][i]
        copy = {k: v for k, v in item.items() if k not in ("id", "materials", "pos")}
        copy.update({"id": key.replace("_terrain", "") + "_deepfloor", "materials": mats,
                     "pos": [item["pos"][0], item["pos"][1], round(item["pos"][2] - (floor_z - target), 1)]})
        out.append(copy)
        print(f"  deep floor: {key} slots {slots} lowered {floor_z - target:.0f} cm")
    return out


def sea_sand(code, m, level, ids, floor):
    """A Flux coast's last floor: our own sea mesh (SM_<code>_Water, one flat
    sheet as wide as CE's sea) again, drawn as CE's sea floor (its first
    floor slot's material, unlit by CE's lightmap: the sheet has none) and
    lowered under the deepest seabed. The sea floor has holes (cut round
    Yoyorast's pipe), and Flux's sea drops out with the horizon on the
    frustum's edge: through both, sand, not the sky or a second sea
    (2026-10-16). The water item itself stays first in decor, where the
    loader takes the sea's height from it."""
    coast = m["flux"]["coast"]
    depth = coast.get("sand_depth", 2560.0 if coast.get("wade") else 900.0)
    sand = None
    for key, slots in floor.items():
        entry = ids[key]["materials"][slots[0]]
        if isinstance(entry, dict):
            sand = json.loads(json.dumps(entry))
            break
    if sand is None:
        return []
    for k in ("HasLightmap", "HasBake"):
        sand.setdefault("scalars", {})[k] = 0.0
    out = []
    for item in level.get("decor") or []:
        if f"/SM_{code}_Water." not in str(item.get("mesh", "")):
            continue
        copy = {k: v for k, v in item.items() if k not in ("id", "materials", "pos")}
        copy.update({"id": item["id"] + "_sand", "materials": [sand] * len(item["materials"]),
                     "pos": [item["pos"][0], item["pos"][1], round(item["pos"][2] - depth, 1)], "cast_shadow": False})
        out.append(copy)
        print(f"  sea sand: {item['id']} as the sea floor, {depth:.0f} cm down")
    return out


SURF = ("/Game/FX/Library/Environment/PNW/Liquids/Splashes/SmallWaveSplash/NS_PNW_SmallWaveSplash_01."
        "NS_PNW_SmallWaveSplash_01")


def structure_surf(m, p, level):
    """Waves breaking on CE's structures in the sea (a coast's `surf`:
    `shaders`, substrings of the materials whose waterline takes them; `gap`
    cm between splashes; `depth` cm of water they need, by the landscape's
    seabed, so none goes off on the sand where a wall runs up the beach):
    the game's small wave splash (its own spray, mist and sound, slept far
    off by its effect type) wherever those surfaces cross the sea.
    Yoyorast's walls and pillars stood in a flat sea (2026-10-16)."""
    coast = m["flux"]["coast"]
    spec = coast.get("surf")
    if not spec:
        return []
    import random
    import numpy as np
    from refine_water_gltf import read_accessor
    sea, gap, depth = coast["water"], float(spec.get("gap", 1500)), float(spec.get("depth", 100))
    tokens = [t.lower() for t in spec["shaders"]]
    g = os.path.join(p["scene"], "scene.gltf")
    doc = json.load(open(g, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(g), doc["buffers"][0]["uri"]), "rb").read()
    land = json.load(open(os.path.join(p["land"], "landscape.json"), encoding="utf-8"))
    n, loc = land["size"], land["location"]
    hts = np.fromfile(os.path.join(p["land"], land["heights"]), "<u2").reshape(n, n).astype(np.float64)
    floor = loc[2] + (hts - 32768) * land["scale"][2] / 128.0

    def deep(x, y):
        i, j = round((x - loc[0]) / land["scale"][0]), round((y - loc[1]) / land["scale"][1])
        return not (0 <= i < n and 0 <= j < n) or floor[j, i] < sea - depth

    pts = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            if not any(t in doc["materials"][prim["material"]]["name"].lower() for t in tokens):
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            P = np.stack([pos[:, 0] * 100, pos[:, 2] * 100, pos[:, 1] * 100], 1)
            for t in P[read_accessor(doc, data, prim["indices"]).reshape(-1, 3)]:
                z = t[:, 2] - sea
                if not (z.min() < 0 < z.max()):
                    continue
                ends = [t[i] + (t[j] - t[i]) * (z[i] / (z[i] - z[j]))
                        for i, j in ((0, 1), (1, 2), (2, 0)) if (z[i] < 0) != (z[j] < 0)]
                if len(ends) != 2:
                    continue
                k = max(1, int(np.linalg.norm(ends[1] - ends[0]) // (gap / 4)))
                pts += [tuple((ends[0] + (ends[1] - ends[0]) * (q + 0.5) / k)[:2]) for q in range(k)]
    pts = [q for q in pts if deep(*q)]
    random.Random(17).shuffle(pts)
    keep = []
    for q in pts:
        if all((q[0] - r[0]) ** 2 + (q[1] - r[1]) ** 2 >= gap * gap for r in keep):
            keep.append(q)
    origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
    print(f"  surf: {len(keep)} splash(es) on {', '.join(spec['shaders'])} ({len(pts)} waterline point(s) deep enough)")
    return [{"system": SURF, "pos": [round(x - origin[0]), round(y - origin[1]), round(sea - origin[2])]} for x, y in keep]


# The apron's depth (m) by metres from a structure's waterline: as shallow as
# CE's own floor (1.5 m) for 5 m, deep water by 40.
APRON_SHELF = "0:1.5,5:1.5,12:5,22:12,40:25"


def flux_dry_zones(m, p, level, cell=100.0):
    """The tunnels and rooms Fluid Flux's sea must stay out of: its surface
    is one plane at sea level everywhere, so where a tunnel ramps under it
    (floor below the sea, roof above) the sea stood inside, its swell
    churning, and its underwater fog volumes filled the rooms wholly under
    it (Yoyorast's ramp down to its sunken room, 2026-10-16). Cells with a
    roof 1.5 to 8 m over a floor less than a metre over the sea (higher, an
    arch over the beach, open to the sky from the side), joined
    into zones (rectangles, cm from the canvas origin, with their floor and
    roof heights) for the loader (Effects.dryTick):
    `cut`: where the sea plane runs through the open space under land
    (roof over the sea, land over the cell) and the open sea cannot reach
    it along the surface (a sea cave keeps its water), split until none
    takes in open sea: Flux's one cut rectangle goes to the one the camera
    is near.
    `fog`: every such space with its floor under the sea, the corridors
    wholly under it too (the sea is over their roofs, so no cut), by metre
    cell [x, y, floor, roof]: Flux's underwater volumes hidden while the
    camera is inside one. CE's own sea floor (the coast's `floor` slots) is
    no floor here: under a bridge over the sea it made the open water a
    "tunnel"."""
    import numpy as np
    from refine_water_gltf import read_accessor
    sea = m["flux"]["coast"]["water"]
    g = os.path.join(p["scene"], "scene.gltf")
    doc = json.load(open(g, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(g), doc["buffers"][0]["uri"]), "rb").read()
    # Terrain slot i is the glTF's material i - 1 (cliff_mesh.py).
    sea_floor = {s - 1 for s in next(iter(((level.get("flux") or {}).get("coast") or {}).get("floor", {}).values()), [])}
    ups, downs, tops = {}, {}, {}
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            if any(w in name for w in ("water", "sky", "fog")):
                continue
            floor_slot = prim["material"] in sea_floor
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            P = np.stack([pos[:, 0] * 100, pos[:, 2] * 100, pos[:, 1] * 100], 1)
            T = P[read_accessor(doc, data, prim["indices"]).reshape(-1, 3)]
            T = T[(T[..., 2].min(1) < sea + 2000) & (T[..., 2].max(1) > sea - 1500)]
            for a, b, c in T:
                n = np.cross(b - a, c - a)
                ln = np.linalg.norm(n)
                det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if ln <= 0 or abs(det) < 1e-6:
                    continue
                nz = n[2] / ln  # Unreal's axes turn the glTF's normal over: +z faces down
                for ix in range(math.floor(min(a[0], b[0], c[0]) / cell), math.floor(max(a[0], b[0], c[0]) / cell) + 1):
                    px = (ix + 0.5) * cell
                    for iy in range(math.floor(min(a[1], b[1], c[1]) / cell),
                                    math.floor(max(a[1], b[1], c[1]) / cell) + 1):
                        py = (iy + 0.5) * cell
                        w1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / det
                        w2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / det
                        if min(w1, w2, 1 - w1 - w2) < 0:
                            continue
                        z = w1 * a[2] + w2 * b[2] + (1 - w1 - w2) * c[2]
                        tops[(ix, iy)] = max(tops.get((ix, iy), -1e9), z)
                        if nz < -0.3 and not floor_slot:
                            ups.setdefault((ix, iy), []).append(z)
                        elif nz > 0.3:
                            downs.setdefault((ix, iy), []).append(z)
    cut, fog = {}, {}
    for k, floors in ups.items():
        for f in floors:
            roofs = [q for q in downs.get(k, []) if f + 150 < q < f + 800]
            if not roofs or f >= sea + 100:
                continue
            r = min(roofs)
            if f < sea:
                lo, hi = fog.get(k, (1e9, -1e9))
                fog[k] = (min(lo, f), max(hi, r))
            if r > sea and tops.get(k, -1e9) > sea + 50:
                lo, hi = cut.get(k, (1e9, -1e9))
                cut[k] = (min(lo, f), max(hi, r))
    # Open sea: the highest surface over the cell under the sea.
    open_sea = {k for k, t in tops.items() if t < sea}
    # Where the open sea reaches along its surface: from cells with nothing
    # over the water (no roof under the surface: not a corridor beneath it),
    # through any whose floor is under the sea with no roof or one over it.
    def surface_open(k):
        for f in ups.get(k, []):
            if f < sea and all(q < f + 150 or q > sea for q in downs.get(k, [])):
                return True
        return False
    seeds = [k for k in open_sea if not any(q < sea for q in downs.get(k, []))]
    reached, stack = set(seeds), list(seeds)
    while stack:
        cx, cy = stack.pop()
        for q in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if q not in reached and (q in open_sea or surface_open(q)):
                reached.add(q)
                stack.append(q)
    # Any space within 3 m of that water is open to the sea (a sea cave, a
    # beach under an overhang: Death Island's shore waves ran up under a
    # cliff, 2026-10-16): the whole of it keeps its water.
    near_sea = set(reached)
    for _ in range(3):
        near_sea |= {(x + dx, y + dy) for x, y in near_sea for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    caves, seen_c = [], set()
    for start in list(cut):
        if start in seen_c:
            continue
        comp, stack = [], [start]
        seen_c.add(start)
        while stack:
            c = stack.pop()
            comp.append(c)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (c[0] + dx, c[1] + dy)
                    if q in cut and q not in seen_c:
                        seen_c.add(q)
                        stack.append(q)
        # ...and one the sea never reaches into (no floor under it: Death
        # Island's grass under an overhang, 0.9 m up) needs no cut.
        if any(c in near_sea for c in comp) or all(cut[c][0] >= sea for c in comp):
            caves += comp
    for k in caves:
        del cut[k]
    # The cut 2 m into the rock round each tunnel (where land is over it):
    # cut to its cells alone, a sliver of sea showed along a ramp's wall.
    for _ in range(2):
        grown = dict(cut)
        for (cx, cy), v in cut.items():
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (cx + dx, cy + dy)
                    if q not in grown and tops.get(q, -1e9) > sea + 50:
                        grown[q] = v
        cut = grown

    def boxes(cells):
        xs, ys = [c[0] for c in cells], [c[1] for c in cells]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        if not any((x, y) in open_sea for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)):
            return [cells]
        if len(cells) < 4:
            return []
        axis = 0 if x1 - x0 >= y1 - y0 else 1
        mid = sorted(c[axis] for c in cells)[len(cells) // 2]
        lo_, hi_ = [c for c in cells if c[axis] < mid], [c for c in cells if c[axis] >= mid]
        if not lo_ or not hi_:
            return []
        return boxes(lo_) + boxes(hi_)

    origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]

    def zones(cells, split):
        seen, out = set(), []
        for start in cells:
            if start in seen:
                continue
            comp, stack = [], [start]
            seen.add(start)
            while stack:
                c = stack.pop()
                comp.append(c)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        q = (c[0] + dx, c[1] + dy)
                        if q in cells and q not in seen:
                            seen.add(q)
                            stack.append(q)
            for part in (boxes(comp) if split else [comp]):
                if len(part) < 4:
                    continue
                xs, ys, zs = [c[0] for c in part], [c[1] for c in part], [cells[c] for c in part]
                out.append({"rect": [round(min(xs) * cell - origin[0]), round(min(ys) * cell - origin[1]),
                                     round((max(xs) + 1) * cell - origin[0]), round((max(ys) + 1) * cell - origin[1])],
                            "z": [round(min(z[0] for z in zs) - origin[2]), round(max(z[1] for z in zs) - origin[2])]})
        return out

    out = {"cut": zones(cut, True),
           "fog": [[round(k[0] * cell - origin[0]), round(k[1] * cell - origin[1]), round(v[0] - origin[2]),
                    round(v[1] - origin[2])] for k, v in sorted(fog.items())], "cell": cell}
    print(f"  flux: {len(out['cut'])} cut zone(s) over {len(cut)} m2 where the sea runs into tunnels "
          f"({len(caves)} m2 the open sea reaches left wet), "
          f"{len(fog)} m2 of them under it (fog cells)")
    return out


def zone_shelf(wade):
    """The seabed by metres from land: none deeper than CE's floor (which it
    keeps) out to the wading line, then down to 25 m, Flux's open sea."""
    w = float(wade)
    return f"0:0,{w:g}:0,{w + 2:g}:3,{w + 15:g}:10,{w + 50:g}:20,{w + 90:g}:25"


def stage_land(code, m, p):
    cmd = [sys.executable, os.path.join(HERE, "build_landscape.py"), os.path.join(p["scene"], "scene.gltf"),
           os.path.join(p["scene"], "materials.spec.json"), p["land"], "--shader", ",".join(m["shaders"]),
           "--name", m["landscape"]]
    if m.get("components"):
        cmd += ["--components", str(m["components"])]
    if m.get("min_z") is not None:
        cmd += ["--min-z", str(m["min_z"])]
    if m.get("ground_also"):
        cmd += ["--also", ",".join(m["ground_also"])]
    if m.get("real_base"):
        cmd += ["--real-base"]
    if m.get("cliff_shaders"):
        cmd += ["--cliff-shaders", ",".join(m["cliff_shaders"])]
    # A coast with a seabed (flux.coast.seabed): the landscape's floor shelves
    # away from the shore under the sea, for Fluid Flux's surf.
    coast = (m.get("flux") or {}).get("coast") or {}
    if coast.get("seabed"):
        cmd += ["--sea", str(coast["water"])]
        if coast.get("wade"):
            # The wading zone (sea_zone.py): CE's own floor out to `wade` m
            # from land, where players can walk, deep water past it, behind
            # the wall stage_collision adds on the same line.
            zone = sea_zone(code, m, p)
            cmd += ["--zone", zone, "--shelf", coast.get("shelf") or zone_shelf(coast["wade"])]
            # A shallow apron round the structures standing in the sea
            # (`apron`: shaders, shelf), which Flux's waves feel.
            if coast.get("apron"):
                cmd += ["--apron-shelf", coast["apron"].get("shelf", APRON_SHELF)]
        elif isinstance(coast["seabed"], str):
            cmd += ["--shelf", coast["seabed"]]
    out = run(cmd)
    print("  " + "\n  ".join(l for l in out.splitlines()
                             if l.startswith(("heights", "holes", "settled", "bakes", "seabed"))))


def stage_foliage(code, m, p):
    level = json.load(open(p["level"], encoding="utf-8"))
    cmd = [sys.executable, os.path.join(HERE, "scatter_foliage.py"), os.path.join(p["scene"], "scene.gltf"),
           os.path.join(p["scene"], "materials.spec.json"), os.path.join(p["foliage"], "foliage.json"),
           "--bin", os.path.join(p["foliage"], "foliage.bin"), "--offset", "0,0,0", "--lift", str(FOLIAGE_LIFT),
           "--edge", os.path.join(p["land"], "landscape.json"), "--swapped-rocks"]
    sea = sea_height(level)
    if sea is not None:
        cmd += ["--sea", f"{sea:.1f}"]
    cmd += ["--staging", staging(p)]
    for name, cls in (m.get("details") or {}).items():
        cmd += ["--detail", f"{name}={cls}"]
    for rule, tint in (m.get("tints") or {}).items():
        cmd += ["--rule-tint", f"{rule}={tint}"]
    if m.get("biome"):
        cmd += ["--biome", m["biome"]]
    if m.get("biome") == "snow":
        # Snow grows only on the map's own ground (the landscape's shaders).
        cmd += ["--ground-shaders", ",".join(m["shaders"] + m.get("ground_also", []))]
    if m.get("cliff_shaders"):
        cmd += ["--cliff-shaders", ",".join(m["cliff_shaders"])]
    # `foliage_extra`: optional scatter rules (Death Island's sea rocks).
    for rule in m.get("foliage_extra", []):
        cmd += ["--extra", rule]
    os.makedirs(p["foliage"], exist_ok=True)
    out = run(cmd)
    print("  " + out.strip().splitlines()[-1][:200])


def stage_swap(code, m, p):
    data = os.path.join(HERE, "data")
    with open(p["level"], encoding="utf-8") as f:
        sea = sea_height(json.load(f))
    # A snow map (`biome: snow`) takes B40's trees and rocks: its own
    # recipes and bounds (scenery_swap.py recipes, `mjolnir mesh list`).
    source = "b40" if m.get("biome") == "snow" else "b30"
    out = run([sys.executable, os.path.join(HERE, "scenery_swap.py"), "swap", p["scene"],
               os.path.join(p["scene"], "materials.spec.json"), os.path.join(data, f"{source}_tree_recipes.json"),
               os.path.join(data, f"{source}_scenery_bounds.json"), os.path.join(p["work"], "swap.json"),
               "--rocks", m.get("rocks", "beach"), "--foliage", os.path.join(p["foliage"], "foliage.json"),
               "--staging", staging(p)]
              + (["--biome", m["biome"]] if m.get("biome") else [])
              + (["--tree-variant", m["tree_variant"]] if m.get("tree_variant") else [])
              + (["--sea", f"{sea:.1f}"] if sea is not None else []))
    print("  " + out.strip().splitlines()[-1][:200])
    # The grass up to each swapped rock's own hull (the foliage stage left
    # them no clearing: it cannot know the rocks).
    fol = os.path.join(p["foliage"], "foliage.bin")
    if os.path.exists(fol):
        out = run([sys.executable, os.path.join(HERE, "rock_foliage.py"), fol, os.path.join(p["work"], "swap.json"),
                   staging(p)] + (["--biome", m["biome"]] if m.get("biome") else []))
        print(f"  {code}: " + out.strip().splitlines()[-1][:200])


def stage_collision(code, m, p):
    """The B30 rocks, tree trunks and reachable cliff cladding in the map's
    collision: tools/level/b30_collision.py's hulls replace the swapped CE
    scenery's own collision (merge_ce_collision.py --extra), and
    `mjolnir level collision --own-bsp` builds the BSP the bake uses. The
    Blam simulation does all collision, so without this players walked
    through every B30 rock and tree (2026-10-12).

    Scenery that overflows the BSP's 16-bit tables goes to instances of
    its own. A Blood Gulch built that way first loaded no scenario at all;
    it loads (and collides) since merge_ce_collision.py counts the new
    objects in the scene's object total (2026-10-12)."""
    extra = os.path.join(p["work"], "b30_collision.json")
    scene = os.path.join(p["work"], "collision_scene.json")
    sbsp = os.path.join(p["work"], m["sbsp"])
    mjolnir = os.environ.get("MJOLNIR", os.path.join(REPO, "target", "release", "mjolnir.exe"))
    made = run([sys.executable, os.path.join(HERE, "b30_collision.py"), os.path.join(p["foliage"], "foliage.json"),
                os.path.join(p["foliage"], "foliage.bin"), os.path.join(p["work"], "swap.json"), extra,
                "--scene", os.path.join(p["scene"], "scene.gltf")]).strip().splitlines()[-1]
    # The wading wall (sea_zone.py, made with the landscape): players stop
    # where the seabed falls away.
    wall = os.path.join(p["work"], "zone", "wall.json")
    if ((m.get("flux") or {}).get("coast") or {}).get("wade") and os.path.exists(wall):
        w, e = json.load(open(wall, encoding="utf-8")), json.load(open(extra, encoding="utf-8"))
        e["triangles"] += w["triangles"]
        e["materials"] += w["materials"]
        json.dump(e, open(extra, "w", encoding="utf-8"))
        made += f"; wading wall {len(w['triangles'])} triangle(s)"
    run([sys.executable, os.path.join(HERE, "merge_ce_collision.py"), staging(p), scene, "--extra", extra])
    out = run([mjolnir, "level", "collision", scene, "--out", sbsp, "--own-bsp", "--bsp-index", "0", "--paks", PAKS])
    placed = [l.strip() for l in out.splitlines() if l.strip().startswith("scenery")]
    print(f"  {code}: {made[:150]}")
    print(f"  {code}: {(placed[-1] if placed else '')[:150]}")


def bake_sbsp(m, p):
    """The map's BSP: the collision stage's, else the conversion's own."""
    own = os.path.join(p["work"], m["sbsp"])
    return own if os.path.exists(own) else os.path.join(p["conv"], m["sbsp"])


def stage_editor(code, m, p):
    if m.get("rock_roughness") is not None and not m.get("bake_foliage"):
        sys.exit(f"{code}: rock_roughness requires bake_foliage")
    if m.get("indoor"):
        print(f"  {code}: indoor, no landscape world")
        return
    env = {"MJ_LANDSCAPE": p["land"], "MJ_LANDSCAPE_NAME": m["landscape"], "MJ_LANDSCAPE_CHUNK": str(m["chunk"])}
    # `bake_foliage`: the foliage, cladding rocks and swapped scenery placed
    # in the world here (tools/level/foliage_bake.py) instead of by the
    # loader at runtime; assemble then marks the level file's foliage `baked`.
    if m.get("bake_foliage"):
        spec = os.path.join(p["work"], "foliage_bake", "spec.json")
        origin = (json.load(open(p["level"], encoding="utf-8")).get("canvas") or {}).get("origin") or [0, 0, 0]
        print("  " + run([sys.executable, os.path.join(HERE, "foliage_bake.py"), p["work"], spec, "--paks", PAKS,
                          "--origin", ",".join(str(v) for v in origin),
                          "--mjolnir", os.environ.get("MJOLNIR", os.path.join(REPO, "target", "release", "mjolnir.exe"))]
                         + (["--rock-roughness", str(m["rock_roughness"])] if m.get("rock_roughness") is not None else [])).strip().splitlines()[-1][:160])
        env["MJ_FOLIAGE"] = spec
    out = powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_landscape.py"],
                     env=env)
    # The editor's own log too: its console capture has stopped short of the
    # end (Death Island, 2026-10-13) with the world built.
    log = "".join(open(f, encoding="utf-8", errors="replace").read() for f in (
        os.path.join(PROJECT, "Saved_build_ce_landscape.log"), os.path.join(PROJECT, "Saved", "Logs", "Meteorite.log"))
        if os.path.exists(f))
    if "landscape built" not in log or os.path.normcase(p["land"]) not in os.path.normcase(log.replace("/", "\\")):
        sys.exit(f"{code}: the landscape world was not built:\n{out[-2000:]}")
    if m.get("bake_foliage") and "landscape foliage:" not in log:
        sys.exit(f"{code}: the world was built without its foliage:\n{out[-2000:]}")
    print(f"  {code}: world /Game/Levels/Halo1/Solo/{m['landscape']} built")


def build_water():
    """The water masters (Scripts/build_ce_water.py, chunk 982)."""
    powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_water.py"])
    log = open(os.path.join(PROJECT, "Saved_build_ce_water.log"), encoding="utf-8", errors="replace").read()
    if "CE water built" not in log or "Traceback" in log:
        sys.exit("the water masters did not build: see " + os.path.join(PROJECT, "Saved_build_ce_water.log"))
    print("  water masters built")


def build_masters():
    # M_CE_Plasma's noise: MCC's plasma shield noise volume as an atlas.
    noise = os.path.join(PROJECT, "Saved", "ce_plasma", "T_CE_PlasmaNoise.png")
    run([sys.executable, os.path.join(HERE, "mcc_tags.py"), "--plasma-noise", noise])
    powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_materials.py"],
               env={"MJ_CE_ROOT": "/Game/MJOLNIR/CETrial", "MJ_CE_CHUNK": "983", "MJ_PLASMA_NOISE": noise})
    log = open(os.path.join(PROJECT, "Saved_build_ce_materials.log"), encoding="utf-8", errors="replace").read()
    if "trial materials built" not in log or "Traceback" in log:
        sys.exit("the trial masters did not build: see " + os.path.join(PROJECT, "Saved_build_ce_materials.log"))
    print("  trial masters built")


def shadow_shells(maps, ps):
    """The maps' walls a little behind themselves (tools/level/shadow_shell.py),
    for the shadow copy: CE's one-sided planes let the sun down every inside
    corner (Sidewinder, 2026-10-14). Built with the cliffs as
    SM_<CODE>_ShadowShell; returns build_ce_cliffs.py entries."""
    specs = []
    for code in maps:
        p = ps[code]
        # A previous assembled level has hidden materials and may use an old
        # slot order after the CE source changes. Start from the current
        # conversion (or configured base_level) and apply only today's cut;
        # shadow_shell.py excludes the current scenery through --swap.
        with open(p["level"], encoding="utf-8") as f:
            level = json.load(f)
        with open(os.path.join(p["land"], "landscape.json"), encoding="utf-8") as f:
            land = json.load(f)
        level["landscape"] = dict(level.get("landscape") or {}, cut=land.get("cut") or {})
        source = os.path.join(p["work"], "shadow_source.json")
        with open(source, "w", encoding="utf-8") as f:
            json.dump(level, f, indent=1)
        out = os.path.join(p["work"], "shadow_shell.json")
        print(f"  {code}: " + run([sys.executable, os.path.join(HERE, "shadow_shell.py"), source,
                                  os.path.join(p["scene"], "scene.gltf"), out, "--swap",
                                  os.path.join(p["work"], "swap.json")]).strip().splitlines()[-1][:160])
        specs.append(f"SM_{code}_ShadowShell={out}")
    return specs


def build_cliffs(maps, ps):
    """The maps' cliff slots as Nanite meshes (tools/level/cliff_mesh.py),
    built in the editor as SM_<CODE>_CliffTess (Scripts/build_ce_cliffs.py,
    chunk 983 with the trial masters)."""
    specs = []
    for code, m in maps.items():
        # cliff_uv: the cliffs drawn by a flat copy with even UVs instead
        # (cliff_mesh.py --flat --conformal), tess or not.
        uv = m.get("cliff_uv")
        if m.get("tess") is False and not uv:
            continue
        p = ps[code]
        out = os.path.join(p["work"], "cliff_mesh.json")
        extra = ["--flat", "--conformal", str(uv)] if uv else []
        print("  " + run([sys.executable, os.path.join(HERE, "cliff_mesh.py"), p["level"],
                          os.path.join(p["scene"], "scene.gltf"), out, "--landscape",
                          os.path.join(p["land"], "landscape.json"), "--swap",
                          os.path.join(p["work"], "swap.json")] + extra).strip().splitlines()[-1][:160])
        specs.append(f"{code}={out}")
    # Translucent slots a conversion left on the opaque terrain mesh (plasma:
    # Yoyorast's beams), as a mesh of their own (level.slot_meshes).
    for code, m in maps.items():
        p = ps[code]
        out = os.path.join(p["work"], "plasma_mesh.json")
        made = run([sys.executable, os.path.join(HERE, "cliff_mesh.py"), p["level"],
                    os.path.join(p["scene"], "scene.gltf"), out, "--parent", "M_CE_Plasma"], check=False)
        if "triangle(s) on M_CE_Plasma" in made:
            print("  " + made.strip().splitlines()[-1][:160])
            specs.append(f"SM_{code}_Plasma={out}")
        elif os.path.exists(out):
            os.remove(out)
    # Rivers (`rivers`): CE's flowing water as a mesh of its own, drawn by
    # M_CE_Ocean: on the shared translucent mesh, whose passes its first
    # slot decides, the water drew as a faint sheen over its bed whatever
    # its depth and absorption (Timberland, 2026-10-14).
    for code, m in maps.items():
        if not m.get("rivers"):
            continue
        p = ps[code]
        out = os.path.join(p["work"], "river_mesh.json")
        made = run([sys.executable, os.path.join(HERE, "cliff_mesh.py"), p["level"],
                    os.path.join(p["scene"], m["rivers"].get("scene", "scene_translucent.gltf")), out, "--parent",
                    # The stream's CE shader: Timberland's a transparent
                    # chicago, Battle Creek's CE water.
                    m["rivers"].get("parent", "M_CE_TransparentAlpha"),
                    "--item", m["rivers"].get("item", "_terrain_1"), "--slot-offset", "0", "--texture", m["rivers"]["textures"][0],
                    "--material", "/Game/MJOLNIR/Water/M_CE_Ocean.M_CE_Ocean"], check=False)
        print("  " + made.strip().splitlines()[-1][:160])
        if "triangle(s) on" in made:
            specs.append(f"SM_{code}_River={out}")
    # Flux beds (`flux.bed`): the river's ground as Flux's capture alone sees
    # it (flux_bed).
    for code, m in maps.items():
        if (m.get("flux") or {}).get("bed") and m.get("rivers"):
            bed = flux_bed(code, m, ps[code])
            if bed:
                specs.append(f"SM_{code}_FluxBed={bed}")
    # The sea's ground (coast `ground_mesh`): CE's scene by its lowest
    # surface, for the coastline's capture alone (flux_coast_ground).
    for code, m in maps.items():
        if ((m.get("flux") or {}).get("coast") or {}).get("ground_mesh"):
            specs.append(f"SM_{code}_FluxGround={flux_coast_ground(code, m, ps[code])}")
    specs += shadow_shells(maps, ps)
    if not specs:
        return
    powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_cliffs.py"],
               env={"MJ_CLIFF_MESHES": ";".join(specs)})
    log = open(os.path.join(PROJECT, "Saved_build_ce_cliffs.log"), encoding="utf-8", errors="replace").read()
    built = [l.split("MJOLNIR cliffs: ", 1)[1] for l in log.splitlines() if "MJOLNIR cliffs: " in l]
    if not built or built[-1] != "built" or "Traceback" in log or len(built) != len(specs) + 1:
        sys.exit("the cliff meshes did not build: see " + os.path.join(PROJECT, "Saved_build_ce_cliffs.log"))
    for line in built[:-1]:
        print("  " + line[:160])


def stage_cook(maps):
    worlds = "+".join(f"/Game/Levels/Halo1/Solo/{m['landscape']}/{m['landscape']}" for m in maps
                      if not m.get("indoor"))
    # StaticMesh too: chunk 983 carries the tessellated cliffs.
    out = powershell(os.path.join(REPO, "tools", "ue", "cook.ps1"),
                     (["-Map", worlds] if worlds else []) + ["-Classes", "Material,MaterialInstanceConstant,StaticMesh"])
    if "BUILD SUCCESSFUL" not in out:
        sys.exit("cook failed:\n" + out[-3000:])
    log = open(os.path.join(PROJECT, "Saved_cook.log"), encoding="utf-8", errors="replace").read()
    errors = [l for l in log.splitlines() if "error X" in l or ": error" in l]
    if errors:
        # The cook only warns when a shader fails; the material then draws
        # the default grey in game.
        sys.exit("shader errors in the cook:\n" + "\n".join(errors[:10]))
    print("  " + "\n  ".join(l for l in out.splitlines() if l.startswith(("cook exit", "retarget"))))


def stage_bake(code, m, p):
    tool_env = {"HCE_PAKS": PAKS,
                "MJOLNIR": os.environ.get("MJOLNIR", "C:/haloce/.claude/worktrees/server-list-hosting-d9e78e/target/release/mjolnir.exe"),
                "EXAMPLES": os.environ.get("EXAMPLES", "C:/haloce/target/debug/examples")}
    if os.path.isdir(p["bake"]):
        for f in glob.glob(os.path.join(p["bake"], "*")):
            if os.path.isfile(f):
                os.remove(f)
    world = f"/Game/Levels/Halo1/Solo/{m['landscape']}/{m['landscape']}"
    out = run([bash(), "tools/level/bake_editor_world.sh", world, str(m["chunk"]), p["level"].replace("\\", "/"),
               bake_sbsp(m, p).replace("\\", "/"), code, p["bake"].replace("\\", "/")],
              env=dict(tool_env, MSYS2_ARG_CONV_EXCL="/Game"))
    if not os.path.exists(os.path.join(p["bake"], f"pakchunk997-MJOLNIRMAP-{code}_P.utoc")):
        sys.exit(f"{code}: no map container baked:\n{out[-2000:]}")
    print(f"  {code}: map container baked")


def scene_reach(p):
    """The map's ground and water across (cm, the diagonal of scene.gltf's
    bounds, from its accessors' min and max), or None."""
    try:
        doc = json.load(open(os.path.join(p["scene"], "scene.gltf"), encoding="utf-8"))
    except FileNotFoundError:
        return None
    lo, hi = [math.inf] * 2, [-math.inf] * 2
    for mesh in doc.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            if "min" in acc and "max" in acc:
                # glTF y up: Unreal's x, y are glTF's x, z.
                for i, k in enumerate((0, 2)):
                    lo[i], hi[i] = min(lo[i], acc["min"][k]), max(hi[i], acc["max"][k])
    if lo[0] == math.inf:
        return None
    return math.hypot(hi[0] - lo[0], hi[1] - lo[1]) * 100.0


def ce_haze(level, reach=None):
    """The map's own CE atmospheric fog (FogColor, FogDensity, FogStart,
    FogOpaque, as its CE surfaces carry it) as Unreal's height fog
    (MJOLNIRLevelLoader environment.haze), over everything: the colour made
    linear (the loader exposes it by the light scale, as the level's
    exposure takes it back out, so it shows as CE's colour), capped at CE's
    maximum density, starting where CE's does and thick enough to reach the
    cap at CE's opaque distance (CE's own is linear in distance; Unreal's
    exponential comes within a few percent of it). The opaque CE surfaces'
    (M_CE_Environment*) own fog is turned off, so they are not fogged twice;
    the transparent ones keep theirs, which fades them as CE did (Unreal's
    fog only darkens an additive surface). Blood Gulch's warm haze (0.4
    by 100 wu) had become Death Island's tuned one, a black fog at 1/200 of
    the colour that darkened the far cliffs (2026-10-13). Cut off past the
    map's own ground and water (`reach`, cm; at least 800 m), short of the
    sky, which CE never fogged and sits 100 km and more out. None when no
    surface carries a fog."""
    for item in level.get("decor") or []:
        for m in item.get("materials") or []:
            sc = m.get("scalars") if isinstance(m, dict) else None
            color = (m.get("vectors") or {}).get("FogColor") if isinstance(m, dict) else None
            if not sc or not color or not sc.get("FogDensity"):
                continue
            density, start, opaque = sc["FogDensity"], sc.get("FogStart", 0.0), sc.get("FogOpaque", 30480.0)
            lin = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in color[:3]]
            haze = {"density": round(-math.log(max(1.0 - min(density, 0.99), 0.01)) / max(opaque, 1.0) * 1000.0, 5),
                    "falloff": 0.02, "start": round(start, 1),
                    "cutoff": round(max(80000.0, reach or 0.0)), "max_opacity": round(density, 3),
                    "color": [round(c, 5) for c in lin]}
            for other in level.get("decor") or []:
                for mat in other.get("materials") or []:
                    if (isinstance(mat, dict) and (mat.get("scalars") or {}).get("FogDensity")
                            and "/M_CE_Environment" in str(mat.get("parent", ""))):
                        mat["scalars"]["FogDensity"] = 0.0
            return haze
    return None


def horizon_skirt(code, m, p, level):
    """A map's land to the horizon (`horizon`: {z: cm, reach: cm}): four
    flat strips round the map's bounds (scene.gltf's, so none crosses the
    map), `z` just under its rim, out `reach` (50 km), in its ground's own
    material (its landscape's slot; CE's lightmap off: the strips have
    none), for the haze to fade into the sky. Past Infinity's rim there was
    nothing under the sky but a black band (2026-10-16). An optional
    `material` object replaces the ground spec, with no corner overlap
    so translucent water does not blend twice (TST, 2026-10-19)."""
    hz = m.get("horizon")
    if not hz:
        return []
    custom = "material" in hz
    if custom and not isinstance(hz["material"], dict):
        raise SystemExit(f"{code}: horizon.material must be a material-spec object")
    import numpy as np
    from refine_water_gltf import read_accessor
    doc = json.load(open(os.path.join(p["scene"], "scene.gltf"), encoding="utf-8"))
    data = open(os.path.join(p["scene"], doc["buffers"][0]["uri"]), "rb").read()
    lo, hi = np.array([np.inf, np.inf]), np.array([-np.inf, -np.inf])
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            if "sky" in doc["materials"][prim["material"]]["name"].lower():
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            xy = np.stack([pos[:, 0] * 100, pos[:, 2] * 100], 1)
            lo, hi = np.minimum(lo, xy.min(0)), np.maximum(hi, xy.max(0))
    if custom:
        mat = json.loads(json.dumps(hz["material"]))
    else:
        # The ground's material: the landscape's own slot on the terrain item
        # (terrain slot i is the glTF's material i - 1).
        land = json.load(open(os.path.join(p["land"], "landscape.json"), encoding="utf-8"))
        names = [mt["name"] for mt in doc["materials"]]
        terrain = next(i for i in level["decor"] if f"/SM_{code}_Terrain." in str(i.get("mesh", "")))
        entry = terrain["materials"][names.index(land["slot"]) + 1]
        mat = json.loads(json.dumps(entry))
        for k in ("HasLightmap", "HasBake"):
            mat.setdefault("scalars", {})[k] = 0.0
        # The ground's mean colour, not its base map: tiled, the map's own paths
        # and track repeated out to the horizon (Infinity, 2026-10-17).
        from PIL import Image
        px = np.asarray(Image.open(os.path.join(p["land"], "base.png")).convert("RGB"), np.float64) / 255.0
        ground = np.asarray(Image.open(os.path.join(p["land"], "landmask.png")).convert("L").resize(
            px.shape[1::-1]), np.float64) < 128
        mean = px[ground].mean(0) if ground.any() else px.reshape(-1, 3).mean(0)
        mat["textures"]["Base"] = WHITE
        mat.setdefault("vectors", {})["MaterialColor"] = [round(float(c), 3) for c in mean] + [1.0]
    origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
    R, z = float(hz.get("reach", 5000000.0)), float(hz["z"])
    # The middle strips overlap the side ones by 20 m: edge to edge, a
    # hairline of sky showed down each seam from above.
    o = 0.0 if custom else 2000.0
    rects = [(-R, -R, lo[0], R), (hi[0], -R, R, R), (lo[0] - o, -R, hi[0] + o, lo[1]), (lo[0] - o, hi[1], hi[0] + o, R)]
    out = []
    for i, (x0, y0, x1, y1) in enumerate(rects):
        # The ground's maps tiled at the map's own size: one copy over a
        # 50 km strip drew it as streaks to the horizon (Infinity, 2026-10-17).
        strip = json.loads(json.dumps(mat))
        if not custom:
            strip.setdefault("vectors", {})["BaseXform"] = [round((x1 - x0) / (hi[0] - lo[0]), 2),
                                                            round((y1 - y0) / (hi[1] - lo[1]), 2), 0.0, 0.0]
        out.append({"id": f"horizon_{i}", "mesh": "/Engine/BasicShapes/Plane.Plane",
                    "pos": [round((x0 + x1) / 2 - origin[0]), round((y0 + y1) / 2 - origin[1]), round(z - origin[2])],
                    "scale": [round((x1 - x0) / 100.0, 1), round((y1 - y0) / 100.0, 1), 1.0],
                    "materials": [strip], "cast_shadow": False})
    print(f"  horizon: 4 strip(s) round {((hi - lo) / 100).round()} m at {z / 100:g} m, out {R / 100000:g} km")
    return out


def flux_ground(code, level):
    """What the Flux ground capture sees: CE's ground and the cliffs' copy."""
    return [item["id"] for item in level.get("decor") or []
            if f"/SM_{code}_Terrain." in str(item.get("mesh", ""))] + ["__cliff_tess"]


def flux_coast(k, land, code, level):
    """The sea as B30's (MJOLNIRLevelLoader Effects.fluxCoast): a coastline
    domain over the landscape (`margin` cm round it, `cell` cm cells), the
    sea at `water` cm. `floor`: the base maps of CE's sea floor, kept out of
    the ground capture (`floor` slots by ground item): Death Island's lies a
    metre under the water everywhere, so the whole domain was surf, a flat
    milky square with a hard edge against the open sea round it."""
    x, y, w, h = land["rect"]
    margin, cell = k.get("margin", 6000.0), int(k.get("cell", 100))
    res = [int(math.ceil((w + 2 * margin) / cell / 32.0)) * 32, int(math.ceil((h + 2 * margin) / cell / 32.0)) * 32]
    tokens = [t.lower() for t in k.get("floor", ["bitmaps_underwater"])]
    ground = set(flux_ground(code, level))
    floor = {}
    for item in level.get("decor") or []:
        if item.get("id") not in ground:
            continue
        for i, entry in enumerate(item.get("materials") or []):
            base = str((entry.get("textures") or {}).get("Base", "")).lower() if isinstance(entry, dict) else ""
            if any(t in base for t in tokens):
                floor.setdefault(item["id"], []).append(i)
    return {"centre": [round(x + w / 2), round(y + h / 2)], "res": res, "cell": cell,
            "height": k.get("height", 10000.0), "water": k["water"], "floor": floor, "swell": k.get("swell", 140),
            "seabed": bool(k.get("seabed"))}


PHANTOM = "/Game/FluidFlux/Simulation/Materials/M_PhantomMesh_3.M_PhantomMesh_3"
# The bed's material in the level: plain and opaque, the decor drawn only into
# scene captures (MJOLNIRLevelLoader `capture_only`); Flux's phantom
# material drew in none of ours.
WHITE = "/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture"
BED_MATERIAL = "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"


def flux_domain_rect(fx, river):
    """The river domain's rectangle (cm) and bottom, as flux_spec makes it."""
    pts = river["positions"] + [f["pos"] for f in fx.get("feeds", [])]
    margin = fx.get("margin", 600.0)
    lo = [min(q[i] for q in pts) - margin for i in range(2)]
    hi = [max(q[i] for q in pts) + margin for i in range(2)]
    return lo, hi, min(q[2] for q in pts) - 300.0


def flux_bed(code, m, p, cell=50.0):
    """A river's bed for Fluid Flux's ground capture alone (`flux.bed`): the
    lowest surface at every point over its domain, as a heightfield mesh in
    Flux's phantom material (drawn only in its capture). Flux captures the
    ground from above, so wherever rock overhangs a river it takes the rock's
    top for the bed: Battle Creek's creek runs under overhangs coming down
    to the water over 61% of its bed, and the water stood in sheets against
    the rock (2026-10-16). The lowest surface is the bed under an overhang
    and a wall's foot rising into it at the canyon's sides. Writes
    <work>/flux_bed.json (cliff_mesh.py's form) and returns its path."""
    import numpy as np
    from refine_water_gltf import read_accessor
    from build_landscape import raster
    river = json.load(open(os.path.join(p["work"], "river_mesh.json"), encoding="utf-8"))
    lo, hi, _ = flux_domain_rect(m["flux"], river)
    doc = json.load(open(os.path.join(p["scene"], "scene.gltf"), encoding="utf-8"))
    data = open(os.path.join(p["scene"], doc["buffers"][0]["uri"]), "rb").read()
    tris = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            if any(w in name for w in ("sky", "water", "fog")):
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            P = np.stack([pos[:, 0] * 100, pos[:, 2] * 100, pos[:, 1] * 100], 1)
            T = P[read_accessor(doc, data, prim["indices"]).reshape(-1, 3)]
            keep = ((T[..., 0].max(1) >= lo[0]) & (T[..., 0].min(1) <= hi[0])
                    & (T[..., 1].max(1) >= lo[1]) & (T[..., 1].min(1) <= hi[1]))
            tris.append(T[keep])
    tris = np.concatenate(tris)
    nx, ny = int(np.ceil((hi[0] - lo[0]) / cell)) + 1, int(np.ceil((hi[1] - lo[1]) / cell)) + 1
    size = max(nx, ny)
    z, _ = raster(tris, np.array(lo), cell, size, [])
    top, _ = raster(tris, np.array(lo), cell, size, [], highest=True)
    z, top = z[:ny, :nx], top[:ny, :nx]
    # The lowest surface only inside CE's own water (the river mesh, a metre
    # round it); everywhere else the top one. On the lowest surface
    # everywhere, the water ran in under every overhang and wall foot round
    # the creek and inside the walls, and drew out of the cliff faces as
    # falls (2026-10-16).
    rv = np.asarray(river["positions"])[np.asarray(river["indices"]).reshape(-1, 3)]
    rz, _ = raster(rv, np.array(lo), cell, size, [])
    wet = np.isfinite(rz[:ny, :nx])
    k = max(1, int(round(100.0 / cell)))
    grown = wet.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            grown |= np.roll(np.roll(wet, dy, 0), dx, 1)
    z = np.where(grown, z, top)
    # Nothing under a point (off the map): high ground, so no water goes. All
    # of it no more than 4 m over the water: ground far up the domain (off
    # the map at 37 m, cliff tops) took a sheet of water 6-7 m deep at the
    # domain's top in Flux, which ran down the canyon walls (2026-10-16).
    cap = max(q["pos"][2] for q in m["flux"].get("feeds", [])) + 400.0 if m["flux"].get("feeds") else np.nanmax(z)
    z = np.minimum(np.where(np.isfinite(z), z, cap), cap)
    xs, ys = lo[0] + np.arange(nx) * cell, lo[1] + np.arange(ny) * cell
    positions = [[round(float(xs[i]), 1), round(float(ys[j]), 1), round(float(z[j, i]), 1)]
                 for j in range(ny) for i in range(nx)]
    idx = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = j * nx + i, j * nx + i + 1, (j + 1) * nx + i, (j + 1) * nx + i + 1
            # Both windings: one-sided, wound the wrong way for a capture
            # from above, the bed was culled and Flux saw no ground at all.
            idx += [a, c, b, b, c, d, a, b, c, b, d, c]
    n = len(positions)
    out = os.path.join(p["work"], "flux_bed.json")
    json.dump({"item": "", "slots": [0], "names": ["flux_bed"], "positions": positions,
               "normals": [[0.0, 0.0, 1.0]] * n, "indices": idx,
               # UVs a corner (build_ce_cliffs.py takes them per index).
               "uv0": [[0.0, 0.0]] * len(idx), "uv1": [[0.0, 0.0]] * len(idx),
               "sections": [0] * (len(idx) // 3), "weight": [1.0] * n, "nanite": False, "material": PHANTOM},
              open(out, "w", encoding="utf-8"))
    print(f"  {code}: flux bed {nx} x {ny} at {cell:g} cm, z {z.min() / 100:.1f}..{z.max() / 100:.1f} m")
    return out


def flux_coast_ground(code, m, p, cell=100.0, cap=400.0, under=50.0):
    """The sea's ground for Fluid Flux's coastline capture alone (coast
    `ground_mesh`): CE's scene as a heightfield of its lowest surface, in
    place of CE's terrain in the capture. Flux captures from above, so at a
    cliff's foot it took the overhang over the beach for the ground, and the
    coastline's water stood up in glassy sheets hanging from it along Death
    Island's sea cliffs (2026-10-18). The lowest surface is the sand under
    the overhang; walls are stepped back into the rock (below). Surfaces more than `under` cm below the water are left out
    (the landscape's seabed is the floor there, and CE's flat sea floor lies a
    metre down everywhere), and nothing stands more than `cap` cm over the
    water (cliff tops), as for the river beds (flux_bed). The mesh lies 5 cm
    under what it copies, so the few seconds it is drawn (the loader hides
    it after the capture) it stays under the sand and inside the rock.
    Writes <work>/flux_ground.json (cliff_mesh.py's form) and returns it."""
    import numpy as np
    from refine_water_gltf import read_accessor
    from build_landscape import raster
    water = float(m["flux"]["coast"]["water"])
    doc = json.load(open(os.path.join(p["scene"], "scene.gltf"), encoding="utf-8"))
    data = open(os.path.join(p["scene"], doc["buffers"][0]["uri"]), "rb").read()
    tris = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            if any(w in name for w in ("sky", "water", "fog")):
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            P = np.stack([pos[:, 0] * 100, pos[:, 2] * 100, pos[:, 1] * 100], 1)
            T = P[read_accessor(doc, data, prim["indices"]).reshape(-1, 3)]
            tris.append(T[T[..., 2].max(1) >= water - under])
    tris = np.concatenate(tris)
    lo = np.floor(tris[..., :2].reshape(-1, 2).min(0) / cell) * cell
    hi = np.ceil(tris[..., :2].reshape(-1, 2).max(0) / cell) * cell
    nx, ny = int((hi[0] - lo[0]) / cell) + 1, int((hi[1] - lo[1]) / cell) + 1
    size = max(nx, ny)
    z, _ = raster(tris, lo, cell, size, [])
    z = z[:ny, :nx]
    z = np.where(np.isfinite(z), np.minimum(z, water + cap), np.nan)
    # Walls stepped back into the rock. The coastline's water is a heightfield
    # that also draws a thin film over the ground near the shore: where the
    # sand at a cliff's foot (Death Island's lies under the water) meets the
    # wall it bridged the step in one cell, a sheet standing up in front of
    # the rock. Ground a wall's height within `back` cells of low ground
    # reads as just over the water, so the step lies that far inside the rock
    # and the water meets the wall flat. Lowering the captured ground never
    # shows water: its film then lies under the real surface. At 1.5 m the
    # ledges at the walls' feet still stood sheets a metre high (2026-10-18).
    back = 4
    low = ~np.isfinite(z) | (z <= water + 30.0)
    near = np.pad(low, back, constant_values=True)
    grown = np.zeros_like(low)
    for dy in range(-back, back + 1):
        for dx in range(-back, back + 1):
            grown |= near[back + dy:back + dy + ny, back + dx:back + dx + nx]
    stepped = np.isfinite(z) & (z > water + 40.0) & grown
    z = np.where(stepped, water + 30.0, z) - 5.0
    have = np.isfinite(z)
    index = np.full((ny, nx), -1, np.int64)
    index[have] = np.arange(int(have.sum()))
    jj, ii = np.nonzero(have)
    positions = [[round(float(lo[0] + i * cell), 1), round(float(lo[1] + j * cell), 1), round(float(z[j, i]), 1)]
                 for j, i in zip(jj, ii)]
    idx = []
    quad = have[:-1, :-1] & have[:-1, 1:] & have[1:, :-1] & have[1:, 1:]
    for j, i in zip(*np.nonzero(quad)):
        a, b, c, d = index[j, i], index[j, i + 1], index[j + 1, i], index[j + 1, i + 1]
        # Both windings, as flux_bed: one-sided, the capture culled it.
        idx += [int(a), int(c), int(b), int(b), int(c), int(d), int(a), int(b), int(c), int(b), int(d), int(c)]
    n = len(positions)
    out = os.path.join(p["work"], "flux_ground.json")
    json.dump({"item": "", "slots": [0], "names": ["flux_ground"], "positions": positions,
               "normals": [[0.0, 0.0, 1.0]] * n, "indices": idx,
               "uv0": [[0.0, 0.0]] * len(idx), "uv1": [[0.0, 0.0]] * len(idx),
               "sections": [0] * (len(idx) // 3), "weight": [1.0] * n, "nanite": False, "material": PHANTOM},
              open(out, "w", encoding="utf-8"))
    print(f"  {code}: flux coast ground {nx} x {ny} at {cell:g} cm, {n} point(s), {len(idx) // 12} quad(s) "
          f"(both sides), {int(stepped.sum())} wall cell(s) stepped back, "
          f"z {np.nanmin(z) / 100:.1f}..{np.nanmax(z) / 100:.1f} m")
    return out


def flux_spec(code, fx, river, level):
    """Fluid Flux over CE's river (MJOLNIRLevelLoader Effects.flux): one
    domain round the river mesh, `fx.feeds` adding water where CE's water
    falls in (BE_FluxMode 0 Add, at a fixed rate, or 2 Adjust, the default:
    up to the source's Z), and grid sources along every flat stretch.
    level_mode 2 fills to CE's water Z; the default 1 preserves existing
    maps' Set sources, which set depth from level_strength. The grid source
    lifetime is controlled separately by hold (otherwise they prime only)."""
    pos, idx = river["positions"], river["indices"]
    # Set sources every `grid` cm over the river's surface, each at CE's water
    # level there, fill the river at the start (`prime`) and are taken away
    # after it: held for good, they stopped the water flowing (a Set source
    # takes away what runs in) and the river ended in the first pool below
    # Timberland's falls; 220 of them at 4 m cost 80 ms a frame (each a draw
    # a simulation step). Left alone, the water runs pool to pool over the
    # bed's humps (2026-10-14).
    grid, cell = fx.get("grid", 1200.0), fx.get("cell", 25.0)
    cells = {}
    for t in range(0, len(idx), 3):
        a, b, c = (pos[idx[t]], pos[idx[t + 1]], pos[idx[t + 2]])
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        length = math.sqrt(sum(x * x for x in n)) or 1.0
        # The rapids (sloped water) are left to the feed: a level source
        # on a slope floods its low side.
        if abs(n[2]) / length < 0.98:
            continue
        for i in range(9):
            for j in range(9 - i):
                p = [a[k] + i / 8.0 * u[k] + j / 8.0 * v[k] for k in range(3)]
                cells.setdefault((math.floor(p[0] / grid), math.floor(p[1] / grid)), []).append(p)
    levels = [[round(sum(q[k] for q in ps) / len(ps)) for k in range(3)]
              for ps in cells.values() if len(ps) >= fx.get("min_samples", 3)]
    feeds = fx.get("feeds", [])
    # A waterfall's feed is Add (mode 0) at the head of the stream above
    # it, so the water runs to the lip and pours over: Adjust at the lip held
    # a column of water to its Z over the void, drawn as a dark block, and a
    # feed at the lip pooled on the plateau behind it (Timberland, 2026-10-14).
    # Add has no level to stop at: volume 3 there flooded the gorge, 1 ran
    # thin, 2 fills the lip.
    sources = [{"pos": f["pos"], "scale": f.get("scale", 1.0), "volume": f.get("volume", 8.0),
                "mode": f.get("mode", 2)} for f in feeds]
    # No velocity on a Set source: it refills each step what its push
    # carried off, so every one became an endless spring and the river
    # flooded its whole domain in two minutes (2026-10-14).
    # `hold`: the level sources stay. A creek that is one flat pool at CE's
    # level (Battle Creek's) has no slope to carry the feed off: with only
    # the outlet to drain it, the feed overfilled it over its banks and out
    # to the domain's edge, where the water stopped in a straight line
    # (2026-10-16).
    # Adjust (level_mode 2) holds the source's world Z. Set (the existing
    # default 1) holds Volume as depth: at strength 1 it drained TST's pond
    # to a 1 cm film despite its sources standing a metre above the bed.
    sources += [{"pos": q, "scale": fx.get("level_scale", 1.0), "volume": fx.get("level_strength", 1.0),
                 "mode": fx.get("level_mode", 1),
                 "prime": not fx.get("hold")} for q in levels]
    # One Set source stays, at the river's end (`outlet`, or the level point
    # furthest from the first feed): the feed never stops, and with no way
    # out the river would rise until it flooded the valley. Not in a pool
    # short of the end: it took all the water and the river stopped there.
    # Feeds along a long river (Timberland's is 280 m) keep it running to the
    # end: from the falls alone it soaked into the bed halfway.
    # `outlet: false`: none. With an Adjust feed (up to CE's level) nothing
    # overfills, and a Set source drains its neighbourhood to a film: Battle
    # Creek's south end lay dry round it (2026-10-16).
    outlet = fx.get("outlet")
    if outlet is False:
        outlet = None
    elif not outlet and levels:
        first = feeds[0]["pos"] if feeds else levels[0]
        outlet = max(levels, key=lambda q: math.hypot(q[0] - first[0], q[1] - first[1]))
    if outlet:
        sources.append({"pos": outlet, "scale": fx.get("level_scale", 1.0), "volume": 1.0, "mode": 1})
    pts = pos + [f["pos"] for f in feeds]
    margin = fx.get("margin", 600.0)
    lo = [min(q[i] for q in pts) - margin for i in range(2)]
    hi = [max(q[i] for q in pts) + margin for i in range(2)]
    # Cells in multiples of 32 per side (the simulation's thread groups).
    res = [int(math.ceil((hi[i] - lo[i]) / cell / 32.0)) * 32 for i in range(2)]
    height = fx.get("height", 5000.0)
    bottom = min(q[2] for q in pts) - 300.0
    domain = {"centre": [round((lo[0] + hi[0]) / 2), round((lo[1] + hi[1]) / 2), round(bottom + 0.75 * height)],
              "res": res, "cell": cell, "height": height}
    # Out of the ground capture: everything the loader spawns but CE's
    # ground and the cliffs' copy; CE's own river mesh hidden outright.
    ground = flux_ground(code, level)
    hide = [f"__slot_mesh_{i + 1}" for i, s in enumerate(level.get("slot_meshes") or [])
            if f"SM_{code}_River" in s.get("mesh", "")]
    spec = {"domain": domain, "sources": sources, "ground": ground, "hide": hide}
    for key in ("color_preset", "surface_vectors"):
        if key in fx:
            spec[key] = fx[key]
    return spec


def flux_state(code, p, flux):
    """The river's baked water (MJOLNIRLevelLoader's `mjolnir_flux_bake`,
    run in game once the river has settled): <work>/flux_state, or picked up
    from the game's map folder where the bake wrote it. Kept only when it was
    baked for this domain; the loader checks again and fills the river the old
    way otherwise."""
    work = os.path.join(p["work"], "flux_state")
    baked = os.path.join(UE4SS, "MJOLNIRMaps", code, "flux_state")
    if os.path.exists(os.path.join(baked, "state.json")) and (
            not os.path.exists(os.path.join(work, "state.json"))
            or os.path.getmtime(os.path.join(baked, "state.json")) > os.path.getmtime(os.path.join(work, "state.json"))):
        shutil.copytree(baked, work, dirs_exist_ok=True)
    path = os.path.join(work, "state.json")
    if not os.path.exists(path):
        return None
    state = json.load(open(path, encoding="utf-8"))
    d = flux.get("domain") or {}
    fits = (state.get("res") == d.get("res") and state.get("cell") == d.get("cell")
            and state.get("height_cm") == d.get("height")
            and all(abs(a - b) < 1 for a, b in zip(state.get("centre", []), d.get("centre", []))))
    if not fits:
        print(f"  {code}: the baked flux state is for another domain; rebake it (mjolnir_flux_bake)")
        return None
    return state


def stage_assemble(code, m, p):
    baked = bool(m.get("bake_foliage"))
    land = json.load(open(os.path.join(p["land"], "landscape.json"), encoding="utf-8"))
    fol = None if m.get("indoor") else json.load(open(os.path.join(p["foliage"], "foliage.json"), encoding="utf-8"))
    level = json.load(open(p["level"], encoding="utf-8"))
    level["landscape"] = {k: land[k] for k in ("material", "cut", "pbr", "cliff") if k in land}
    # The masters this pipeline builds read the deformation map's centre from
    # the game's globals (FootFromMPC): the loader stops following it.
    if isinstance(level["landscape"].get("pbr"), dict):
        level["landscape"]["pbr"]["foot_mpc"] = True
    if m.get("indoor"):
        level["landscape"]["indoor"] = True
    # `ground_looks`: some ground slots' own parameters over the ground's
    # (MJOLNIRLevelLoader cut.looks), by shader name substring: Ice Fields'
    # ice patches as ice.
    looks = []
    for look in m.get("ground_looks") or []:
        doc = json.load(open(os.path.join(p["scene"], "scene.gltf"), encoding="utf-8"))
        slots = [i + 1 for i, mt in enumerate(doc["materials"])
                 if any(x in mt.get("name", "").lower() for x in look["shaders"])]
        if slots:
            looks.append({"slots": slots, "vectors": look.get("vectors") or {}, "scalars": look.get("scalars") or {}})
    if looks and isinstance(level["landscape"].get("cut"), dict):
        level["landscape"]["cut"]["looks"] = looks
    plasma = os.path.join(p["work"], "plasma_mesh.json")
    if os.path.exists(plasma):
        spec = json.load(open(plasma, encoding="utf-8"))
        level["slot_meshes"] = [{"mesh": f"/Game/MJOLNIR/CETrial/SM_{code}_Plasma.SM_{code}_Plasma",
                                 "item": spec["item"], "slots": spec["slots"]}]
    river = os.path.join(p["work"], "river_mesh.json")
    # `rivers.flux_only`: the river is Fluid Flux's alone; CE's stream (its
    # slots, the river mesh) goes, the mesh kept only for the domain.
    if m.get("rivers") and os.path.exists(river) and not m["rivers"].get("flux_only"):
        spec = json.load(open(river, encoding="utf-8"))
        level.setdefault("slot_meshes", []).append({
            "mesh": f"/Game/MJOLNIR/CETrial/SM_{code}_River.SM_{code}_River", "item": spec["item"],
            "slots": spec["slots"]})
    cliff = level["landscape"].get("cliff")
    if isinstance(cliff, dict):
        cliff["fill_dir"] = CLIFF_FILL_DIR
        if m.get("cliff_scalars"):
            cliff["scalars"] = dict(m["cliff_scalars"])
        mesh = os.path.join(p["work"], "cliff_mesh.json")
        if (m.get("tess") is not False or m.get("cliff_uv")) and os.path.exists(mesh):
            spec = json.load(open(mesh, encoding="utf-8"))
            # `tess` as an object: the map's own over TESS (Rat Race's
            # tunnels: a wall pushed 30 cm into a 3 m passage).
            own = m["tess"] if isinstance(m.get("tess"), dict) else {}
            cliff["tess"] = dict(TESS, **own, mesh=f"/Game/MJOLNIR/CETrial/SM_{code}_CliffTess.SM_{code}_CliffTess",
                                 item=spec["item"], slots=spec["slots"])
    if os.path.exists(os.path.join(p["work"], "shadow_shell.json")):
        level["shadow_shell"] = {"mesh": f"/Game/MJOLNIR/CETrial/SM_{code}_ShadowShell.SM_{code}_ShadowShell"}
    if fol:
        level["foliage"] = {"file": "foliage.bin", "wind": WIND, "groups": list(fol["groups"])}
        shutil.copyfile(os.path.join(p["foliage"], "foliage.bin"), os.path.join(p["work"], "foliage.bin"))
    # Rivers: CE's flowing water (a transparent shader scrolling a stream
    # texture, not shader_water) drawn by M_CE_Ocean instead: still (no
    # swell), its ripples running along CE's own UVs, clear over its bed.
    # Timberland's stream was a ghost of a texture over a dirt path
    # (2026-10-14).
    if m.get("rivers"):
        rv = m["rivers"]
        n = 0
        for item in level.get("decor") or []:
            mats = item.get("materials") if isinstance(item, dict) else None
            for i, entry in enumerate(mats or []):
                tex = json.dumps(entry.get("textures", {}) if isinstance(entry, dict) else {}).lower()
                if any(t in tex for t in rv.get("textures", [])):
                    # CE water's background pass (Battle Creek's stream): a
                    # second copy of the surface; the river mesh is the one.
                    if "M_CE_WaterBackground" in str(entry.get("parent", "")) or rv.get("flux_only"):
                        mats[i] = HIDDEN
                        continue
                    spec = json.loads(json.dumps(rv["spec"]))
                    spec["parent"] = "/Game/MJOLNIR/Water/M_CE_Ocean.M_CE_Ocean"
                    mats[i] = spec
                    n += 1
        print(f"  {code}: {n} river slot(s) as M_CE_Ocean")
        # The game's river spray along it (MJOLNIRLevelLoader Effects).
        fx = level.setdefault("effects", {"placed": [], "camera": []})
        for pos in rv.get("splashes", []):
            fx.setdefault("placed", []).append({"system": RIVER_SPLASH, "pos": pos})
    # Waterfalls (MJOLNIRLevelLoader Effects.waterfalls): the game's large
    # waterfall over CE's flat card, which is hidden by its textures' names.
    if m.get("waterfalls"):
        wf = m["waterfalls"]
        level["waterfalls"] = wf["falls"]
        tokens = [t.lower() for t in wf.get("hide", [])]
        for item in level.get("decor") or []:
            mats = item.get("materials") if isinstance(item, dict) else None
            for i, entry in enumerate(mats or []):
                tex = json.dumps((entry or {}).get("textures", {}) if isinstance(entry, dict) else {}).lower()
                if any(t in tex for t in tokens):
                    mats[i] = HIDDEN
    if m.get("flux") and os.path.exists(river):
        level["flux"] = flux_spec(code, m["flux"], json.load(open(river, encoding="utf-8")), level)
        state = flux_state(code, p, level["flux"])
        if state:
            level["flux"]["state"] = state
            print(f"  {code}: flux river starts from its baked state")
        # The bed Flux alone sees (flux_bed), its only ground.
        if m["flux"].get("bed") and os.path.exists(os.path.join(p["work"], "flux_bed.json")):
            origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
            level["decor"].append({"id": f"{code.lower()}_flux_bed",
                                   "mesh": f"/Game/MJOLNIR/CETrial/SM_{code}_FluxBed.SM_{code}_FluxBed",
                                   "pos": [-origin[0], -origin[1], -origin[2]],
                                   "materials": [BED_MATERIAL], "capture_only": True, "cast_shadow": False})
            level["flux"]["ground"] = [f"{code.lower()}_flux_bed"]
        print(f"  {code}: flux {level['flux']['domain']['res']} at {level['flux']['domain']['cell']} cm, "
              f"{len(level['flux']['sources'])} source(s)")
    if (m.get("flux") or {}).get("coast"):
        flux = level.setdefault("flux", {})
        flux["coast"] = flux_coast(m["flux"]["coast"], land, code, level)
        # With a seabed, CE's own flat sea floor goes: the landscape's floor
        # covers its rectangle, and past it the old floor (Yoyorast's 1.5 m
        # down) drew the open sea pale and shallow, a hard square round the
        # coastline (2026-10-15).
        if flux["coast"]["seabed"]:
            ids = {item["id"]: item for item in level.get("decor") or []}
            deep = deep_floor(m, p, ids, flux["coast"]["floor"]) + sea_sand(code, m, level, ids, flux["coast"]["floor"])
            for key, slots in flux["coast"]["floor"].items():
                for i in slots:
                    ids[key]["materials"][i] = HIDDEN
            level["decor"] += deep
        flux.setdefault("ground", flux_ground(code, level))
        # `ground_mesh`: the capture sees CE's scene by its lowest surface
        # (flux_coast_ground) instead of CE's terrain, whose overhangs stood
        # the water up in sheets at the cliffs' feet.
        if m["flux"]["coast"].get("ground_mesh") and os.path.exists(os.path.join(p["work"], "flux_ground.json")):
            origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
            level["decor"].append({"id": f"{code.lower()}_flux_ground",
                                   "mesh": f"/Game/MJOLNIR/CETrial/SM_{code}_FluxGround.SM_{code}_FluxGround",
                                   "pos": [-origin[0], -origin[1], -origin[2]],
                                   "materials": [BED_MATERIAL], "capture_only": True, "cast_shadow": False})
            flux["ground"] = [f"{code.lower()}_flux_ground"]
        # The sea is Flux's alone. Our own water mesh (SM_<code>_Water) is
        # hidden (it stays in the level, the loader's sea height), and CE's
        # background water slot with it. Sunk under Flux's as a fallback for
        # Flux's dropouts (its grid goes with the horizon on the frustum's
        # edge) it showed as a second sea, through the shallows, under a
        # player wading, and down the holes in the sea floor (Yoyorast,
        # 2026-10-16). A dropout shows the seabed now (sea_sand).
        water = [item["id"] for item in level.get("decor") or []
                 if f"/SM_{code}_Water." in str(item.get("mesh", "")) and not item["id"].endswith("_sand")]
        flux["hide"] = sorted(set(flux.get("hide", []) + water))
        n = 0
        for item in level.get("decor") or []:
            for i, entry in enumerate(item.get("materials") or []):
                if isinstance(entry, dict) and "M_CE_WaterBackground" in str(entry.get("parent", "")):
                    item["materials"][i] = HIDDEN
                    n += 1
        print(f"  {code}: only Flux's sea ({len(water)} water mesh(es) hidden, {n} background water slot(s))")
        print(f"  {code}: flux coast {flux['coast']['res']} at {flux['coast']['cell']} cm, sea at {flux['coast']['water']}")
    if m.get("water"):
        water = level.setdefault("environment", {}).setdefault("water", {})
        water.setdefault("params", {}).update(m["water"])
    if (m.get("flux") or {}).get("coast"):
        level.setdefault("flux", {})["dry"] = flux_dry_zones(m, p, level)
        surf = structure_surf(m, p, level)
        if surf:
            fx = level.setdefault("effects", {"placed": [], "camera": []})
            fx.setdefault("placed", []).extend(surf)
    swap_path = os.path.join(p["work"], "swap.json")
    if os.path.exists(swap_path):
        swap = json.load(open(swap_path, encoding="utf-8"))
        hidden = 0
        for item in level.get("decor") or []:
            mats = item.get("materials") if isinstance(item, dict) else None
            for i, entry in enumerate(mats or []):
                if entry in swap["hide"]:
                    mats[i] = HIDDEN
                    hidden += 1
        swapped_decor = swap["decor"]
        if m.get("rock_roughness") is not None:
            if not m.get("bake_foliage"):
                sys.exit(f"{code}: rock_roughness requires bake_foliage")
            from foliage_bake import runtime_decor
            swapped_decor = runtime_decor(swapped_decor, m["rock_roughness"])
            print(f"  {code}: {len(swap['decor']) - len(swapped_decor)} rock MIC(s) kept entirely in the baked world")
        level["decor"] = (level.get("decor") or []) + swapped_decor
        if swap.get("effects"):
            # Over any the level has already (a river's spray).
            before = (level.get("effects") or {}).get("placed") or []
            level["effects"] = swap["effects"]
            level["effects"]["placed"] = list(swap["effects"].get("placed") or []) + before
        leaf = leaf_groups(swap)
        for records, group in leaf:
            append_foliage(os.path.join(p["work"], "foliage.bin"), records)
            level["foliage"]["groups"].append(group)
        if leaf:
            print(f"  {code}: {sum(len(r) for r, _ in leaf)} leaf cluster(s) on the swapped trees, "
                  f"{sum(len(r) for r, g in leaf if g.get('static'))} small ones still")
        print(f"  {code}: {swap['count']} scenery object(s) swapped, {hidden} CE slot(s) hidden")
    # After the swap: the swap hides CE scenery by its slot's material as the
    # spec has it, and the haze turns the terrain materials' own fog off, so
    # run first it left every swapped CE rock and tree drawn under its
    # stand-in (2026-10-13).
    if m.get("haze") == "ce" and isinstance(level["landscape"].get("pbr"), dict):
        haze = ce_haze(level, scene_reach(p))
        # A Flux coast: the haze out past the far ocean (Flux draws it some
        # 10 km out, the sky mesh is far beyond) and free to thicken there,
        # so the sea fades into the sky. Cut off at the map's reach and held
        # to CE's 25%, the far ocean was a flat grey band under a hard
        # horizon (Yoyorast, 2026-10-15). `haze_color` sets it to the sky's
        # colour at the horizon.
        coast = (m.get("flux") or {}).get("coast") or {}
        if haze and coast:
            haze["cutoff"] = max(haze["cutoff"], coast.get("haze_cutoff", 1500000))
            haze["max_opacity"] = coast.get("haze_opacity", 1.0)
            if coast.get("haze_color"):
                haze["color"] = list(coast["haze_color"])
        if haze:
            level["landscape"]["pbr"]["haze"] = haze
    # `haze` as an object: the height fog itself (MJOLNIRLevelLoader
    # environment.haze; colour linear), for a map with no CE fog of its own
    # (Infinity) or a fog CE draws as a plane: Gephyrophobia's chasm fog is
    # a slab under the bridge that only CE's materials take, so the glacial
    # rock and its boulders stopped dead at a hard line; as a height fog at
    # the plane, thinning fast above it, they fade into it (2026-10-16).
    if isinstance(m.get("haze"), dict) and isinstance(level["landscape"].get("pbr"), dict):
        level["landscape"]["pbr"]["haze"] = dict({"falloff": 0.02, "start": 30000.0, "max_opacity": 1.0},
                                                 **m["haze"])
    level["decor"] += horizon_skirt(code, m, p, level)
    # The level's sky (ce_upgrade_maps.json "environment"): merged into
    # environment, a key at a time (skylight.lower, clouds, ...).
    env = level.setdefault("environment", {})
    for key, value in (m.get("environment") or {}).items():
        if isinstance(value, dict) and isinstance(env.get(key), dict):
            env[key].update(value)
        else:
            env[key] = value
    # `weather: "snow"`: falling snow the CE map never had (Ice Fields, in
    # B40's), the game's snow as Coldsnap's is (gen_ce_level.WEATHER_SYSTEMS),
    # kept out from under the map's roofs and caves (weather_roofs).
    if m.get("weather") and not env.get("weather"):
        sys.path.insert(0, HERE)
        import gen_ce_level
        delta = json.load(open(os.path.join(p["conv"], m["sbsp"] + ".transform.json"), encoding="utf-8"))["delta"]

        def to_ue(v):
            return [round((v[0] + delta[0]) * 304.8, 1), round(-(v[1] + delta[1]) * 304.8, 1),
                    round((v[2] + delta[2]) * 304.8, 1)]
        weather = {**gen_ce_level.WEATHER_SYSTEMS[m["weather"]], "source": f"upgrade ({m['weather']})"}
        roofs = gen_ce_level.weather_roofs(staging(p), to_ue)
        if roofs:
            weather["roofs"] = roofs
        env["weather"] = weather
        print(f"  {code}: {m['weather']} falling, {len((roofs or {}).get('cells') or {})} roof cell(s)")
    # One sea: CE's distant-water slot on the water mesh drawn exactly as
    # the near water (M_CE_Ocean takes each slot's ripples, tints and
    # brightness, and the distant one's paler set drew a seam across Death
    # Island's sea where the two met).
    for item in level.get("decor") or []:
        if isinstance(item, dict) and "_Water." in str(item.get("mesh", "")):
            mats = item.get("materials") or []
            first = next((i for i, material in enumerate(mats)
                          if isinstance(material, dict) and "M_CE_Water" in material.get("parent", "")), None)
            for i, material in enumerate(mats):
                if first is not None and i != first and isinstance(material, dict) and "M_CE_Water" in material.get("parent", ""):
                    mats[i] = json.loads(json.dumps(mats[first]))
    structures = mark_structures(level)
    pulses = bake_pulses(level)
    if pulses:
        print(f"  {code}: {pulses} flare pulse(s) in the material")
    lights = ce_lights(p)
    if lights:
        level["lights"] = lights
    decals, files = ce_decals(p)
    level["decor"] = (level.get("decor") or []) + decals
    # Grime is opt-in per map (ce_upgrade_maps.json "grime": true): on
    # CE's dark metal the Megascans soil read as pale blocky patches, and
    # it barely showed elsewhere (Yoyorast and Blood Gulch, 2026-10-12).
    grime = grime_decals(p) if m.get("grime") else []
    if grime:
        level["decals"] = grime
    out = os.path.join(p["work"], "decals")
    os.makedirs(out, exist_ok=True)
    for f in files:
        shutil.copyfile(f, os.path.join(out, os.path.basename(f)))
    if baked and level.get("foliage"):
        mark_baked_foliage(level["foliage"], os.path.join(p["work"], "foliage.bin"))
        print(f"  {code}: foliage baked into the world, centre {level['foliage']['centre']}")
    json.dump(level, open(p["out_level"], "w", encoding="utf-8"), indent=1)
    print(f"  {code}: level file with {len((level.get('foliage') or {}).get('groups') or [])} foliage group(s), "
          f"{structures} structure slot(s), "
          f"{len(lights)} light(s), {len(decals)} CE decal(s), {len(grime)} grime decal(s)")


# CE's placed lights as Unreal point lights (the loader's `lights`). With
# physical inverse-square falloff the surfaces beside a floor lamp burned
# white long before its pool reached the hall, so the lights use Unreal's
# non-physical falloff (exponent LIGHT_FALLOFF): a CE radiosity intensity
# of 3 (Death Island's fixtures) is 600 unitless at the loader's light
# scale of 256, pools at the lamps and the hall's dark red kept
# (2026-10-12). Each light steps LIGHT_STEP cm out of its fixture: CE's
# marker sits on the fixture's face, and in Unreal the fixture's own shadow
# hid a wall sconce and the floor above leaked an underside lamp's light
# through its seams.
LIGHT_UNITS = 600.0 / 256.0 / 3.0
LIGHT_FALLOFF = 4.0
LIGHT_RADIUS = 1500.0
LIGHT_STEP = 30.0


def ray_room(v0, e1, e2, origin, d, start=1e-3):
    """Metres along d from origin before the first triangle (Moller-Trumbore;
    triangles as corner v0 and edges e1, e2), at most 10."""
    import numpy as np
    pv = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, pv)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tv = origin - v0
    u = np.einsum("ij,ij->i", tv, pv) * inv
    qv = np.cross(tv, e1)
    v = (qv @ d) * inv
    t = np.einsum("ij,ij->i", e2, qv) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > start)
    return float(t[hit].min()) if hit.any() else 10.0


def scene_triangles(p):
    """The conversion scene's triangles, (n, 3, 3) in glTF metres (y up)."""
    import numpy as np
    sys.path.insert(0, HERE)
    from refine_water_gltf import read_accessor
    gltf = os.path.join(p["scene"], "scene.gltf")
    doc = json.load(open(gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(gltf), doc["buffers"][0]["uri"]), "rb").read()
    tris = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            tris.append(pos[idx])
    return np.concatenate(tris)


def ce_lights(p):
    """The conversion's scene_lights.json (merge_ce_scene.py --lights) in the
    level's own terms: position (Unreal cm), colour, candela, radius. A
    fixture's marker points into the wall for some models and out of the
    fixture for others, so each light steps out along whichever way of its
    axis has more room before the scene's geometry."""
    path = os.path.join(p["scene"], "scene_lights.json")
    if not os.path.exists(path):
        return []
    lights = [l for l in json.load(open(path, encoding="utf-8")).get("lights") or []
              if l.get("intensity", 0) > 0 and max(l.get("colour") or [0]) > 0]
    if not lights:
        return []
    import numpy as np
    tris = scene_triangles(p)
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]

    def room(origin, d):
        return ray_room(v0, e1, e2, origin, d)

    out = []
    for l in lights:
        g = np.asarray(l["pos"], dtype=np.float64)
        d = np.asarray(l.get("dir") or [0.0, -1.0, 0.0], dtype=np.float64)
        d = d / max(np.linalg.norm(d), 1e-9)
        if room(g, -d) > room(g, d):
            d = -d
        g = g + d * (LIGHT_STEP / 100.0)
        out.append({"name": l.get("name"), "pos": [round(float(g[0]) * 100, 1), round(float(g[2]) * 100, 1), round(float(g[1]) * 100, 1)],
                    "colour": [round(c, 3) for c in l["colour"]], "intensity": round(l["intensity"] * LIGHT_UNITS, 3),
                    "falloff": LIGHT_FALLOFF, "radius": LIGHT_RADIUS})
    return out


# CE's scenario decals (placement.json `decals`: Blood Gulch's Forerunner
# team symbols on its bases' pillars) as quads lying on the surface under
# each, drawn by the CE transparent masters with CE's own texture (a PNG
# beside the level file, imported at runtime). Unreal decals were not an
# option: a decal-domain material from our cook fails the game's pipeline
# state creation (PipelineStateCache.cpp:551, 2026-10-11 and 2026-10-12),
# and the game's own decal masters sample only virtual textures.
DECAL_QUAD = "/Engine/BasicShapes/Plane.Plane"  # 100 cm square, facing +Z
DECAL_LIFT = 1.0  # cm off the surface
# CE's additive decals went onto lightmapped surfaces far darker than our
# Unreal-lit ones: Blood Gulch's symbols (red at most 148/255) barely showed
# at CE's own strength (2026-10-12).
DECAL_EXPOSURE = 6.0
DECAL_PARENTS = {3: "Add", 7: "Add", 1: "Mul", 2: "Mul", 5: "Mul"}  # CE framebuffer blend; the rest alpha


def ce_decals(p):
    """CE's decals as decor (a quad each, its material a CE transparent
    master over the decal's texture), and the textures they need, as
    (decor, [source png]). Each quad lies on the nearest surface within
    3 m of the decal's position, its texture upright on walls."""
    path = os.path.join(staging(p), "placement.json")
    decals = json.load(open(path, encoding="utf-8")).get("decals") or [] if os.path.exists(path) else []
    if not decals:
        return [], []
    import math
    import numpy as np
    tris = scene_triangles(p)
    cent = tris.mean(axis=1)
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    unit = 3.048
    decor, files = [], []
    for i, d in enumerate(decals):
        tex = os.path.join(staging(p), "textures", d.get("texture") or "")
        if not d.get("texture") or not os.path.exists(tex):
            continue
        g = np.array([d["pos"][0], d["pos"][2], -d["pos"][1]]) * unit
        near = np.where(np.linalg.norm(cent - g, axis=1) < 3.0)[0]
        if not len(near):
            continue
        dist = np.einsum("ij,ij->i", g - tris[near, 0], nrm[near])
        k = near[np.argmin(np.abs(dist))]
        # The quad faces the open side: CE's decal sits on the surface to
        # within millimetres, either side of it.
        ng = nrm[k]
        v0, e1, e2 = tris[near, 0], tris[near, 1] - tris[near, 0], tris[near, 2] - tris[near, 0]
        if ray_room(v0, e1, e2, g, -ng, 0.02) > ray_room(v0, e1, e2, g, ng, 0.02):
            ng = -ng
        n = np.array([ng[0], ng[2], ng[1]])  # Unreal axes (x, y, z) = glTF (x, z, y)
        pos = np.array([g[0], g[2], g[1]]) * 100.0 + n * DECAL_LIFT
        # The quad's x along the surface and level, its y up the surface
        # (on a floor: x along Unreal's x), so the rotator never nears
        # gimbal lock.
        if abs(n[2]) < 0.9:
            # (Plane's texture runs down its y: this way the texture is upright.)
            x = np.cross(n, [0.0, 0.0, 1.0])
            x /= np.linalg.norm(x)
        else:
            x = np.array([1.0, 0.0, 0.0]) - n * n[0]
            x /= np.linalg.norm(x)
        y = np.cross(n, x)
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, x[2]))))
        yaw = math.degrees(math.atan2(x[1], x[0]))
        roll = math.degrees(math.atan2(-y[2], n[2]))
        size = float(d.get("radius") or 0.5) * 2 * unit  # m across, the quad 1 m
        blend = int(d.get("blend_function") or 0)
        name = os.path.basename(tex)
        decor.append({"id": f"ce_decal_{i}", "mesh": DECAL_QUAD,
                      "pos": [round(float(v), 1) for v in pos], "rot": [round(pitch, 2), round(yaw, 2), round(roll, 2)],
                      "scale": [round(size, 3), round(size, 3), 1.0], "cast_shadow": False,
                      "materials": [{"parent": f"/Game/MJOLNIR/CE/M_CE_Transparent{DECAL_PARENTS.get(blend, 'Alpha')}."
                                               f"M_CE_Transparent{DECAL_PARENTS.get(blend, 'Alpha')}",
                                     "textures": {"Map0": "decals/" + name},
                                     "scalars": {"StageCount": 1, "ChicagoFlags": 0.0, "BlendFunction": float(blend),
                                                 "FadeMode": 0.0,
                                                 "Exposure": DECAL_EXPOSURE if DECAL_PARENTS.get(blend) == "Add" else 1.0},
                                     "vectors": {"Stage0Xform": [1.0, 1.0, 0.0, 0.0], "Stage0UAnim": [0, 1.0, 0.0, 1.0],
                                                 "Stage0VAnim": [0, 1.0, 0.0, 1.0], "Stage0RAnim": [0, 1.0, 0.0, 360.0],
                                                 "Stage0Misc": [0.0, 0.0, 0.0, 0.0],
                                                 "StageColorFunctions": [0, 0.0, 0.0, 0.0],
                                                 "StageAlphaFunctions": [0, 0.0, 0.0, 0.0]}}]})
        if tex not in files:
            files.append(tex)
    return decor, files


# B30's grime on CE's structures, as the game's own Megascans decals: soil
# splashed up a wall where it meets the ground, leaks run down from a
# wall's top. Unreal decals project along their x; these face into the wall
# with their z up. Sizes are half extents (cm): depth, width, height.
SOIL = ["/Game/Env/Bio/DirtyDecals/Soil/MI_Decal_soil_Vertical_01.MI_Decal_soil_Vertical_01",
        "/Game/Env/Bio/DirtyDecals/Soil/MI_Decal_soil_Vertical_02.MI_Decal_soil_Vertical_02"]
LEAKS = ["/Game/Megascans/Decals/Leakage_tdfdfebc/MI_Leakage_tdfdfebc_4K.MI_Leakage_tdfdfebc_4K",
         "/Game/Megascans/Decals/Leakage_tdlbcbrc/MI_Leakage_tdlbcbrc_4K.MI_Leakage_tdlbcbrc_4K"]
SOIL_SIZE = [40.0, 160.0, 70.0]
LEAK_SIZE = [40.0, 110.0, 180.0]
GRIME_SPACING = 3.5  # m between decals of a kind
GRIME_KEEP = {"soil": 0.7, "leak": 0.35}
# At the Megascans instances' own opacity the grime barely showed on CE's
# dark metal; 2.5 reads as dust kicked up the walls (Blood Gulch, 2026-10-12).
GRIME_SCALARS = {"Opacity Intensity": 2.5}


def grime_decals(p, seed=7):
    """Soil and leak decals on the conversion's structure walls (materials
    whose base map names metal, panels and the like: mark_structures's
    STRUCTURE), as level `decals`. A wall's base counts where a ray down
    from just outside its lowest edge meets something that is not
    structure within 1.6 m; a wall's top where it stands 2.5 m or more."""
    import math
    import random
    import numpy as np
    sys.path.insert(0, HERE)
    from refine_water_gltf import read_accessor
    spec = json.load(open(os.path.join(p["scene"], "materials.spec.json"), encoding="utf-8"))
    structure = {mat["name"] for mat in spec.get("materials") or []
                 if any(w in str((mat.get("textures") or {}).get("Base", "")).rsplit("/", 1)[-1].lower() for w in STRUCTURE)}
    gltf = os.path.join(p["scene"], "scene.gltf")
    doc = json.load(open(gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(gltf), doc["buffers"][0]["uri"]), "rb").read()
    tris, is_struct = [], []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"]
            if name.endswith("__sky") or "water" in name or "underwater" in name:
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            tris.append(pos[idx])
            is_struct.append(np.full(len(idx), name in structure))
    if not tris:
        return []
    T = np.concatenate(tris)
    S = np.concatenate(is_struct)
    if not S.any():
        return []
    v0, e1, e2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    cross = np.cross(e1, e2)
    area = np.linalg.norm(cross, axis=1) / 2
    nrm = cross / (2 * area[:, None] + 1e-12)
    cent = T.mean(axis=1)
    up = np.array([0.0, 1.0, 0.0])  # glTF

    def first_hit(origin, d, reach):
        """(distance, triangle) of the first hit along d within reach m, or None."""
        near = np.where(np.linalg.norm(cent - origin, axis=1) < reach + 30.0)[0]
        if not len(near):
            return None
        pv = np.cross(d, e2[near])
        det = np.einsum("ij,ij->i", e1[near], pv)
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = origin - v0[near]
        u = np.einsum("ij,ij->i", tv, pv) * inv
        qv = np.cross(tv, e1[near])
        v = (qv @ d) * inv
        t = np.einsum("ij,ij->i", e2[near], qv) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-3) & (t < reach)
        if not hit.any():
            return None
        k = np.argmin(np.where(hit, t, np.inf))
        return float(t[k]), int(near[k])

    rng = random.Random(seed)
    taken = {"soil": set(), "leak": set()}
    out = []
    walls = np.where(S & (np.abs(nrm[:, 1]) < 0.25) & (area > 0.5))[0]
    for w in walls:
        n = nrm[w]
        ys = T[w][:, 1]
        for kind in ("soil", "leak"):
            if kind == "leak" and ys.max() - ys.min() < 2.5:
                continue
            # The triangle's lowest (or highest) edge, sampled every couple of metres.
            order = np.argsort(ys) if kind == "soil" else np.argsort(-ys)
            a, b = T[w][order[0]], T[w][order[1]]
            if abs(a[1] - b[1]) > 0.5:
                continue
            steps = max(1, int(np.linalg.norm(b - a) / 2.0))
            for s in range(steps):
                pt = a + (b - a) * ((s + 0.5) / steps)
                cell = (round(pt[0] / GRIME_SPACING), round(pt[1] / GRIME_SPACING), round(pt[2] / GRIME_SPACING))
                if cell in taken[kind]:
                    continue
                outside = pt + n * 0.3
                if kind == "soil":
                    hit = first_hit(outside + up * 0.4, -up, 2.0)
                    if hit is None or S[hit[1]]:
                        continue
                    base = outside[1] + 0.4 - hit[0]
                    centre = np.array([pt[0], base + SOIL_SIZE[2] / 100.0 * 0.8, pt[2]])
                    size, material = SOIL_SIZE, rng.choice(SOIL)
                else:
                    # Open sky above the top: rain runs down from it.
                    if first_hit(outside + up * 0.05, up, 3.0) is not None:
                        continue
                    centre = np.array([pt[0], pt[1] - LEAK_SIZE[2] / 100.0 * 0.9, pt[2]])
                    size, material = LEAK_SIZE, rng.choice(LEAKS)
                taken[kind].add(cell)
                if rng.random() > GRIME_KEEP[kind]:
                    continue
                into = -np.array([n[0], n[2], n[1]])  # Unreal axes
                yaw = math.degrees(math.atan2(into[1], into[0]))
                c = np.array([centre[0], centre[2], centre[1]]) * 100.0
                out.append({"material": material, "pos": [round(float(v), 1) for v in c],
                            "rot": [0.0, round(yaw, 2), 0.0], "size": size, "scalars": GRIME_SCALARS})
    return out


# Leaf clusters smaller than this hold still. The material's flutter and
# branch motion are distances, not angles a cluster's size scales: on
# Infinity a small tree's clusters at 0.03 thrashed (2026-10-19), while
# Timberland's at 0.2 to 0.36 moved as a breath.
LEAF_STILL_SCALE = 0.15


def leaf_groups(swap):
    """The swapped trees' leaf clusters as foliage groups, each with its
    records: the ones that move, then the small ones held still. The
    editor's bake (foliage_bake.py) and assemble both append these in this
    order, so the baked components and the level file's groups agree."""
    lv = swap.get("leaves") or {}
    records = lv.get("records") or []
    if not records:
        return []
    group = {"mesh": lv["mesh"], "rule": "tree leaves", "cull": [20000, 45000], "shadow": True,
             "scalars": lv.get("scalars")}
    # A biome's own leaf material (B40's snow-packed branches) and
    # stillness (scenery_swap.py): dropped, the firs' branches drew bare
    # and swayed.
    for key in ("material", "static"):
        if lv.get(key) is not None:
            group[key] = lv[key]
    moving = [r for r in records if r[4] >= LEAF_STILL_SCALE]
    small = [r for r in records if r[4] < LEAF_STILL_SCALE]
    out = [(moving, group)] if moving else []
    if small:
        out.append((small, dict(group, static=True)))
    return out


def append_foliage(path, records):
    """One more group at the end of a foliage file (MJF3): records of
    [x, y, z, yaw degrees, scale, normal x, normal y]."""
    import struct
    raw = bytearray(open(path, "rb").read())
    version, n = struct.unpack_from("<II", raw, 4)
    struct.pack_into("<II", raw, 4, version, n + 1)
    raw += struct.pack("<I", len(records))
    for x, y, z, yaw, sc, nx, ny in (r[:7] for r in records):
        raw += struct.pack("<fffBBbbBBB", x, y, z, int(yaw / 360.0 * 256) % 256, max(1, min(255, round(sc * 100))),
                           max(-127, min(127, round(nx * 127))), max(-127, min(127, round(ny * 127))), 255, 255, 255)
    open(path, "wb").write(bytes(raw))


def mark_baked_foliage(foliage, path):
    """The level file's foliage, baked into the world by the editor stage
    (foliage_bake.py): `baked` tells the loader to leave every group but the
    cliffs' cladding to the world, and `centre` is where the clumps lie on
    average, which the loader's wind flowmap centres on (it took that from
    the clumps it placed)."""
    import struct
    raw = open(path, "rb").read()
    tilted, coloured = raw[:4] in (b"MJF2", b"MJF3"), raw[:4] == b"MJF3"
    stride = 19 if coloured else 16 if tilted else 14
    _, count = struct.unpack_from("<II", raw, 4)
    pos, sx, sy, n = 12, 0.0, 0.0, 0
    for g in range(count):
        (size,) = struct.unpack_from("<I", raw, pos)
        pos += 4
        if not (foliage["groups"][g] or {}).get("cliff"):
            for k in range(size):
                x, y = struct.unpack_from("<ff", raw, pos + k * stride)
                sx, sy, n = sx + x, sy + y, n + 1
        pos += size * stride
    foliage["baked"] = True
    foliage["centre"] = [round(sx / max(n, 1), 1), round(sy / max(n, 1), 1)]


def bake_pulses(level):
    """A pulsing flare's object function (gen_ce_level's `pulse`) as the
    trial M_CE_Flare's `Pulse` vector (function, period, phase), which runs
    CE's wave on the material's clock: the loader no longer sets each
    flare's Brightness from Lua 25 times a second."""
    n = 0
    for item in level.get("decor") or []:
        pulse = item.get("pulse") if isinstance(item, dict) else None
        mats = item.get("materials") if isinstance(item, dict) else None
        if not (isinstance(pulse, dict) and pulse.get("param") == "Brightness" and mats
                and str(mats[0].get("parent", "")).startswith("/Game/MJOLNIR/CE/M_CE_Flare")):
            continue
        mats[0]["parent"] = mats[0]["parent"].replace("/Game/MJOLNIR/CE/", "/Game/MJOLNIR/CETrial/")
        mats[0].setdefault("vectors", {})["Pulse"] = [float(pulse["function"]), float(pulse["period"]), 0.0, 0.0]
        del item["pulse"]
        n += 1
    return n


def mark_structures(level):
    """Point the structure slots at the trial master with SURFACE on."""
    n = 0
    for item in level.get("decor") or []:
        for entry in (item.get("materials") or []) if isinstance(item, dict) else []:
            if not isinstance(entry, dict) or not str(entry.get("parent", "")).startswith("/Game/MJOLNIR/CE/M_CE_Environment"):
                continue
            base = str((entry.get("textures") or {}).get("Base", "")).rsplit("/", 1)[-1].lower()
            if not any(w in base for w in STRUCTURE):
                continue
            entry["parent"] = entry["parent"].replace("/Game/MJOLNIR/CE/", "/Game/MJOLNIR/CETrial/")
            entry.setdefault("vectors", {})["Surface"] = SURFACE
            entry.setdefault("textures", {})["SurfaceWear"] = SURFACE_WEAR
            entry["vectors"]["SurfaceMetal"] = SURFACE_METAL
            n += 1
    return n


def hub_map_container(m, prefix="pakchunk997-"):
    """The installed hub copy's container (its map, 997, by default), by the
    launcher's state."""
    state = json.load(open(LAUNCHER_STATE, encoding="utf-8"))
    inst = next((x for x in state.get("installed", []) if x["slug"] == m["hub"]), None)
    if not inst:
        sys.exit(f"{m['hub']} is not installed from the hub")
    j = next(i for i, c in enumerate(inst["containers"]) if c.startswith(prefix))
    hits = glob.glob(os.path.join(PAKS, f"pakchunk*-MJOLNIRHUB-{m['hub']}-{j}_P.utoc"))
    if len(hits) != 1:
        sys.exit(f"{m['hub']}: expected one installed map container, found {hits}")
    return hits[0][:-5]


def require_game_closed():
    if "halocampaignevolved" in run(["tasklist"]).lower():
        sys.exit("close the game before installing")


def local_install_plan(code, m, p):
    """Validate a fresh local install before any files in the game change.

    Use the map-pack data layout so `level register` merges this map with
    both hub maps and older --install-test maps. Never copy the bake's
    registration container: its snapshot may omit hub-installed maps.
    """
    if len(code) != 3 or not code.isascii() or not code.isalnum() or code != code.upper():
        sys.exit("local install needs a three-character uppercase map code")
    state = {}
    if os.path.isfile(LAUNCHER_STATE):
        with open(LAUNCHER_STATE, encoding="utf-8") as f:
            state = json.load(f)
    installed = state.get("installed", [])
    if m.get("hub") or any(i.get("map_code") == code for i in installed):
        sys.exit(f"{code}: use --install for an existing hub map")
    with open(p["out_level"], encoding="utf-8") as f:
        level = json.load(f)
    source = p["conv"] if m.get("indoor") else p["bake"]
    record = os.path.join(source, f"{code}.registration.json")
    with open(record, encoding="utf-8") as f:
        if json.load(f).get("code") != code:
            sys.exit(f"{code}: registration record names a different map")

    loader = os.path.join(UE4SS, "Mods", "MJOLNIRLevelLoader")
    cli = os.environ.get("MJOLNIR", os.path.join(REPO, "target", "release", "mjolnir.exe"))
    required = [cli, os.path.join(loader, "Scripts", "main.lua"),
                os.path.join(loader, "native", "mjolnir_map_registry.dll")]
    for mode in level.get("modes", [level.get("variant", "slayer")]):
        required += [os.path.join(loader, "variants", f"{mode}.{ext}") for ext in ("mglo", "layout.json")]
    runtime = next((i for i in installed if i.get("slug") == "mjolnir-ce-runtime"), {})
    stems = ["pakchunk983-MJOLNIRCETRIAL-Windows", "pakchunk988-MJOLNIRMAT-Windows", "pakchunk994-MJOLNIRSPAWN_P",
             "pakchunk993-MJOLNIRTELES_P", "pakchunk992-MJOLNIRTELER_P", "pakchunk991-MJOLNIRTELE2_P"]
    if "ctf" in level.get("modes", []):
        stems += [f"pakchunk990-MJOLNIR{s}_P" for s in ("CTFMESH", "FLAG", "STAND", "MOTL")]
    if level.get("health_pack"):
        stems += [f"pakchunk990-MJOLNIR{s}_P" for s in ("HPACK", "HPSPOT", "HPMESH", "MOTL")]
    if level.get("flux"):
        stems.append("pakchunk990-MJOLNIRFLUX_P")
    for stem in stems:
        candidates = [os.path.join(PAKS, stem)]
        if stem in runtime.get("containers", []):
            index = runtime["containers"].index(stem)
            candidates += [f[:-5] for f in glob.glob(os.path.join(PAKS,
                           f"pakchunk*-MJOLNIRHUB-mjolnir-ce-runtime-{index}_P.utoc"))]
        if not any(all(os.path.isfile(f"{base}.{e}") for e in ("pak", "utoc", "ucas")) for base in candidates):
            sys.exit(f"{code}: install the CE runtime first (missing {stem})")

    data = os.path.join(UE4SS, "MJOLNIRMaps", code)
    files = [(p["out_level"], os.path.join(data, "level.json")),
             (record, os.path.join(data, "registration.json"))]
    stub = os.path.join(PAKS, "pakchunk115-Windows.pak")
    containers = [(os.path.join(source, f"pakchunk997-MJOLNIRMAP-{code}_P"), None),
                  (m.get("mesh_container") or os.path.join(p["conv"], f"pakchunk986-MJOLNIRMESH-{code}_P"),
                   f"pakchunk986-MJOLNIRMESH-{code}_P"),
                  (os.path.join(p["conv"], f"pakchunk985-MJOLNIRCOOK-{code}_P"), None)]
    if not m.get("indoor"):
        containers.append((os.path.join(p["bake"], f"pakchunk{m['chunk']}-MJOLNIRLAND-Windows"), None))
    for base, name in containers:
        dest = os.path.join(PAKS, name or os.path.basename(base))
        files += [(f"{base}.{e}", f"{dest}.{e}") for e in ("utoc", "ucas")]
        files.append((f"{base}.pak" if os.path.isfile(f"{base}.pak") else stub, f"{dest}.pak"))
    if level.get("foliage"):
        files.append((os.path.join(p["work"], "foliage.bin"), os.path.join(data, "foliage.bin")))
    for f in glob.glob(os.path.join(p["work"], "decals", "*")):
        if os.path.isfile(f):
            files.append((f, os.path.join(data, "decals", os.path.basename(f))))
    # install_shared runs first, after every map's plan has passed.
    required += [os.path.join(STAGED, f"pakchunk983-Windows.{e}") for e in ("utoc", "ucas")]
    required.append(os.path.join(REPO, "mods", "MJOLNIRLevelLoader", "Scripts", "main.lua"))
    missing = [f for f in required + [src for src, _ in files] if not os.path.isfile(f)]
    if missing:
        sys.exit(f"{code}: local install is incomplete:\n  " + "\n  ".join(missing))
    return files, cli


def install_local(code, plan):
    files, _ = plan
    for src, dest in files:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
    print(f"  {code}: local containers and map data installed")


def stage_install(code, m, p):
    require_game_closed()
    data = os.path.join(UE4SS, "MJOLNIRMaps", code)
    if m.get("indoor"):
        # The hub copy's own containers; only the level file changes.
        os.makedirs(data, exist_ok=True)
        shutil.copyfile(p["out_level"], os.path.join(data, "level.json"))
        decals = os.path.join(p["work"], "decals")
        if os.path.isdir(decals) and os.listdir(decals):
            os.makedirs(os.path.join(data, "decals"), exist_ok=True)
            for f in os.listdir(decals):
                shutil.copyfile(os.path.join(decals, f), os.path.join(data, "decals", f))
        print(f"  {code}: level file installed (indoor)")
        return
    base = hub_map_container(m)
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(p["bake"], f"pakchunk997-MJOLNIRMAP-{code}_P.{e}"), f"{base}.{e}")
    if m.get("mesh_container"):
        mesh = hub_map_container(m, "pakchunk986-")
        for e in ("utoc", "ucas"):
            shutil.copyfile(f"{m['mesh_container']}.{e}", f"{mesh}.{e}")
    for f in glob.glob(os.path.join(p["bake"], f"pakchunk{m['chunk']}-MJOLNIRLAND-Windows.*")):
        shutil.copyfile(f, os.path.join(PAKS, os.path.basename(f)))
    # The hub copy of the landscape chunk (a _P container) outranks ours on
    # mount priority, shader library and all: write over it too, or the game
    # keeps the old landscape shaders (Death Island, 2026-10-18).
    for hub in glob.glob(os.path.join(PAKS, f"pakchunk{m['chunk']}-MJOLNIRHUB-{m['hub']}-*_P.utoc")):
        for e in ("utoc", "ucas"):
            shutil.copyfile(os.path.join(p["bake"], f"pakchunk{m['chunk']}-MJOLNIRLAND-Windows.{e}"), hub[:-4] + e)
        print(f"  {code}: landscape chunk also over {os.path.basename(hub)[:-5]}")
    data = os.path.join(UE4SS, "MJOLNIRMaps", code)
    shutil.copyfile(p["out_level"], os.path.join(data, "level.json"))
    shutil.copyfile(os.path.join(p["work"], "foliage.bin"), os.path.join(data, "foliage.bin"))
    if os.path.exists(os.path.join(p["work"], "flux_state", "state.json")):
        shutil.copytree(os.path.join(p["work"], "flux_state"), os.path.join(data, "flux_state"), dirs_exist_ok=True)
    decals = os.path.join(p["work"], "decals")
    if os.path.isdir(decals) and os.listdir(decals):
        os.makedirs(os.path.join(data, "decals"), exist_ok=True)
        for f in os.listdir(decals):
            shutil.copyfile(os.path.join(decals, f), os.path.join(data, "decals", f))
    print(f"  {code}: installed over {os.path.basename(base)}")


def install_shared():
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(STAGED, f"pakchunk983-Windows.{e}"),
                        os.path.join(PAKS, f"pakchunk983-MJOLNIRCETRIAL-Windows.{e}"))
        # The CE runtime from the hub carries chunk 983 too, as a _P container
        # that outranks ours: a master new in this build (the trial
        # M_CE_Flare) found no shaders and drew as a black dome
        # (2026-10-18). Write over the hub's as well.
        for hub in glob.glob(os.path.join(PAKS, "pakchunk983-MJOLNIRHUB-*_P.utoc")):
            shutil.copyfile(os.path.join(STAGED, f"pakchunk983-Windows.{e}"), hub[:-4] + e)
        # The water masters (M_CE_Ocean, chunk 982), when this cook made them.
        staged = os.path.join(STAGED, f"pakchunk982-Windows.{e}")
        if os.path.exists(staged):
            shutil.copyfile(staged, os.path.join(PAKS, f"pakchunk982-MJOLNIRWATER-Windows.{e}"))
    shutil.copyfile(os.path.join(REPO, "mods", "MJOLNIRLevelLoader", "Scripts", "main.lua"),
                    os.path.join(UE4SS, "Mods", "MJOLNIRLevelLoader", "Scripts", "main.lua"))
    print("  trial masters and the loader installed")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("maps", nargs="+", help="map codes in ce_upgrade_maps.json")
    ap.add_argument("--stages", default=",".join(s for s in STAGES if s != "install"),
                    help="comma-separated, of " + ", ".join(STAGES))
    install = ap.add_mutually_exclusive_group()
    install.add_argument("--install", action="store_true", help="add the install stage (existing hub maps)")
    install.add_argument("--local-install", action="store_true", help="add the install stage for a fresh local map (no hub)")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/upgrade")
    ap.add_argument("--no-masters", action="store_true", help="skip rebuilding the trial masters in the editor stage")
    a = ap.parse_args()
    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)
    stages = [s for s in a.stages.split(",") if s]
    if (a.install or a.local_install) and "install" not in stages:
        stages.append("install")
    bad = [s for s in stages if s not in STAGES] + [c for c in a.maps if c not in config]
    if bad:
        sys.exit(f"unknown: {bad}")
    maps = {c: config[c] for c in a.maps}
    ps = {c: paths(c, m, a.work) for c, m in maps.items()}
    for p in ps.values():
        os.makedirs(p["work"], exist_ok=True)
    for c, m in maps.items():
        if m.get("indoor"):
            indoor_landscape(c, m, ps[c])
    for stage in STAGES:
        if stage not in stages:
            continue
        print(f"== {stage}", flush=True)
        if stage == "editor" and not a.no_masters:
            build_masters()
            build_water()
            build_cliffs(maps, ps)
        if stage == "cook":
            stage_cook(list(maps.values()))
            continue
        if stage == "install":
            require_game_closed()
            plans = {c: local_install_plan(c, m, ps[c]) for c, m in maps.items()} if a.local_install else {}
            install_shared()
            if a.local_install:
                for c, plan in plans.items():
                    install_local(c, plan)
                cli = next(iter(plans.values()))[1]
                print("  " + run([cli, "level", "register", "--paks", PAKS]).strip())
                continue
        for c, m in maps.items():
            if m.get("indoor") and stage in INDOOR_SKIP:
                continue
            globals()[f"stage_{stage}"](c, m, ps[c])
    print("done")


if __name__ == "__main__":
    main()
