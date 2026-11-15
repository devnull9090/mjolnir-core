"""The simulation's own machines for a Halo 2 machine that moves in parts (a
door, a platform or a gear of several parts: Zanzibar's house gate,
Containment's base gates, Triplicate's garage gates and train), so its
collision moves with it, every player in the match sees it move, and Unreal
moves its meshes with no script.

The Blam simulation does all collision and networking. Each of the machine's
collision BSPs (crate::h2::door; the staged `h2_door.collision` BSPs, one a
node) becomes a device machine with tags of its own: animation, collision,
physics, model and machine, written into the layout of B40's elevator family,
whose Unreal class draws it. A node that moves without collision gets one
too, with no collision or physics model, to carry its mesh. The machine's
root follows its node exactly, turning and sliding as the node does at every
frame of Halo 2's motion (`h2_machines.pose_resource`), so a ramp that swings
about its hinge and a bar that rides a sliding lock are one machine each.
Nodes that never move but have collision get one too, so a door's frame
collides. The machine tag's behaviour is Halo 2's (`machine_sets`): a door
opens by itself within its activation radius, a gear runs round by itself, a
platform goes where its device group sends it. A control of the same
position group (Zanzibar's keypad) becomes B40's switch panel; the machines
and the control share one device group, so a player pressing the control
moves the machine in the simulation, for every player.

A machine's tags are built once a Halo 2 tag, however often it is placed.
Each placement's machines stand on a small grid about its origin, `SPACING`
wu apart (`spot`): close enough that a door's parts measure its activation
radius from nearly one point, apart enough that the game keeps them apart.
Machines 1.5 cm apart broke Unreal's copy of their poses: three of the
gate's four ramps never moved and the fourth froze mid-swing, though the
simulation had them all open (2026-11-15), as Zanzibar's wheel and blades,
two machines on one spot, froze before. The level loader (doors.lua) tells
them apart by where they stand and attaches each node's meshes to its
machine once. Unreal carries the meshes from then on.
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

# wu between a placement's machines (15 cm), on a grid about its origin.
SPACING = 0.05
WU_CM = 304.8


def spot(k, count):
    """Machine k of `count`'s origin in the placement's space: a square grid
    about the origin, `SPACING` apart, at the origin's height."""
    side = int(np.ceil(np.sqrt(max(count, 1))))
    i, j = k % side, k // side
    return np.array([(i - (side - 1) / 2) * SPACING, (j - (side - 1) / 2) * SPACING, 0.0])
# Halo 2 machine type (mach 0x11C).
DOOR, PLATFORM, GEAR = 0, 1, 2


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


def machine_sets(kind, seconds):
    """--set arguments that give a machine tag Halo 2's behaviour (`kind`:
    the staged `h2_door.machine`): a door opens by itself when a unit comes
    within its automatic activation radius and closes after its open time; a
    gear runs its position round by itself; a platform goes where its device
    group sends it (the donor's own type)."""
    sets = ["--set", f"device.position transition time={1.0 / max(seconds, 0.1):.6f}"]
    if kind.get("type") == GEAR:
        sets += ["--set", "type=gear"]
    elif kind.get("type") == DOOR:
        sets += ["--set", "type=0", "--set", f"door open time={float(kind.get('door_open_time') or 0.0):.3f}",
                 "--set", f"device.automatic activation radius={float(kind.get('automatic_radius') or 0.0):.3f}"]
    return sets


def moving_parts(door, frames):
    """(node, collision BSP or None) for each machine to build: one a
    collision BSP, and one a node that moves without collision."""
    parts = [(c["node"], c["bsp"]) for c in door.get("collision") or []]
    with_collision = {n for n, _ in parts}
    parts += [(n, None) for n in range(len(door["nodes"])) if n not in with_collision
              and any(not np.allclose(f[n], frames[0][n], atol=1e-4) for f in frames)]
    return parts


def root_frames(frames, n, origin):
    """The root's (quaternion, translation) at every frame for node n of a
    machine standing at `origin` (object space): it moves machine-local
    points as the node moves the object's (node_f rest^-1), shifted to the
    machine's origin."""
    shift = np.eye(4)
    shift[:3, 3] = origin
    shift_i = np.linalg.inv(shift)
    rest_i = np.linalg.inv(frames[0][n])
    out = []
    for f in frames:
        m = shift_i @ f[n] @ rest_i @ shift
        out.append((matrix_quat(m[:3, :3]), m[:3, 3].tolist()))
    return out


def build_tags(fresh_dir, entry, code, out, mjolnir, prefix):
    """The machine tags of one Halo 2 machine tag. Returns [{tag, node,
    origin, root, containers}]."""
    door = entry["h2_door"]
    nodes = door["nodes"]
    kind = door.get("machine") or {"type": PLATFORM}
    frames = [node_matrices(door, f) for f in range(len(door["poses"]))]
    leaf = entry["asset"].split("\\")[-1]
    work = tempfile.mkdtemp(prefix="h2door_")

    def run(*args):
        return subprocess.run([mjolnir, *args], check=True, capture_output=True, text=True).stdout

    run("extract", "--out", work, "--group", "model_animation_graph", "--filter", DONOR)
    donor = open(next(os.path.join(dp, f) for dp, _, fs in os.walk(work) for f in fs
                      if f.endswith(".model_animation_graph")), "rb").read()
    built = []
    parts = moving_parts(door, frames)
    for k, (n, bsp) in enumerate(parts):
        rest = frames[0][n]
        origin = spot(k, len(parts))
        root = root_frames(frames, n, origin)
        platform_q = matrix_quat(rest[:3, :3])
        platform_t = (rest[:3, 3] - origin).tolist()
        base = os.path.join(work, f"g{k}")
        tag = f"objects\\mjolnir\\{code.lower()}\\{leaf}_{nodes[n]['name']}_{k}"

        def name(g, k=k):
            return f"pakchunk986-MJOLNIRMACH-{code}-{prefix}G{k}{g}"

        open(base + ".jmad", "wb").write(pose_resource(donor, platform_q, platform_t, root))
        run("new-tag", "--group", "model_animation_graph", "--from", DONOR, "--to", tag, "--payload", base + ".jmad",
            "--set", f"definitions.animations[0].shared animation data[0].frame count={len(root)}",
            "--out-dir", out, "--name", name("J"))
        groups, surfaces = "JHM", 0
        tris = np.array([platform_t])
        if bsp:
            bsp_json = json.load(open(os.path.join(fresh_dir, bsp), encoding="utf-8"))
            shutil.copyfile(os.path.join(fresh_dir, os.path.dirname(bsp), os.path.basename(bsp_json["bin"])),
                            base + ".bsp.bin")
            bsp_json["bin"] = os.path.basename(base) + ".bsp.bin"
            json.dump(bsp_json, open(base + ".bsp.json", "w", encoding="utf-8"))
            surfaces = bsp_json["counts"].get("surfaces")
            run("level", "machine-collision", base + ".bsp.json", "--donor", DONOR, "--out", base + ".coll")
            run("new-tag", "--group", "collision_model", "--from", DONOR, "--to", tag, "--payload", base + ".coll",
                "--out-dir", out, "--name", name("C"))
            # Physics boxes over the BSP's own triangles (a box over its
            # bounds filled a barred gate's gaps and a ramp's whole swing),
            # in the root's space at rest: under the platform.
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
            groups = "JCPHM"
        else:
            run("new-tag", "--group", "model", "--from", DONOR, "--to", tag,
                "--set", f"animation=jmad:{tag}", "--set", "physics_model=none",
                "--set", "collision model=none", "--out-dir", out, "--name", name("H"))
        # Bounds over the whole motion.
        reach = max(float(np.linalg.norm(quat_matrix(q) @ cn + np.array(t))) for q, t in root for cn in tris)
        run("new-tag", "--group", "device_machine", "--from", DONOR, "--to", tag,
            *machine_sets(kind, door["seconds"]),
            "--set", f"device.object.bounding radius={max(reach, 1.0):.3f}",
            "--set", f"device.object.model=hlmt:{tag}", "--out-dir", out, "--name", name("M"))
        built.append({"tag": tag, "node": nodes[n]["name"], "origin": origin.tolist(), "root": root,
                      "containers": [name(g) for g in groups]})
        turn = 2 * np.degrees(np.arccos(min(1.0, abs(root[-1][0][3]))))
        print(f"  machine {k}: {nodes[n]['name']} slides {[round(v, 3) for v in root[-1][1]]} wu, turns {turn:.0f} deg, "
              f"{surfaces or 'no'} collision surfaces, machine type {kind.get('type')}")
    return built


def build(fresh_dir, entry, controls, code, out, mjolnir, cache=None):
    """Machines, control and device group for one placed machine. `cache` (a
    dict shared across a map's placements) keeps each Halo 2 tag's machine
    tags, built once; each placement places them again at its own spot.
    Returns {"machines": [...], "control": ..., "blam": {"objects": [...],
    "device_groups": [...]}}."""
    cache = {} if cache is None else cache
    tags_of = cache.setdefault("tags", {})
    asset = entry["asset"]
    if asset not in tags_of:
        tags_of[asset] = build_tags(fresh_dir, entry, code, out, mjolnir, f"D{len(tags_of)}" if tags_of else "")
    tags = tags_of[asset]
    pos = np.array(entry["pos"], dtype=float)
    yaw = float((entry.get("rot") or [0, 0, 0])[0])
    rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])

    def ue(v):
        return [round(float(v[0]) * WU_CM, 2), round(-float(v[1]) * WU_CM, 2), round(float(v[2]) * WU_CM, 2)]

    # Halo 2's position group (device 0x36): every machine and control of
    # one number moves together (Containment's gate and its switch share 0),
    # so it is one device group of the simulation's, named for the number.
    grp = (entry.get("h2_device") or {}).get("position_group", -1)
    group = f"{code.lower()}_group{grp}"
    machines, objects = [], []
    for t in tags:
        at_cm = ue(pos + rz @ np.array(t["origin"]))
        machines.append({"tag": t["tag"], "class": DONOR_CLASS, "node": t["node"], "at_cm": at_cm,
                         "travel_cm": ue(rz @ np.array(t["root"][-1][1])), "containers": t["containers"]})
        obj = {"tag": t["tag"], "group": "machines", "pos": at_cm, "rot": [0, round(-np.degrees(yaw), 2), 0]}
        # A device group only where Halo 2 gives the machine a position group
        # (a control or a script moves it); a gear, or a door that opens by
        # itself, has none.
        if grp >= 0:
            obj["position_group"] = group
        objects.append(obj)
    groups = []
    if machines and grp >= 0 and group not in cache.setdefault("groups", set()):
        cache["groups"].add(group)
        groups.append({"name": group, "initial_value": 0.0, "flags": 0})
    # Its controls: each control of the same position group becomes B40's
    # switch panel (one tag a map), placed once however many machines share
    # the group. `control` is the first, for the loader (its press sound,
    # its panel hidden).
    control = None
    ck = f"pakchunk986-MJOLNIRMACH-{code}-GK"
    tag = f"objects\\mjolnir\\{code.lower()}\\control"
    for ctl in (c for c in controls if grp >= 0 and (c.get("h2_device") or {}).get("position_group") == grp):
        if not machines:
            break
        if "control" not in cache:
            subprocess.run([mjolnir, "new-tag", "--group", "device_control", "--from", CONTROL_DONOR, "--to", tag,
                            "--set", "action string=activate_device", "--out-dir", out, "--name", ck],
                           check=True, capture_output=True, text=True)
            cache["control"] = True
        cp = ctl["pos"]
        at = [round(cp[0] * WU_CM, 1), round(-cp[1] * WU_CM, 1), round(cp[2] * WU_CM, 1)]
        control = control or {"tag": tag, "containers": [ck], "at_cm": at}
        if tuple(at) not in cache.setdefault("placed_controls", set()):
            cache["placed_controls"].add(tuple(at))
            objects.append({"tag": tag, "group": "controls", "pos": at,
                            "rot": [0, round(-np.degrees(float(ctl["rot"][0])), 2), 0], "position_group": group})
    return {"machines": machines, "control": control, "blam": {"objects": objects, "device_groups": groups}}
