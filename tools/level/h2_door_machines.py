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
wu apart (`spot`), every machine of the map on a cell of its own: close
enough that a door's parts measure its activation radius from nearly one
point, apart enough that the level loader (doors.lua) tells them apart by
where they stand. It attaches each node's meshes to its machine once, and
Unreal carries the meshes from then on.

The game hides a machine's actor while the player cannot see it (`bHidden`;
FlyCam is not the player's view) and poses it again, at its present
position, as soon as the player can: a part that seems stuck in a FlyCam
shot is that, not a fault (docs/h2_map_conversion.md).
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
from h2_machines import (DONOR, DONOR_CLASS, boxes, matrix_quat, mesh_list_edits, physics_args,  # noqa: E402
                         pose_resource, write_actor_container)

# wu between a placement's machines (15 cm), on a grid about its origin.
SPACING = 0.05
WU_CM = 304.8


# Cells a grid row and column: 64 cells a layer, within 0.18 wu (53 cm) of
# the origin; a 65th machine starts a layer SPACING higher.
GRID = 8


def spot(i):
    """The origin of a map's machine number i in its placement's space: a
    cell of a grid about the origin, `SPACING` apart. Numbered across every
    machine tag of the map, so two Halo 2 tags placed at one point (a train
    and its deathball, 3 cm apart on Triplicate) never put machines on one
    spot: they had, and the loader bound one actor twice and left the
    other's elevator mesh riding the train's nose (2026-11-15)."""
    layer, cell = divmod(i, GRID * GRID)
    row, col = divmod(cell, GRID)
    return np.array([(col - (GRID - 1) / 2) * SPACING, (row - (GRID - 1) / 2) * SPACING, layer * SPACING])
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


def placement_flags(entry):
    """The placement's own device and machine flags, as Halo 2 placed it
    (the staged `h2_device`), for every machine built from it. The
    simulation's bits are Halo 2's: device 1 initially open, 2 initially
    off, 8 position reversed; machine 1 does not operate automatically,
    0x20 does not close automatically. A door with no activation radius
    opens for any unit within its bounding radius unless bit 1 says
    otherwise: Containment's base gates, which only their switches move,
    stood open (2026-11-16)."""
    dev = entry.get("h2_device") or {}
    out = {}
    if dev.get("device_flags") is not None:
        out["device data.flags"] = hex(int(dev["device_flags"]))
    if dev.get("machine_flags") is not None:
        out["machine data.flags"] = hex(int(dev["machine_flags"]))
    return out


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


def build_tags(fresh_dir, entry, code, out, mjolnir, prefix, first=0):
    """The machine tags of one Halo 2 machine tag, its machines on grid cells
    from `first` (`spot`). Returns [{tag, node, origin, root, containers}]."""
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
        origin = spot(first + k)
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
        groups, surfaces = "JH", 0
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
            groups = "JCPH"
        else:
            run("new-tag", "--group", "model", "--from", DONOR, "--to", tag,
                "--set", f"animation=jmad:{tag}", "--set", "physics_model=none",
                "--set", "collision model=none", "--out-dir", out, "--name", name("H"))
        # Bounds over the whole motion. The machine tag itself is each
        # placement's (`build`): it names the placement's own actor.
        reach = max(float(np.linalg.norm(quat_matrix(q) @ cn + np.array(t))) for q, t in root for cn in tris)
        m_sets = [*machine_sets(kind, door["seconds"]), "--set", f"device.object.model=hlmt:{tag}"]
        built.append({"tag": tag, "node": nodes[n]["name"], "origin": origin.tolist(), "root": root,
                      "containers": [name(g) for g in groups], "m_sets": m_sets, "m_name": name("M"),
                      "reach": max(reach, 1.0)})
        turn = 2 * np.degrees(np.arccos(min(1.0, abs(root[-1][0][3]))))
        print(f"  machine {k}: {nodes[n]['name']} slides {[round(v, 3) for v in root[-1][1]]} wu, turns {turn:.0f} deg, "
              f"{surfaces or 'no'} collision surfaces, machine type {kind.get('type')}")
    return built


def build(fresh_dir, entry, controls, code, out, mjolnir, cache=None, delta=(0.0, 0.0, 0.0)):
    """Machines, control and device group for one placed machine. `cache` (a
    dict shared across a map's placements) keeps each Halo 2 tag's machine
    tags, built once; each placement places them again at its own spot.
    `delta` (wu) moves every position as a conversion moves its map
    (`level collision`'s transform). Returns {"machines": [...], "control":
    ..., "blam": {"objects": [...], "device_groups": [...]}}."""
    cache = {} if cache is None else cache
    tags_of = cache.setdefault("tags", {})
    asset = entry["asset"]
    if asset not in tags_of:
        first = sum(len(t) for t in tags_of.values())
        tags_of[asset] = build_tags(fresh_dir, entry, code, out, mjolnir, f"D{len(tags_of)}" if tags_of else "", first)
    tags = tags_of[asset]
    pos = np.array(entry["pos"], dtype=float) + np.array(delta, dtype=float)
    yaw = float((entry.get("rot") or [0, 0, 0])[0])
    rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])

    def ue(v):
        return [round(float(v[0]) * WU_CM, 2), round(-float(v[1]) * WU_CM, 2), round(float(v[2]) * WU_CM, 2)]

    # Halo 2's position group (device 0x36): every machine and control of
    # one number moves together (Containment's gate and its switch share 0),
    # so it is one device group of the simulation's, named for the number.
    grp = (entry.get("h2_device") or {}).get("position_group", -1)
    group = f"{code.lower()}_group{grp}"
    # Each placed machine's own machine tag (its shared animation, collision,
    # physics and model under it) names an actor of its own: the elevator
    # Blueprint wearing the placement's part (`write_actors`), so Unreal
    # draws and moves the part, and nothing has to hide B40's elevator.
    placed = cache.setdefault("placed", {})
    pa = placed.get(asset, 0)
    placed[asset] = pa + 1
    machines, objects = [], []
    for t in tags:
        at_cm = ue(pos + rz @ np.array(t["origin"]))
        index = cache.setdefault("actors", 0)
        cache["actors"] = index + 1
        actor = f"/Game/MJOLNIR/Maps/{code}/Machines/BP_{code}_Machine{index}"
        m_tag = t["tag"] + (f"_p{pa}" if pa else "")
        m_name = t["m_name"] + (str(pa) if pa else "")
        # One bounding radius for all of a placement's machines, the largest
        # reach: the game culls an object it judges too small at its
        # distance (Zanzibar's gate parts hid between 20 and 45 wu from the
        # player, and a hidden actor draws nothing), and Halo 2 culls the
        # machine as one object, so its parts appear and go together.
        radius = max(x["reach"] for x in tags)
        subprocess.run([mjolnir, "new-tag", "--group", "device_machine", "--from", DONOR, "--to", m_tag, *t["m_sets"],
                        "--set", f"device.object.bounding radius={radius:.3f}",
                        "--asset-reference", actor, "--out-dir", out, "--name", m_name],
                       check=True, capture_output=True, text=True,
                       env=dict(os.environ, MSYS2_ARG_CONV_EXCL="*"))
        machines.append({"tag": m_tag, "class": actor.rsplit("/", 1)[1] + "_C", "actor": actor, "node": t["node"],
                         "at_cm": at_cm, "yaw_ue": round(-float(np.degrees(yaw)), 4),
                         "travel_cm": ue(rz @ np.array(t["root"][-1][1])),
                         "containers": t["containers"] + [m_name, f"pakchunk987-MJOLNIRACT-{code}"]})
        obj = {"tag": m_tag, "group": "machines", "pos": at_cm, "rot": [0, round(-np.degrees(yaw), 2), 0]}
        # A device group only where Halo 2 gives the machine a position group
        # (a control or a script moves it); a gear, or a door that opens by
        # itself, has none.
        if grp >= 0:
            obj["position_group"] = group
        obj["set"] = placement_flags(entry)
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
        at = [round(c, 1) for c in ue(np.array(ctl["pos"], dtype=float) + np.array(delta, dtype=float))]
        control = control or {"tag": tag, "containers": [ck], "at_cm": at}
        if tuple(at) not in cache.setdefault("placed_controls", set()):
            cache["placed_controls"].add(tuple(at))
            objects.append({"tag": tag, "group": "controls", "pos": at,
                            "rot": [0, round(-np.degrees(float(ctl["rot"][0])), 2), 0], "position_group": group})
    return {"machines": machines, "control": control, "blam": {"objects": objects, "device_groups": groups}}


def actor_edits(machine, items):
    """vehicle_actor edits that make the elevator Blueprint wear a placed
    machine's part meshes (h2_machines.mesh_list_edits), its actor turned by
    the placement's yaw."""
    psi = np.radians(machine["yaw_ue"])
    rot = [[np.cos(psi), -np.sin(psi), 0.0], [np.sin(psi), np.cos(psi), 0.0], [0.0, 0.0, 1.0]]
    return mesh_list_edits(items, machine["at_cm"], rot)


def write_actors(doors, items, code, out, paks, examples):
    """Every placed machine's actor (`build`'s `actor`): B40's elevator
    Blueprint cloned to wear the machine's part meshes, into
    pakchunk987-MJOLNIRACT-<CODE>_P in `out` (h2_machines
    write_actor_container). `items`: decor entries by id (mesh, pos, scale),
    whose ids the doors' `parts` name. Each node's meshes go on the first
    machine of that node."""
    actors = []
    for door in doors:
        worn = set()
        for m in door["machines"]:
            mine = [] if m["node"] in worn else [items[p["id"]] for p in door.get("parts") or []
                                                if p["node"] == m["node"] and p["id"] in items]
            worn.add(m["node"])
            actors.append((m["actor"], actor_edits(m, mine)))
    name = f"pakchunk987-MJOLNIRACT-{code}_P"
    count = write_actor_container(actors, name, out, paks, examples)
    if count:
        print(f"  {count} machine actor(s) -> {os.path.join(out, name)}")
    return name if count else None


def main():
    """A fresh conversion's machines (tools/level/convert_ce_map.sh):

        h2_door_machines.py <staging> <CODE> <out dir> --transform <sbsp.transform.json> [--mjolnir PATH]

    builds every staged `h2_door` placement's machines into <out dir> (their
    containers beside h2_machines.py's, installed with them) and writes
    <out dir>/doors.json: one record a placement, by its staging entry, for
    gen_ce_level.py --doors (the machines and controls it places, the device
    groups, and the level loader's `doors`)."""
    import argparse
    if len(sys.argv) > 1 and sys.argv[1] == "actors":
        # h2_door_machines.py actors <doors.json> <terrain.json> <CODE> <out dir> --paks P --examples E
        # Once build_terrain_meshes.py has placed the part meshes: each
        # machine's actor wearing its part (`write_actors`).
        ap = argparse.ArgumentParser(prog="h2_door_machines.py actors")
        ap.add_argument("doors")
        ap.add_argument("terrain")
        ap.add_argument("code")
        ap.add_argument("out")
        ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
        ap.add_argument("--examples", required=True)
        a = ap.parse_args(sys.argv[2:])
        doors = json.load(open(a.doors, encoding="utf-8"))
        terrain = json.load(open(a.terrain, encoding="utf-8"))
        terrain = terrain if isinstance(terrain, list) else [terrain]
        for door in doors:
            door["parts"] = [{"id": t["id"], "node": t["door_part"]["node"]} for t in terrain
                             if (t.get("door_part") or {}).get("entry") == door["entry"]]
        write_actors(doors, {t["id"]: t for t in terrain if t.get("id")}, a.code, a.out, a.paks, a.examples)
        return
    ap = argparse.ArgumentParser(description=main.__doc__.strip().splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("code")
    ap.add_argument("out")
    ap.add_argument("--transform", required=True, help="the conversion's <name>.sbsp.transform.json (its delta)")
    ap.add_argument("--mjolnir", default=os.environ.get("MJOLNIR", "mjolnir"))
    a = ap.parse_args()
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    delta = json.load(open(a.transform, encoding="utf-8"))["delta"]
    controls = [e for e in placement["entries"] if e.get("tag_class") == "ctrl"]
    os.makedirs(a.out, exist_ok=True)
    cache, doors = {}, []
    for index, e in enumerate(placement["entries"]):
        if "h2_door" not in e:
            continue
        built = build(a.staging, e, controls, a.code, a.out, a.mjolnir, cache, delta)
        if not built["machines"]:
            continue
        grp = (e.get("h2_device") or {}).get("position_group", -1)
        ctl = next((c for c in controls if grp >= 0 and (c.get("h2_device") or {}).get("position_group") == grp), None)
        pos = [c + d for c, d in zip(e["pos"], delta)]
        doors.append({"entry": index, "asset": e["asset"], "seconds": e["h2_door"]["seconds"],
                      "sounds": e["h2_door"].get("sounds") or {},
                      "press_sound": ((ctl or {}).get("h2_device") or {}).get("press_sound"),
                      "at_cm": [round(pos[0] * WU_CM, 1), round(-pos[1] * WU_CM, 1), round(pos[2] * WU_CM, 1)],
                      **({"control_cm": built["control"]["at_cm"], "sim_control": built["control"]}
                         if built["control"] else {}),
                      "machines": built["machines"], "blam": built["blam"]})
    json.dump(doors, open(os.path.join(a.out, "doors.json"), "w", encoding="utf-8"), indent=1)
    print(f"  {len(doors)} moving machine placement(s), {sum(len(d['machines']) for d in doors)} machine(s) "
          f"-> {os.path.join(a.out, 'doors.json')}")


if __name__ == "__main__":
    main()
