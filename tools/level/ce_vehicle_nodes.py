#!/usr/bin/env python3
"""One node list for a vehicle, from ce_vehicle_skin.py's bones.json.

The skeleton, collision, physics and animation tags must agree on their nodes,
and the drawn mesh's bones must carry the same names, so everything here starts
from the manifest the mesh was built from. A tag built from anything else can
drift from the mesh without either noticing.

Rules, none of them per vehicle:

- A manifest rotation is already as a tag stores it: the conjugate of what CE
  stores. CE's own animation data goes through the same conjugate.
- An overlay frame is a delta on the node's rest, in CE and here, so the deltas
  carry over.
- Overlays keep the donor graph's frame counts, so its blend screen table stays
  valid: CE's frames are resampled onto them.
- CE ground depth is minus the height of the point above the ground, and this
  engine's is plus that height.
"""
import math

import numpy as np

IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])

# A CE suspension row names its animation, and the graph's slots are by label.
SUSPENSION = {
    "suspension left back": ("suspension:left:back", 0),
    "suspension left front": ("suspension:left:front", 1),
    "suspension right back": ("suspension:right:back", 2),
    "suspension right front": ("suspension:right:front", 3),
}
# The donor's steering blend screen: yaw in degrees for frames 0 to 4.
STEERING_FRAMES = (45.0, 22.5, 0.0, -22.5, -45.0)
SUSPENSION_FRAMES = 4
GROUND_SPEED_FRAMES = 9


def unit(q):
    q = np.array(q, float)
    return q / np.linalg.norm(q)


def conjugate(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def rotate(q, v):
    axis = np.array(q[:3], float)
    v = np.array(v, float)
    c = np.cross(axis, v)
    return v + 2 * (q[3] * c + np.cross(axis, c))


def slerp(a, b, t):
    a, b = unit(a), unit(b)
    d = float(a @ b)
    if d < 0:
        b, d = -b, -d
    if d > 0.99999:
        return unit(a + t * (b - a))
    w = math.acos(d)
    return unit((math.sin((1 - t) * w) * a + math.sin(t * w) * b) / math.sin(w))


def rounded(q):
    return [round(float(c), 7) for c in q]


def vec3(v):
    return ",".join(f"{float(c):.6f}" for c in v)


def quat(q):
    return ",".join(f"{float(c):.7f}" for c in q)


def index_text(i):
    return "-1" if i is None or i < 0 else str(i)


def matrix(q):
    return np.array([rotate(q, e) for e in np.eye(3)]).T


def inverse_frame(object_rotation, object_translation):
    """A skeleton node's inverse fields: forward, left, up, position. The tag's
    rows are the object-to-node rotation turned a quarter about up."""
    quarter = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    r = matrix(object_rotation)
    f = r.T @ quarter
    return f[:, 0], f[:, 1], f[:, 2], -(r.T @ object_translation)


class NodeTable:
    """Nodes in tag order, with the links and object frames a tag needs."""

    def __init__(self, names, parents, rotations, translations, ce_nodes):
        self.names = list(names)
        self.parent = list(parents)
        self.q = [unit(q) for q in rotations]
        self.t = [np.array(t, float) for t in translations]
        self.ce_nodes = list(ce_nodes)
        self.count = len(self.names)
        for i, p in enumerate(self.parent):
            if p >= i:
                raise ValueError(f"node {self.names[i]} comes before its parent")
        self.child = [None] * self.count
        self.sibling = [None] * self.count
        for i in reversed(range(self.count)):
            p = self.parent[i]
            if p >= 0:
                self.sibling[i] = self.child[p]
                self.child[p] = i
        self.wq, self.wt = [], []
        for i, p in enumerate(self.parent):
            if p < 0:
                self.wq.append(self.q[i])
                self.wt.append(self.t[i])
            else:
                self.wq.append(multiply(self.wq[p], self.q[i]))
                self.wt.append(self.wt[p] + rotate(self.wq[p], self.t[i]))

    @classmethod
    def from_bones(cls, manifest):
        rows = manifest["bones"]
        if [r["index"] for r in rows] != list(range(len(rows))):
            raise ValueError("bones are not in index order")
        if manifest["contract"]["node_count"] != len(rows):
            raise ValueError("the manifest's node count disagrees with its bones")
        return cls([r["name"] for r in rows], [r["parent"] for r in rows],
                   [r["tag_local"]["rotation_xyzw"] for r in rows], [r["tag_local"]["translation"] for r in rows],
                   [r["ce_node"] for r in rows])

    def of_ce(self, ce_node):
        """The node a CE node index became."""
        return self.ce_nodes.index(ce_node)

    def links(self, i):
        return self.parent[i], self.sibling[i], self.child[i]

    def link_sets(self, block, parent="parent node", sibling="next sibling node", child="first child node"):
        """new-tag edits that give a node block these names and links."""
        sets = []
        for i in range(self.count):
            p = f"{block}[{i}]"
            sets += [f"{p}.name={self.names[i]}", f"{p}.{parent}={index_text(self.parent[i])}",
                     f"{p}.{sibling}={index_text(self.sibling[i])}", f"{p}.{child}={index_text(self.child[i])}"]
        return sets

    def skeleton_sets(self):
        """The skeleton's node and runtime orientation rows."""
        sets = self.link_sets("nodes")
        for i in range(self.count):
            p = f"nodes[{i}]"
            f, l, u, at = inverse_frame(self.wq[i], self.wt[i])
            sets += [f"{p}.default translation={vec3(self.t[i])}", f"{p}.default rotation={quat(self.q[i])}",
                     f"{p}.inverse scale=1", f"{p}.inverse forward={vec3(f)}", f"{p}.inverse left={vec3(l)}",
                     f"{p}.inverse up={vec3(u)}", f"{p}.inverse position={vec3(at)}"]
            r = f"runtime node orientations[{i}]"
            sets += [f"{r}.rotation={quat(self.q[i])}", f"{r}.translation={vec3(self.t[i])}", f"{r}.scale=1"]
        return sets


def moved_nodes(animation, table, frame_rotation):
    """{node name: rotation or rotations} over the CE nodes an animation turns."""
    nodes = {}
    for ce_node in range(len(animation["data"][0])):
        if animation["rot_flags"] >> ce_node & 1:
            nodes[table.names[table.of_ce(ce_node)]] = frame_rotation(ce_node)
    return nodes


def check_rest(ce, table):
    """CE's idle is its rest pose; say so rather than assume it."""
    idle = next(a for a in ce["animations"] if a["name"] == "stand fixed idle")
    for ce_node, got in enumerate(idle["data"][0]):
        i = table.of_ce(ce_node)
        if np.abs(conjugate(unit(got["r"])) - table.q[i]).max() >= 2e-3:
            raise ValueError(f"{table.names[i]}: idle rotation is not the rest")
        if np.abs(np.array(got["t"]) - table.t[i]).max() >= 1e-4:
            raise ValueError(f"{table.names[i]}: idle translation is not the rest")


def jmad_spec(ce, table):
    """The `mjolnir jmad rewrite` spec for a CE vehicle on this table."""
    anims = {a["name"]: a for a in ce["animations"]}
    check_rest(ce, table)
    nodes = []
    for i in range(table.count):
        row = {"name": table.names[i], "rotation": rounded(table.q[i]), "translation": [float(c) for c in table.t[i]],
               "scale": 1.0}
        if table.parent[i] >= 0:
            row["parent"] = table.names[table.parent[i]]
        nodes.append(row)
    spec = {"nodes": nodes, "reencode": True, "animations": [{
        "name": "any:idle", "frames": 1,
        "nodes": {n["name"]: {"rotation": n["rotation"], "translation": n["translation"]} for n in nodes}}]}

    # Suspension: the donor's frames run from full extension to full compression,
    # as CE's two do.
    last = SUSPENSION_FRAMES - 1
    for ce_name, (label, _) in SUSPENSION.items():
        a = anims[ce_name]

        def travel(ce_node, a=a):
            extended = conjugate(unit(a["data"][0][ce_node]["r"]))
            compressed = conjugate(unit(a["data"][1][ce_node]["r"]))
            return {"rotation": [rounded(slerp(extended, compressed, k / last)) for k in range(SUSPENSION_FRAMES)]}
        spec["animations"].append({"name": label, "frames": SUSPENSION_FRAMES, "nodes": moved_nodes(a, table, travel)})

    # Ground speed: one turn, last frame back at rest. CE turns every driven node
    # on one animation; the donor splits front from rear, so a node's place in the
    # object decides: +x is forward, and front is ahead of the driven nodes' middle.
    a = anims["vehicle ground-speed"]

    def turn(ce_node):
        keys = [IDENTITY] + [conjugate(unit(a["data"][k][ce_node]["r"])) for k in range(a["frames"])]
        frames = []
        for f in range(GROUND_SPEED_FRAMES):
            at = (f + 1) / GROUND_SPEED_FRAMES * a["frames"]
            k = min(int(at), a["frames"] - 1)
            frames.append(rounded(slerp(keys[k], keys[k + 1], at - k)))
        return {"rotation": frames}

    spinning = moved_nodes(a, table, turn)
    along = {n: float(table.wt[table.names.index(n)][0]) for n in spinning}
    middle = (min(along.values(), default=0.0) + max(along.values(), default=0.0)) / 2
    front = {n: v for n, v in spinning.items() if along[n] >= middle}
    rear = {n: v for n, v in spinning.items() if n not in front}
    spec["animations"].append({"name": "vehicle:ground_speed", "frames": GROUND_SPEED_FRAMES, "nodes": front})
    spec["animations"].append({"name": "vehicle:ground_speed_rear", "frames": GROUND_SPEED_FRAMES, "nodes": rear})

    # Steering: CE runs linearly to its end frame's yaw, then stops. Frame 0 is
    # hard right, the middle frame is straight, the last is hard left.
    a = anims["vehicle steering"]
    limit = math.degrees(ce["vehicle_anims"][0]["left_yaw"])

    def steer(ce_node):
        right = conjugate(unit(a["data"][0][ce_node]["r"]))
        left = conjugate(unit(a["data"][a["frames"] - 1][ce_node]["r"]))
        if np.abs(unit(a["data"][a["frames"] // 2][ce_node]["r"]) - IDENTITY).max() >= 1e-3:
            raise ValueError("the steering animation's middle frame is not straight")
        frames = []
        for yaw in STEERING_FRAMES:
            frames.append(rounded(slerp(IDENTITY, left if yaw > 0 else right, min(abs(yaw) / limit, 1.0))))
        return {"rotation": frames}

    spec["animations"].append({"name": "vehicle:steering", "frames": len(STEERING_FRAMES),
                               "nodes": moved_nodes(a, table, steer)})
    return spec


def default_sets(table):
    """Each node's bind pose in the graph's own node rows. A shipped graph holds
    these in object space, where they match its mesh's bones, while the rewrite
    needs locals to work frames out, so they go on after it."""
    sets = []
    for i in range(table.count):
        p = f"additional node data[{i}]"
        sets += [f"{p}.default rotation={quat(table.wq[i])}", f"{p}.default translation={vec3(table.wt[i])}"]
    return sets


def suspension_sets(ce):
    """The graph's suspension depths from CE's rows. A row is matched by its
    animation: its point index reads differently between tags."""
    names = {a["i"]: a["name"] for a in ce["animations"]}
    sets = []
    for row in ce["vehicle_anims"][0]["suspension"]:
        _, k = SUSPENSION[names[row["animation"]]]
        p = f"content.vehicle suspension[{k}]"
        for field, value in (("full extension ground_depth", -row["extension"]),
                             ("full compression ground_depth", -row["compression"]),
                             ("destroyed full extension ground_depth", -row["extension"]),
                             ("destroyed full compression ground_depth", -row["compression"])):
            sets.append(f"{p}.{field}={value:.6f}")
    return sets


def disagreements(table, lists):
    """Where each tag's read-back node list leaves the table. `lists` is
    {tag: [(name, parent, sibling, child), ...]}, with -1 for no link; a name of
    None skips the name check for tags that hold none."""
    want = [(table.names[i], *(-1 if v is None else v for v in table.links(i))) for i in range(table.count)]
    out = []
    for tag, rows in lists.items():
        if len(rows) != len(want):
            out.append(f"{tag}: {len(rows)} nodes, wanted {len(want)}")
            continue
        for i, (got, expected) in enumerate(zip(rows, want)):
            if got[0] is not None and got[0] != expected[0]:
                out.append(f"{tag}[{i}]: named {got[0]}, wanted {expected[0]}")
            if tuple(got[1:]) != expected[1:]:
                out.append(f"{tag}[{i}] {expected[0]}: links {tuple(got[1:])}, wanted {expected[1:]}")
    return out
