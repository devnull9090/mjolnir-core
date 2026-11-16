#!/usr/bin/env python3
"""Make every prop a Halo 2 map moves a physics object, from the map's own tag
data, for tools/level/upgrade_ce_map.py's `physics_props`.

    python tools/level/h2_physics_props.py --conversion <h2 conversion> --out <dir> --code ZAN
        --paks <Paks> [--h2-staging <fresh mjolnir cache stage>] [--skip <asset substring> ...]

Halo 2 moves a crate (`bloc`) whose physics model has a rigid body that is
neither keyframed nor fixed (crate::h2::props, the staging's `h2_physics`);
scenery never moves. Each such prop type (one rigid body: a jointed crane or
awning stays still) gets:

- its model copied out of the staging, its materials named as the merged
  scene's object-lit slots (`__lmobj`), and its copies taken out of the
  merged scene and translucent meshes (remove_placed_props.py);
- three crate tags (physics_prop_tags.py): a physics shape of the model's
  box, a mass scale from Halo 2's mass, and, when Halo 2's damage info gives
  it vitality and a response that kills it, that vitality and our death
  response (Zanzibar's fusion coils: 15);
- its mesh, built with the scene's into the map's mesh container
  (build_terrain_meshes.py);
- a `physics_props.json` entry: the crate tag, the shared crate actor class
  (props.lua tells types apart by where a crate appears), the mesh, and for
  a prop that dies the sounds Halo 2's death effect plays (staged by `mjolnir
  cache stage` into sounds_out, imported to /Game/MJOLNIR/Maps/<CODE>/Sounds
  by build_ce_sounds.py) with our explosion, fire and scorch.

The staging's placement.json needs the `h2_physics` and `h2_damage` fields
(written by `mjolnir cache stage` since 2026-11-15); an older conversion's
are merged from --h2-staging, matched by asset and position.
"""
import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WU = 3.048
# One crate actor class for every prop type: props.lua dresses each crate by
# the prop placed nearest where it first appears.
CRATE_ACTOR = "/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_F/BP_UNSC_Gen_Crate_F"
FX = "/Game/FX/Library/Sandbox/Weapons/Launcher/FuelRodCannon/Explo/"
DEATH_FX = {
    "systems": [
        {"system": FX + "NS_FuelRod_Explo.NS_FuelRod_Explo", "scale": 1.5, "up": 12},
        {"system": FX + "NS_FuelRod_Explo_GroundReaction.NS_FuelRod_Explo_GroundReaction", "scale": 1.5},
    ],
    "decal": {
        "material": "/Game/FX/Library/Sandbox/Weapons/Grenades/Plasma/Explo/"
                    "MI_PlasmaGrenadeExplo_Update_Decal.MI_PlasmaGrenadeExplo_Update_Decal",
        "color": [0.06, 0.40, 0.0, 1.0], "size": [120, 180, 180], "life": 45,
    },
}


def camel(leaf):
    return "".join(w[:1].upper() + w[1:] for w in leaf.replace("-", "_").split("_") if w)


def gltf_bounds(path):
    """(min, max) of a glTF's positions, metres, y up."""
    g = json.load(open(path, encoding="utf-8"))
    lo, hi = [1e9] * 3, [-1e9] * 3
    for mesh in g["meshes"]:
        for p in mesh["primitives"]:
            a = g["accessors"][p["attributes"]["POSITION"]]
            lo = [min(x, y) for x, y in zip(lo, a["min"])]
            hi = [max(x, y) for x, y in zip(hi, a["max"])]
    return lo, hi


def merge_h2_fields(placement, fresh):
    """Copy h2_* fields from a fresh staging's entries onto an older one's,
    matched by asset and position."""
    key = lambda e: (e.get("asset"), tuple(round(v, 2) for v in e.get("pos") or []))
    by = {key(e): e for e in fresh["entries"]}
    n = 0
    for e in placement["entries"]:
        f = by.get(key(e))
        if f:
            for k, v in f.items():
                if k.startswith("h2_"):
                    e[k] = v
                    n += 1
    return n


def static_extras(fresh_dir, conv_placement, code, out, cli=None):
    """Devices a fresh staging places that the conversion did not: doors
    (machine type 1: Zanzibar's house gate) and controls (its keypad). A
    control is one world-space mesh. A door is a mesh a moving node (the
    staged model's `_NODE`), each at the door's rest pose in world space,
    and `doors.json` gives every part's world transform at every frame of
    Halo 2's opening (crate::h2::door) for the level loader to play when a
    player presses the control of the door's position group. Returns (mesh
    jobs, spec materials, texture imports, decor meshes)."""
    sys.path.insert(0, os.path.join(REPO, "tools", "level"))
    import numpy as np
    import merge_ce_scene as mcs
    fresh = json.load(open(os.path.join(fresh_dir, "placement.json"), encoding="utf-8"))
    shaders = json.load(open(os.path.join(fresh_dir, "materials.json"), encoding="utf-8"))
    sounds = json.load(open(os.path.join(fresh_dir, "sounds_out", "sounds.json"), encoding="utf-8")).get("sounds", {})
    have = {(e.get("asset"), tuple(round(v, 2) for v in e.get("pos") or [])) for e in conv_placement["entries"]}
    jobs, mats, tex, ids, doors = [], [], {}, [], []
    machine_cache = {}  # h2_door_machines: each Halo 2 tag's machine tags, built once
    T_ = lambda f: f"/Game/MJOLNIR/Maps/{code}/Textures/T_{f[:-4]}.T_{f[:-4]}"

    def waves(sid):
        snd = sounds.get(sid) or {}
        return [f"/Game/MJOLNIR/Maps/{code}/Sounds/{os.path.splitext(f)[0]}.{os.path.splitext(f)[0]}"
                for f in snd.get("files") or []], snd.get("gain", 1.0)

    def material(name):
        sh = shaders.get(name) or {}
        d = (sh.get("shader") or {})
        textures, scalars = {}, {"PrimaryScale": 1.0, "BumpScale": 1.0, "HasPrimary": 0.0, "HasBump": 0.0}
        if sh.get("base_map"):
            textures["Base"] = T_(sh["base_map"])
            tex[sh["base_map"]] = 1
        bump = (d.get("bump") or {}).get("map")
        if bump:
            textures["Bump"] = T_(bump)
            scalars.update(HasBump=1.0, BumpScale=float((d.get("bump") or {}).get("scale") or 1.0))
            tex[bump] = 1
        prim = (d.get("detail") or {}).get("primary")
        if prim:
            textures["Primary"] = T_(prim)
            scalars.update(HasPrimary=1.0, PrimaryScale=float((d.get("detail") or {}).get("primary_scale") or 1.0))
            tex[prim] = 1
        # A self-illuminated screen (the gate keypad's `screen`,
        # tex_bump_illum with no base map: Halo 2 draws its map's blue
        # icon glowing on black). The base goes black (AlbedoGain 0) where
        # there is no base map, or the master's white default showed as a
        # blank white screen (2026-11-15); upgrade_ce_map.prop_lit makes it
        # a plain glow (PlainGlow) in its first channel's colour.
        vectors = {}
        si = d.get("self_illum") or {}
        if si.get("map"):
            textures["SelfIllumMap"] = T_(si["map"])
            tex[si["map"]] = 1
            scalars.update(HasSelfIllum=1.0, SelfIllumScale=float(si.get("map_scale") or 1.0), PlainGlow=1.0)
            ch = (si.get("channels") or [{"on": si.get("on_color") or [1, 1, 1]}])[0]
            vectors["SelfOn0"] = list(map(float, ch.get("on") or [1, 1, 1])) + [1.0]
            if not sh.get("base_map"):
                scalars["AlbedoGain"] = 0.0
        if not any(m["name"] == name for m in mats):
            mats.append({"name": name, "parent": "/Game/MJOLNIR/CE/M_CE_Environment.M_CE_Environment",
                         "scalars": scalars, "vectors": vectors, "textures": textures})

    def to_world(prims, e):
        r = mcs.ce_rotation(*e.get("rot", [0, 0, 0]))
        t = mcs.ce_to_gltf(e["pos"])
        for pr in prims:
            pr["pos"] = pr["pos"] @ r.T + t
            pr["nrm"] = pr["nrm"] @ r.T
            pr["tan"] = mcs.tangents_for(pr["nrm"]) if pr.get("tan") is None else pr["tan"]
            if pr.get("uv1") is None:
                pr["uv1"] = pr["uv0"]
            if pr.get("inc") is None:
                pr["inc"] = pr["nrm"]
        return r, t

    def mesh_for(prims, leaf):
        gpath = os.path.join(out, f"extra_{leaf}.gltf")
        mcs.write_gltf(prims, gpath)
        mesh = f"SM_{code}_{camel(leaf)}"
        jobs.append(f"{gpath}=basicshapes/cube=/Game/MJOLNIR/Maps/{code}/{mesh}")
        ids.append(mesh)
        for pr in prims:
            material(pr["material"])
        return mesh

    controls = [e for e in fresh["entries"] if e.get("tag_class") == "ctrl"]
    for e in fresh["entries"]:
        if e.get("tag_class") not in ("mach", "ctrl") or not e.get("model") or e.get("h2_motion"):
            continue
        if (e.get("asset"), tuple(round(v, 2) for v in e.get("pos") or [])) in have:
            continue
        g, buf = mcs.load_gltf(os.path.join(fresh_dir, e["model"]))
        prims = mcs.primitives(g, buf)
        leaf = e["asset"].split("\\")[-1]
        door = e.get("h2_door")
        if not door:
            to_world(prims, e)
            mesh_for(prims, leaf)
            continue
        # The node of each vertex, primitive by primitive (as primitives()
        # walks them), each triangle by its first corner.
        node_of = []
        for nd in g["nodes"]:
            if "mesh" in nd:
                for pp in g["meshes"][nd["mesh"]]["primitives"]:
                    acc = pp["attributes"].get("_NODE")
                    node_of.append(mcs.accessor(g, buf, acc)[:, 0].round().astype(int) if acc is not None else None)
        to_world(prims, e)
        nodes = door["nodes"]
        parts = {}
        for pr, nv in zip(prims, node_of):
            tris = pr["idx"].reshape(-1, 3)
            per = nv[tris[:, 0]] if nv is not None else np.zeros(len(tris), dtype=int)
            for n in sorted(set(per.tolist())):
                keep = tris[per == n]
                used, inv = np.unique(keep.reshape(-1), return_inverse=True)
                q = {kk: (v[used] if isinstance(v, np.ndarray) and len(v) == len(pr["pos"]) else v) for kk, v in pr.items()}
                q["idx"] = inv.astype(np.uint32)
                parts.setdefault(n, []).append(q)

        # Each node's mesh, at rest; the loader attaches it to its node's
        # machine (h2_door_machines), which Unreal then carries.
        part_list = []
        for n, ps in sorted(parts.items()):
            mesh = mesh_for(ps, f"{leaf}_n{n}")
            part_list.append({"id": f"{code.lower()}_{mesh.lower()}", "node": nodes[n]["name"]})
        grp = (e.get("h2_device") or {}).get("position_group", -1)
        ctl = next((c for c in controls if grp >= 0 and (c.get("h2_device") or {}).get("position_group") == grp), None)
        entry = {"asset": e["asset"], "seconds": door["seconds"], "parts": part_list, "sounds": {},
                 "at_cm": [round(v * 304.8, 1) for v in (e["pos"][0], -e["pos"][1], e["pos"][2])]}
        for key, sid in (door.get("sounds") or {}).items():
            w, gn = waves(sid)
            if w:
                entry["sounds"][key] = {"paths": w, "gain": round(gn, 3)}
        if ctl:
            entry["control_cm"] = [round(v * 304.8, 1) for v in (ctl["pos"][0], -ctl["pos"][1], ctl["pos"][2])]
            ps = (ctl.get("h2_device") or {}).get("press_sound")
            if ps:
                w, gn = waves(ps)
                if w:
                    entry["sounds"]["press"] = {"paths": w, "gain": round(gn, 3)}
        # Its collision and its opening in the simulation (h2_door_machines):
        # the machines slide with the door, the control opens it for every
        # player, the loader poses these meshes from the machines.
        if cli:
            import h2_door_machines
            built = h2_door_machines.build(fresh_dir, e, controls, code, out, cli, machine_cache)
            entry["machines"], entry["blam"] = built["machines"], built["blam"]
            if built["control"]:
                entry["sim_control"] = built["control"]
        doors.append(entry)
    json.dump(doors, open(os.path.join(out, "doors.json"), "w", encoding="utf-8"), indent=1)
    imports = [{"file": os.path.join(fresh_dir, "textures", f), "dest": f"/Game/MJOLNIR/Maps/{code}/Textures",
                "name": "T_" + f[:-4]} for f in sorted(tex)]
    return jobs, mats, imports, ids


def run(*args, **kw):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"{os.path.basename(str(args[1]))} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--conversion", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--paks", required=True)
    ap.add_argument("--h2-staging", help="a fresh `mjolnir cache stage` of the map, for an older conversion")
    ap.add_argument("--skip", action="append", default=[], help="leave props whose asset contains this still")
    ap.add_argument("--cli", default=os.path.join(REPO, "target", "release", "mjolnir.exe"))
    ap.add_argument("--no-meshes", action="store_true", help="skip the mesh container (tags and json only)")
    a = ap.parse_args()
    conv, out, code = a.conversion, a.out, a.code
    staging = os.path.join(conv, "staging")
    os.makedirs(out, exist_ok=True)
    placement = json.load(open(os.path.join(staging, "placement.json"), encoding="utf-8"))
    fresh_dir = a.h2_staging or staging
    if not any("h2_physics" in e for e in placement["entries"]):
        if not a.h2_staging:
            sys.exit("the staging has no h2_physics fields: restage it, or pass --h2-staging")
        fresh = json.load(open(os.path.join(a.h2_staging, "placement.json"), encoding="utf-8"))
        print(f"  {merge_h2_fields(placement, fresh)} h2 field(s) merged from {a.h2_staging}")
    sounds = json.load(open(os.path.join(fresh_dir, "sounds_out", "sounds.json"), encoding="utf-8")).get("sounds", {})

    types = {}
    for e in placement["entries"]:
        ph = e.get("h2_physics")
        if e.get("tag_class") != "bloc" or not ph or not e.get("model"):
            continue
        if any(s in e["asset"] for s in a.skip):
            continue
        if ph.get("bodies", 1) != 1 or ph.get("constraints", 0):
            types.setdefault("__jointed", set()).add(e["asset"])
            continue
        types.setdefault(e["asset"], e)
    jointed = types.pop("__jointed", set())
    for asset in sorted(jointed):
        print(f"  still: {asset} (jointed: several rigid bodies or constraints)")

    specs, jobs, assets = [], [], []
    names = {m.get("name") for m in json.load(open(os.path.join(conv, "materials.spec.json"), encoding="utf-8"))["materials"]}
    tags_dir = os.path.join(out, "tags")
    for asset, e in sorted(types.items()):
        leaf = asset.split("\\")[-1]
        mesh_name = f"SM_{code}_{camel(leaf)}"
        # The model, its materials named as the merged scene's object-lit slots.
        g = json.load(open(os.path.join(staging, e["model"]), encoding="utf-8"))
        for mat in g.get("materials", []):
            if not mat["name"].endswith("__lmobj"):
                mat["name"] += "__lmobj"
            if mat["name"] not in names:
                print(f"    {leaf}: material {mat['name']} is not in the spec")
        for b in g["buffers"]:
            shutil.copyfile(os.path.join(staging, os.path.dirname(e["model"]), b["uri"]), os.path.join(out, leaf + ".bin"))
            b["uri"] = leaf + ".bin"
        gpath = os.path.join(out, leaf + ".gltf")
        json.dump(g, open(gpath, "w", encoding="utf-8"))
        lo, hi = gltf_bounds(gpath)
        # glTF (x, y up, -z) metres -> Halo world units.
        hx = max(abs(lo[0]), abs(hi[0])) / WU
        hy = max(abs(lo[2]), abs(hi[2])) / WU
        top, bottom = hi[1] / WU, min(0.0, lo[1] / WU)
        ph = e["h2_physics"]
        mass_scale = round(min(3.0, max(0.05, ph["mass"] / 900.0)), 3)
        dmg = e.get("h2_damage")
        death = None
        if dmg:
            death = next((r for r in dmg["responses"] if r["flags"] & 0x81 and r.get("effect")), None)
        tag = "\\".join(["objects", "mjolnir", code.lower(), leaf, leaf])
        args = [sys.executable, os.path.join(REPO, "tools", "level", "physics_prop_tags.py"), "--paks", a.paks,
                "--out", tags_dir, "--tag", tag, "--half", f"{max(hx, 0.03):.4f},{max(hy, 0.03):.4f}",
                "--height", f"{max(top, 0.05):.4f}", "--bottom", f"{bottom:.4f}", "--blueprint", CRATE_ACTOR,
                "--mass-scale", str(mass_scale), "--cli", a.cli]
        if death:
            args += ["--explode", str(dmg["vitality"])]
        print("  " + run(*args, env=dict(os.environ, MSYS2_ARG_CONV_EXCL="*")).strip().splitlines()[-1])
        spec = {"asset": asset, "crate": tag, "actor_class": f"{CRATE_ACTOR}.{CRATE_ACTOR.rsplit('/', 1)[-1]}_C",
                "mesh": f"/Game/MJOLNIR/Maps/{code}/{mesh_name}.{mesh_name}",
                "terrain": os.path.join(out, "terrain.json").replace("\\", "/"),
                "tags": [f"pakchunk996-MJOLNIRPROP-{leaf}-{p}_P" for p in "PHC"]}
        if death:
            fx = json.loads(json.dumps(DEATH_FX))
            waves, gain = [], 1.0
            for sid in death.get("sounds") or []:
                s = sounds.get(sid) or {}
                gain = s.get("gain", gain)
                for f in s.get("files") or []:
                    stem = os.path.splitext(f)[0]
                    waves.append(f"/Game/MJOLNIR/Maps/{code}/Sounds/{stem}.{stem}")
            if waves:
                fx["waves"] = {"paths": waves, "gain": round(gain, 3)}
            spec["death_fx"] = fx
            spec["h2_death"] = {"effect": death["effect"], "damage_effect": death.get("damage_effect"),
                                "decals": death.get("decals")}
        specs.append(spec)
        assets.append(asset)
        donor = "basicshapes/cylinder" if abs(hx - hy) < 0.05 * max(hx, hy) else "basicshapes/cube"
        jobs.append(f"{gpath}={donor}=/Game/MJOLNIR/Maps/{code}/{mesh_name}")

    # The props out of the merged meshes.
    for f in ("scene", "scene_translucent"):
        argv = [sys.executable, os.path.join(REPO, "tools", "level", "remove_placed_props.py"), staging,
                os.path.join(conv, f + ".gltf"), os.path.join(out, f + ".gltf")]
        for asset in assets:
            argv += ["--asset", asset]
        print("  " + run(*argv).strip().split(": ")[-1])
    # The scene's other pieces and the files the level build reads beside it.
    for f in os.listdir(conv):
        if f.startswith("scene_") and not os.path.exists(os.path.join(out, f)) and f not in (
                "scene.gltf", "scene_translucent.gltf"):
            shutil.copyfile(os.path.join(conv, f), os.path.join(out, f))
        if f in ("materials.spec.json",) or f.endswith((".collision.json", ".ce_collision.json")):
            shutil.copyfile(os.path.join(conv, f), os.path.join(out, f))

    if not a.no_meshes:
        r = f"/Game/MJOLNIR/Maps/{code}"
        mesh_jobs = [f"{out}/scene.gltf=basicshapes/cylinder={r}/SM_{code}_Terrain",
                     f"{out}/scene_translucent.gltf=basicshapes/cone={r}/SM_{code}_Translucent",
                     f"{conv}/scene_sky.gltf=basicshapes/sphere={r}/SM_{code}_Sky"]
        for f in sorted(os.listdir(conv)):
            if f.startswith("scene_machine_") and f.endswith(".gltf"):
                k = f[len("scene_machine_"):-len(".gltf")]
                mesh_jobs.append(f"{conv}/{f}=basicshapes/cube={r}/SM_{code}_Machine{k}")
        mesh_jobs += jobs
        # Machines the conversion left out (a closed door), as static decor.
        ex_jobs, ex_mats, ex_imports, ex_ids = static_extras(fresh_dir, placement, code, out, a.cli)
        spec_path = os.path.join(conv, "materials.spec.json")
        if ex_jobs:
            spec = json.load(open(spec_path, encoding="utf-8"))
            known = {m["name"] for m in spec["materials"]}
            spec["materials"] += [m for m in ex_mats if m["name"] not in known]
            # The mesh builder resolves a section's material from `slots`,
            # by its name as a pattern.
            have = {sl["name"] for sl in spec["slots"]}
            spec["slots"] += [{"name": m["name"], "pattern": m["name"] + "$",
                               "material": {k: v for k, v in m.items() if k != "name"}}
                              for m in ex_mats if m["name"] not in have]
            spec_path = os.path.join(out, "materials.spec.json")
            json.dump(spec, open(spec_path, "w", encoding="utf-8"))
            mesh_jobs += ex_jobs
            if ex_imports:
                lst = os.path.join(out, "import_extras.json")
                json.dump(ex_imports, open(lst, "w", encoding="utf-8"), indent=1)
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                    os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), "-Script", "Scripts/import_textures.py"],
                                   capture_output=True, text=True, env=dict(os.environ, MJ_IMPORT=lst))
                print(f"  extras: {', '.join(ex_ids)}; textures {len(ex_imports)}: "
                      + (r.stdout.strip().splitlines() or ["(no output)"])[-1][-80:])
        log = run(sys.executable, os.path.join(REPO, "tools", "level", "build_terrain_meshes.py"), "--paks", a.paks,
                  "--spec", spec_path, "--out", out, "--name", code.lower(),
                  "--offset", "0,0,0", "--fallback", "/Game/Env/Bio/Rock/Canyon/Materials/MI_Rock_Canyon_Generic",
                  "--examples", os.path.join(REPO, "target", "release", "examples"),
                  "--container", f"pakchunk986-MJOLNIRMESH-{code}_P",
                  "--placement", os.path.join(staging, "placement.json"), *mesh_jobs,
                  env=dict(os.environ, MSYS2_ARG_CONV_EXCL="/Game"))
        open(os.path.join(out, "build.log"), "w", encoding="utf-8").write(log)
        print(f"  meshes: {len(mesh_jobs)} into pakchunk986-MJOLNIRMESH-{code}_P")
    # The props' stencils as they are (upgrade_ce_map.py prop_lit draws a
    # slot on an `__overlay` copy with M_CE_PropOverlay, a 2x multiply that
    # needs the stencil itself), imported beside the copies.
    terrain = os.path.join(out, "terrain.json")
    if os.path.exists(terrain):
        meshes = {s["mesh"] for s in specs}
        wanted = set()
        for t in json.load(open(terrain, encoding="utf-8")):
            if t.get("mesh") in meshes:
                for mat in t.get("materials") or []:
                    map0 = str((mat.get("textures") or {}).get("Map0", "")) if isinstance(mat, dict) else ""
                    if "__overlay." in map0:
                        wanted.add(map0.rsplit("/", 1)[-1].split(".")[0].replace("__overlay", ""))
        items = []
        for name in sorted(wanted):
            png = os.path.join(staging, "textures", name[2:] + ".png")
            if os.path.exists(png):
                items.append({"file": png, "dest": f"/Game/MJOLNIR/Maps/{code}/Textures", "name": name})
        if items:
            lst = os.path.join(out, "import_textures.json")
            json.dump(items, open(lst, "w", encoding="utf-8"), indent=1)
            print(f"  stencils: importing {len(items)} ({', '.join(i['name'] for i in items)})")
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                os.path.join(REPO, "tools", "ue", "editor_cmd.ps1"), "-Script", "Scripts/import_textures.py"],
                               capture_output=True, text=True, env=dict(os.environ, MJ_IMPORT=lst))
            print("  " + (r.stdout.strip().splitlines() or ["(no output)"])[-1])
    # The extras' decor entries (terrain.json's, by mesh), for
    # upgrade_ce_map.py's `extra_decor`; a door part's id is the one
    # doors.json names. Not terrain (an id with "_terrain" gets the
    # terrain's shading and shadow copy); a door casts its shadow.
    ids_path = os.path.join(out, "extra_ids.json")
    if not a.no_meshes:
        json.dump(ex_ids, open(ids_path, "w", encoding="utf-8"))
    if os.path.exists(terrain) and os.path.exists(ids_path):
        want = {f"/Game/MJOLNIR/Maps/{code}/{m}" for m in json.load(open(ids_path, encoding="utf-8"))}
        extra = [t for t in json.load(open(terrain, encoding="utf-8")) if str(t.get("mesh", "")).split(".")[0] in want]
        for t in extra:
            t["id"] = f"{code.lower()}_" + str(t["mesh"]).split(".")[-1].lower()
            t["cast_shadow"] = True
        json.dump(extra, open(os.path.join(out, "extra_decor.json"), "w", encoding="utf-8"), indent=1)
        print(f"  extra decor: {len(extra)} item(s)")
        # Each machine's actor wears its part meshes (h2_door_machines
        # write_actors), now their rest positions are known.
        doors_path = os.path.join(out, "doors.json")
        if os.path.exists(doors_path):
            import h2_door_machines
            h2_door_machines.write_actors(json.load(open(doors_path, encoding="utf-8")), {t["id"]: t for t in extra},
                                          code, out, a.paks, os.path.join(REPO, "target", "release", "examples"))
    json.dump(specs, open(os.path.join(out, "physics_props.json"), "w", encoding="utf-8"), indent=1)
    print(f"{code}: {len(specs)} physics prop type(s) over "
          f"{sum(1 for e in placement['entries'] if e.get('asset') in assets)} placement(s) -> {out}/physics_props.json")


if __name__ == "__main__":
    main()
