#!/usr/bin/env python3
"""Experiment 2: the Mongoose on its own 14 nodes, as a full tag set.

    build_native.py <variant dir> --code NAT [--names ce|registered] [--root ce|origin]

Reads ce.json (ce_dump.py) and the values dumps in ref/. Writes every container
into <variant dir>/out. Experiment driver: see README.md here.

Rules applied, none per vehicle:
- A CE rotation is the conjugate of what this engine stores (wheel spin and arm
  travel only come out right that way; see the report).
- A CE overlay frame is a delta on the node's rest, as here, so deltas carry over.
- Overlays keep the donor graph's frame count, so its blend screen table stays
  valid: CE's frames are resampled onto them.
- CE ground depth is minus the height of the point above the ground, and this
  engine's is plus that height.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO + "/tools/level")
sys.path.insert(0, HERE + "/ref")
import ce_vehicle_nodes as N  # noqa: E402
import ce_vehicle_physics as P  # noqa: E402
from fk import qm, qr, conj  # noqa: E402

MJ = REPO + "/target/release/mjolnir.exe"
MJD = REPO + "/target/debug/mjolnir.exe"  # the only build with `jmad` yet
SP = os.environ["MJ_NATIVE_WORK"]  # decoded game data lives here, never in the repository
PAKS = os.environ["HCE_PAKS"]
WARTHOG_GRAPH = SP + "/nx/jw/all/objects/Vehicles/human/warthog/warthog.model_animation_graph"
BSP = SP + "/col/ce"
B = chr(92)
IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])
# The shift the shipped Mongoose's parts took to fit the Warthog's wheels, in wu:
# its hull BSP offset (col/build13/collision.plan.json) less CE's hull rest.
SHIPPED_HULL_AT = np.array([-0.0033630424446064455, 0.0, 0.3164294566421371])

# Registered names that no Warthog bone has, for the variant that keeps novel
# string ids out of the test.
STAND_INS = ["hull", "b_l_thigh", "b_l_clav", "b_r_thigh", "b_r_clav", "steering", "b_l_calf", "b_l_forearm",
             "b_r_calf", "b_r_forearm", "b_l_foot", "b_l_hand", "b_r_foot", "b_r_hand"]


def run(*args):
    env = dict(os.environ, HCE_PAKS=PAKS, MSYS_NO_PATHCONV="1")
    r = subprocess.run([str(a) for a in args], env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if r.returncode:
        sys.exit(f"{args[:3]} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r.stdout


def values(name):
    return P.flatten(json.load(open(f"{HERE}/ref/{name}.json", encoding="utf-8"))["fields"])


def unit(q):
    q = np.array(q, float)
    return q / np.linalg.norm(q)


def slerp(a, b, t):
    a, b = unit(a), unit(b)
    d = float(a @ b)
    if d < 0:
        b, d = -b, -d
    if d > 0.99999:
        return unit(a + t * (b - a))
    w = math.acos(d)
    return unit((math.sin((1 - t) * w) * a + math.sin(t * w) * b) / math.sin(w))


def q2(q):
    return [round(float(c), 7) for c in q]


def vec3(v):
    return ",".join(f"{float(c):.6f}" for c in v)


def quat(q):
    return ",".join(f"{float(c):.7f}" for c in q)


def index_text(i):
    return "-1" if i is None or i < 0 else str(i)


def rz90():
    return np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def matrix(q):
    return np.array([qr(q, e) for e in np.eye(3)]).T


def inverse_fields(wq, wt):
    """The skeleton's inverse frame, checked against all 119 Warthog nodes."""
    r = matrix(wq)
    f = r.T @ rz90()
    return f[:, 0], f[:, 1], f[:, 2], -(r.T @ wt)


def check_inverse_rule():
    from fk import skeleton
    os.chdir(HERE + "/ref")
    _, s = skeleton()
    worst = 0.0
    for n in s:
        f, l, u, p = inverse_fields(n["wq"], n["wt"])
        for got, want in zip((f, l, u, p), n["inv"]):
            worst = max(worst, float(np.abs(np.array(got) - np.array(want)).max()))
    os.chdir(HERE)
    print(f"inverse frame rule: worst miss {worst:.5f} over {len(s)} Warthog nodes")
    assert worst < 2e-3


class Nodes:
    """CE's nodes as this engine stores them."""

    def __init__(self, ce, names, root):
        self.parent = [n["parent"] for n in ce["nodes"]]
        self.count = len(self.parent)
        self.ce_names = [n["name"] for n in ce["nodes"]]
        self.names = self.ce_names if names == "ce" else STAND_INS
        self.q = [conj(unit(n["q"])) for n in ce["nodes"]]
        self.t = [np.array(n["t"]) for n in ce["nodes"]]
        self.hull = self.t[0].copy()
        if root == "origin":
            # The same object space, with the root at the object's origin.
            for i in range(1, self.count):
                if self.parent[i] == 0:
                    self.t[i] = self.t[i] + self.hull
            self.t[0] = np.zeros(3)
        # The first child and next sibling the graph writer gives new nodes.
        self.child = [None] * self.count
        self.sibling = [None] * self.count
        for i in reversed(range(self.count)):
            p = self.parent[i]
            if p >= 0:
                self.sibling[i] = self.child[p]
                self.child[p] = i
        self.wq, self.wt = [], []
        for i in range(self.count):
            p = self.parent[i]
            if p < 0:
                self.wq.append(self.q[i])
                self.wt.append(self.t[i])
            else:
                self.wq.append(qm(self.wq[p], self.q[i]))
                self.wt.append(self.wt[p] + qr(self.wq[p], self.t[i]))

    def to_root(self, object_point):
        """An object-space point, relative to node 0."""
        return np.array(object_point) - self.wt[0]


class Pedestal(N.NodeTable):
    """The mesh's own bone list: an identity pedestal over CE's nodes, verbatim."""

    def __init__(self, manifest):
        t = N.NodeTable.from_bones(manifest)
        super().__init__(t.names, t.parent, t.q, t.t, t.ce_nodes)
        self.ce_names = self.names
        self.hull = np.zeros(3)
        assert self.names[0] == "pedestal" and not self.wt[0].any()

    def to_root(self, object_point):
        return np.array(object_point) - self.wt[0]


def bone_of(nd, ce_node):
    return nd.of_ce(ce_node) if isinstance(nd, Pedestal) else ce_node


def jmad_spec(ce, nd):
    anim = {a["name"]: a for a in ce["animations"]}
    block = ce["vehicle_anims"][0]
    idle = anim["stand fixed idle"]
    for i in range(nd.count):  # CE's idle is its rest pose; say so rather than assume it.
        got = idle["data"][0][i]
        assert np.abs(conj(unit(got["r"])) - nd.q[i]).max() < 2e-3, i
        assert np.abs(np.array(got["t"]) - np.array(ce["nodes"][i]["t"])).max() < 1e-4, i
    spec = {"nodes": [], "animations": [], "reencode": True}
    for i in range(nd.count):
        e = {"name": nd.names[i], "rotation": q2(nd.q[i]), "translation": [float(c) for c in nd.t[i]], "scale": 1.0}
        if nd.parent[i] >= 0:
            e["parent"] = nd.names[nd.parent[i]]
        spec["nodes"].append(e)
    spec["animations"].append({"name": "any:idle", "frames": 1, "nodes": {
        nd.names[i]: {"rotation": q2(nd.q[i]), "translation": [float(c) for c in nd.t[i]]} for i in range(nd.count)}})

    # Suspension: the donor's four frames run from full extension to full
    # compression, as CE's two do.
    labels = {"suspension left back": "suspension:left:back", "suspension left front": "suspension:left:front",
              "suspension right back": "suspension:right:back", "suspension right front": "suspension:right:front"}
    for ce_name, label in labels.items():
        a = anim[ce_name]
        nodes = {}
        for i in range(nd.count):
            if a["rot_flags"] >> i & 1:
                ext, comp = conj(unit(a["data"][0][i]["r"])), conj(unit(a["data"][1][i]["r"]))
                nodes[nd.names[i]] = {"rotation": [q2(slerp(ext, comp, k / 3)) for k in range(4)]}
        assert nodes
        spec["animations"].append({"name": label, "frames": 4, "nodes": nodes})

    # Ground speed: one turn of the wheel, last frame back at rest, in both
    # graphs. CE turns all four engine nodes on one animation; the donor splits
    # front and rear.
    a = anim["vehicle ground-speed"]

    def turn(i, frames):
        keys = [IDENTITY] + [conj(unit(a["data"][k][i]["r"])) for k in range(a["frames"])]
        out = []
        for f in range(frames):
            at = (f + 1) / frames * a["frames"]
            k = min(int(at), a["frames"] - 1)
            out.append(q2(slerp(keys[k], keys[k + 1], at - k)))
        return out

    spinning = [i for i in range(nd.count) if a["rot_flags"] >> i & 1]
    front = [i for i in spinning if "lf_" in nd.ce_names[i] or "rf_" in nd.ce_names[i]]
    rear = [i for i in spinning if i not in front]
    spec["animations"].append({"name": "vehicle:ground_speed", "frames": 9,
                               "nodes": {nd.names[i]: {"rotation": turn(i, 9)} for i in front}})
    spec["animations"].append({"name": "vehicle:ground_speed_rear", "frames": 9,
                               "nodes": {nd.names[i]: {"rotation": turn(i, 9)} for i in rear}})

    # Steering: the donor's blend screen maps yaw +45, +22.5, 0, -22.5, -45 degrees
    # to frames 0 to 4, plus being left. CE runs linearly to its frame's yaw, then stops.
    a = anim["vehicle steering"]
    per_frame = math.degrees(block["left_yaw"])
    nodes = {}
    for i in range(nd.count):
        if not a["rot_flags"] >> i & 1:
            continue
        right, left = conj(unit(a["data"][0][i]["r"])), conj(unit(a["data"][2][i]["r"]))
        assert np.abs(unit(a["data"][1][i]["r"]) - IDENTITY).max() < 1e-3
        frames = []
        for yaw in (45.0, 22.5, 0.0, -22.5, -45.0):
            side = left if yaw > 0 else right
            frames.append(q2(slerp(IDENTITY, side, min(abs(yaw) / per_frame, 1.0))))
        nodes[nd.names[i]] = {"rotation": frames}
    spec["animations"].append({"name": "vehicle:steering", "frames": 5, "nodes": nodes})
    return spec


def jmad_sets(ce):
    """Depths by each animation's own CE row. The row's mass point index reads as a
    node index in this tag (10, 12, 11, 13 are lb, rb, lf, rf as nodes, not as mass
    points), so a row is matched by its animation, which is unambiguous."""
    rows = {r["animation"]: r for r in ce["vehicle_anims"][0]["suspension"]}
    names = {a["i"]: a["name"] for a in ce["animations"]}
    want = {"suspension left back": 0, "suspension left front": 1, "suspension right back": 2, "suspension right front": 3}
    sets = []
    for anim, row in rows.items():
        k = want[names[anim]]
        p = f"content.vehicle suspension[{k}]"
        for field, value in (("full extension ground_depth", -row["extension"]), ("full compression ground_depth", -row["compression"]),
                             ("destroyed full extension ground_depth", -row["extension"]),
                             ("destroyed full compression ground_depth", -row["compression"])):
            sets.append(f"{p}.{field}={value:.6f}")
    return sets


def donor_markers(skel, shipped_nodes, moved):
    """Every shipped Mongoose marker group in object space."""
    out = []
    for g in range(P.count(skel, "marker groups")):
        name = skel[f"marker groups[{g}].name"]
        p = f"marker groups[{g}].markers[0]"
        node = int(skel[p + ".node index"].lstrip("#"))
        wq, wt = shipped_nodes[node]["wq"], shipped_nodes[node]["wt"]
        t = wt + qr(wq, P.vec(skel[p + ".translation"]))
        q = qm(wq, unit(P.vec(skel[p + ".rotation"])))
        d = qr(wq, P.vec(skel[p + ".direction"]))
        if name in moved:  # placed on the CE body, so out of the shipped fit's frame
            t = t - (SHIPPED_HULL_AT - np.array([-0.07072780427970285, 0.0, 0.35181903620091637]))
        out.append(dict(name=name, node=0, t=t, q=q, d=d, scale=float(skel[p + ".scale"]), object_space=True))
    return out


def skeleton_build(ce, nd, a, registered):
    skel = values("m_skeleton_model")
    os.chdir(HERE + "/ref")
    from fk import skeleton
    _, ship = skeleton("m_skeleton_model.json")
    os.chdir(HERE)
    ik = {f"spartan_{s}_{d}" for s in ("foot", "hand") for d in ("left", "right")} | {"chief_p_ik_left_arm", "chief_p_ik_left_leg", "chief_p_ik_right_leg"}
    moved = ik | {"driver", "passenger", "driver_enter", "passenger_enter"}
    groups = donor_markers(skel, ship, moved)
    by_name = {g["name"]: i for i, g in enumerate(groups)}

    # Wheels: at CE's tyre mass points, on the root, as the Warthog's are.
    mass = {m["name"]: m for m in ce["phys"]["mass_points"]}
    for marker, point in (("vh_wheel_back_left", "tire back left"), ("vh_wheel_back_right", "tire back right"),
                          ("vh_wheel_front_left", "tire front left"), ("vh_wheel_front_right", "tire front right")):
        groups[by_name[marker]]["t"] = np.array(mass[point]["position"])

    # CE's own markers at their true places.
    ce_groups = {}
    for m in ce["markers"]:
        ce_groups.setdefault(m["name"], []).append(m)
    multi = []
    for name, rows in ce_groups.items():
        if name not in registered:
            if a.names != "ce":
                continue
        parts = [dict(node=bone_of(nd, m["node"]), t=np.array(m["t"]) + (nd.hull if a.root == "origin" and m["node"] == 0 else 0),
                      q=conj(unit(m["q"])), d=np.array([1.0, 0, 0]), scale=0.01) for m in rows]
        entry = dict(name=name, markers=parts)
        if name in by_name:
            at = by_name[name]
            if len(parts) > 1:
                sys.exit(f"{name}: a shipped single with several CE markers")
            groups[at] = dict(entry, ce=True)
        elif len(parts) > 1:
            multi.append(dict(entry, ce=True))
        else:
            groups.append(dict(entry, ce=True))

    # A group of several markers takes a slot grafted to that size, and the group
    # that held the slot moves to an appended single.
    expendable = ["vfx_wheelwell_inner_l_01_0", "vfx_wheelwell_inner_r_02", "vfx_wheelwell_inner_r_01"]
    sources = {2: "skeleton_model:warthog_troop-skeleton_model:marker groups[4].markers",
               4: "skeleton_model:warthog_troop-skeleton_model:marker groups[0].markers"}
    grafts = []
    for entry, name in zip(multi, expendable):
        slot = by_name[name]
        groups.append(groups[slot])
        groups[slot] = entry
        grafts += ["--graft", f"marker groups[{slot}].markers={sources[len(entry['markers'])]}"]

    # Rider limbs: each IK proxy where CE's own limb ends, on the node CE's ik point
    # rides, turned as the translated idle's joint lies. ce_vehicle_rider.py works
    # them out, already local to the node.
    limbs = json.load(open(os.path.join(HERE, "..", "rider2", "limbs.json"), encoding="utf-8"))
    for name, row in limbs.items():
        g = groups[by_name[name]]
        assert nd.names[row["node"]] == row["node_name"], name
        groups[by_name[name]] = dict(name=name, markers=[dict(node=row["node"], t=np.array(row["translation"]),
                                                              q=np.array(row["rotation"]), d=g["d"], scale=g["scale"])])

    sets = []
    for i in range(0 if isinstance(nd, Pedestal) else nd.count):
        p = f"nodes[{i}]"
        f, l, u, pos = inverse_fields(nd.wq[i], nd.wt[i])
        sets += [f"{p}.name={nd.names[i]}", f"{p}.parent node={index_text(nd.parent[i])}",
                 f"{p}.next sibling node={index_text(nd.sibling[i])}", f"{p}.first child node={index_text(nd.child[i])}",
                 f"{p}.default translation={vec3(nd.t[i])}", f"{p}.default rotation={quat(nd.q[i])}", f"{p}.inverse scale=1",
                 f"{p}.inverse forward={vec3(f)}", f"{p}.inverse left={vec3(l)}", f"{p}.inverse up={vec3(u)}", f"{p}.inverse position={vec3(pos)}"]
        r = f"runtime node orientations[{i}]"
        sets += [f"{r}.rotation={quat(nd.q[i])}", f"{r}.translation={vec3(nd.t[i])}", f"{r}.scale=1"]
    if isinstance(nd, Pedestal):
        sets += nd.skeleton_sets()
    for g, entry in enumerate(groups):
        sets.append(f"marker groups[{g}].name={entry['name']}")
        rows = entry.get("markers")
        if rows is None:  # an object-space shipped marker, on the root
            rows = [dict(node=0, t=nd.to_root(entry["t"]), q=entry["q"], d=entry["d"], scale=entry["scale"])]
        for k, m in enumerate(rows):
            p = f"marker groups[{g}].markers[{k}]"
            sets += [f"{p}.region index=-1", f"{p}.permutation index=-1", f"{p}.node index={m['node']}", f"{p}.flags=0x1",
                     f"{p}.translation={vec3(m['t'])}", f"{p}.rotation={quat(m['q'])}", f"{p}.scale={m['scale']:.4f}",
                     f"{p}.direction={vec3(m['d'])}"]
    resizes = ["--resize", f"nodes={nd.count}", "--resize", f"runtime node orientations={nd.count}",
               "--resize", f"marker groups={len(groups)}"]
    return sets, grafts + resizes, groups


def collision_build(ce, nd, a, out):
    coll = values("m_collision_model")
    names = {coll[f"regions[{i}].name"]: i for i in range(P.count(coll, "regions"))}
    tyres = {"lf": "wheel_front_left", "rf": "wheel_front_right", "lb": "wheel_back_left", "rb": "wheel_back_right"}
    # Regions and materials share their index in the donor.
    parts = [{"region": names["hull"], "material": names["hull"], "node": bone_of(nd, 0), "bsp": f"{BSP}/frame_hull.bsp.json",
              "offset": [float(c) for c in (nd.hull if a.root == "origin" else [0, 0, 0])]}]
    for key, region in tyres.items():
        node = nd.ce_names.index(f"frame {key}_tire")
        parts.append({"region": names[region], "material": names[region], "node": node,
                      "bsp": f"{BSP}/frame_{key}_tire.bsp.json", "offset": [0.0, 0.0, 0.0]})
    plan = os.path.join(out, "collision.plan.json")
    json.dump({"blank_others": True, "parts": parts}, open(plan, "w"), indent=1)
    payload = os.path.join(out, "mongoose.collision_model")
    print(run(MJ, "level", "machine-collision", "--plan", plan, "--donor", "human/warthog/warthog-collision_model", "--out", payload).strip())

    os.chdir(HERE + "/ref")
    from fk import skeleton
    _, ship = skeleton("m_skeleton_model.json")
    os.chdir(HERE)
    sets = []
    for i in range(nd.count):
        p = f"nodes[{i}]"
        sets += [f"{p}.name={nd.names[i]}", f"{p}.parent node={index_text(nd.parent[i])}",
                 f"{p}.next sibling node={index_text(nd.sibling[i])}", f"{p}.first child node={index_text(nd.child[i])}"]
    for i in range(P.count(coll, "pathfinding spheres")):
        p = f"pathfinding spheres[{i}]"
        n = ship[int(coll[p + ".node"].lstrip("#"))]
        world = n["wt"] + qr(n["wq"], P.vec(coll[p + ".center"]))
        sets += [f"{p}.node=0", f"{p}.center={vec3(nd.to_root(world))}"]
    return payload, sets, ["--resize", f"nodes={nd.count}"]


def physics_build(nd, a):
    model = values("m_physics_model")
    # The shipped body sits in the fit's frame. Take that out, then go to the
    # root node's space. One body on the root: the Tick's layout.
    shift = SHIPPED_HULL_AT - np.array([-0.07072780427970285, 0.0, 0.35181903620091637])
    total = -(shift + nd.wt[0])
    lo, hi = P.shape_box(model)
    stretch = P.Stretch(lo, hi, [lo[k] + total[k] for k in range(3)], [hi[k] + total[k] for k in range(3)])
    centre = [c + total[k] for k, c in enumerate(P.shipped_centre_of_mass(model))]
    sets = P.physics_sets(model, stretch, float(model["mass"]), centre)
    # A second body's edits go with the body.
    sets = [s for s in sets if not s.startswith("rigid bodies[1]")]
    sets += ["regions[0].name=hull", "regions[0].permutations[0].name=default"]
    for i in range(nd.count):
        p = f"nodes[{i}]"
        sets += [f"{p}.name={nd.names[i]}", f"{p}.parent={index_text(nd.parent[i])}",
                 f"{p}.sibling={index_text(nd.sibling[i])}", f"{p}.child={index_text(nd.child[i])}"]
    sets.append("rigid bodies[0].node=0")
    return sets, ["--graft", "regions=physics_model:Tick/tick-physics_model:regions", "--resize", "rigid bodies=1",
                  "--resize", "node edges=0", "--resize", f"nodes={nd.count}"]


def vehicle_build(ce, a, tag):
    v = values("m_vehicle")
    sets = [f"unit.object.model=hlmt:{tag}", "unit.seats[0].marker name=driver", "unit.seats[1].marker name=gunner"]
    if a.names == "ce":
        sets += ["unit.seats[0].entry marker(s) name=driver enter", "unit.seats[1].entry marker(s) name=gunner enter"]
    radius = {}
    for m in ce["phys"]["mass_points"]:
        if m["name"].startswith("tire"):
            radius[m["name"]] = np.frombuffer(bytes.fromhex(m["raw"][24:32]), dtype="<f4")[0]
    r = float(next(iter(radius.values())))
    assert all(abs(x - r) < 1e-5 for x in radius.values()), radius
    h = "havok vehicle physics"
    for i in range(P.count(v, f"{h}.friction points")):
        p = f"{h}.friction points[{i}]"
        old = float(v[p + ".radius"])
        sets += [f"{p}.radius={r:.6f}", f"{p}.damaged radius={float(v[p + '.damaged radius']) * r / old:.6f}"]
    return sets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--code", required=True)
    ap.add_argument("--names", default="ce", choices=("ce", "registered"))
    ap.add_argument("--root", default="ce", choices=("ce", "origin", "pedestal"))
    ap.add_argument("--bones", help="bones.json, with --root pedestal")
    ap.add_argument("--asset", help="the Blueprint the vehicle tag binds")
    ap.add_argument("--out", help="the containers' folder, kept as it is; default <dir>/out, emptied")
    ap.add_argument("--only", action="append", help="build only this container: jmad, skel, coll, phmo, model, vehi")
    a = ap.parse_args()
    check_inverse_rule()
    ce = json.load(open(HERE + "/ce.json"))
    nd = Pedestal(json.load(open(a.bones, encoding="utf-8"))) if a.root == "pedestal" else Nodes(ce, a.names, a.root)
    registered = set(json.load(open(HERE + "/ref/registered.json")))
    assert set(STAND_INS) <= registered, set(STAND_INS) - registered
    work = os.path.join(HERE, a.dir)
    os.makedirs(work, exist_ok=True)
    if a.out:
        out = a.out
    else:
        out = os.path.join(work, "out")
        assert os.path.basename(out) == "out" and os.path.dirname(os.path.dirname(out)).replace(chr(92), "/") == HERE.replace(chr(92), "/")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
    tag = B.join(["objects", "mjolnir", a.code.lower(), "mongoose"])
    stub = next(f for f in sorted(os.listdir(PAKS)) if f.startswith("pakchunk997-MJOLNIRMAP-") and f.endswith("_P.pak"))

    def new(group, source, suffix, sets, extra=(), to=tag):
        if a.only and suffix not in a.only:
            return
        path = os.path.join(work, suffix + ".sets.txt")
        open(path, "w", encoding="utf-8").write("\n".join(sets) + "\n")
        name = f"pakchunk996-MJOLNIR{a.code}-{suffix}"
        text = run(MJ, "new-tag", "--group", group, "--from", source, "--to", to, "--out-dir", out, "--name", name,
                   *extra, "--set-file", path)
        open(os.path.join(work, suffix + ".log"), "w", encoding="utf-8").write(text)
        shutil.copyfile(os.path.join(PAKS, stub), os.path.join(out, name + "_P.pak"))
        print(suffix, "built")

    spec = N.jmad_spec(ce, nd) if isinstance(nd, Pedestal) else jmad_spec(ce, nd)
    spec_path = os.path.join(work, "jmad.spec.json")
    json.dump(spec, open(spec_path, "w"), indent=1)
    payload = os.path.join(work, "mongoose.jmad")
    print(run(MJD, "jmad", "rewrite", WARTHOG_GRAPH, "--spec", spec_path, "--out", payload).strip())
    # The rewrite drops the donor's usage rows with their nodes. Every shipped
    # vehicle graph has a pedestal row on node 0, so this one keeps it.
    usage = "definitions.node usage"
    new("model_animation_graph", "human/warthog/warthog-model_animation_graph", "jmad",
        [f"{usage}[0].node to use=0"] + (N.suspension_sets(ce) + N.default_sets(nd) if isinstance(nd, Pedestal) else jmad_sets(ce)),
        ("--payload", payload, "--graft", f"{usage}=model_animation_graph:sensor_relay/sensor_relay-model_animation_graph:{usage}"))

    sets, extra, groups = skeleton_build(ce, nd, a, registered)
    new("skeleton_model", "mjolnir/vht/mongoose-skeleton_model", "skel", sets, extra)

    payload, sets, extra = collision_build(ce, nd, a, work)
    new("collision_model", "mjolnir/vht/mongoose-collision_model", "coll", sets, ("--payload", payload, *extra))

    sets, extra = physics_build(nd, a)
    new("physics_model", "mjolnir/vht/mongoose-physics_model", "phmo", sets, extra)

    new("model", "mjolnir/vht/mongoose-model", "model",
        [f"skeleton model=skel:{tag}", f"collision model=coll:{tag}", f"physics_model=phmo:{tag}", f"animation=jmad:{tag}"])
    new("vehicle", "mjolnir/vht/mongoose-vehicle", "vehi", vehicle_build(ce, a, tag),
        ("--asset-reference", a.asset) if a.asset else ())
    json.dump({"code": a.code, "tag": tag, "names": nd.names, "groups": [g["name"] for g in groups]}, open(os.path.join(work, "built.json"), "w"), indent=1)
    print("tag", tag, "containers in", out)


if __name__ == "__main__":
    main()
