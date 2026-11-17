"""Cooked materials for the parts of Halo 2's machines (gears, doors, trains).

A part moves, so it is lit by Unreal where it is (prop_lit.py's M_CE_PropLit).
Its mesh's slots name material instances of their own, cooked with the map
(build_terrain_meshes.py --machine-instances, mesh_rewrite --asset-imports),
so the game draws a part dressed on every client with no Lua: the loader's
dressing at spawn was lost whenever a second match on the same map made new
actors (2026-11-15).

    build_terrain_meshes.py   slot() per section, plan() writes the file
    a fresh conversion        convert_ce_map.sh: ce_vehicle_instances_editor.py
                              on the file (after build_ce_level.py, before
                              the cook), then `machine_instances.py check`.
                              The instances live in the map's own folder
                              (<root>/MachineMaterials) and chunk.
    an upgraded map           upgrade_ce_map.py: the meshes are built naming
                              instances under /Game/MJOLNIR/MachineParts/<land>
                              (h2_physics_props.py --instance-root), a folder
                              and a label of its own in the landscape's chunk.
                              The editor stage finishes each entry (the
                              redrawn textures, detail_fill) and makes them
                              after the landscape world; the cook stage checks.

`check <instances.json> --chunk N [--also <dir>=<utoc substring> ...]`: after
the cook, stop unless every instance is in chunk N, reads back what the file
says (no static permutation: ce_vehicle_materials.read_back), its folder holds
nothing else, no master came with it (a recursive label's trap: the chunk
would shadow the runtime pack's shaders), and every texture it names is cooked
there or in an `--also` container.
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


def slot(material, folder, leaf, j, instances):
    """The package a moving part's slot `j` names: a material instance of
    its prop_lit material in `folder` (appended to `instances`, the editor's
    entries), or the bare material prop_lit chose when it has no parameters
    (a hidden bloom shell)."""
    lit = prop_lit(material, {}) if isinstance(material, dict) else material
    if isinstance(lit, str):
        return lit.split(".")[0]
    name = asset_name("MI_", f"{leaf[3:] if leaf.startswith('SM_') else leaf}_{j}")
    package = f"{folder}/{name}"
    instances.append({"material": f"{leaf}_{j}", "slot": j, "package": package, "object": f"{package}.{name}",
                      "mesh": leaf, "parent": lit["parent"], "textures": lit.get("textures", {}),
                      "scalars": lit.get("scalars", {}), "vectors": lit.get("vectors", {})})
    return package


def plan(folder, instances, path, label=None):
    """The editor's file (ce_vehicle_instances_editor.py's shape). `label`
    ({"name", "chunk"}): a label of the folder's own, for a folder no map
    label covers."""
    doc = {"folder": folder, "overrides": {}, "drop_textures": True, "instances": instances}
    if label:
        doc["label"] = label
    json.dump(doc, open(path, "w", encoding="utf-8"), indent=1)
    print(f"{len(instances)} machine part instance(s) -> {path}")


def listing(directory, want):
    from ce_vehicle_materials import REPO
    out = subprocess.run([os.path.join(REPO, "target", "release", "examples", "container_ls.exe"), directory, want],
                         capture_output=True, text=True).stdout
    return {line.strip().split(".")[0] for line in out.splitlines()[1:]}


def check(argv):
    ap = argparse.ArgumentParser(prog="machine_instances.py check")
    ap.add_argument("instances")
    ap.add_argument("--chunk", required=True)
    ap.add_argument("--also", action="append", default=[], metavar="DIR=UTOC",
                    help="a container that carries textures the instances name (the conversion's own cook)")
    ap.add_argument("--mjolnir", default=os.path.join(HERE, "..", "..", "target", "release", "mjolnir.exe"))
    a = ap.parse_args(argv)
    from ce_vehicle_materials import REPO, STAGED, read_back
    p = json.load(open(a.instances, encoding="utf-8"))
    if not p["instances"]:
        return
    # The editor writes <file>.dropped last, after every instance is saved:
    # one older than the file, or missing an instance, is a run that did not
    # finish. (Its log is shared by every run of the script, so a later
    # map's run would hide this one's.)
    done = a.instances + ".dropped"
    if not os.path.exists(done) or os.path.getmtime(done) < os.path.getmtime(a.instances):
        sys.exit(f"the machine instances did not build (no {done} newer than the file): "
                 f"see {os.path.join(REPO, 'unreal', 'MJOLNIRMaterials', 'Saved_ce_vehicle_instances_editor.log')}")
    dropped = json.load(open(done, encoding="utf-8"))
    unbuilt = sorted(e["package"] for e in p["instances"] if e["package"] not in dropped)
    if unbuilt:
        sys.exit(f"the machine instances did not all build: {unbuilt}")
    # container_ls prints paths from the container's mount point, the longest
    # prefix its files share: a file is matched by the end of its path.
    files = listing(STAGED, f"pakchunk{a.chunk}-")
    leaves = {f.rsplit("/", 1)[-1] for f in files}
    tail = p["folder"].rsplit("/", 1)[1]
    have = {f.rsplit("/", 1)[-1] for f in files if f"/{tail}/" in "/" + f
            and f"{p['folder']}/{f.rsplit('/', 1)[-1]}".endswith("/" + f)} - {(p.get("label") or {}).get("name")}
    want = {e["package"].rsplit("/", 1)[1] for e in p["instances"]}
    if have != want:
        sys.exit(f"pakchunk{a.chunk}'s {tail}: missing {sorted(want - have)}, extra {sorted(have - want)}")
    masters = sorted({e["parent"].rsplit(".", 1)[1] for e in p["instances"]} & leaves)
    if masters:
        sys.exit(f"pakchunk{a.chunk} took copies of the masters {masters}: the instances' label is recursive")
    # A texture an instance names is cooked where the game will find it: one
    # left out draws as the engine's default.
    cooked = set(leaves)
    for also in a.also:
        directory, want_utoc = also.split("=", 1)
        cooked |= {f.rsplit("/", 1)[-1] for f in listing(directory, want_utoc)}
    lost = sorted({t.rsplit(".", 1)[-1] for e in p["instances"] for k, t in e["textures"].items()
                   if t.startswith("/Game/MJOLNIR/") and k not in dropped[e["package"]]} - cooked)
    if lost:
        sys.exit(f"texture(s) the machine instances name are in no container given: {lost}")
    for e in p["instances"]:
        read_back(a.mjolnir, e, dropped[e["package"]], {})
    print(f"read back {len(p['instances'])} machine part instance(s) in pakchunk{a.chunk}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check(sys.argv[2:])
    else:
        sys.exit(__doc__)
