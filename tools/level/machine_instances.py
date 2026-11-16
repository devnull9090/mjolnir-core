"""Cooked materials for the parts of Halo 2's machines (gears, doors, trains).

A part moves, so it is lit by Unreal where it is (prop_lit.py's M_CE_PropLit).
Its mesh's slots name material instances of their own, cooked with the map
(build_terrain_meshes.py --machine-instances, mesh_rewrite --asset-imports),
so the game draws a part dressed on every client with no Lua: the loader's
dressing at spawn was lost whenever a second match on the same map made new
actors (2026-11-15).

    build_terrain_meshes.py   slot() per section, plan() writes the file
    convert_ce_map.sh         ce_vehicle_instances_editor.py on the file
                              (after build_ce_level.py, before the cook),
                              then `machine_instances.py check`

`check <instances.json> <materials.spec.json>`: after the cook, stop unless
every instance is in the map's chunk, reads back what the file says (no static
permutation: ce_vehicle_materials.read_back), and the folder holds nothing
else.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ce_material_spec import asset_name  # noqa: E402
from prop_lit import prop_lit  # noqa: E402

FOLDER = "MachineMaterials"


def slot(material, root, leaf, j, instances):
    """The package a moving part's slot `j` names: a material instance of
    its prop_lit material (appended to `instances`, the editor's entries), or
    the bare material prop_lit chose when it has no parameters (a hidden
    bloom shell)."""
    lit = prop_lit(material, {}) if isinstance(material, dict) else material
    if isinstance(lit, str):
        return lit.split(".")[0]
    name = asset_name("MI_", f"{leaf[3:] if leaf.startswith('SM_') else leaf}_{j}")
    package = f"{root}/{FOLDER}/{name}"
    instances.append({"material": f"{leaf}_{j}", "slot": j, "package": package, "object": f"{package}.{name}",
                      "parent": lit["parent"], "textures": lit.get("textures", {}),
                      "scalars": lit.get("scalars", {}), "vectors": lit.get("vectors", {})})
    return package


def plan(root, instances, path):
    """The editor's file (ce_vehicle_instances_editor.py's shape)."""
    json.dump({"folder": f"{root}/{FOLDER}", "overrides": {}, "drop_textures": True, "instances": instances},
              open(path, "w", encoding="utf-8"), indent=1)
    print(f"{len(instances)} machine part instance(s) -> {path}")


def check(argv):
    ap = argparse.ArgumentParser(prog="machine_instances.py check")
    ap.add_argument("instances")
    ap.add_argument("spec")
    ap.add_argument("--mjolnir", default=os.path.join(HERE, "..", "..", "target", "release", "mjolnir.exe"))
    a = ap.parse_args(argv)
    from ce_vehicle_materials import REPO, STAGED, read_back
    p = json.load(open(a.instances, encoding="utf-8"))
    if not p["instances"]:
        return
    spec = json.load(open(a.spec, encoding="utf-8"))
    log = os.path.join(REPO, "unreal", "MJOLNIRMaterials", "Saved_ce_vehicle_instances_editor.log")
    if f"MJOLNIR vehicle instances: {len(p['instances'])} under {p['folder']}" not in open(
            log, encoding="utf-8", errors="replace").read():
        sys.exit(f"the machine instances did not build: see {log}")
    listing = subprocess.run([os.path.join(REPO, "target", "release", "examples", "container_ls.exe"), STAGED,
                              f"pakchunk{spec['chunk']}-"], capture_output=True, text=True).stdout
    files = {line.strip().split(".")[0] for line in listing.splitlines()[1:]}
    have = {f for f in files if f.startswith(FOLDER + "/")}
    want = {f"{FOLDER}/{e['package'].rsplit('/', 1)[1]}" for e in p["instances"]}
    if have != want:
        sys.exit(f"pakchunk{spec['chunk']}'s {FOLDER}: missing {sorted(want - have)}, extra {sorted(have - want)}")
    dropped = json.load(open(a.instances + ".dropped", encoding="utf-8"))
    # The map's own textures an instance names cook beside it: one left out
    # draws as the engine's default.
    root = p["folder"].rsplit("/", 1)[0] + "/"
    lost = sorted({t.split(".")[0][len(root):] for e in p["instances"] for k, t in e["textures"].items()
                   if t.startswith(root) and k not in dropped[e["package"]]} - files)
    if lost:
        sys.exit(f"pakchunk{spec['chunk']} lacks texture(s) the machine instances name: {lost}")
    for e in p["instances"]:
        read_back(a.mjolnir, e, dropped[e["package"]], {})
    print(f"read back {len(p['instances'])} machine part instance(s) in pakchunk{spec['chunk']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check(sys.argv[2:])
    else:
        sys.exit(__doc__)
