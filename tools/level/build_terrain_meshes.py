#!/usr/bin/env python3
"""Write a converted CE map's terrain meshes and the level-file entries that
spawn them.

    build_terrain_meshes.py --paks <Paks> --spec <materials.spec.json> --out <dir> --name <map>
        --offset x,y,z --fallback </Game/...> --container <name> [--examples <dir>] [--repo <dir>]
        <scene.gltf>=<donor>=</Game/new/package/Path> [<scene_translucent.gltf>=<donor>=</Game/...>]

Each mesh is a shipped basic shape's mesh rewritten with the map's geometry
(`mesh_rewrite`, docs/ue_mesh_write.md) and renamed to a package of the
map's own, so any number of maps install side by side; `package_add` puts
all of one map's meshes in one container (`--container`, e.g.
`pakchunk986-MJOLNIRMESH-BGL_P`). The loader finds the new packages by their
soft path. Each mesh's sections get one material slot per glTF material, the
runtime materials the spec lists for them.

A rewritten mesh keeps its donor's one material slot, and Unreal decides
which passes a mesh takes part in from that slot alone. The first mesh (the
opaque terrain and scenery) leaves slot 0 to `--fallback`, an opaque
material. Any later mesh (the transparent sections) gives slot 0 to its first
section, so the mesh is drawn in the translucency pass.

Writes `<out>/terrain.json`: a list of decor entries, one per mesh, for
gen_ce_level.py --terrain.
"""
import argparse
import json
import os
import re
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paks", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--offset", default="0,0,0")
    ap.add_argument("--fallback", required=True, help="opaque material for the first mesh's slot 0")
    ap.add_argument("--container", required=True, help="container base name for the map's meshes")
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.normpath(os.path.join(here, "..", ".."))
    ap.add_argument("--repo", default=repo)
    ap.add_argument("--examples", default=os.path.join(repo, "target", "release", "examples"))
    ap.add_argument("meshes", nargs="+", help="<gltf>=<donor path substring>=</Game/new/package/Path>")
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    by_pattern = {s["pattern"]: s for s in spec["slots"]}
    entries, added = [], []
    exe = lambda n: os.path.join(a.examples, n + (".exe" if os.name == "nt" else ""))
    for k, mesh in enumerate(a.meshes):
        gltf, donor, package = mesh.split("=")
        leaf = package.rsplit("/", 1)[-1]
        uasset = os.path.join(a.out, f"{leaf}.uasset")
        doc = json.load(open(gltf, encoding="utf-8"))
        if k > 0 and not any(m.get("primitives") for m in doc.get("meshes", [])):
            # An indoor map (Chill Out) has no sky, a map without glass or
            # teleporter fields no translucent pieces: no mesh to build.
            print(f"{leaf}: {os.path.basename(gltf)} is empty, skipped")
            continue
        names = [m["name"] for m in doc.get("materials", [])]
        slots = [by_pattern[n.lower() + "$"] for n in names if n.lower() + "$" in by_pattern]
        args = [exe("mesh_rewrite"), a.paks, donor, gltf, uasset, "--offset", a.offset, "--lightmap-uvs",
                "--rename", package]
        materials = []
        if k == 0:
            args += ["--material", f"Terrain={a.fallback}=*"]
            materials.append(a.fallback + "." + a.fallback.rsplit("/", 1)[-1])
        for j, s in enumerate(slots):
            # On a later mesh the first section claims slot 0 ("*").
            pattern = s["pattern"] + ("|*" if k > 0 and j == 0 else "")
            args += ["--material", f"s_{s['name']}={s['material']['parent']}={pattern}"]
            materials.append(s["material"])
        log = subprocess.run(args, cwd=a.repo, capture_output=True, text=True)
        open(os.path.join(a.out, f"{leaf}.log"), "w").write(log.stdout + log.stderr)
        if log.returncode != 0 or "MISMATCH" in log.stdout:
            sys.exit(f"mesh_rewrite failed for {gltf}:\n{(log.stdout + log.stderr)[-2000:]}")
        for line in log.stdout.splitlines():
            if re.search(r"SPAWN|MATCHES|slot 0|renamed", line):
                print(line)
        m = re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)", log.stdout)
        x, y, z, sc = map(float, m.groups())
        added += ["--package", f"{package}={uasset}"]
        entry = {"id": f"{a.name}_terrain" + (f"_{k}" if k else ""),
                 "mesh": f"{package}.{leaf}",
                 "pos": [x, y, z], "scale": [sc, sc, sc], "materials": materials,
                 # Its shadows are baked into the lightmaps; objects cast
                 # the real ones (MJOLNIRLevelLoader).
                 "cast_shadow": False}
        if leaf.endswith("_Sky"):
            # Drawn before every other translucent thing, as CE's sky is.
            entry["sort_priority"] = -100
        entries.append(entry)

    po = subprocess.run([exe("package_add"), a.paks, a.out, "--name", a.container] + added,
                        capture_output=True, text=True)
    print(po.stdout.strip())
    if po.returncode != 0:
        sys.exit(f"package_add failed:\n{po.stderr[-2000:]}")
    json.dump(entries, open(os.path.join(a.out, "terrain.json"), "w", encoding="utf-8"), indent=2)
    print(f"{len(entries)} terrain mesh(es) in {a.container} -> {os.path.join(a.out, 'terrain.json')}")


if __name__ == "__main__":
    main()
