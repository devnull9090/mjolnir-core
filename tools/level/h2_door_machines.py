"""The simulation's own machines for a Halo 2 door (machine type 1, such as
Zanzibar's house gate), so its collision opens with it, every player in the
match sees it open, and Unreal moves its meshes with no script.

The Blam simulation does all collision and networking. Each of the door's
collision BSPs (crate::h2::door; the staged `h2_door.collision` BSPs, one a
node) becomes a device machine with tags of its own: animation, collision,
physics, model and machine, written into the layout of B40's elevator family.
The machine's root follows its node exactly, turning and sliding as the node
does at every frame of Halo 2's opening (`h2_machines.pose_resource`), so a
ramp that swings about its hinge and a bar that rides a sliding lock are one
machine each. Nodes that never move get one too, so the door's frame has
collision. The door's control (the keypad) becomes B40's switch panel; the
machines and the control share one device group, so a player pressing the
control opens the door in the simulation, which moves the collision and
replicates to every player.

Each machine stands at its node's rest origin, raised `STAGGER` wu a machine
so no two stand in the same place: the level loader (doors.lua) tells them
apart by where they stand and attaches each door mesh to its node's machine
once. Unreal carries the mesh from then on.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

from ce_machines import CONTROL_DONOR

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ce_scripts"))
import ce_scenario  # noqa: E402
from h2_machines import DONOR, DONOR_CLASS, boxes, matrix_quat, physics_args, pose_resource  # noqa: E402

# wu between machines' origins (1.5 cm): a unique place each to bind by.
STAGGER = 0.005
WU_CM = 304.8


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_matrices(door, frame):
    """Object-space (CE world units) 4x4 matrices of every node at a frame: a
    sliding key is an offset added to the default translation, a node not
    sliding keeps its default (crate::h2::door)."""
    out = []
    for i, nd in enumerate(door["nodes"]):
        tr, rq = door["poses"][frame][i]
        d0 = np.array(nd["t"], dtype=float)
        tl = d0 if np.allclose(tr, nd["t"]) else d0 + np.array(tr, dtype=float)
        m = np.eye(4)
        m[:3, :3] = quat_matrix(rq)
        m[:3, 3] = tl
        out.append(m if nd["parent"] < 0 else out[nd["parent"]] @ m)
    return out


def build(fresh_dir, entry, controls, code, out, mjolnir):
    """Machines, control and device group for one staged door. Returns
    {"machines": [...], "control": ..., "blam": {"objects": [...], "device_groups": [...]}}."""
    door = entry["h2_door"]
    nodes = door["nodes"]
    frames = [node_matrices(door, f) for f in range(len(door["poses"]))]
    leaf = entry["asset"].split("\\")[-1]
    group = f"{code.lower()}_{leaf}"
    work = tempfile.mkdtemp(prefix="h2door_")
    run = lambda *args: subprocess.run([mjolnir, *args], check=True, capture_output=True, text=True).stdout
    run("extract", "--out", work, "--group", "model_animation_graph", "--filter", DONOR)
    donor = open(next(os.path.join(dp, f) for dp, _, fs in os.walk(work) for f in fs
                      if f.endswith(".model_animation_graph")), "rb").read()
    pos = np.array(entry["pos"], dtype=float)
    yaw = float((entry.get("rot") or [0, 0, 0])[0])
    rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])

    def ue(v):
        return [round(float(v[0]) * WU_CM, 2), round(-float(v[1]) * WU_CM, 2), round(float(v[2]) * WU_CM, 2)]

    machines, objects = [], []
    with_collision = {c["node"] for c in door.get("collision") or []}
    for n, nd in enumerate(nodes):
        if n not in with_collision and any(not np.allclose(f[n], frames[0][n], atol=1e-4) for f in frames):
            print(f"  door node {nd['name']} moves but has no collision: no machine carries its mesh")
    for k, c in enumerate(door.get("collision") or []):
        n = c["node"]
        rest = frames[0][n]
        # The machine's origin: the node's rest origin, staggered. Its root's
        # transform at frame f moves machine-local points as the node moves
        # door points (node_f rest^-1), shifted to the machine's origin.
        origin = rest[:3, 3] + np.array([0.0, 0.0, STAGGER * k])
        shift = np.eye(4)
        shift[:3, 3] = origin
        shift_i = np.linalg.inv(shift)
        rest_i = np.linalg.inv(rest)
        root = []
        for f in frames:
            m = shift_i @ f[n] @ rest_i @ shift
            root.append((matrix_quat(m[:3, :3]), m[:3, 3].tolist()))
        platform_q = matrix_quat(rest[:3, :3])
        platform_t = (rest[:3, 3] - origin).tolist()
        bsp_json = json.load(open(os.path.join(fresh_dir, c["bsp"]), encoding="utf-8"))
        base = os.path.join(work, f"g{k}")
        shutil.copyfile(os.path.join(fresh_dir, os.path.dirname(c["bsp"]), os.path.basename(bsp_json["bin"])),
                        base + ".bsp.bin")
        bsp_json["bin"] = os.path.basename(base) + ".bsp.bin"
        json.dump(bsp_json, open(base + ".bsp.json", "w", encoding="utf-8"))
        tag = f"objects\\mjolnir\\{code.lower()}\\{leaf}_{nodes[n]['name']}_{k}"

        def name(g, k=k):
            return f"pakchunk986-MJOLNIRMACH-{code}-G{k}{g}"

        open(base + ".jmad", "wb").write(pose_resource(donor, platform_q, platform_t, root))
        run("new-tag", "--group", "model_animation_graph", "--from", DONOR, "--to", tag, "--payload", base + ".jmad",
            "--set", f"definitions.animations[0].shared animation data[0].frame count={len(root)}",
            "--out-dir", out, "--name", name("J"))
        run("level", "machine-collision", base + ".bsp.json", "--donor", DONOR, "--out", base + ".coll")
        run("new-tag", "--group", "collision_model", "--from", DONOR, "--to", tag, "--payload", base + ".coll",
            "--out-dir", out, "--name", name("C"))
        # Physics boxes over the BSP's own triangles (a box over its bounds
        # filled a barred gate's gaps and a ramp's whole swing), in the
        # root's space at rest: under the platform.
        tris = np.array(ce_scenario.triangles(ce_scenario.read_bsp(base + ".bsp.json")), dtype=float).reshape(-1, 3)
        tris = tris @ rest[:3, :3].T + np.array(platform_t)
        pargs = physics_args(boxes(tris.reshape(-1).tolist()))
        sets = base + ".sets"
        open(sets, "w", encoding="utf-8").write("\n".join(v for f, v in zip(pargs[::2], pargs[1::2]) if f == "--set"))
        resizes = [x for f, v in zip(pargs[::2], pargs[1::2]) if f == "--resize" for x in (f, v)]
        run("new-tag", "--group", "physics_model", "--from", DONOR, "--to", tag, *resizes, "--set-file", sets,
            "--out-dir", out, "--name", name("P"))
        run("new-tag", "--group", "model", "--from", DONOR, "--to", tag,
            "--set", f"animation=jmad:{tag}", "--set", f"physics_model=phmo:{tag}",
            "--set", f"collision model=coll:{tag}", "--out-dir", out, "--name", name("H"))
        # Bounds over the whole opening.
        reach = max(float(np.linalg.norm(quat_matrix(q) @ cn + np.array(t))) for q, t in root for cn in tris)
        run("new-tag", "--group", "device_machine", "--from", DONOR, "--to", tag,
            "--set", f"device.position transition time={1.0 / max(door['seconds'], 0.1):.6f}",
            "--set", f"device.object.bounding radius={max(reach, 1.0):.3f}",
            "--set", f"device.object.model=hlmt:{tag}", "--out-dir", out, "--name", name("M"))
        at_cm = ue(pos + rz @ origin)
        travel = root[-1][1]
        machines.append({"tag": tag, "class": DONOR_CLASS, "node": nodes[n]["name"], "at_cm": at_cm,
                         "travel_cm": ue(rz @ np.array(travel)), "containers": [name(g) for g in "JCPHM"]})
        objects.append({"tag": tag, "group": "machines", "pos": at_cm, "rot": [0, round(-np.degrees(yaw), 2), 0],
                        "position_group": group})
        turn = 2 * np.degrees(np.arccos(min(1.0, abs(root[-1][0][3]))))
        print(f"  door machine {k}: {nodes[n]['name']} slides {[round(v, 3) for v in travel]} wu, turns {turn:.0f} deg, "
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
                   "at_cm": [round(cp[0] * WU_CM, 1), round(-cp[1] * WU_CM, 1), round(cp[2] * WU_CM, 1)]}
        objects.append({"tag": tag, "group": "controls", "pos": control["at_cm"],
                        "rot": [0, round(-np.degrees(float(ctl["rot"][0])), 2), 0], "position_group": group})
    return {"machines": machines, "control": control,
            "blam": {"objects": objects,
                     "device_groups": [{"name": group, "initial_value": 0.0, "flags": 0}] if machines else []}}
