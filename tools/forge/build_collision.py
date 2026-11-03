#!/usr/bin/env python3
"""Cook exact, fixed Forge polyhedra from original metre/Z-up collision hulls.

python tools/forge/build_collision.py geometry.json build/physics --paks PAKS --mjolnir MJOLNIR

Only the supplied output directory is written. No game installation is changed.
The generated set files and JSON argv arrays make every tag edit reviewable.
Use --commands-only to generate them without reading/cooking game content.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

METRES_PER_BLAM_UNIT = 3.048
DONOR = "crate_space_a/crate_space_a"
LIST_DONOR = "elevator_a/elevator_a_b40"
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def vec(values):
    return "(" + ", ".join(f"{v:.9g}" for v in values) + ")"


def sub(a, b):
    return [a[k] - b[k] for k in range(3)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def converted_hull(hull):
    """Keep source axes, convert metres to Blam units, derive outward planes."""
    vertices = [[float(x)/METRES_PER_BLAM_UNIT for x in v] for v in hull["vertices"]]
    if not 4 <= len(vertices) <= 256 or not all(len(v) == 3 and all(math.isfinite(x) for x in v) for v in vertices):
        raise ValueError("Each convex hull needs 4..256 finite 3D vertices")
    planes, seen, volume, edges = [], set(), 0.0, {}
    for triangle in hull["triangles"]:
        if len(triangle) != 3 or len(set(triangle)) != 3 or not all(isinstance(i, int) and 0 <= i < len(vertices) for i in triangle):
            raise ValueError("Invalid triangle vertex indices")
        a, b, c = [vertices[i] for i in triangle]
        normal = cross(sub(b, a), sub(c, a))
        length = math.sqrt(dot(normal, normal))
        if length < 1e-10:
            raise ValueError("Degenerate collision triangle")
        normal = [v/length for v in normal]
        distance = dot(normal, a)
        if any(dot(normal, v)-distance > 1e-6 for v in vertices):
            raise ValueError("Hull is not convex or a triangle faces inward")
        volume += dot(a, cross(b, c))/6
        key = tuple(round(v, 7) for v in [*normal, distance])
        if key not in seen:
            seen.add(key)
            planes.append([*normal, -distance])  # Havok n dot p + w = 0.
        for i, j in zip(triangle, triangle[1:] + triangle[:1]):
            edges[i, j] = edges.get((i, j), 0) + 1
    if volume <= 0 or any(count != 1 or edges.get((j,i)) != 1 for (i,j),count in edges.items()):
        raise ValueError("Hull is not a closed, consistently wound solid")
    lo = [min(p[k] for p in vertices) for k in range(3)]
    hi = [max(p[k] for p in vertices) for k in range(3)]
    return {"vertices": vertices, "planes": planes, "volume": volume,
            "center": [(lo[k]+hi[k])/2 for k in range(3)],
            "half": [(hi[k]-lo[k])/2 for k in range(3)]}


def physics_edits(piece):
    hulls = [converted_hull(hull) for hull in piece["collision"]["hulls"]]
    if not 1 <= len(hulls) <= 256:
        raise ValueError("Expected 1..256 independently convex hulls")
    vector_count = sum((len(h["vertices"])+3)//4 for h in hulls)
    plane_count = sum(len(h["planes"]) for h in hulls)
    if vector_count > 8192 or plane_count > 4096:
        raise ValueError("Physics hull data exceeds tag table limits")
    resizes = {"polyhedra": len(hulls), "polyhedron four vectors": vector_count,
               "polyhedron plane equations": plane_count}
    grafts, sets = {}, []

    def set_value(path, value):
        sets.append(f"{path}={value}")

    at_vector, at_plane = 0, 0
    for index, hull in enumerate(hulls):
        prefix = f"polyhedra[{index}]"
        vertices, planes = hull["vertices"], hull["planes"]
        groups = (len(vertices)+3)//4
        set_value(prefix+".base.material", "#0")
        set_value(prefix+".base.volume", f"{hull['volume']:.9g}")
        set_value(prefix+".base.friction", "0.7")
        set_value(prefix+".base.restitution", "0")
        set_value(prefix+".base.mass distribution index", "0")
        # No inflated Havok margin: nominal grid faces must coincide exactly.
        set_value(prefix+".polyhedron shape.radius", "0")
        set_value(prefix+".aabb center", vec(hull["center"]))
        set_value(prefix+".aabb half extents", vec(hull["half"]))
        set_value(prefix+".havok w aabb center", "0")
        set_value(prefix+".havok w aabb half extents", "0")
        set_value(prefix+".four vectors size", groups)
        set_value(prefix+".four vectors capacity", -(2**31)+groups)
        set_value(prefix+".num vertices", len(vertices))
        set_value(prefix+".plane equations size", len(planes))
        set_value(prefix+".plane equations capacity", -(2**31)+len(planes))
        # The loader allocates these flat tables sequentially according to each
        # preceding polyhedron's sizes. Each group is x4/y4/z4 (SOA), not xyzw.
        padded = vertices + [vertices[-1]]*(groups*4-len(vertices))
        for offset in range(groups):
            four = padded[offset*4:offset*4+4]
            for axis, name in enumerate("xyz"):
                data = [p[axis] for p in four]
                base = f"polyhedron four vectors[{at_vector+offset}]"
                set_value(base+f".four vectors {name}", vec(data[:3]))
                set_value(base+f".havok w four vectors {name}", f"{data[3]:.9g}")
        for offset, plane in enumerate(planes):
            base = f"polyhedron plane equations[{at_plane+offset}]"
            set_value(base+".plane equations", vec(plane[:3]))
            set_value(base+".havok w plane equations", f"{plane[3]:.9g}")
        at_vector += groups
        at_plane += len(planes)

    all_points = [p for h in hulls for p in h["vertices"]]
    lo = [min(p[k] for p in all_points) for k in range(3)]
    hi = [max(p[k] for p in all_points) for k in range(3)]
    center = [(lo[k]+hi[k])/2 for k in range(3)]
    half = [(hi[k]-lo[k])/2 for k in range(3)]
    radius = max(math.sqrt(dot(p,p)) for p in all_points)
    set_value("rigid bodies[0].node", "#0")
    set_value("rigid bodies[0].motion type", "fixed")
    set_value("rigid bodies[0].bouding sphere offset", "(0, 0, 0)")
    set_value("rigid bodies[0].bounding sphere radius", f"{radius:.9g}")
    set_value("rigid bodies[0].center of mass", vec(center))
    set_value("mass distributions[0].center of mass", vec(center))
    set_value("rigid bodies[0].shape reference.shape type", "list" if len(hulls)>1 else "polyhedron")
    set_value("rigid bodies[0].shape reference.shape", "#0")
    if len(hulls) > 1:
        for name in ("lists", "list shapes"):
            grafts[name] = f"physics_model:{LIST_DONOR}:{name}"
        resizes["lists"] = 1
        resizes["list shapes"] = len(hulls)
        set_value("lists[0].child shapes size", len(hulls))
        set_value("lists[0].child shapes capacity", -(2**31)+len(hulls))
        set_value("lists[0].aabb center", vec(center))
        set_value("lists[0].aabb half extents", vec(half))
        set_value("lists[0].havok w aabb half extents", "0")
        for index in range(len(hulls)):
            set_value(f"list shapes[{index}].shape reference.shape type", "polyhedron")
            set_value(f"list shapes[{index}].shape reference.shape", f"#{index}")
            set_value(f"list shapes[{index}].num child shapes", len(hulls))
    return resizes, grafts, sets, {"hulls": len(hulls), "vectors": vector_count,
                                  "planes": plane_count, "radius_blam": radius}


def run(argv):
    result = subprocess.run([str(a) for a in argv], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {argv[0]} {argv[1]}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("geometry", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mjolnir", required=True, type=Path)
    parser.add_argument("--paks", required=True, type=Path)
    parser.add_argument("--pack-id", default="foundry")
    parser.add_argument("--only", help="Build just this piece ID")
    parser.add_argument("--commands-only", action="store_true")
    parser.add_argument("--payload-out", type=Path, help="Also verify/extract cooked raw physics_model payloads into this directory")
    options = parser.parse_args()
    if not ID.fullmatch(options.pack_id):
        parser.error("Invalid pack ID")
    if options.commands_only and options.payload_out:
        parser.error("--payload-out requires cooking; omit --commands-only")
    geometry = json.loads(options.geometry.read_text(encoding="utf-8"))
    if geometry.get("units") != "meters" or geometry.get("axes") != "right_handed_z_up":
        parser.error("Expected metres in right_handed_z_up coordinates")
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    containers = output / "containers"
    containers.mkdir(exist_ok=True)
    report = []
    for piece in geometry["pieces"]:
        ident = piece["id"]
        if not ID.fullmatch(ident):
            raise ValueError("Invalid piece ID")
        if options.only and options.only != ident:
            continue
        resizes, grafts, sets, counts = physics_edits(piece)
        set_file = output / (ident+".physics.sets")
        set_file.write_text("\n".join(sets)+"\n", encoding="utf-8")
        tag = f"objects\\mjolnir\\forge\\{options.pack_id}\\{ident}"
        command = [str(options.mjolnir.resolve()), "new-tag", "--paks", str(options.paks.resolve()),
                   "--group", "physics_model", "--from", DONOR, "--to", tag]
        for name, value in grafts.items():
            command += ["--graft", f"{name}={value}"]
        for name, value in resizes.items():
            command += ["--resize", f"{name}={value}"]
        command += ["--set-file", str(set_file), "--out-dir", str(containers),
                    "--name", f"pakchunk987-MJOLNIRFORGE-{options.pack_id}-{ident}-physics"]
        (output / (ident+".physics-command.json")).write_text(json.dumps(command, indent=2)+"\n")
        if not options.commands_only:
            log = run(command)
            (output / (ident+".physics-build.log")).write_text(log, encoding="utf-8")
        report.append({"id": ident, "tag": tag, "cooked": not options.commands_only, **counts})
        print(f"{ident}: {counts['hulls']} exact hull(s), {counts['planes']} planes; {'prepared' if options.commands_only else 'cooked'}")
    if not report:
        parser.error("No pieces selected")
    if options.payload_out:
        extracted = output / "verified-payloads"
        run([options.mjolnir.resolve(), "extract", "--paks", containers,
             "--out", extracted, "--group", "physics_model", "--filter", options.pack_id, "--verify"])
        payload_out = options.payload_out.resolve()
        payload_out.mkdir(parents=True, exist_ok=True)
        for entry in report:
            matches = list(extracted.rglob(entry["id"]+".physics_model"))
            if len(matches) != 1:
                raise RuntimeError(f"Expected one verified payload for {entry['id']}, got {len(matches)}")
            shutil.copyfile(matches[0], payload_out / matches[0].name)
        print(f"Verified {len(report)} raw physics_model payloads -> {payload_out}")
    (output / "physics-report.json").write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    main()
