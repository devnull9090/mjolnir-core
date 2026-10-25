#!/usr/bin/env python3
"""Build the simulation's own machines for a Halo 2 map's turning parts
(Ascension's antennas, Zanzibar's wheels, Foundation's fans), so their
collision turns with them.

    h2_machines.py <staging> <CODE> <out dir> [--mjolnir PATH]

The Blam simulation does all collision and never reads Unreal geometry, and
its structure BSP cannot move: collision baked at rest stood where an arm
only sometimes is, and players walked through the arm everywhere else. A
device machine moves its collision with its animation, so each turning part
becomes one, cloned from B40's elevator (machine, model, collision model,
physics model and animation graph, whose nodes and Havok layouts agree):

- animation graph: the elevator's, its one animation rewritten to turn the
  root node by the part's keys about the part's axis, every frame stored
  with codec 3 (the format the shipped turning props use) beside the
  static pose, the node flags, the uncompressed copy and the object-space
  frames the resource carries (`turn_resource`);
- collision model: the part's own Halo 2 collision BSP (staged by
  `mjolnir cache stage` as `collision/<part>.bsp.json`), packed with its
  Havok MOPP by `mjolnir level machine-collision`. Bipeds meet a machine's
  collision model, not its physics model's shapes;
- physics model: boxes over the part's collision triangles (`boxes`), for
  what moves through Havok (vehicles, grenades); the elevator's lift
  phantom goes with it;
- machine: a gear running its position from 0 to 1 at 1 / period, as Halo
  2's does. The engine stores the "position transition time" as that rate.

Each tag is a container of its own, `pakchunk986-MJOLNIRMACH-<CODE>-<k><g>`,
under `objects\\mjolnir\\<code>\\`. `machines.json` maps each part's tag path
to its machine's for tools/level/gen_ce_level.py (--machines), which places
the machines and has the level loader ride each part's mesh on its
machine's Unreal actor (`motion.follow`).
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile

DONOR = "elevator_a/elevator_a_b40"
# The Unreal class the donor machine binds, which the level loader finds.
DONOR_CLASS = "BP_ElevatorAB40_C"


def quat(axis, deg):
    h = math.radians(deg) / 2
    s = math.sin(h)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(h))


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qrot(q, v):
    x, y, z, w = q
    uv = (y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0])
    uuv = (y * uv[2] - z * uv[1], z * uv[0] - x * uv[2], x * uv[1] - y * uv[0])
    return tuple(v[k] + 2 * (w * uv[k] + uuv[k]) for k in range(3))


# Seconds between stored frames.
FRAME_STEP = 0.1


def frames_of(turn):
    """The turn as evenly spaced frames, one every FRAME_STEP, each the
    angle the keys give at that time. This engine shows a gear at frame
    position x N, held at the last frame (Halo 2 used N - 1): frame f is the
    angle at f / N of the period, and the hold at the end of each turn is
    one step. Five frames of Zanzibar's wheel made it turn a whole circle
    in 24 s of its 30 and stop for 6."""
    keys = turn["keys"]
    period = turn["period"]
    n = max(2, min(1000, int(math.ceil(period / FRAME_STEP))))

    def at(t):
        for (t0, a0), (t1, a1) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                return a0 + (a1 - a0) * (t - t0) / (t1 - t0) if t1 > t0 else a1
        return keys[-1][1]
    return [at(period * f / n) for f in range(n)]


def turn_resource(donor, axis, angles):
    """The donor animation graph (two nodes, root and platform, one
    animation) with its one resource member rewritten: the root turns by
    `angles` (degrees about `axis`, frame f at f / N of the turn).
    The member's segments, in order: static pose (codec 1), animated data
    (codec 3), static and animated node flags (rotation, translation,
    scale), per-frame root movement, the animated data uncompressed (codec
    2), object-space frames (node-major) and the object-space node mask;
    their sizes, the member's data size and every section that encloses
    the data grow with it."""
    b = bytearray(donor)
    n = len(angles)
    j = b.find(b"lbgt", b.find(b"crgt"))
    e = j + 20
    old_sizes = struct.unpack_from("<17i", b, e + 12)
    old_size = struct.unpack_from("<I", b, e + 80)[0]
    d = b.find(b"adgt", j)
    blob_at = d + 12
    f0 = bytes(b[blob_at:blob_at + old_sizes[0]])
    rot1 = struct.unpack_from("<4h", f0, 0x28)
    trans1 = struct.unpack_from("<3f", f0, 0x30)
    qs = [quat(axis, a) for a in angles]

    def i16q(q):
        norm = math.sqrt(sum(c * c for c in q))
        return tuple(int(round(c / norm * 32767)) for c in q)

    static = struct.pack("<4B2f5I", 1, 1, 2, 2, 0.0, 0.0, 0x28, 0x28 + 24, 0, 0, 0)
    static += struct.pack("<4h", *rot1) + struct.pack("<3f", 0.0, 0.0, 0.0) + struct.pack("<3f", *trans1)
    static += struct.pack("<2f", 1.0, 1.0)
    anim = struct.pack("<4B2f5I", 3, 1, 0, 0, 0.0, 1.0, 0x20 + 8 * n, 0x20 + 8 * n, 8 * n, 12 * n, 4 * n)
    anim += b"".join(struct.pack("<4h", *i16q(q)) for q in qs)
    unc = struct.pack("<4B2f5I", 2, 1, 0, 0, 0.0, 0.0, 0x20 + 16 * n, 0x20 + 16 * n, 16 * n, 12 * n, 4 * n)
    unc += b"".join(struct.pack("<4f", *q) for q in qs)
    r1 = tuple(c / 32767 for c in rot1)
    osp = struct.pack("<HH", 2, n)
    osp += b"".join(struct.pack("<4f3ff", *q, 0.0, 0.0, 0.0, 1.0) for q in qs)
    osp += b"".join(struct.pack("<4f3ff", *qmul(q, r1), *qrot(q, trans1), 1.0) for q in qs)
    seg = {0: static, 1: anim, 2: struct.pack("<3I", 0b10, 0b11, 0b11), 3: struct.pack("<3I", 0b01, 0, 0),
           5: b"\0" * (12 * n), 6: unc, 13: osp, 15: struct.pack("<I", 0b11) + b"\0" * 28}
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


def boxes(triangles, cell=0.25, limit=200):
    """Boxes over a triangle mesh (world units): the cells of a grid the
    triangles pass through, merged greedily along x, then y, then z. The
    grid coarsens until there are at most `limit` boxes."""
    tris = [triangles[i:i + 9] for i in range(0, len(triangles), 9)]
    pts = [(t[k], t[k + 1], t[k + 2]) for t in tris for k in (0, 3, 6)]
    lo = [min(p[k] for p in pts) for k in range(3)]
    while True:
        cells = set()
        for t in tris:
            a, b, c = (t[0:3], t[3:6], t[6:9])
            span = max(max(abs(a[k] - b[k]), abs(a[k] - c[k]), abs(b[k] - c[k])) for k in range(3))
            steps = max(1, int(math.ceil(span / (cell * 0.5))))
            for i in range(steps + 1):
                for j in range(steps + 1 - i):
                    u, v = i / steps, j / steps
                    p = [a[k] + u * (b[k] - a[k]) + v * (c[k] - a[k]) for k in range(3)]
                    cells.add(tuple(int(math.floor((p[k] - lo[k]) / cell)) for k in range(3)))
        out = []
        left = set(cells)
        for c in sorted(cells):
            if c not in left:
                continue
            x1 = c[0]
            while (x1 + 1, c[1], c[2]) in left:
                x1 += 1
            y1 = c[1]
            while all((x, y1 + 1, c[2]) in left for x in range(c[0], x1 + 1)):
                y1 += 1
            z1 = c[2]
            while all((x, y, z1 + 1) in left for x in range(c[0], x1 + 1) for y in range(c[1], y1 + 1)):
                z1 += 1
            for x in range(c[0], x1 + 1):
                for y in range(c[1], y1 + 1):
                    for z in range(c[2], z1 + 1):
                        left.discard((x, y, z))
            mn = [lo[0] + c[0] * cell, lo[1] + c[1] * cell, lo[2] + c[2] * cell]
            mx = [lo[0] + (x1 + 1) * cell, lo[1] + (y1 + 1) * cell, lo[2] + (z1 + 1) * cell]
            out.append({"center": [(mn[k] + mx[k]) / 2 for k in range(3)],
                        "half": [(mx[k] - mn[k]) / 2 for k in range(3)]})
        if len(out) <= limit:
            return out
        cell *= 1.5


def physics_args(box_list):
    """new-tag arguments that make the donor physics model the boxes, in
    one list both its rigid bodies use (the donor's platform mopp and lift
    phantom go unused)."""
    n = len(box_list)
    args = ["--resize", f"boxes={n}", "--resize", f"list shapes={n}"]
    lo = [min(b["center"][k] - b["half"][k] for b in box_list) for k in range(3)]
    hi = [max(b["center"][k] + b["half"][k] for b in box_list) for k in range(3)]
    for k, b in enumerate(box_list):
        (cx, cy, cz), (hx, hy, hz) = b["center"], b["half"]
        args += ["--set", f"boxes[{k}].base.material=#0",
                 "--set", f"boxes[{k}].base.volume={8 * hx * hy * hz:.6f}",
                 "--set", f"boxes[{k}].half extents=({hx:.5f}, {hy:.5f}, {hz:.5f})",
                 "--set", f"boxes[{k}].havok w half extents={hx:.5f}",
                 "--set", f"boxes[{k}].convex transform shape.translation=({cx:.5f}, {cy:.5f}, {cz:.5f})",
                 "--set", f"list shapes[{k}].shape reference.shape type=box",
                 "--set", f"list shapes[{k}].shape reference.shape=#{k}",
                 "--set", f"list shapes[{k}].num child shapes={n}"]
    radius = max(math.dist((0, 0, 0), (x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2]))
    args += ["--set", f"lists[0].child shapes size={n}",
             "--set", f"lists[0].child shapes capacity={-2 ** 31 + n}",
             "--set", "lists[0].aabb half extents=({:.5f}, {:.5f}, {:.5f})".format(*[(hi[k] - lo[k]) / 2 for k in range(3)]),
             "--set", "lists[0].aabb center=({:.5f}, {:.5f}, {:.5f})".format(*[(hi[k] + lo[k]) / 2 for k in range(3)])]
    for r in (0, 1):
        args += ["--set", f"rigid bodies[{r}].shape reference.shape type=list",
                 "--set", f"rigid bodies[{r}].shape reference.shape=#0",
                 "--set", f"rigid bodies[{r}].bounding sphere radius={radius:.4f}"]
    return args


def leaf(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower().replace(" ", "_")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("code")
    ap.add_argument("out")
    ap.add_argument("--mjolnir", default=os.environ.get("MJOLNIR", "target/release/mjolnir"))
    a = ap.parse_args()
    code = a.code.upper()
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    parts = {}
    for e in placement["entries"]:
        m = e.get("h2_motion")
        if m and m.get("bsp") and e.get("collision") and e["asset"] not in parts:
            parts[e["asset"]] = e
    os.makedirs(a.out, exist_ok=True)
    manifest = {}
    if parts:
        work = tempfile.mkdtemp(prefix="h2mach_")
        run = lambda *args: subprocess.run([a.mjolnir, *args], check=True, capture_output=True, text=True).stdout
        run("extract", "--out", work, "--group", "model_animation_graph", "--filter", DONOR)
        donor_jmad = next(os.path.join(dp, f) for dp, _, fs in os.walk(work) for f in fs
                          if f.endswith(".model_animation_graph"))
        donor = open(donor_jmad, "rb").read()
        for k, (asset, e) in enumerate(sorted(parts.items())):
            m = e["h2_motion"]
            tag = f"objects\\mjolnir\\{code.lower()}\\{leaf(asset)}"
            name = lambda g: f"pakchunk986-MJOLNIRMACH-{code}-{k}{g}"
            axis = m["axis"] if isinstance(m.get("axis"), list) else [0.0, 0.0, 1.0]
            angles = frames_of(m)
            payload = os.path.join(work, f"{k}.jmad")
            open(payload, "wb").write(turn_resource(donor, axis, angles))
            run("new-tag", "--group", "model_animation_graph", "--from", DONOR, "--to", tag, "--payload", payload,
                "--set", f"definitions.animations[0].shared animation data[0].frame count={len(angles)}",
                "--out-dir", a.out, "--name", name("J"))
            coll = os.path.join(work, f"{k}.coll")
            run("level", "machine-collision", os.path.join(a.staging, m["bsp"]), "--donor", DONOR, "--out", coll)
            run("new-tag", "--group", "collision_model", "--from", DONOR, "--to", tag, "--payload", coll,
                "--out-dir", a.out, "--name", name("C"))
            tris = json.load(open(os.path.join(a.staging, e["collision"]), encoding="utf-8"))["triangles"]
            pargs = physics_args(boxes(tris))
            sets = os.path.join(work, f"{k}.sets")
            # Hundreds of boxes outgrow a command line (Zanzibar's wheel).
            open(sets, "w", encoding="utf-8").write("\n".join(v for f, v in zip(pargs[::2], pargs[1::2]) if f == "--set"))
            resizes = [x for f, v in zip(pargs[::2], pargs[1::2]) if f == "--resize" for x in (f, v)]
            run("new-tag", "--group", "physics_model", "--from", DONOR, "--to", tag, *resizes, "--set-file", sets,
                "--out-dir", a.out, "--name", name("P"))
            run("new-tag", "--group", "model", "--from", DONOR, "--to", tag,
                "--set", f"animation=jmad:{tag}", "--set", f"physics_model=phmo:{tag}",
                "--set", f"collision model=coll:{tag}", "--out-dir", a.out, "--name", name("H"))
            run("new-tag", "--group", "device_machine", "--from", DONOR, "--to", tag,
                "--set", "type=gear", "--set", f"device.position transition time={1.0 / m['period']:.6f}",
                "--set", f"device.object.model=hlmt:{tag}", "--out-dir", a.out, "--name", name("M"))
            manifest[asset] = {"tag": tag, "class": DONOR_CLASS, "frames": len(angles)}
            print(f"  machine {k}: {asset} -> {tag} ({len(angles)} frames over {m['period']:g} s)")
    json.dump(manifest, open(os.path.join(a.out, "machines.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(manifest)} machine(s) -> {os.path.join(a.out, 'machines.json')}")


if __name__ == "__main__":
    main()
