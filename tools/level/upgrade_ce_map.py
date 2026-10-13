"""Take converted CE maps through the B30 pipeline in one run.

    python tools/level/upgrade_ce_map.py BGL YOY [--install] [--stages ...]

For each map named in tools/level/ce_upgrade_maps.json this does what was
done by hand per map until 2026-10-12:

  land      build_landscape.py: the ground's heights, holes and bakes
  foliage   scatter_foliage.py: grass, debris and the cliffs' cladding
  swap      scenery_swap.py: the natural CE scenery (boulders, trees,
            shrubs, plants) in B30's own meshes, the CE slots hidden
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
# cladding rocks are tessellated too and theirs (at the walls' 0.6 the
# Megascans rocks folded, backfaces showing as lavender patches).
TESS = {"disp": 0.6, "cladding": True, "clad_disp": 0.2}
GAME = os.environ.get("HCE_GAME", "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved")
PAKS = os.path.join(GAME, "Meteorite", "Content", "Paks")
UE4SS = os.path.join(GAME, "Meteorite", "Binaries", "Win64", "ue4ss")
LAUNCHER_STATE = os.path.join(os.environ.get("APPDATA", ""), "com.devnull9090.mjolnir-launcher", "hub_state.json")
# What a swapped scenery slot draws (scenery_swap.py).
HIDDEN = "/Game/MJOLNIR/CETrial/M_CE_Hidden.M_CE_Hidden"
# Structures: slots whose CE base map is one of these (metal, panels,
# machinery) draw with the trial environment master's surface section
# (build_ce_materials.py SURFACE_CODE): relief from the base map, roughness
# and specular, the Forerunner kit's scratch wear. Surface: on, relief,
# plate roughness, wear.
STRUCTURE = ("metal", "panel", "tech", "steel", "plate", "strip", "circuit", "generator", "pipe", "grate",
             "girder", "beam", "rivet", "vent")
SURFACE = [1.0, 2.5, 0.55, 0.5]
SURFACE_WEAR = "/Game/Env/HS/FR/Gen/+Materials/T_FR_Gen_Scratch_01_Mask.T_FR_Gen_Scratch_01_Mask"
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


def staging(p):
    """The conversion's staging folder: placement.json and the CE models
    (the scene folder's own when it has them)."""
    own = os.path.join(p["scene"], "staging")
    return own if os.path.isdir(os.path.join(own, "models")) else os.path.join(p["conv"], "staging")


def stage_land(code, m, p):
    cmd = [sys.executable, os.path.join(HERE, "build_landscape.py"), os.path.join(p["scene"], "scene.gltf"),
           os.path.join(p["scene"], "materials.spec.json"), p["land"], "--shader", ",".join(m["shaders"]),
           "--name", m["landscape"]]
    if m.get("components"):
        cmd += ["--components", str(m["components"])]
    if m.get("ground_also"):
        cmd += ["--also", ",".join(m["ground_also"])]
    out = run(cmd)
    print("  " + "\n  ".join(l for l in out.splitlines() if l.startswith(("heights", "holes", "settled", "bakes"))))


def stage_foliage(code, m, p):
    level = json.load(open(p["level"], encoding="utf-8"))
    cmd = [sys.executable, os.path.join(HERE, "scatter_foliage.py"), os.path.join(p["scene"], "scene.gltf"),
           os.path.join(p["scene"], "materials.spec.json"), os.path.join(p["foliage"], "foliage.json"),
           "--bin", os.path.join(p["foliage"], "foliage.bin"), "--offset", "0,0,0", "--lift", str(FOLIAGE_LIFT),
           "--edge", os.path.join(p["land"], "landscape.json")]
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
    os.makedirs(p["foliage"], exist_ok=True)
    out = run(cmd)
    print("  " + out.strip().splitlines()[-1][:200])


def stage_swap(code, m, p):
    data = os.path.join(HERE, "data")
    sea = sea_height(json.load(open(p["level"], encoding="utf-8")))
    # A snow map (`biome: snow`) takes B40's trees and rocks: its own
    # recipes and bounds (scenery_swap.py recipes, `mjolnir mesh list`).
    source = "b40" if m.get("biome") == "snow" else "b30"
    out = run([sys.executable, os.path.join(HERE, "scenery_swap.py"), "swap", p["scene"],
               os.path.join(p["scene"], "materials.spec.json"), os.path.join(data, f"{source}_tree_recipes.json"),
               os.path.join(data, f"{source}_scenery_bounds.json"), os.path.join(p["work"], "swap.json"),
               "--rocks", m.get("rocks", "beach"), "--foliage", os.path.join(p["foliage"], "foliage.json"),
               "--staging", staging(p)]
              + (["--biome", m["biome"]] if m.get("biome") else [])
              + (["--sea", f"{sea:.1f}"] if sea is not None else []))
    print("  " + out.strip().splitlines()[-1][:200])


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
    out = powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_landscape.py"],
                     env={"MJ_LANDSCAPE": p["land"], "MJ_LANDSCAPE_NAME": m["landscape"],
                          "MJ_LANDSCAPE_CHUNK": str(m["chunk"])})
    # The editor's own log too: its console capture has stopped short of the
    # end (Death Island, 2026-10-13) with the world built.
    log = "".join(open(f, encoding="utf-8", errors="replace").read() for f in (
        os.path.join(PROJECT, "Saved_build_ce_landscape.log"), os.path.join(PROJECT, "Saved", "Logs", "Meteorite.log"))
        if os.path.exists(f))
    if "landscape built" not in log or os.path.normcase(p["land"]) not in os.path.normcase(log.replace("/", "\\")):
        sys.exit(f"{code}: the landscape world was not built:\n{out[-2000:]}")
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


def build_cliffs(maps, ps):
    """The maps' cliff slots as Nanite meshes (tools/level/cliff_mesh.py),
    built in the editor as SM_<CODE>_CliffTess (Scripts/build_ce_cliffs.py,
    chunk 983 with the trial masters)."""
    specs = []
    for code, m in maps.items():
        if m.get("tess") is False:
            continue
        p = ps[code]
        out = os.path.join(p["work"], "cliff_mesh.json")
        print("  " + run([sys.executable, os.path.join(HERE, "cliff_mesh.py"), p["level"],
                          os.path.join(p["scene"], "scene.gltf"), out, "--landscape",
                          os.path.join(p["land"], "landscape.json"), "--swap",
                          os.path.join(p["work"], "swap.json")]).strip().splitlines()[-1][:160])
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
    worlds = "+".join(f"/Game/Levels/Halo1/Solo/{m['landscape']}/{m['landscape']}" for m in maps)
    # StaticMesh too: chunk 983 carries the tessellated cliffs.
    out = powershell(os.path.join(REPO, "tools", "ue", "cook.ps1"),
                     ["-Map", worlds, "-Classes", "Material,MaterialInstanceConstant,StaticMesh"])
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


def stage_assemble(code, m, p):
    land = json.load(open(os.path.join(p["land"], "landscape.json"), encoding="utf-8"))
    fol = json.load(open(os.path.join(p["foliage"], "foliage.json"), encoding="utf-8"))
    level = json.load(open(p["level"], encoding="utf-8"))
    level["landscape"] = {k: land[k] for k in ("material", "cut", "pbr", "cliff") if k in land}
    plasma = os.path.join(p["work"], "plasma_mesh.json")
    if os.path.exists(plasma):
        spec = json.load(open(plasma, encoding="utf-8"))
        level["slot_meshes"] = [{"mesh": f"/Game/MJOLNIR/CETrial/SM_{code}_Plasma.SM_{code}_Plasma",
                                 "item": spec["item"], "slots": spec["slots"]}]
    cliff = level["landscape"].get("cliff")
    if isinstance(cliff, dict):
        cliff["fill_dir"] = CLIFF_FILL_DIR
        mesh = os.path.join(p["work"], "cliff_mesh.json")
        if m.get("tess") is not False and os.path.exists(mesh):
            spec = json.load(open(mesh, encoding="utf-8"))
            cliff["tess"] = dict(TESS, mesh=f"/Game/MJOLNIR/CETrial/SM_{code}_CliffTess.SM_{code}_CliffTess",
                                 item=spec["item"], slots=spec["slots"])
    level["foliage"] = {"file": "foliage.bin", "wind": WIND, "groups": list(fol["groups"])}
    shutil.copyfile(os.path.join(p["foliage"], "foliage.bin"), os.path.join(p["work"], "foliage.bin"))
    if m.get("water"):
        water = level.setdefault("environment", {}).setdefault("water", {})
        water.setdefault("params", {}).update(m["water"])
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
        level["decor"] = (level.get("decor") or []) + swap["decor"]
        if swap.get("effects"):
            level["effects"] = swap["effects"]
        leaves = (swap.get("leaves") or {}).get("records") or []
        if leaves:
            append_foliage(os.path.join(p["work"], "foliage.bin"), leaves)
            level["foliage"]["groups"].append({"mesh": swap["leaves"]["mesh"], "rule": "tree leaves",
                                               "cull": [20000, 45000], "shadow": True,
                                               "scalars": swap["leaves"].get("scalars")})
            print(f"  {code}: {len(leaves)} leaf cluster(s) on the swapped trees")
        print(f"  {code}: {swap['count']} scenery object(s) swapped, {hidden} CE slot(s) hidden")
    # After the swap: the swap hides CE scenery by its slot's material as the
    # spec has it, and the haze turns the terrain materials' own fog off, so
    # run first it left every swapped CE rock and tree drawn under its
    # stand-in (2026-10-13).
    if m.get("haze") == "ce" and isinstance(level["landscape"].get("pbr"), dict):
        haze = ce_haze(level, scene_reach(p))
        if haze:
            level["landscape"]["pbr"]["haze"] = haze
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
            first = next((i for i, m in enumerate(mats) if isinstance(m, dict) and "M_CE_Water" in m.get("parent", "")), None)
            for i, m in enumerate(mats):
                if first is not None and i != first and isinstance(m, dict) and "M_CE_Water" in m.get("parent", ""):
                    mats[i] = json.loads(json.dumps(mats[first]))
    structures = mark_structures(level)
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
    json.dump(level, open(p["out_level"], "w", encoding="utf-8"), indent=1)
    print(f"  {code}: level file with {len(level['foliage']['groups'])} foliage group(s), {structures} structure slot(s), "
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


def append_foliage(path, records):
    """One more group at the end of a foliage file (MJF3): records of
    [x, y, z, yaw degrees, scale, normal x, normal y]."""
    import struct
    raw = bytearray(open(path, "rb").read())
    version, n = struct.unpack_from("<II", raw, 4)
    struct.pack_into("<II", raw, 4, version, n + 1)
    raw += struct.pack("<I", len(records))
    for x, y, z, yaw, sc, nx, ny in records:
        raw += struct.pack("<fffBBbbBBB", x, y, z, int(yaw / 360.0 * 256) % 256, max(1, min(255, round(sc * 100))),
                           max(-127, min(127, round(nx * 127))), max(-127, min(127, round(ny * 127))), 255, 255, 255)
    open(path, "wb").write(bytes(raw))


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


def stage_install(code, m, p):
    if "HaloCampaignEvolved" in run(["tasklist"], check=False):
        sys.exit("close the game before installing")
    base = hub_map_container(m)
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(p["bake"], f"pakchunk997-MJOLNIRMAP-{code}_P.{e}"), f"{base}.{e}")
    if m.get("mesh_container"):
        mesh = hub_map_container(m, "pakchunk986-")
        for e in ("utoc", "ucas"):
            shutil.copyfile(f"{m['mesh_container']}.{e}", f"{mesh}.{e}")
    for f in glob.glob(os.path.join(p["bake"], f"pakchunk{m['chunk']}-MJOLNIRLAND-Windows.*")):
        shutil.copyfile(f, os.path.join(PAKS, os.path.basename(f)))
    data = os.path.join(UE4SS, "MJOLNIRMaps", code)
    shutil.copyfile(p["out_level"], os.path.join(data, "level.json"))
    shutil.copyfile(os.path.join(p["work"], "foliage.bin"), os.path.join(data, "foliage.bin"))
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
    ap.add_argument("--install", action="store_true", help="add the install stage")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/upgrade")
    ap.add_argument("--no-masters", action="store_true", help="skip rebuilding the trial masters in the editor stage")
    a = ap.parse_args()
    config = json.load(open(CONFIG, encoding="utf-8"))
    stages = [s for s in a.stages.split(",") if s]
    if a.install and "install" not in stages:
        stages.append("install")
    bad = [s for s in stages if s not in STAGES] + [c for c in a.maps if c not in config]
    if bad:
        sys.exit(f"unknown: {bad}")
    maps = {c: config[c] for c in a.maps}
    ps = {c: paths(c, m, a.work) for c, m in maps.items()}
    for p in ps.values():
        os.makedirs(p["work"], exist_ok=True)
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
            install_shared()
        for c, m in maps.items():
            globals()[f"stage_{stage}"](c, m, ps[c])
    print("done")


if __name__ == "__main__":
    main()
