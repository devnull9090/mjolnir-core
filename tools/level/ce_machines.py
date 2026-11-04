#!/usr/bin/env python3
"""Build the simulation's own machines for a CE map's scripted devices, so a
gate's collision moves with it and a script can drive it.

    ce_machines.py <map> <staging> <CODE> <out dir> [--names <machine name>...] [--report report.json]
                   [--auto] [--mjolnir PATH]

`--report` takes tools/ce_scripts/ce_translate.py's report for the names.

Each distinct machine tag becomes a clone of B40's elevator family, as
tools/level/h2_machines.py does for Halo 2's turning parts (machine, model,
collision model, physics model and animation graph). The difference is the
motion: the elevator's own `device:position` animation is already a slide of
its root by the device's position, so a CE gate keeps the elevator's layout
and only its frames change (`slide_resource`).

- Collision: CE's BSP goes across as it is, in its node's space. A BSP cannot
  simply be moved (its 2D nodes hold offsets too), so the node's rest offset
  goes in the donor's second node (`platform`, which the collision hangs on)
  as a static translation.
- A gate (a tag with an animation graph): frames are its moving node's
  overlay, added to the rest pose: position 0 is the pose the model is drawn
  in. A real CE machine eases, so every frame is kept.
- A panic shield (no animation; CE's scripts create and destroy it): a machine
  that is always there, parked `PARK` wu under the map at position 0 and at
  home at position 1, so a shield needs no object_create, and its actor stays
  bound for the loader's mesh on every machine in the game.

- An automatic door (`--auto`: a door-type machine no script names): CE's are
  several parts moving apart, each with a BSP of its own, and a clone has one
  moving root. So each part is a door of its own, placed at its node
  (`offset`), and they open together because they sit together.
- A turning device (frames that rotate): the node's rotation about its own
  origin, by `h2_machines.turn_resource`, placed at its node the same way.
- Scripted scenery (a `promoted` staging entry, tools/level/ce_promote.py): as
  a shield.

Writes machines.json, keyed by tag path: tag, class, frames, kind, or `parts`,
a list of those with `offset` and `node`.
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "ce_scripts"))
import ce_scenario  # noqa: E402
from h2_machines import DONOR, DONOR_CLASS, boxes, leaf, physics_args, turn_resource  # noqa: E402

PARK = 300.0
# A gate retracted flush with the floor stops a biped dead, where CE walks over
# it: moving collision has no step-up. Its low end sinks this much further.
SINK = 0.15
CONTROL_DONOR = "b40-forerunner_switch-elevator"
WU_M = 3.048


def node_chain(gltf):
    """Each glTF node's name, its parent's index and its translation in CE wu
    (a staged model's nodes are metres, Y up)."""
    nodes = gltf["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    out = {}
    for i, n in enumerate(nodes):
        t = n.get("translation", [0, 0, 0])
        out[n.get("name", "")] = {"index": i, "parent": parent.get(i),
                                  "t": [t[0] / WU_M, -t[2] / WU_M, t[1] / WU_M], "r": n.get("rotation", [0, 0, 0, 1])}
    return out


def rest_offset(chain, name):
    """A node's rest position in the object, summed up its parents. Refuses a
    rotated chain, which `slide_resource` has no way to carry yet."""
    by_index = {v["index"]: v for v in chain.values()}
    n = chain.get(name)
    if n is None:
        # A one-node collision model can name a node the render model lacks
        # (YOY's panichill shield): it is the object's root.
        return [0.0, 0.0, 0.0]
    t = [0.0, 0.0, 0.0]
    while n is not None:
        if abs(abs(n["r"][3]) - 1) > 1e-4:
            raise SystemExit(f"node {name!r} is rotated at rest ({n['r']}); not supported yet")
        t = [a + b for a, b in zip(t, n["t"])]
        n = by_index.get(n["parent"])
    return t


def slide_resource(donor, static_t, offsets):
    """The donor animation graph with its one member rewritten: node 1 sits at
    `static_t`, and the root's translation runs through `offsets`. Segments as
    `h2_machines.turn_resource` lists them; the donor's static pose (two
    rotations, node 1's translation, two scales) and its flags stay."""
    b = bytearray(donor)
    n = len(offsets)
    j = b.find(b"lbgt", b.find(b"crgt"))
    e = j + 20
    old_sizes = struct.unpack_from("<17i", b, e + 12)
    old_size = struct.unpack_from("<I", b, e + 80)[0]
    d = b.find(b"adgt", j)
    blob_at = d + 12
    segs, at = {}, blob_at
    for i, s in enumerate(old_sizes):
        if s:
            segs[i] = bytes(b[at:at + s])
        at += s
    static = bytearray(segs[0])
    struct.pack_into("<3f", static, 0x30, *static_t)
    floats = b"".join(struct.pack("<3f", *t) for t in offsets)
    anim = struct.pack("<4B2f5I", 3, 0, 1, 0, 0.0, 1.0, 0x20, 0x20 + 12 * n, 8 * n, 12 * n, 4 * n) + floats
    unc = struct.pack("<4B2f5I", 2, 0, 1, 0, 0.0, 0.0, 0x20, 0x20 + 12 * n, 16 * n, 12 * n, 4 * n) + floats
    q = (0.0, 0.0, 0.0, 1.0)
    osp = struct.pack("<HH", 2, n)
    osp += b"".join(struct.pack("<4f3ff", *q, *t, 1.0) for t in offsets)
    osp += b"".join(struct.pack("<4f3ff", *q, *(a + c for a, c in zip(t, static_t)), 1.0) for t in offsets)
    seg = dict(segs)
    seg.update({0: bytes(static), 1: anim, 6: unc, 13: osp})
    sizes = [len(seg.get(i, b"")) for i in range(17)]
    blob = b"".join(seg[i] for i in sorted(seg))
    delta = len(blob) - old_size
    struct.pack_into("<h", b, e + 8, n)
    struct.pack_into("<17i", b, e + 12, *sizes)
    struct.pack_into("<I", b, e + 80, len(blob))
    end = blob_at + old_size
    for magic in (b"tadb", b"lbgt", b"tsgt", b"crgt", b"adgt"):
        p = -1
        while True:
            p = b.find(magic, p + 1)
            if p < 0 or p > blob_at:
                break
            v, s = struct.unpack_from("<II", b, p + 4)
            if p + 12 + s == end:
                struct.pack_into("<I", b, p + 8, s + delta)
                if magic == b"tsgt" and v == s:
                    struct.pack_into("<I", b, p + 4, s + delta)
    total = struct.unpack_from("<I", b, 0x48)[0]
    struct.pack_into("<I", b, 0x48, total + delta)
    b[blob_at:end] = blob
    return bytes(b)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def turn_of(frames, k):
    """A node's frames as a turn about one axis: (axis, degrees per frame), or
    None when it holds still. Refuses a node that turns about more than one
    axis, which `turn_resource` has no way to carry."""
    q0 = frames[0][k]["q"]
    inverse = (-q0[0], -q0[1], -q0[2], q0[3])
    rel = [qmul(f[k]["q"], inverse) for f in frames]
    axis, angles, last = None, [], 0.0
    for q in rel:
        s = math.sqrt(sum(c * c for c in q[:3]))
        a = 2 * math.degrees(math.atan2(s, q[3]))
        if s > 1e-4:
            v = [c / s for c in q[:3]]
            if axis is None:
                axis = v
            d = sum(x * y for x, y in zip(axis, v))
            if abs(abs(d) - 1) > 1e-2:
                raise SystemExit("a device turning about more than one axis is not supported")
            a = a if d > 0 else -a
        # A loop passes 180 degrees, where the angle's sign flips.
        while a - last > 180:
            a -= 360
        while a - last < -180:
            a += 360
        angles.append(a)
        last = a
    return (axis, angles) if axis else None


def part_motion(frames, k):
    """What a node does: ("turn", axis, degrees) or ("slide", offsets)."""
    turn = turn_of(frames, k)
    if turn:
        if max(math.dist(f[k]["t"], frames[0][k]["t"]) for f in frames) > 1e-3:
            raise SystemExit("a device that turns and slides at once is not supported")
        return ("turn", *turn)
    t0 = frames[0][k]["t"]
    offsets = [[a - b for a, b in zip(f[k]["t"], t0)] for f in frames]
    zs = [t[2] for t in offsets]
    lo, hi = min(zs), max(zs)
    if hi - lo > 0.5:
        for t in offsets:
            t[2] -= SINK * (hi - t[2]) / (hi - lo)
    return ("slide", offsets)


def moving_node(frames):
    """The node index of an overlay that moves most, and what it does."""
    def travel(k):
        return max(math.dist(f[k]["t"], frames[0][k]["t"]) + sum(abs(a - b) for a, b in zip(f[k]["q"], frames[0][k]["q"]))
                   for f in frames)
    k = max(range(len(frames[0])), key=travel)
    return k, part_motion(frames, k)


def moving_parts(frames, bsps, chain):
    """Each node that moves and has collision: (node index, its BSP)."""
    out = []
    for bsp in bsps:
        n = chain.get(bsp["node"])
        if n is None or n["index"] >= len(frames[0]):
            continue
        k = n["index"]
        if any(f[k]["t"] != frames[0][k]["t"] or f[k]["q"] != frames[0][k]["q"] for f in frames):
            out.append((k, bsp))
    return out


class Builder:
    """Writes one machine family at a time into `out`."""

    def __init__(self, a, code, donor, work):
        self.a, self.code, self.donor, self.work, self.count = a, code, donor, work, 0

    def run(self, *args):
        return subprocess.run([self.a.mjolnir, *args], check=True, capture_output=True, text=True).stdout

    def family(self, asset, bsp, static_t, motion, seconds, radius, kind, door=None):
        k, a, run = self.count, self.a, self.run
        self.count += 1
        base = os.path.join(self.work, f"{k}")
        ce_scenario.write_bsp(bsp, base)
        tag = f"objects\\mjolnir\\{self.code.lower()}\\{leaf(asset)}_{k}"
        name = lambda g: f"pakchunk986-MJOLNIRMACH-{self.code}-{k}{g}"
        payload = base + ".jmad"
        if motion[0] == "turn":
            frames, travel = len(motion[2]), [0.0, 0.0, 0.0]
            open(payload, "wb").write(turn_resource(self.donor, motion[1], motion[2]))
        else:
            frames, travel = len(motion[1]), motion[1][-1]
            open(payload, "wb").write(slide_resource(self.donor, static_t, motion[1]))
        run("new-tag", "--group", "model_animation_graph", "--from", DONOR, "--to", tag, "--payload", payload,
            "--set", f"definitions.animations[0].shared animation data[0].frame count={frames}",
            "--out-dir", a.out, "--name", name("J"))
        coll = base + ".coll"
        run("level", "machine-collision", base + ".bsp.json", "--donor", DONOR, "--out", coll)
        run("new-tag", "--group", "collision_model", "--from", DONOR, "--to", tag, "--payload", coll,
            "--out-dir", a.out, "--name", name("C"))
        tris = [c + s for t in ce_scenario.triangles(bsp) for p in t for c, s in zip(p, static_t)]
        pargs = physics_args(boxes(tris))
        sets = base + ".sets"
        open(sets, "w", encoding="utf-8").write("\n".join(v for f, v in zip(pargs[::2], pargs[1::2]) if f == "--set"))
        resizes = [x for f, v in zip(pargs[::2], pargs[1::2]) if f == "--resize" for x in (f, v)]
        run("new-tag", "--group", "physics_model", "--from", DONOR, "--to", tag, *resizes, "--set-file", sets,
            "--out-dir", a.out, "--name", name("P"))
        run("new-tag", "--group", "model", "--from", DONOR, "--to", tag,
            "--set", f"animation=jmad:{tag}", "--set", f"physics_model=phmo:{tag}",
            "--set", f"collision model=coll:{tag}", "--out-dir", a.out, "--name", name("H"))
        extra = []
        if door:
            extra = ["--set", "type=0", "--set", f"door open time={door['open_time']}",
                     "--set", f"device.automatic activation radius={door['radius']}"]
        run("new-tag", "--group", "device_machine", "--from", DONOR, "--to", tag,
            "--set", f"device.position transition time={1.0 / seconds:.6f}",
            "--set", f"device.object.bounding radius={radius}",
            "--set", f"device.object.model=hlmt:{tag}", *extra, "--out-dir", a.out, "--name", name("M"))
        print(f"  machine {k}: {asset} -> {tag}: {kind}, {frames} frames over {seconds:g} s, "
              f"{bsp['arrays'][5][0]} surfaces on {bsp['node']!r}, travel {[round(c, 3) for c in travel]}")
        return {"tag": tag, "class": DONOR_CLASS, "frames": frames, "kind": kind, "travel": travel, "seconds": seconds}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("staging")
    ap.add_argument("code")
    ap.add_argument("out")
    ap.add_argument("--names", nargs="*", default=[], help="the machines' object names")
    ap.add_argument("--report", help="ce_translate.py's report: its machines and promoted scenery")
    ap.add_argument("--auto", action="store_true", help="also every automatic door no script names")
    ap.add_argument("--mjolnir", default=os.environ.get("MJOLNIR", "target/release/mjolnir"))
    a = ap.parse_args()
    code = a.code.upper()
    names = set(a.names)
    if a.report:
        names |= set(json.load(open(a.report, encoding="utf-8"))["carry"].get("machines", []))
    scenario = ce_scenario.Scenario(a.map, os.path.join(a.staging, "tags.json"))
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    entries = {e["asset"]: e for e in placement["entries"] if e.get("kind") == "machine"}
    wanted, doors = {}, {}
    for m in scenario.machines():
        if m["name"] in names:
            wanted.setdefault(m["tag"], m["datum"])
    if a.auto:
        for m in scenario.machines():
            dev = entries.get(m["tag"], {}).get("device") or {}
            if m["tag"] not in wanted and dev.get("machine_type") == "door" and dev.get("animation") \
                    and not m["flags"] & 1:
                doors.setdefault(m["tag"], m["datum"])
    promoted = {e["asset"]: e for e in entries.values() if e.get("promoted")}
    objects = scenario.named_objects()
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="cemach_")
    run = lambda *args: subprocess.run([a.mjolnir, *args], check=True, capture_output=True, text=True).stdout
    run("extract", "--out", work, "--group", "model_animation_graph", "--filter", DONOR)
    donor_path = next(os.path.join(dp, f) for dp, _, fs in os.walk(work) for f in fs
                      if f.endswith(".model_animation_graph"))
    b = Builder(a, code, open(donor_path, "rb").read(), work)
    manifest = {}
    for asset, datum in sorted(wanted.items()):
        e = entries[asset]
        tag_info = scenario.device_tag(datum)
        bsps = [x for x in tag_info["bsps"] if x["arrays"][5][0]]
        if len(bsps) != 1:
            raise SystemExit(f"{asset}: {len(bsps)} collision BSPs; one is supported for a scripted machine")
        bsp = bsps[0]
        chain = node_chain(json.load(open(os.path.join(a.staging, e["model"]), encoding="utf-8")))
        static_t = rest_offset(chain, bsp["node"])
        animation = (e.get("device") or {}).get("animation")
        if animation:
            node, motion = moving_node(animation["frames"])
            kind, seconds = motion[0], tag_info["position_transition"]
        else:
            node, motion = None, ("slide", [[0.0, 0.0, -PARK], [0.0, 0.0, 0.0]])
            kind, seconds = "shield", max(tag_info["position_transition"], 0.1)
        if motion[0] == "turn":
            # A turn is about the node: the machine stands there.
            built = b.family(asset, bsp, [0.0, 0.0, 0.0], motion, seconds, tag_info["bounding_radius"], kind)
            manifest[asset] = {"parts": [{**built, "node": node, "offset": static_t}]}
            continue
        manifest[asset] = {**b.family(asset, bsp, static_t, motion, seconds, tag_info["bounding_radius"], kind), "node": node}
    for asset, e in sorted(promoted.items()):
        o = objects[e["promoted"]]
        tag_info = scenario.scenery_tag(o["index"])
        bsps = [x for x in tag_info["bsps"] if x["arrays"][5][0]]
        if len(bsps) != 1:
            raise SystemExit(f"{asset}: {len(bsps)} collision BSPs; one is supported for scripted scenery")
        chain = node_chain(json.load(open(os.path.join(a.staging, e["model"]), encoding="utf-8")))
        manifest[asset] = {**b.family(asset, bsps[0], rest_offset(chain, bsps[0]["node"]),
                                      ("slide", [[0.0, 0.0, -PARK], [0.0, 0.0, 0.0]]), 0.1,
                                      tag_info["bounding_radius"], "shield"), "node": None}
    for asset, datum in sorted(doors.items()):
        e = entries[asset]
        dev = e["device"]
        tag_info = scenario.device_tag(datum)
        frames = dev["animation"]["frames"]
        chain = node_chain(json.load(open(os.path.join(a.staging, e["model"]), encoding="utf-8")))
        parts = moving_parts(frames, [x for x in tag_info["bsps"] if x["arrays"][5][0]], chain)
        if not parts:
            print(f"  {asset}: no moving part with collision, left as it is")
            continue
        try:
            for _, bsp in parts:
                rest_offset(chain, bsp["node"])
        except SystemExit as why:
            print(f"  {asset}: left as it is: {why}")
            continue
        door = {"open_time": dev["door_open_time"], "radius": max(tag_info["bounding_radius"], 1.5)}
        built = []
        for node, bsp in parts:
            motion = part_motion(frames, node)
            built.append({**b.family(asset, bsp, [0.0, 0.0, 0.0], motion, dev["position_transition"],
                                     tag_info["bounding_radius"], "door", door),
                          "node": node, "offset": rest_offset(chain, bsp["node"])})
        manifest[asset] = {"parts": built}
    # The map's buttons: B40's panel, which draws itself, with the plain prompt.
    button = f"objects\\mjolnir\\{code.lower()}\\button"
    run("new-tag", "--group", "device_control", "--from", CONTROL_DONOR, "--to", button,
        "--set", "action string=activate_device", "--out-dir", a.out,
        "--name", f"pakchunk986-MJOLNIRMACH-{code}-BK")
    manifest["_control"] = {"tag": button}
    json.dump(manifest, open(os.path.join(a.out, "machines.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(manifest) - 1} machine tag(s), {b.count} famil(ies) -> {os.path.join(a.out, 'machines.json')}")


if __name__ == "__main__":
    main()
