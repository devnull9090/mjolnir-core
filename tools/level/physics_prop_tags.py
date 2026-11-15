#!/usr/bin/env python3
"""Make the crate tags a converted map's physics props ride: one a prop type,
cloned from crate_space_a with a physics shape of the prop's size.

    python tools/level/physics_prop_tags.py --paks <Paks> --out <dir> --tag <objects\\...\\leaf>
        --half <hx>,<hy> --height <h> --blueprint </Game/.../BP_Thing> [--mass-scale 0.2] [--name <container base>]

Only crate_space_a, of the game's crates, has a multiplayer object block,
which a Megalo game needs to keep a crate at all (the others are deleted as
the match starts). Each prop type therefore gets three new tags (mjolnir
new-tag), chained by reference:

  physics_model  crate_space_a's convex polyhedron scaled per axis to the
                 prop's box (half widths hx, hy and height h, world units,
                 its base at the origin as crate_space_a's is), its planes
                 renormalized, with `mass scale` so a shot or a melee moves
                 it (crate_space_a's mass barely moved under fire)
  model          crate_space_a's, pointing at that physics model
  crate          crate_space_a's, pointing at that model, its abandonment
                 time raised to the maximum (at the shipped 60 s an untouched
                 crate that had settled off its spot was deleted a minute in
                 and never came back), bound to `--blueprint`: a crate actor
                 class of the prop type's own, so the loader can tell which
                 prop to draw on it (level `dress`, props.lua)

The collision model (what bullets hit) stays crate_space_a's. Writes three
containers into --out, for `mjolnir dev install` or a map pack.
"""
import argparse
import math
import os
import re
import subprocess
import sys

DONOR = "covenant/crate_space_a/crate_space_a"
# crate_space_a's polyhedron: aabb half extents (0.222392, 0.24796, 0.352695)
# about (0.002874, 0.002103, 0.369094): it stands 0.7218 world units tall from
# its origin.
DONOR_HALF = (0.222392, 0.24796)
DONOR_TOP = 0.369094 + 0.352695
# crate_space_a's own actor class. A clone bound to it again (`--asset-reference`
# naming the donor's own Blueprint) imported it twice and the binding did not
# resolve: no coil spawned at all (Zanzibar, 2026-11-15). The donor's own
# reference is kept instead.
DONOR_BLUEPRINT = "/Game/_Prototypes/SynchronizationTestContent/Assets/props/crate_space_a/BP_CrateSpaceACrateActor"


def run(cli, *args):
    r = subprocess.run([cli, *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"mjolnir {' '.join(args[:6])} failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def convex_radius(dump):
    """The polyhedron's Havok convex radius: a shell that pads the shape on
    every side (crate_space_a: 0.0164 world units)."""
    block = None
    for line in dump.splitlines():
        m = re.match(r"^  (\S.*?)  \[\d+ element", line)
        if m:
            block = m.group(1).strip()
            continue
        m = re.match(r"^\s+radius = (-?[\d.]+)", line)
        if m and block == "polyhedra":
            return float(m.group(1))
    return 0.0


def scaled_shape(dump, k, z0=0.0):
    """`path=value` lines scaling the polyhedron by k = (kx, ky, kz), z about
    height z0 (its base: crate_space_a's polyhedron starts one convex radius
    up, so its shell meets the ground at the origin)."""
    kx, ky, kz = k
    vec = lambda s: [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", s)]
    fmt = lambda v: "(" + ", ".join(f"{x:.6f}" for x in v) + ")"
    off = (0.0, 0.0, z0)
    move = lambda v, axis: off[axis] + (v - off[axis]) * k[axis]
    sets, planes = [], {}
    block = index = None
    for line in dump.splitlines():
        m = re.match(r"^  (\S.*?)  \[\d+ element", line)
        if m:
            block = m.group(1).strip()
            continue
        m = re.match(r"^    \[(\d+)\]", line)
        if m:
            index = int(m.group(1))
            continue
        m = re.match(r"^\s+(.+?) = (.+?)    \[", line)
        if not m or block is None:
            continue
        field, value = m.group(1).strip(), m.group(2).strip()
        path = f"{block}[{index}].{field}"
        if block == "polyhedron four vectors":
            axis = {"x": 0, "y": 1, "z": 2}[field[-1]]
            if field.startswith("four vectors"):
                sets.append(f"{path}={fmt([move(v, axis) for v in vec(value)])}")
            elif field.startswith("havok w four vectors"):
                sets.append(f"{path}={move(vec(value)[0], axis):.6f}")
        elif block == "polyhedron plane equations":
            planes.setdefault(index, {})[field] = vec(value)
        elif block == "polyhedra" and field == "aabb half extents":
            sets.append(f"{path}={fmt([v * kk for v, kk in zip(vec(value), k)])}")
        elif block == "polyhedra" and field == "aabb center":
            sets.append(f"{path}={fmt([move(v, axis) for axis, v in enumerate(vec(value))])}")
        elif block == "polyhedra" and field == "volume":
            sets.append(f"polyhedra[{index}].base.volume={vec(value)[0] * kx * ky * kz:.6f}")
        elif block == "rigid bodies" and field == "bounding sphere radius":
            sets.append(f"{path}={vec(value)[0] * max(k):.6f}")
    for i, p in sorted(planes.items()):
        # a x + b y + c z + w = 0 with x = x'/kx, y = y'/ky, z = z0 + (z' - z0)/kz:
        # normal (a/kx, b/ky, c/kz), w + c z0 (1 - 1/kz), renormalized.
        n, w = p["plane equations"], p["havok w plane equations"][0]
        m = [n[0] / kx, n[1] / ky, n[2] / kz]
        w += n[2] * z0 * (1.0 - 1.0 / kz)
        length = math.sqrt(sum(v * v for v in m)) or 1.0
        sets.append(f"polyhedron plane equations[{i}].plane equations={fmt([v / length for v in m])}")
        sets.append(f"polyhedron plane equations[{i}].havok w plane equations={w / length:.6f}")
    return sets


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True, help="the new tags' path, objects\\...\\leaf")
    ap.add_argument("--half", required=True, help="the prop's half widths hx,hy (world units)")
    ap.add_argument("--height", type=float, required=True, help="the prop's height from its origin (world units)")
    ap.add_argument("--blueprint", required=True, help="the crate actor Blueprint package the new crate binds to")
    ap.add_argument("--mass-scale", type=float, default=0.2)
    ap.add_argument("--name", help="container base name (default: pakchunk996-MJOLNIRPROP-<leaf>)")
    ap.add_argument("--cli", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "target",
                                                  "release", "mjolnir.exe"))
    a = ap.parse_args()
    hx, hy = (float(v) for v in a.half.split(","))
    leaf = a.tag.replace("/", "\\").split("\\")[-1]
    base = a.name or f"pakchunk996-MJOLNIRPROP-{leaf}"
    os.makedirs(a.out, exist_ok=True)
    dump = run(a.cli, "values", "--paks", a.paks, "--group", "physics_model", "--tag", DONOR,
               "--depth", "4", "--elements", "1000", "--all")
    # The convex radius pads the polyhedron on every side and is not scaled:
    # sized to the prop's box itself, a coil stood 0.03 world units (8 cm)
    # proud of the one under it (Zanzibar, 2026-11-15). The polyhedron is the
    # box less the shell: half widths less r, height less 2r from its base at r.
    r = convex_radius(dump)
    k = ((hx - r) / DONOR_HALF[0], (hy - r) / DONOR_HALF[1], (a.height - 2 * r) / (DONOR_TOP - r))
    sets = [f"mass scale={a.mass_scale}"] + scaled_shape(dump, k, z0=r)
    set_file = os.path.join(a.out, f"{leaf}.phmo.sets")
    open(set_file, "w", encoding="utf-8").write("\n".join(sets))
    run(a.cli, "new-tag", "--paks", a.paks, "--group", "physics_model", "--from", DONOR, "--to", a.tag,
        "--set-file", set_file, "--out-dir", a.out, "--name", base + "-P")
    run(a.cli, "new-tag", "--paks", a.paks, "--group", "model", "--from", DONOR, "--to", a.tag,
        "--set", f"physics_model=phmo:{a.tag}", "--out-dir", a.out, "--name", base + "-H")
    bind = [] if a.blueprint.split(".")[0].lower() == DONOR_BLUEPRINT.lower() else ["--asset-reference", a.blueprint]
    run(a.cli, "new-tag", "--paks", a.paks, "--group", "crate", "--from", DONOR + "-crate", "--to", a.tag,
        "--set", f"object.model=hlmt:{a.tag}", "--set", "object.multiplayer object[0].default abandonment time=32767",
        *bind, "--out-dir", a.out, "--name", base + "-C")
    print(f"{a.tag}: shape x{k[0]:.2f} y{k[1]:.2f} z{k[2]:.2f}, mass scale {a.mass_scale}, "
          f"{len(sets)} physics field(s); containers {base}-P/-H/-C in {a.out}")


if __name__ == "__main__":
    main()
