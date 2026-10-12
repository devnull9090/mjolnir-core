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
            trial masters (Scripts/build_ce_materials.py, chunk 983)
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
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CONFIG = os.path.join(HERE, "ce_upgrade_maps.json")
PROJECT = os.path.join(REPO, "unreal", "MJOLNIRMaterials")
STAGED = os.path.join(PROJECT, "Saved", "StagedBuilds", "Windows", "Meteorite", "Content", "Paks")
STAGES = ("land", "foliage", "swap", "editor", "cook", "bake", "assemble", "install")
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
    os.makedirs(p["foliage"], exist_ok=True)
    out = run(cmd)
    print("  " + out.strip().splitlines()[-1][:200])


def stage_swap(code, m, p):
    data = os.path.join(HERE, "data")
    sea = sea_height(json.load(open(p["level"], encoding="utf-8")))
    out = run([sys.executable, os.path.join(HERE, "scenery_swap.py"), "swap", p["scene"],
               os.path.join(p["scene"], "materials.spec.json"), os.path.join(data, "b30_tree_recipes.json"),
               os.path.join(data, "b30_scenery_bounds.json"), os.path.join(p["work"], "swap.json"),
               "--rocks", m.get("rocks", "beach"), "--foliage", os.path.join(p["foliage"], "foliage.json"),
               "--staging", staging(p)]
              + (["--sea", f"{sea:.1f}"] if sea is not None else []))
    print("  " + out.strip().splitlines()[-1][:200])


def stage_editor(code, m, p):
    out = powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_landscape.py"],
                     env={"MJ_LANDSCAPE": p["land"], "MJ_LANDSCAPE_NAME": m["landscape"],
                          "MJ_LANDSCAPE_CHUNK": str(m["chunk"])})
    log = open(os.path.join(PROJECT, "Saved_build_ce_landscape.log"), encoding="utf-8", errors="replace").read()
    if "landscape built" not in log or os.path.normcase(p["land"]) not in os.path.normcase(log.replace("/", "\\")):
        sys.exit(f"{code}: the landscape world was not built:\n{out[-2000:]}")
    print(f"  {code}: world /Game/Levels/Halo1/Solo/{m['landscape']} built")


def build_masters():
    powershell(os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), ["-Script", "Scripts/build_ce_materials.py"],
               env={"MJ_CE_ROOT": "/Game/MJOLNIR/CETrial", "MJ_CE_CHUNK": "983"})
    log = open(os.path.join(PROJECT, "Saved_build_ce_materials.log"), encoding="utf-8", errors="replace").read()
    if "trial materials built" not in log or "Traceback" in log:
        sys.exit("the trial masters did not build: see " + os.path.join(PROJECT, "Saved_build_ce_materials.log"))
    print("  trial masters built")


def stage_cook(maps):
    worlds = "+".join(f"/Game/Levels/Halo1/Solo/{m['landscape']}/{m['landscape']}" for m in maps)
    out = powershell(os.path.join(REPO, "tools", "ue", "cook.ps1"), ["-Map", worlds])
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
               os.path.join(p["conv"], m["sbsp"]).replace("\\", "/"), code, p["bake"].replace("\\", "/")],
              env=dict(tool_env, MSYS2_ARG_CONV_EXCL="/Game"))
    if not os.path.exists(os.path.join(p["bake"], f"pakchunk997-MJOLNIRMAP-{code}_P.utoc")):
        sys.exit(f"{code}: no map container baked:\n{out[-2000:]}")
    print(f"  {code}: map container baked")


def stage_assemble(code, m, p):
    land = json.load(open(os.path.join(p["land"], "landscape.json"), encoding="utf-8"))
    fol = json.load(open(os.path.join(p["foliage"], "foliage.json"), encoding="utf-8"))
    level = json.load(open(p["level"], encoding="utf-8"))
    level["landscape"] = {k: land[k] for k in ("material", "cut", "pbr", "cliff") if k in land}
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
                                               "cull": [20000, 45000], "shadow": True})
            print(f"  {code}: {len(leaves)} leaf cluster(s) on the swapped trees")
        print(f"  {code}: {swap['count']} scenery object(s) swapped, {hidden} CE slot(s) hidden")
    # The level's sky (ce_upgrade_maps.json "environment"): merged into
    # environment, a key at a time (skylight.lower, clouds, ...).
    env = level.setdefault("environment", {})
    for key, value in (m.get("environment") or {}).items():
        if isinstance(value, dict) and isinstance(env.get(key), dict):
            env[key].update(value)
        else:
            env[key] = value
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
    json.dump(level, open(p["out_level"], "w", encoding="utf-8"), indent=1)
    print(f"  {code}: level file with {len(level['foliage']['groups'])} foliage group(s), {structures} structure slot(s)")


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
    print(f"  {code}: installed over {os.path.basename(base)}")


def install_shared():
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(STAGED, f"pakchunk983-Windows.{e}"),
                        os.path.join(PAKS, f"pakchunk983-MJOLNIRCETRIAL-Windows.{e}"))
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
