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

CE water (M_CE_Water sections) leaves the translucent mesh for one of its
own, `SM_<map>_Water`, built last so the other meshes keep their ids. Slot 0
deciding the passes is why: the loader can draw that water as the game's
ocean (MJOLNIRLevelLoader `mjolnir_water`), a Single Layer Water material,
and Unreal draws it as water only on a mesh whose slot 0 is water too. On
the translucent mesh it was drawn unlit, and giving slot 0 the ocean there
took the glass, teleporter fields and shore foam out of the translucency
pass (Death Island, 2026-10-10). The water is refined first
(refine_water_gltf.py) into triangles small enough to carry the ocean's
waves, densest over the playable area (`--placement`, the staging's
placement.json).

Writes `<out>/terrain.json`: a list of decor entries, one per mesh, for
gen_ce_level.py --terrain.
"""
import argparse
import json
import os
import re
import subprocess
import sys

from refine_water_gltf import playable_area, refine_file

WATER_PARENT = "/Game/MJOLNIR/CE/M_CE_Water.M_CE_Water"
# After the sky (-100), before the rest of the translucency: CE's shore foam
# and wave masks are drawn over the water.
WATER_SORT_PRIORITY = -50


def gltf_subset(src, dst, keep):
    """Write `dst`, the glTF `src` with only the primitives whose material name
    `keep` accepts, its materials pruned and renumbered. The buffers stay
    where they are: `dst` sits beside `src`, so their URIs still resolve.
    Returns the number of primitives kept."""
    doc = json.load(open(src, encoding="utf-8"))
    names = [m["name"] for m in doc.get("materials", [])]
    for mesh in doc.get("meshes", []):
        mesh["primitives"] = [p for p in mesh.get("primitives", [])
                              if "material" in p and keep(names[p["material"]])]
    used = sorted({p["material"] for m in doc.get("meshes", []) for p in m["primitives"]})
    renumber = {old: new for new, old in enumerate(used)}
    doc["materials"] = [doc["materials"][i] for i in used]
    for mesh in doc.get("meshes", []):
        for p in mesh["primitives"]:
            p["material"] = renumber[p["material"]]
    json.dump(doc, open(dst, "w", encoding="utf-8"))
    return sum(len(m["primitives"]) for m in doc.get("meshes", []))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paks", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--offset", default="0,0,0")
    ap.add_argument("--fallback", required=True, help="opaque material for the first mesh's slot 0")
    ap.add_argument("--container", required=True, help="container base name for the map's meshes")
    ap.add_argument("--placement", help="the staging's placement.json: where the water is refined most")
    ap.add_argument("--water-near", type=float, default=4.0, help="water edge length over the playable area, m")
    ap.add_argument("--water-growth", type=float, default=0.08, help="water edge length added per metre beyond it")
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

    def is_water(name):
        s = by_pattern.get(name.lower() + "$")
        return bool(s) and s["material"].get("parent") == WATER_PARENT

    # The translucent mesh's water becomes a mesh of its own, built last.
    jobs = [mesh.split("=") for mesh in a.meshes]
    water_jobs = []
    for job in jobs:
        gltf, _, package = job
        if not (package.endswith("_Translucent") and os.path.isfile(gltf)):
            continue
        base = gltf[: -len(".gltf")]
        if gltf_subset(gltf, base + "_water.gltf", is_water):
            gltf_subset(gltf, base + "_nowater.gltf", lambda n: not is_water(n))
            job[0] = base + "_nowater.gltf"
            center, radius = playable_area(a.placement) if a.placement else (None, None)
            before, after, center, radius = refine_file(base + "_water.gltf", base + "_water_dense.gltf",
                                                        a.water_near, a.water_growth, center, radius)
            print(f"water: {before} -> {after} triangle(s), {a.water_near} m within {radius:.0f} m "
                  f"of ({center[0]:.0f}, {center[1]:.0f})")
            water_jobs.append([base + "_water_dense.gltf", "basicshapes/cube",
                               package[: -len("_Translucent")] + "_Water"])
    jobs += water_jobs

    for k, (gltf, donor, package) in enumerate(jobs):
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
        # The slot list goes through a response file: hundreds of slots
        # (Coldsnap) pass Windows' 32K command line.
        rsp = os.path.join(a.out, f"{leaf}.args")
        with open(rsp, "w", encoding="utf-8") as f:
            f.write("\n".join(args[9:]) + "\n")
        log = subprocess.run(args[:9] + ["@" + rsp], cwd=a.repo, capture_output=True, text=True)
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
        elif leaf.endswith("_Water"):
            entry["sort_priority"] = WATER_SORT_PRIORITY
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
