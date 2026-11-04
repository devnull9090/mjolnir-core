#!/usr/bin/env python3
"""Build the simulation's own machines for a CE map's scripted devices, so a
gate's collision moves with it and a script can drive it.

    ce_machines.py <map> <staging> <CODE> <out dir> --names <machine name>... [--mjolnir PATH]

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

Writes machines.json, keyed by tag path: tag, class, frames, kind.
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
from h2_machines import DONOR, DONOR_CLASS, boxes, leaf, physics_args  # noqa: E402

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


def moving_node(frames):
    """The node index of an overlay that moves most, and its frames' offsets."""
    travel = [max(math.dist(f[k]["t"], frames[0][k]["t"]) for f in frames) for k in range(len(frames[0]))]
    k = max(range(len(travel)), key=travel.__getitem__)
    for f in frames:
        if any(abs(c) > 1e-4 for c in f[k]["q"][:3]):
            raise SystemExit("a turning device is not supported yet")
    t0 = frames[0][k]["t"]
    offsets = [[a - b for a, b in zip(f[k]["t"], t0)] for f in frames]
    zs = [t[2] for t in offsets]
    lo, hi = min(zs), max(zs)
    if hi - lo > 0.5:
        for t in offsets:
            t[2] -= SINK * (hi - t[2]) / (hi - lo)
    return k, offsets


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("staging")
    ap.add_argument("code")
    ap.add_argument("out")
    ap.add_argument("--names", nargs="+", required=True, help="the machines' object names")
    ap.add_argument("--mjolnir", default=os.environ.get("MJOLNIR", "target/release/mjolnir"))
    a = ap.parse_args()
    code = a.code.upper()
    scenario = ce_scenario.Scenario(a.map, os.path.join(a.staging, "tags.json"))
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    entries = {e["asset"]: e for e in placement["entries"] if e.get("kind") == "machine"}
    wanted = {}
    for m in scenario.machines():
        if m["name"] in a.names:
            wanted.setdefault(m["tag"], m["datum"])
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="cemach_")
    run = lambda *args: subprocess.run([a.mjolnir, *args], check=True, capture_output=True, text=True).stdout
    run("extract", "--out", work, "--group", "model_animation_graph", "--filter", DONOR)
    donor_path = next(os.path.join(dp, f) for dp, _, fs in os.walk(work) for f in fs
                      if f.endswith(".model_animation_graph"))
    donor = open(donor_path, "rb").read()
    manifest = {}
    for k, (asset, datum) in enumerate(sorted(wanted.items())):
        e = entries[asset]
        tag_info = scenario.device_tag(datum)
        bsps = [b for b in tag_info["bsps"] if b["arrays"][5][0]]
        if len(bsps) != 1:
            raise SystemExit(f"{asset}: {len(bsps)} collision BSPs; one is supported")
        bsp = bsps[0]
        model = json.load(open(os.path.join(a.staging, e["model"]), encoding="utf-8"))
        chain = node_chain(model)
        static_t = rest_offset(chain, bsp["node"])
        animation = (e.get("device") or {}).get("animation")
        if animation:
            node, offsets = moving_node(animation["frames"])
            kind, seconds = "slide", tag_info["position_transition"]
        else:
            node, offsets = None, [[0.0, 0.0, -PARK], [0.0, 0.0, 0.0]]
            kind, seconds = "shield", max(tag_info["position_transition"], 0.1)
        base = os.path.join(work, f"{k}")
        ce_scenario.write_bsp(bsp, base)
        tag = f"objects\\mjolnir\\{code.lower()}\\{leaf(asset)}"
        name = lambda g: f"pakchunk986-MJOLNIRMACH-{code}-{k}{g}"
        payload = base + ".jmad"
        open(payload, "wb").write(slide_resource(donor, static_t, offsets))
        run("new-tag", "--group", "model_animation_graph", "--from", DONOR, "--to", tag, "--payload", payload,
            "--set", f"definitions.animations[0].shared animation data[0].frame count={len(offsets)}",
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
        run("new-tag", "--group", "device_machine", "--from", DONOR, "--to", tag,
            "--set", f"device.position transition time={1.0 / seconds:.6f}",
            "--set", f"device.object.bounding radius={tag_info['bounding_radius']}",
            "--set", f"device.object.model=hlmt:{tag}", "--out-dir", a.out, "--name", name("M"))
        travel = offsets[-1]
        manifest[asset] = {"tag": tag, "class": DONOR_CLASS, "frames": len(offsets), "kind": kind, "node": node,
                           "travel": travel, "seconds": seconds}
        print(f"  machine {k}: {asset} -> {tag}: {kind}, {len(offsets)} frames over {seconds:g} s, "
              f"{bsp['arrays'][5][0]} surfaces on {bsp['node']!r} at {[round(c, 3) for c in static_t]}, "
              f"travel {[round(c, 3) for c in travel]}")
    # The map's buttons: B40's panel, which draws itself, with the plain prompt.
    button = f"objects\\mjolnir\\{code.lower()}\\button"
    run("new-tag", "--group", "device_control", "--from", CONTROL_DONOR, "--to", button,
        "--set", "action string=activate_device", "--out-dir", a.out,
        "--name", f"pakchunk986-MJOLNIRMACH-{code}-BK")
    manifest["_control"] = {"tag": button}
    json.dump(manifest, open(os.path.join(a.out, "machines.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(manifest) - 1} machine(s) -> {os.path.join(a.out, 'machines.json')}")


if __name__ == "__main__":
    main()
