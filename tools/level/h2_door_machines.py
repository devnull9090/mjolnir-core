"""The simulation's own machines for a Halo 2 door (Zanzibar's house gate), so
its collision opens with it and every player in the match sees it open.

The Blam simulation does all collision and networking. Each part of the door
that slides and has collision (crate::h2::door; the staged
`h2_door.collision` BSPs, one a node) becomes a device machine cloned from
B40's elevator family, as tools/level/ce_machines.py builds a CE gate: its
root slides by the node's offset at every frame of Halo 2's opening
(`slide_resource`), its collision is the node's own BSP at the node's rest
offset. The door's control (the keypad) becomes B40's switch panel; the
machines and the control share one device group, so a player pressing the
control opens the door in the simulation, which moves the collision and
replicates to every player. The level loader (doors.lua) poses the door's
own meshes from the machines' progress. Parts that turn (the gate's ramps)
are not machines: a clone has one root that slides or turns, not both.
"""
import json
import os
import shutil
import subprocess
import tempfile

import numpy as np

from ce_machines import CONTROL_DONOR, slide_resource
from h2_machines import DONOR, DONOR_CLASS, boxes, physics_args


def node_rest(nodes):
    """Each node's rest position in the object (CE wu), summed up its parents
    (the door's nodes are unrotated at rest)."""
    out = []
    for nd in nodes:
        t = np.array(nd["t"], dtype=float)
        out.append(t if nd["parent"] < 0 else out[nd["parent"]] + t)
    return out


def node_offsets(door, n):
    """Node n's object-space position offset from rest at every frame (its
    own slide plus its parents'), or None when it or a parent turns."""
    nodes, poses = door["nodes"], door["poses"]
    chain, k = [], n
    while k >= 0:
        chain.append(k)
        k = nodes[k]["parent"]
    for k in chain:
        for f in poses:
            q = f[k][1]
            if abs(abs(q[3]) - 1.0) > 1e-3:
                return None
    out = []
    for f in poses:
        d = np.zeros(3)
        for k in chain:
            tr = np.array(f[k][0], dtype=float)
            if not np.allclose(tr, nodes[k]["t"]):
                d += tr
        out.append(d)
    base = out[0].copy()
    return [list(map(float, o - base)) for o in out]


def box_triangles(lo, hi):
    """Two triangles a face of an axis box, for physics_args' boxes."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    c = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]
    tris = []
    for a, b, cc, d in faces:
        tris += [c[a], c[b], c[cc], c[a], c[cc], c[d]]
    return [v for p in tris for v in p]


def build(fresh_dir, entry, controls, code, out, mjolnir):
    """Machines, control and device group for one staged door. Returns
    {"machines": [...], "blam": {"objects": [...], "device_groups": [...]}}."""
    door = entry["h2_door"]
    nodes = door["nodes"]
    rest = node_rest(nodes)
    leaf = entry["asset"].split("\\")[-1]
    group = f"{code.lower()}_{leaf}"
    work = tempfile.mkdtemp(prefix="h2door_")
    run = lambda *args: subprocess.run([mjolnir, *args], check=True, capture_output=True, text=True).stdout
    run("extract", "--out", work, "--group", "model_animation_graph", "--filter", DONOR)
    donor = open(next(os.path.join(dp, f) for dp, _, fs in os.walk(work) for f in fs
                      if f.endswith(".model_animation_graph")), "rb").read()
    pos = entry["pos"]
    yaw = float((entry.get("rot") or [0, 0, 0])[0])
    at_cm = [round(pos[0] * 304.8, 1), round(-pos[1] * 304.8, 1), round(pos[2] * 304.8, 1)]
    machines, objects = [], []
    for k, c in enumerate(door.get("collision") or []):
        n = c["node"]
        offsets = node_offsets(door, n)
        if offsets is None or max(np.linalg.norm(o) for o in offsets) < 0.01:
            continue
        bsp_json = json.load(open(os.path.join(fresh_dir, c["bsp"]), encoding="utf-8"))
        base = os.path.join(work, f"g{k}")
        shutil.copyfile(os.path.join(fresh_dir, os.path.dirname(c["bsp"]), os.path.basename(bsp_json["bin"])),
                        base + ".bsp.bin")
        bsp_json["bin"] = os.path.basename(base) + ".bsp.bin"
        json.dump(bsp_json, open(base + ".bsp.json", "w", encoding="utf-8"))
        tag = f"objects\\mjolnir\\{code.lower()}\\{leaf}_{nodes[n]['name']}_{k}"
        name = lambda g: f"pakchunk986-MJOLNIRMACH-{code}-G{k}{g}"
        static_t = list(map(float, rest[n]))
        open(base + ".jmad", "wb").write(slide_resource(donor, static_t, offsets))
        run("new-tag", "--group", "model_animation_graph", "--from", DONOR, "--to", tag, "--payload", base + ".jmad",
            "--set", f"definitions.animations[0].shared animation data[0].frame count={len(offsets)}",
            "--out-dir", out, "--name", name("J"))
        run("level", "machine-collision", base + ".bsp.json", "--donor", DONOR, "--out", base + ".coll")
        run("new-tag", "--group", "collision_model", "--from", DONOR, "--to", tag, "--payload", base + ".coll",
            "--out-dir", out, "--name", name("C"))
        lo = [a + b for a, b in zip(bsp_json["world_bounds"]["min"], static_t)]
        hi = [a + b for a, b in zip(bsp_json["world_bounds"]["max"], static_t)]
        pargs = physics_args(boxes(box_triangles(lo, hi)))
        sets = base + ".sets"
        open(sets, "w", encoding="utf-8").write("\n".join(v for f, v in zip(pargs[::2], pargs[1::2]) if f == "--set"))
        resizes = [x for f, v in zip(pargs[::2], pargs[1::2]) if f == "--resize" for x in (f, v)]
        run("new-tag", "--group", "physics_model", "--from", DONOR, "--to", tag, *resizes, "--set-file", sets,
            "--out-dir", out, "--name", name("P"))
        run("new-tag", "--group", "model", "--from", DONOR, "--to", tag,
            "--set", f"animation=jmad:{tag}", "--set", f"physics_model=phmo:{tag}",
            "--set", f"collision model=coll:{tag}", "--out-dir", out, "--name", name("H"))
        radius = max(np.linalg.norm(np.array(hi) - np.array(lo)) / 2 + np.linalg.norm(offsets[-1]), 1.0)
        run("new-tag", "--group", "device_machine", "--from", DONOR, "--to", tag,
            "--set", f"device.position transition time={1.0 / max(door['seconds'], 0.1):.6f}",
            "--set", f"device.object.bounding radius={radius:.3f}",
            "--set", f"device.object.model=hlmt:{tag}", "--out-dir", out, "--name", name("M"))
        travel = offsets[-1]
        machines.append({"tag": tag, "class": DONOR_CLASS, "node": nodes[n]["name"], "at_cm": at_cm,
                         "travel_cm": [round(travel[0] * 304.8, 2), round(-travel[1] * 304.8, 2), round(travel[2] * 304.8, 2)],
                         "containers": [name(g) for g in "JCPHM"]})
        objects.append({"tag": tag, "group": "machines", "pos": at_cm, "rot": [0, round(-np.degrees(yaw), 2), 0],
                        "position_group": group})
        print(f"  door machine {k}: {nodes[n]['name']} slides {[round(v, 3) for v in travel]} wu, "
              f"{bsp_json['counts'].get('surfaces')} surfaces")
    grp = (entry.get("h2_device") or {}).get("position_group", -1)
    ctl = next((c for c in controls if grp >= 0 and (c.get("h2_device") or {}).get("position_group") == grp), None)
    control = None
    if ctl and machines:
        tag = f"objects\\mjolnir\\{code.lower()}\\{leaf}_control"
        run("new-tag", "--group", "device_control", "--from", CONTROL_DONOR, "--to", tag,
            "--set", "action string=activate_device", "--out-dir", out,
            "--name", f"pakchunk986-MJOLNIRMACH-{code}-GK")
        cp = ctl["pos"]
        control = {"tag": tag, "containers": [f"pakchunk986-MJOLNIRMACH-{code}-GK"],
                   "at_cm": [round(cp[0] * 304.8, 1), round(-cp[1] * 304.8, 1), round(cp[2] * 304.8, 1)]}
        objects.append({"tag": tag, "group": "controls", "pos": control["at_cm"],
                        "rot": [0, round(-np.degrees(float(ctl["rot"][0])), 2), 0], "position_group": group})
    return {"machines": machines, "control": control,
            "blam": {"objects": objects,
                     "device_groups": [{"name": group, "initial_value": 0.0, "flags": 0}] if machines else []}}
