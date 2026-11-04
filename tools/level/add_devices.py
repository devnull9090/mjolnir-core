#!/usr/bin/env python3
"""Give an already converted CE map its scripted devices, with no reconvert.

    add_devices.py <map.map> <staging> <scene dir> <base level.json> <runtime level.json> <CODE> <out dir>
        --script <map.hsc> --machines <machines dir> [--control <tag>] [--paks ...] [--examples ...]

`staging` must be a fresh halo2ue export (with `device` blocks), `scene dir`
the folder the map's meshes were built in (scene.gltf and its siblings,
materials.spec.json, the SM_*.uasset and .args of the last build). `machines
dir` is tools/level/ce_machines.py's output.

The script decides what comes across: the machines and controls it names
become placements of the simulation's own, the trigger volumes and cutscene
flags it names are carried over. So does each automatic door machines.json
holds, one machine per moving part, and scenery ce_promote.py marked. A machine
the script names and machines.json lacks stops the tool, since the engine would
silently drop every script that uses it.

- The parts that move leave the map's meshes (triangles matched to the staged
  model, so every other section keeps its slot and lighting) and become meshes
  of their own, one per machine, `SM_<CODE>_Dev<k>` and `..t` for its
  transparent parts.
- Both level files gain what they need: the base level (what `level bake`
  reads) the `blam` lanes, the runtime level the decor and `devices`, which
  MJOLNIRLevelLoader's devices.lua rides on the machines' actors.

Writes to <out dir>: <name>.base.level.json, level.json, the mesh container
pakchunk986-MJOLNIRMESH-<CODE>_P, and the rebuilt .uasset files.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "ce_scripts"))
import ce_scenario  # noqa: E402
from merge_ce_scene import ce_rotation, ce_to_gltf, load_gltf, primitives, write_gltf  # noqa: E402

CM = 304.8
WU_M = 3.048


def to_ue(p):
    return [round(p[0] * CM, 1), round(-p[1] * CM, 1), round(p[2] * CM, 1)]


def group_lanes(device):
    """A placement's `power_group` and `position_group`, where it has them."""
    return {k: device[k + "_name"] for k in ("power_group", "position_group") if k + "_name" in device}


def gltf_to_ce(p):
    """`ce_to_gltf` undone: glTF metres, y up, to CE world units."""
    return [float(p[0]) / WU_M, -float(p[2]) / WU_M, float(p[1]) / WU_M]


def yaw_ue(rot):
    return round(-math.degrees(rot[0]), 1)


def script_words(text):
    """Every bare word of a script, comments and strings aside."""
    text = re.sub(r";.*", "", text)
    text = re.sub(r'"[^"]*"', " ", text)
    return set(re.findall(r"[A-Za-z0-9_\-]+", text))


def key(p):
    return tuple(np.round(p / 0.002).astype(np.int64))


def split_scene(prims, moving):
    """Take the triangles whose corners are all in `moving` (one set of
    vertex keys per machine) out of `prims`. Returns the remaining primitives
    and, per machine, its triangles as primitives of their own. A section
    left with nothing keeps a degenerate triangle, so its slot stays."""
    taken = [[] for _ in moving]
    rest = []
    for p in prims:
        tri = p["idx"].reshape(-1, 3)
        keys = [key(v) for v in p["pos"]]
        owner = np.full(len(tri), -1)
        for m, verts in enumerate(moving):
            inside = np.array([k in verts for k in keys])
            hit = inside[tri].all(axis=1) & (owner < 0)
            owner[hit] = m
        for m in range(len(moving)):
            sel = tri[owner == m]
            if len(sel):
                taken[m].append({**p, "idx": sel.reshape(-1)})
        left = tri[owner < 0]
        if len(left) == 0:
            left = np.zeros((1, 3), dtype=tri.dtype)
        rest.append({**p, "idx": left.reshape(-1)})
    return rest, taken


def compact(p):
    used, inverse = np.unique(p["idx"], return_inverse=True)
    out = dict(p)
    for k in ("pos", "nrm", "uv0", "uv1", "tan", "inc"):
        out[k] = p[k][used]
    out["idx"] = inverse.astype(np.uint32)
    return out


def rewrite(a, gltf, donor, package, rsp_lines, leaf):
    """Run mesh_rewrite; returns (x, y, z, scale)."""
    exe = os.path.join(a.examples, "mesh_rewrite.exe")
    rsp = os.path.join(a.out, leaf + ".args")
    open(rsp, "w", encoding="utf-8").write("\n".join(rsp_lines) + "\n")
    uasset = os.path.join(a.out, leaf + ".uasset")
    args = [exe, a.paks, donor, gltf, uasset, "--offset", "0,0,0", "--lightmap-uvs", "--rename", "@" + rsp]
    log = subprocess.run(args, cwd=a.repo, capture_output=True, text=True)
    open(os.path.join(a.out, leaf + ".log"), "w").write(log.stdout + log.stderr)
    if log.returncode != 0 or "MISMATCH" in log.stdout:
        sys.exit(f"mesh_rewrite failed for {gltf}:\n{(log.stdout + log.stderr)[-1500:]}")
    m = re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)", log.stdout)
    return tuple(map(float, m.groups())), uasset


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for n in ("map", "staging", "scene", "base", "runtime", "code", "out"):
        ap.add_argument(n)
    ap.add_argument("--script", required=True)
    ap.add_argument("--machines", required=True)
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    repo = os.path.dirname(os.path.dirname(HERE))
    ap.add_argument("--repo", default=repo)
    ap.add_argument("--examples", default=os.path.join(repo, "target", "release", "examples"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    code = a.code.upper()
    root = f"/Game/MJOLNIR/Maps/{code}"
    scenario = ce_scenario.Scenario(a.map, os.path.join(a.staging, "tags.json"))
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    built = json.load(open(os.path.join(a.machines, "machines.json"), encoding="utf-8"))
    spec = json.load(open(os.path.join(a.scene, "materials.spec.json"), encoding="utf-8"))
    by_pattern = {s["pattern"]: s for s in spec["slots"]}
    text = open(a.script, encoding="utf-8").read()
    words = script_words(text)

    # Every part of what moves: a device, its tag, the node it rides and where
    # it stands (a door's parts stand at their nodes). An unnamed door gets a
    # name of its own: the level's lanes and the loader's list go by name.
    machines = []
    staged = [e for e in placement["entries"] if e["kind"] == "machine" and not e.get("promoted")]
    if len(staged) != len(scenario.machines()):
        sys.exit("the staging's machines do not line up with the scenario's")
    for m in scenario.machines():
        spec = built.get(m["tag"])
        if m["name"] in words and not spec:
            sys.exit(f"{m['name']}: {m['tag']} is not in machines.json")
        if m["name"] in words and spec and "parts" not in spec:
            machines.append({**m, "spec": spec, "entry": staged[m["index"]], "auto": False})
        elif spec and "parts" in spec and (m["name"] in words or not m["flags"] & 1):
            r = ce_rotation(*m["rotation"])
            for j, part in enumerate(spec["parts"]):
                at = ce_to_gltf(m["position"]) + r @ ce_to_gltf(part["offset"])
                machines.append({**m, "name": f"{m['name'] or 'door%d' % m['index']}_{j}", "spec": part,
                                 "position": gltf_to_ce(at), "entry": staged[m["index"]], "auto": part["kind"] == "door"})
    objects = scenario.named_objects()
    for e in placement["entries"]:
        name = e.get("promoted")
        if name and name in words and e["asset"] in built:
            o = objects[name]
            machines.append({"name": name, "tag": e["asset"], "position": o["position"], "rotation": o["rotation"],
                             "spec": built[e["asset"]], "entry": e, "auto": False})
    controls = [c for c in scenario.controls() if c["name"] in words]
    volumes = [v for v in scenario.trigger_volumes() if v["name"] in words]
    flags = [f for f in scenario.cutscene_flags() if f["name"] in words]
    print(f"{len(machines)} machine(s), {len(controls)} control(s), {len(volumes)} volume(s), {len(flags)} flag(s)")

    # The staged entries, in machine order, and each moving part's vertices.
    moving = []
    for m in machines:
        e = m["entry"]
        g, buf = load_gltf(os.path.join(a.staging, e["model"]))
        r = ce_rotation(*e.get("rot", [0, 0, 0]))
        t = ce_to_gltf(e["pos"])
        node = m["spec"]["node"]
        verts = set()
        for p in primitives(g, buf):
            pos = p["pos"] @ r.T + t
            for k, v in enumerate(pos):
                if node is None or p["joint"] is None or int(p["joint"][k]) == node:
                    verts.add(key(v))
        moving.append(verts)

    # The two meshes the parts leave.
    # A map with no water has no water-free copy of its transparent parts.
    clear = "scene_translucent_nowater.gltf"
    if not os.path.exists(os.path.join(a.scene, clear)):
        clear = "scene_translucent.gltf"
    jobs = [("scene.gltf", "basicshapes/cylinder", "Terrain"), (clear, "basicshapes/cone", "Translucent")]
    parts = [{"opaque": [], "clear": []} for _ in machines]
    spawned = {}
    for gltf, donor, suffix in jobs:
        g, buf = load_gltf(os.path.join(a.scene, gltf))
        prims = primitives(g, buf)
        for p in prims:
            if p["uv1"] is None:
                p["uv1"] = np.zeros((len(p["pos"]), 2))
            if p["inc"] is None:
                p["inc"] = np.zeros((len(p["pos"]), 3))
        rest, taken = split_scene(prims, moving)
        moved = sum(len(q["idx"]) // 3 for t in taken for q in t)
        print(f"  {gltf}: {moved} triangle(s) of {sum(len(p['idx']) // 3 for p in prims)} move")
        for k, t in enumerate(taken):
            parts[k]["opaque" if suffix == "Terrain" else "clear"] += [compact(q) for q in t]
        out = os.path.join(a.out, f"scene_{suffix}.gltf")
        write_gltf(rest, out)
        leaf = f"SM_{code}_{suffix}"
        lines = open(os.path.join(a.scene, leaf + ".args"), encoding="utf-8").read().splitlines()
        spawned[leaf] = rewrite(a, out, donor, f"{root}/{leaf}", lines, leaf)

    # A mesh per machine's opaque and transparent parts.
    decor, devices, added = [], [], []
    for k, (m, part) in enumerate(zip(machines, parts)):
        ids = []
        for kind, prims in (("", part["opaque"]), ("t", part["clear"])):
            if not prims:
                continue
            leaf = f"SM_{code}_Dev{k}{kind}"
            out = os.path.join(a.out, leaf + ".gltf")
            write_gltf(prims, out)
            names = []
            for p in prims:
                if p["material"] not in names:
                    names.append(p["material"])
            slots = [by_pattern[n.lower() + "$"] for n in names]
            lines = [f"{root}/{leaf}"]
            for j, s in enumerate(slots):
                lines += ["--material", f"s_{s['name']}={s['material']['parent']}={s['pattern']}" + ("|*" if j == 0 else "")]
            (x, y, z, sc), uasset = rewrite(a, out, "basicshapes/cube", f"{root}/{leaf}", lines, leaf)
            added += ["--package", f"{root}/{leaf}={uasset}"]
            ident = f"dev_{m['name']}{kind}"
            ids.append(ident)
            decor.append({"id": ident, "mesh": f"{root}/{leaf}.{leaf}", "pos": [x, y, z], "scale": [sc, sc, sc],
                          "materials": [s["material"] for s in slots], "cast_shadow": False})
        if not ids:
            sys.exit(f"{m['name']}: no triangles matched; is the scene built from this staging?")
        devices.append({"name": m["name"], "class": m["spec"]["class"], "pos": to_ue(m["position"]), "decor": ids,
                        "shield": m["spec"]["kind"] == "shield"})
        print(f"  {m['name']}: {ids}")

    for leaf in ("Terrain", "Translucent", "Sky", "Water"):
        name = f"SM_{code}_{leaf}"
        at = os.path.join(a.out, name + ".uasset")
        if not os.path.exists(at):
            if not os.path.exists(os.path.join(a.scene, name + ".uasset")):
                continue
            shutil.copyfile(os.path.join(a.scene, name + ".uasset"), at)
        added += ["--package", f"{root}/{name}={at}"]
    po = subprocess.run([os.path.join(a.examples, "package_add.exe"), a.paks, a.out, "--name", f"pakchunk986-MJOLNIRMESH-{code}_P"] + added,
                        capture_output=True, text=True)
    print(po.stdout.strip()[-300:])
    if po.returncode != 0:
        sys.exit(f"package_add failed:\n{po.stderr[-2000:]}")

    # The bake's half.
    base = json.load(open(a.base, encoding="utf-8"))
    blam = base["blam"]
    blam["object_names"] = [m["name"] for m in machines] + [c["name"] for c in controls]
    blam["trigger_volumes"] = [{"name": v["name"], "pos": to_ue(v["position"]), "forward": v["forward"], "up": v["up"],
                                "extents": v["extents"]} for v in volumes]
    # A group a script names, or that ties a carried control to a machine.
    groups = scenario.device_groups()
    used = {g["name"] for g in groups if g["name"] in words}
    for d in machines + controls:
        for lane in ("power_group", "position_group"):
            k = d.get(lane, -1)
            if 0 <= k < len(groups):
                d[lane + "_name"] = groups[k]["name"]
                used.add(groups[k]["name"])
    blam["device_groups"] = [{"name": g["name"], "initial_value": g["initial_value"], "flags": g["flags"]}
                             for g in groups if g["name"] in used]
    blam["cutscene_flags"] = [{"name": f["name"], "pos": to_ue(f["position"]), "yaw": round(-math.degrees(f["facing"][0]), 2),
                               "pitch": round(math.degrees(f["facing"][1]), 2)} for f in flags]
    for m in machines:
        r = m["rotation"]
        blam["objects"].append({"tag": m["spec"]["tag"], "group": "machines", "pos": to_ue(m["position"]),
                                "rot": [0, yaw_ue(r), 0], "name": m["name"],
                                "set": {"object data.rotation": "({}, {}, {})".format(*r),
                                        # "does not operate automatically" and "does not close automatically".
                                        "machine data.flags": "0x0" if m["auto"] else "0x21"},
                                **group_lanes(m)})
    for c in controls:
        r = c["rotation"]
        blam["objects"].append({"tag": built["_control"]["tag"], "group": "controls", "pos": to_ue(c["position"]),
                                "rot": [0, yaw_ue(r), 0], "name": c["name"],
                                # The game's panel faces its actor's forward; CE's holo
                                # panel's front is the other way.
                                "set": {"object data.rotation": "({}, {}, {})".format(r[0] + math.pi, r[1], r[2]),
                                        "control data.flags": "0x1"},
                                **group_lanes(c)})
    script = f"{code.lower()}.hsc"
    shutil.copyfile(a.script, os.path.join(a.out, script))
    blam["script"] = script
    clear = blam["clear"]
    clear["scripts"] = True
    json.dump(base, open(os.path.join(a.out, f"{code.lower()}.base.level.json"), "w", encoding="utf-8"), indent=1)

    # The loader's half.
    level = json.load(open(a.runtime, encoding="utf-8"))
    for item in level["decor"]:
        leaf = item.get("mesh", "").rsplit(".", 1)[-1]
        if leaf in spawned and item["id"].endswith(("_terrain", "_terrain_1")):
            (x, y, z, sc), _ = spawned[leaf]
            item["pos"], item["scale"] = [x, y, z], [sc, sc, sc]
        elif leaf in spawned:
            # The deep floor copy and such: moved by what the mesh moved.
            print(f"  note: {item['id']} also draws {leaf}")
    level["decor"] += decor
    level["devices"] = devices
    # A rebake starts from the level the pack ships (tools/level/add_bots.py).
    level["blam"] = {**blam, "bots": level["blam"].get("bots")} if level["blam"].get("bots") else blam
    json.dump(level, open(os.path.join(a.out, "level.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(devices)} device(s) -> {a.out}")


if __name__ == "__main__":
    main()
