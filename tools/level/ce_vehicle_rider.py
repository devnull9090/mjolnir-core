#!/usr/bin/env python3
"""A rider's seat pose from CE's own idle, as an edit of a Spartan animation.

    ce_vehicle_rider.py --ce seats.json --donor frames.json --bones bones.json
                        --seat M-driver=ghost_d:idle --seat M-passenger=warthog_p:rifle:idle
                        --copy ghost_d:idle=ghost_d:grip --out spec.json --limbs limbs.json

`--donor` is `mjolnir jmad frames` over the graph, naming every animation used.
`--out` is a spec for `mjolnir jmad rewrite`. `--limbs` is each IK proxy, on the
node it rides, and `--bones` is the vehicle's manifest for those nodes.

The spec edits the Spartan's own animations, by their names in its pool. `SEATS`
says which modes play them on this vehicle: `mjolnir jmad child --mode` copies each
under the seat's label, so a real Ghost or Warthog on the map keeps its pose.

`--ce` is a JSON file, with quaternions as CE stores them:

    {"vehicle": {"markers": {name: {"node", "position", "forward", "left", "up"}}},
     "rider": {"nodes": [{"name", "parent", "translation", "rotation"}],
               "markers": {name: {"node", "translation", "rotation"}}},
     "seats": [{"label", "marker", "idle", "ik_points": [{"marker", "attached_to"}],
                "frames": [[{"rotation", "translation"}, ...], ...]}]}

Rules, none of them per vehicle, with one table per pair of rigs:

- CE's idle is taken after CE's IK, in the seat marker's frame, the frame the
  rider's root is attached in. CE's frames are resampled onto the donor's, whose
  count stays: the graph's rows and chain data hold for it.
- `root_m` takes CE's pelvis place. Every other local translation stays the
  donor's, so no bone changes length.
- Two nodes that branch take a frame from two directions: the pelvis, from the
  spine and the hips, and the chest, from the neck and the shoulders.
- A bone of the spine or neck swings from the donor's direction to CE's.
- A clavicle aims its shoulder at CE's, whose shoulders are wider apart.
- A head and a foot turn by what CE's turned from its bind pose, since both rigs
  stand the same way round when bound.
- A limb reaches CE's joint, bending in CE's plane. Its joints turn about the
  donor's hinge, so the elbow and knee stay hinges.
- A wrist keeps the donor's rotation in the seat, which is what points a held
  weapon, and CE's hand axes are not a Spartan's.
- Nodes outside the table (fingers, armour, cloth) keep the donor's local frames.

An IK proxy is where CE's limb ends and how the Spartan's joint lies there: the
stock rule, marker equals effector joint, on the node CE's ik point rides, or
on the seat's node for a limb with no ik point.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_vehicle_nodes as nodes  # noqa: E402

WU_CM = 304.8
# A limb stops short of straight.
REACH = 0.98

# The cyborg's bones on the Spartan's.
ROOT = ("root_m", "bip01 pelvis")
# Frames: node, the child that is up, its two sides; CE's up bone and two sides.
PELVIS = ("root_m", "spine1_m", ("hip_l", "hip_r"),
          "bip01 pelvis", "bip01 spine", ("bip01 l thigh", "bip01 r thigh"))
CHEST = ("chest_m", "neck_m", ("scapula_l", "scapula_r"),
         "bip01 spine1", "bip01 neck", ("bip01 l clavicle", "bip01 r clavicle"))
# Swings: node, the child it points at, and CE's bone.
SPINE = (("spine1_m", "spine2_m", "bip01 spine", "bip01 spine1"),
         ("spine2_m", "chest_m", "bip01 spine", "bip01 spine1"))
NECK = (("neck_m", "head_m", "bip01 neck", "bip01 head"),)
# Aims: node, the child it points, and CE's joint to point it at.
CLAVICLES = (("scapula_l", "shoulder_l", "bip01 l upperarm"),
             ("scapula_r", "shoulder_r", "bip01 r upperarm"))
# Limbs: top, joint and end on the Spartan, then on CE.
ARMS = (("shoulder_l", "elbow_l", "wrist_l", "bip01 l upperarm", "bip01 l forearm", "bip01 l hand"),
        ("shoulder_r", "elbow_r", "wrist_r", "bip01 r upperarm", "bip01 r forearm", "bip01 r hand"))
LEGS = (("hip_l", "knee_l", "ankle_l", "bip01 l thigh", "bip01 l calf", "bip01 l foot"),
        ("hip_r", "knee_r", "ankle_r", "bip01 r thigh", "bip01 r calf", "bip01 r foot"))
# Turned from the bind pose: node, CE's node.
HEAD = ("head_m", "bip01 head")
FEET = (("ankle_l", "bip01 l foot"), ("ankle_r", "bip01 r foot"))

# A vehicle's seats in order: the label each seat gives, and the Spartan mode
# whose rows that label plays.
SEATS = (("mongoose_d", "ghost_d"), ("mongoose_p", "warthog_p"))

# What a mode's proxy groups hold on to: the joint they end.
MODE_PROXIES = {
    "ghost_d": {"spartan_hand_left": "wrist_l", "spartan_hand_right": "wrist_r",
                "spartan_foot_left": "ankle_l", "spartan_foot_right": "ankle_r"},
    "warthog_p": {"chief_p_ik_left_arm": "wrist_l", "chief_p_ik_left_leg": "ankle_l",
                  "chief_p_ik_right_leg": "ankle_r"},
}


def seat_sets(seats=SEATS):
    """The vehicle tag's seat labels, as `new-tag` sets."""
    return [f"unit.seats[{i}].label={label}" for i, (label, _) in enumerate(seats)]


def child_modes(seats=SEATS):
    """The seats as `mjolnir jmad child` arguments."""
    return [arg for label, donor in seats for arg in ("--mode", f"{donor}={label}")]


def frame(rotation=None, position=(0.0, 0.0, 0.0)):
    m = np.eye(4)
    if rotation is not None:
        m[:3, :3] = rotation
    m[:3, 3] = position
    return m


def quaternion(r):
    """The unit quaternion of a rotation matrix, x, y, z, w."""
    t = np.trace(r)
    if t > 0:
        s = math.sqrt(t + 1) * 2
        q = [r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1], s * s / 4]
        return nodes.unit(np.array(q) / s)
    i = int(np.argmax(np.diag(r)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(r[i, i] - r[j, j] - r[k, k] + 1) * 2
    q = [0.0, 0.0, 0.0, (r[k, j] - r[j, k]) / s]
    q[i] = s / 4
    q[j] = (r[j, i] + r[i, j]) / s
    q[k] = (r[k, i] + r[i, k]) / s
    return nodes.unit(q)


def along(v):
    return v / np.linalg.norm(v)


def basis(first, second):
    """Axes with `first` exact and `second` as near as it can be."""
    x = along(first)
    z = along(np.cross(x, second))
    return np.stack([x, np.cross(z, x), z], 1)


def swing(a, b):
    """The smallest rotation taking direction `a` to direction `b`."""
    a, b = along(a), along(b)
    axis = np.cross(a, b)
    s, c = np.linalg.norm(axis), float(a @ b)
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        other = np.eye(3)[int(np.argmin(np.abs(a)))]
        return 2 * np.outer(along(np.cross(a, other)), along(np.cross(a, other))) - np.eye(3)
    k = axis / s
    hat = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * hat + (1 - c) * hat @ hat


def bend(start, pole, target, upper, lower):
    """A two-bone limb from `start` towards `target`, bending towards `pole`:
    where its joint goes and where it ends. It ends short of straight."""
    to = target - start
    reach = np.linalg.norm(to)
    towards = to / reach
    reach = min(reach, REACH * (upper + lower))
    run = (reach * reach + upper * upper - lower * lower) / (2 * reach)
    rise = math.sqrt(max(upper * upper - run * run, 0.0))
    side = pole - start
    side = along(side - towards * (side @ towards))
    return start + towards * run + side * rise, start + towards * reach


# CE's side.


def ce_local(entry):
    """A CE node's frame on its parent. CE stores the conjugate of a rotation."""
    return frame(nodes.matrix(nodes.conjugate(nodes.unit(entry["rotation"]))), entry["translation"])


def ce_pose(rider, locals_):
    """Every node's frame over the seat, by name."""
    world = {}
    for n, local in zip(rider["nodes"], locals_):
        parent = n["parent"]
        above = world[rider["nodes"][parent]["name"]] if parent >= 0 else np.eye(4)
        world[n["name"]] = above @ ce_local(local)
    return world


def ce_bind(rider):
    return ce_pose(rider, rider["nodes"])


def ce_ik(world, top, joint, end, goal):
    """CE's two-bone step: the end goes to `goal`, and the two bones above it
    aim along the limb, each keeping its own left."""
    t, j, e = world[top], world[joint], world[end]
    upper = np.linalg.norm(j[:3, 3] - t[:3, 3])
    lower = np.linalg.norm(e[:3, 3] - j[:3, 3])
    knee, ends = bend(t[:3, 3], j[:3, 3], goal[:3, 3], upper, lower)
    for bone, start, to in ((t, t[:3, 3], knee), (j, knee, ends)):
        forward = along(to - start)
        up = along(np.cross(forward, bone[:3, 1]))
        bone[:3, :3] = np.stack([forward, np.cross(up, forward), up], 1)
    j[:3, 3] = knee
    e[:] = goal
    e[:3, 3] = ends


def marker_frame(m):
    return frame(np.stack([m["forward"], m["left"], m["up"]], 1), m["position"])


def seat_frame(ce, seat):
    return marker_frame(ce["vehicle"]["markers"][seat["marker"]])


def ce_after_ik(ce, seat, locals_):
    """A frame of CE's idle after its IK, over the seat."""
    rider = ce["rider"]
    world = ce_pose(rider, locals_)
    parent = {n["name"]: rider["nodes"][n["parent"]]["name"] for n in rider["nodes"] if n["parent"] >= 0}
    over_seat = np.linalg.inv(seat_frame(ce, seat))
    for point in seat["ik_points"]:
        held = rider["markers"].get(point["marker"])
        target = ce["vehicle"]["markers"].get(point["attached_to"])
        if held is None or target is None:
            continue
        joint = parent[held["node"]]
        goal = over_seat @ marker_frame(target) @ np.linalg.inv(ce_local(held))
        ce_ik(world, parent[joint], joint, held["node"], goal)
    return world


def resampled(frames, count):
    """`count` frames over the loop of `frames`, the first on the first."""
    out = []
    for f in range(count):
        at = f * len(frames) / count
        k = int(at)
        a, b, t = frames[k], frames[(k + 1) % len(frames)], at - k
        out.append([{"rotation": nodes.slerp(x["rotation"], y["rotation"], t),
                     "translation": (1 - t) * np.array(x["translation"]) + t * np.array(y["translation"])}
                    for x, y in zip(a, b)])
    return out


# The Spartan's side.


def channel_at(channel, f):
    if channel is None:
        return None
    if "static" in channel:
        return channel["static"]
    return channel["each"][f]


class Pose:
    """One frame of a donor animation: local frames, and the world they make."""

    def __init__(self, skeleton, tracks, f):
        self.names = [n["name"] for n in skeleton]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.parent = [n["parent"] for n in skeleton]
        self.local = []
        for t in tracks:
            scale = channel_at(t["scale"], f)
            if scale is not None and abs(scale - 1) > 1e-6:
                raise ValueError("a donor node scales, which this rule does not cover")
            q, v = channel_at(t["rotation"], f), channel_at(t["translation"], f)
            self.local.append(frame(nodes.matrix(nodes.unit(q)) if q is not None else None, v if v is not None else (0, 0, 0)))
        self.cache = {}

    def world(self, name):
        i = self.index[name] if isinstance(name, str) else name
        if i not in self.cache:
            p = self.parent[i]
            self.cache[i] = self.local[i] if p is None else self.world(p) @ self.local[i]
        return self.cache[i]

    def at(self, name):
        return self.world(name)[:3, 3]

    def place(self, name, position):
        """Move a node with a parent at the origin."""
        i = self.index[name]
        p = self.parent[i]
        above = np.eye(4) if p is None else self.world(p)
        self.local[i][:3, 3] = (np.linalg.inv(above) @ np.append(position, 1))[:3]
        self.cache = {}

    def turn(self, name, rotation):
        """Set a node's rotation in the seat."""
        i = self.index[name]
        p = self.parent[i]
        above = np.eye(3) if p is None else self.world(p)[:3, :3]
        self.local[i][:3, :3] = above.T @ rotation
        self.cache = {}

    def turn_by(self, name, delta):
        self.turn(name, delta @ self.world(name)[:3, :3])


def take_frame(pose, ce, table):
    node, child, (a, b), up_from, up_to, (side_a, side_b) = table
    was = basis(pose.at(child) - pose.at(node), pose.at(a) - pose.at(b))
    now = basis(ce[up_to][:3, 3] - ce[up_from][:3, 3], ce[side_a][:3, 3] - ce[side_b][:3, 3])
    pose.turn_by(node, now @ was.T)


def swing_bones(pose, ce, table):
    for node, child, ce_from, ce_to in table:
        pose.turn_by(node, swing(pose.at(child) - pose.at(node), ce[ce_to][:3, 3] - ce[ce_from][:3, 3]))


def aim_bones(pose, ce, table):
    for node, child, ce_joint in table:
        at = pose.at(node)
        pose.turn_by(node, swing(pose.at(child) - at, ce[ce_joint][:3, 3] - at))


def hinged_turn(was_bone, was_hinge, bone, hinge):
    return basis(bone, hinge) @ basis(was_bone, was_hinge).T


def reach(pose, ce, limb):
    """Bring a limb to CE's joint, in CE's plane, about the donor's hinge."""
    top, joint, end, _, ce_joint, ce_end = limb
    start = pose.at(top)
    was_upper, was_lower = pose.at(joint) - start, pose.at(end) - pose.at(joint)
    upper, lower = np.linalg.norm(was_upper), np.linalg.norm(was_lower)
    knee, ends = bend(start, ce[ce_joint][:3, 3], ce[ce_end][:3, 3], upper, lower)
    was_hinge = np.cross(was_upper, was_lower)
    hinge = np.cross(knee - start, ends - knee)
    was_top, was_joint = pose.world(top)[:3, :3].copy(), pose.world(joint)[:3, :3].copy()
    if np.linalg.norm(was_hinge) < 1e-6 or np.linalg.norm(hinge) < 1e-6:
        pose.turn(top, swing(was_upper, knee - start) @ was_top)
        pose.turn(joint, swing(was_lower, ends - knee) @ was_joint)
        return
    pose.turn(top, hinged_turn(was_upper, was_hinge, knee - start, hinge) @ was_top)
    pose.turn(joint, hinged_turn(was_lower, was_hinge, ends - knee, hinge) @ was_joint)


def bind_turn(pose, ce, ce_binding, spartan_binding, node, ce_node):
    turned = ce[ce_node][:3, :3] @ ce_binding[ce_node][:3, :3].T
    pose.turn(node, turned @ spartan_binding[node])


def retarget(pose, ce, ce_binding, spartan_binding):
    """Pose a donor frame on CE's. `ce` is CE's frames over the seat."""
    donor_rotation = {name: pose.world(name)[:3, :3].copy() for name in ("wrist_l", "wrist_r")}
    pose.place(ROOT[0], ce[ROOT[1]][:3, 3])
    take_frame(pose, ce, PELVIS)
    swing_bones(pose, ce, SPINE)
    take_frame(pose, ce, CHEST)
    swing_bones(pose, ce, NECK)
    bind_turn(pose, ce, ce_binding, spartan_binding, *HEAD)
    aim_bones(pose, ce, CLAVICLES)
    for limb in ARMS:
        reach(pose, ce, limb)
        pose.turn(limb[2], donor_rotation[limb[2]])
    for limb in LEGS:
        reach(pose, ce, limb)
    for node, ce_node in FEET:
        bind_turn(pose, ce, ce_binding, spartan_binding, node, ce_node)


def edited_nodes():
    rows = [PELVIS[0], CHEST[0], HEAD[0], *[b[0] for b in SPINE + NECK + CLAVICLES]]
    for limb in ARMS + LEGS:
        rows += limb[:3]
    return rows


def continuous(rotations):
    """The same rotations with no sign flip between frames."""
    out = [rotations[0]]
    for q in rotations[1:]:
        out.append(-q if q @ out[-1] < 0 else q)
    return out


def translate_seat(ce, seat, skeleton, animation):
    """Every frame of `animation` posed on CE's seat. Returns the poses, and
    CE's frames over the seat."""
    binding = ce_bind(ce["rider"])
    spartan_binding = {n["name"]: nodes.matrix(nodes.unit(n["default"]["rotation"])) for n in skeleton}
    frames = resampled(seat["frames"], animation["frames"])
    poses, targets = [], []
    for f, locals_ in enumerate(frames):
        pose = Pose(skeleton, animation["tracks"], f)
        world = ce_after_ik(ce, seat, locals_)
        retarget(pose, world, binding, spartan_binding)
        poses.append(pose)
        targets.append(world)
    return poses, targets


def spec_rows(poses):
    """The nodes the table moves, one value a frame."""
    rows = {}
    for name in edited_nodes():
        i = poses[0].index[name]
        rotation = continuous([quaternion(p.local[i][:3, :3]) for p in poses])
        rows[name] = {"rotation": [nodes.rounded(q) for q in rotation]}
    i = poses[0].index[ROOT[0]]
    rows[ROOT[0]]["translation"] = [[round(float(c), 7) for c in p.local[i][:3, 3]] for p in poses]
    return rows


def copy_rows(rows, names, animation):
    """`rows`' first frame written over a one-frame animation: its channels stay
    what they are, static or a frame each, and a channel it leaves out stays out."""
    out = {}
    for name, row in rows.items():
        track = animation["tracks"][names.index(name)]
        out[name] = {key: values[0] if "static" in track[key] else [values[0]]
                     for key, values in row.items() if track[key] is not None}
    return out


def proxy(ce, seat, group, joint, poses, targets, table):
    """One IK proxy, in the vehicle's frame and on the node it rides."""
    limb = next(x for x in ARMS + LEGS if x[2] == joint)
    ce_end = limb[5]
    seat_matrix = seat_frame(ce, seat)
    rider = ce["rider"]
    held = [p for p in seat["ik_points"] if rider["markers"].get(p["marker"], {}).get("node") == ce_end]
    markers = ce["vehicle"]["markers"]
    node = markers[held[0]["attached_to"]]["node"] if held else markers[seat["marker"]]["node"]
    pose = poses[0]
    fk = pose.world(joint)
    target = targets[0][ce_end][:3, 3]
    in_vehicle = seat_matrix @ frame(fk[:3, :3], target)
    bone = table[node]
    local = np.linalg.inv(bone) @ in_vehicle
    start = pose.at(limb[0])
    length = np.linalg.norm(pose.at(limb[1]) - start) + np.linalg.norm(pose.at(limb[2]) - pose.at(limb[1]))
    worst = max(np.linalg.norm(p.at(joint) - t[ce_end][:3, 3]) for p, t in zip(poses, targets))
    return {"group": group, "joint": joint, "node_name": node,
            "translation": [float(c) for c in local[:3, 3]],
            "rotation": [float(c) for c in quaternion(local[:3, :3])],
            "object_position_cm": [float(c) * WU_CM for c in in_vehicle[:3, 3]],
            "fk_distance_cm": float(np.linalg.norm(fk[:3, 3] - target)) * WU_CM,
            "fk_distance_worst_frame_cm": float(worst) * WU_CM,
            "reach_cm": float(np.linalg.norm(target - start)) * WU_CM,
            "limb_length_cm": float(length) * WU_CM,
            "share_of_limb": float(np.linalg.norm(target - start) / length)}


def bone_frames(manifest):
    """A manifest's bones in the object: by name, and each one's index."""
    frames, index = {}, {}
    for b in manifest["bones"]:
        o = b["tag_object"]
        frames[b["name"]] = frame(nodes.matrix(nodes.unit(o["rotation_xyzw"])), o["translation"])
        index[b["name"]] = b["index"]
    return frames, index


def build(ce, donor, seats, copies, manifest):
    """The jmad spec and the proxies. `seats` is seat label to donor animation,
    and `copies` animation to the one-frame animations that repeat it."""
    skeleton = donor["nodes"]
    table, index = bone_frames(manifest)
    animations, limbs, posed = [], {}, {}
    for label, name in seats.items():
        seat = next(s for s in ce["seats"] if s["label"] == label)
        animation = donor["animations"][name]
        poses, targets = translate_seat(ce, seat, skeleton, animation)
        rows = spec_rows(poses)
        animations.append({"name": name, "frames": animation["frames"], "nodes": rows})
        for other in copies.get(name, ()):
            copied = donor["animations"][other]
            if copied["frames"] != 1:
                raise ValueError(f"{other} has {copied['frames']} frames, not one")
            names = [n["name"] for n in skeleton]
            animations.append({"name": other, "frames": 1, "nodes": copy_rows(rows, names, copied)})
        for group, joint in MODE_PROXIES[name.split(":")[0]].items():
            row = proxy(ce, seat, group, joint, poses, targets, table)
            row["node"] = index[row["node_name"]]
            limbs[group] = row
        posed[name] = (poses, targets)
    return {"animations": animations}, limbs, posed


def pairs(text):
    a, _, b = text.partition("=")
    if not b:
        raise argparse.ArgumentTypeError(f"{text!r} is not A=B")
    return a, b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ce", required=True, help="CE's seats, as the docstring describes")
    ap.add_argument("--donor", required=True, help="`mjolnir jmad frames` of the graph")
    ap.add_argument("--bones", required=True, help="the vehicle's bones.json")
    ap.add_argument("--seat", type=pairs, action="append", required=True, help="CE seat label=donor animation")
    ap.add_argument("--copy", type=pairs, action="append", default=[], help="animation=one-frame animation repeating it")
    ap.add_argument("--out", required=True, help="the jmad spec")
    ap.add_argument("--limbs", required=True, help="the IK proxies")
    a = ap.parse_args()

    def load(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    copies = {}
    for name, other in a.copy:
        copies.setdefault(name, []).append(other)
    spec, limbs, _ = build(load(a.ce), load(a.donor), dict(a.seat), copies, load(a.bones))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    with open(a.limbs, "w", encoding="utf-8") as f:
        json.dump(limbs, f, indent=1)
    for group, row in limbs.items():
        print(f"{group:24s} on {row['node_name']:15s} FK off by {row['fk_distance_cm']:5.2f} cm, "
              f"reach {row['reach_cm']:5.1f} of {row['limb_length_cm']:5.1f} cm")


if __name__ == "__main__":
    main()
