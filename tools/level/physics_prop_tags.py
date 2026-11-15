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


def scaled_shape(dump, k, z0=0.0, bottom=0.0):
    """`path=value` lines scaling the polyhedron by k = (kx, ky, kz), z about
    height z0 (its base: crate_space_a's polyhedron starts one convex radius
    up, so its shell meets the ground at the origin)."""
    kx, ky, kz = k
    vec = lambda s: [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", s)]
    fmt = lambda v: "(" + ", ".join(f"{x:.6f}" for x in v) + ")"
    # z about the donor's base z0, moved so that base lands at bottom + z0
    # (a prop whose origin is not at its foot: a tire, a coconut).
    off, to = (0.0, 0.0, z0), (0.0, 0.0, z0 + bottom)
    move = lambda v, axis: to[axis] + (v - off[axis]) * k[axis]
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
        w += n[2] * (z0 - (z0 + bottom) / kz)
        length = math.sqrt(sum(v * v for v in m)) or 1.0
        sets.append(f"polyhedron plane equations[{i}].plane equations={fmt([v / length for v in m])}")
        sets.append(f"polyhedron plane equations[{i}].havok w plane equations={w / length:.6f}")
    return sets


def explode_args(vitality):
    """`mjolnir new-tag` arguments that make the model die and blow up after
    `vitality` damage (None: indestructible, as crate_space_a is).

    crate_space_a's model has no damage info (maximum vitality 0). The Ghost's
    body section is grafted in, trimmed to its death response (instant
    response 2: the Warthog's destroyed explosion and the Ghost's hull
    burst, and trans_damage_medium, high explosive, 0.67-2 world units, up
    to 161: it hurts players near by and sets off the coils beside it), with
    the regions, seats and transfers that name Ghost parts emptied. A crate
    has no unit logic to die by its own, as a vehicle does: with a plain
    response a shot coil sank to -1800% and stood (Zanzibar, 2026-11-15), so
    the response kills the object and destroys it. Bullets reach the section
    through the model material and as indirect damage; the body does not
    recharge."""
    if not vitality:
        return []
    s = "damage info.damage sections"
    r = f"{s}[0].instant responses"
    return ["--graft", f"{s}=model:ghost-model:{s}", "--keep", f"{s}=0", "--keep", f"{r}=2",
            "--keep", f"{r}[0].region_transitions=", "--keep", f"{r}[0].response damage transfers=",
            "--keep", f"{r}[0].seat eject=", "--keep", f"{s}[0].section damage transfers=",
            "--set", f"damage info.maximum vitality={vitality}", "--set", "damage info.flags=none",
            "--set", "damage info.indirect damage section=#0",
            "--set", "damage info.response damage reporting type=generic explosion",
            "--set", "model materials[0].damage section=#0", "--set", "materials old[0].damage section=#0",
            "--set", f"{s}[0].recharge time=0", "--set", f"{s}[0].stun time=0",
            # Killed, not destroyed: the dead coil stays where the blast throws
            # it, burnt (props.lua turns its look `Charred`). Destroyed, it
            # just vanished (2026-11-15).
            "--set", f"{r}[0].flags=kills object",
            # The Hunter fuel rod's green detonation and the plasma grenade's
            # burst, and the large vehicle blast (200, 1-3 world units, harder
            # push) to fling what stands near. Only effects whose tag binds an
            # Unreal Blueprint draw anything: covenant_explosion_large and the
            # EMP drain bind the empty default and showed nothing (2026-11-15).
            "--set", f"{r}[0].transition effect (generic)=effe:{BOOM}",
            "--set", f"{r}[0].transition effect (specific)=effe:{ARCS}",
            "--set", f"{r}[0].damage effect.transition damage effect=jpt!:{BLAST}",
            "--set", f"{r}[0].generic effect marker=", "--set", f"{r}[0].specific effect marker="]


BOOM = "objects\\characters\\hunter\\fx\\weapon\\detonation"
ARCS = "objects\\weapons\\grenade\\plasma_grenade\\fx\\detonation"
BLAST = "globals\\damage_effects\\trans_damage_large"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True, help="the new tags' path, objects\\...\\leaf")
    ap.add_argument("--half", required=True, help="the prop's half widths hx,hy (world units)")
    ap.add_argument("--height", type=float, required=True, help="the prop's top above its origin (world units)")
    ap.add_argument("--bottom", type=float, default=0.0, help="the prop's foot relative to its origin (world units, <= 0)")
    ap.add_argument("--blueprint", required=True, help="the crate actor Blueprint package the new crate binds to")
    ap.add_argument("--mass-scale", type=float, default=0.2)
    ap.add_argument("--explode", type=float, metavar="VITALITY",
                    help="die after this much damage and blow up (a fusion coil: 40, about ten rifle rounds)")
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
    k = ((hx - r) / DONOR_HALF[0], (hy - r) / DONOR_HALF[1], (a.height - a.bottom - 2 * r) / (DONOR_TOP - r))
    sets = [f"mass scale={a.mass_scale}"] + scaled_shape(dump, k, z0=r, bottom=a.bottom)
    set_file = os.path.join(a.out, f"{leaf}.phmo.sets")
    open(set_file, "w", encoding="utf-8").write("\n".join(sets))
    run(a.cli, "new-tag", "--paks", a.paks, "--group", "physics_model", "--from", DONOR, "--to", a.tag,
        "--set-file", set_file, "--out-dir", a.out, "--name", base + "-P")
    run(a.cli, "new-tag", "--paks", a.paks, "--group", "model", "--from", DONOR, "--to", a.tag,
        "--set", f"physics_model=phmo:{a.tag}", *explode_args(a.explode), "--out-dir", a.out, "--name", base + "-H")
    bind = [] if a.blueprint.split(".")[0].lower() == DONOR_BLUEPRINT.lower() else ["--asset-reference", a.blueprint]
    run(a.cli, "new-tag", "--paks", a.paks, "--group", "crate", "--from", DONOR + "-crate", "--to", a.tag,
        "--set", f"object.model=hlmt:{a.tag}", "--set", "object.multiplayer object[0].default abandonment time=32767",
        *bind, "--out-dir", a.out, "--name", base + "-C")
    print(f"{a.tag}: shape x{k[0]:.2f} y{k[1]:.2f} z{k[2]:.2f}, mass scale {a.mass_scale}, "
          f"{len(sets)} physics field(s); containers {base}-P/-H/-C in {a.out}")


if __name__ == "__main__":
    main()
