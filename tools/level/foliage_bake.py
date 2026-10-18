"""The bake spec for a map whose foliage goes into its landscape world.

    python tools/level/foliage_bake.py <work dir> <out spec.json> [--paks P] [--mjolnir EXE]

MJOLNIRLevelLoader spawns a converted map's foliage at runtime (Foliage.spawn:
foliage.bin beside level.json, ~535,000 clumps on Death Island, ~6 s of the
load frame). With `bake_foliage` on a map (tools/level/ce_upgrade_maps.json)
upgrade_ce_map.py's editor stage writes this spec and
unreal/MJOLNIRMaterials/Scripts/build_ce_landscape.py places the clumps in
the landscape world instead (MjolnirUIBuilderLibrary.BakeFoliage), as
hierarchical instanced meshes of the game's own grass and rocks.

The world can name the game's meshes because each gets an editor-only
stand-in at its path (/Game/Env, /Game/Megascans), never cooked
(DefaultGame.ini DirectoriesToNeverCook): in game the reference resolves to
the game's mesh. The stand-in is a box of the game mesh's bounds with its
slots, because the cook builds each component's cluster tree and cached
bounds from the mesh's bounds; the bounds come from the game's package
(`mjolnir ue get`).

The spec: `bin`, the foliage file with the swapped trees' leaf clusters
appended as assemble appends them (so group numbers match the level file's);
`groups`, per group its mesh, bands, cull and flags (1 shadow, 2 static,
4 grassy: thinned by quality, 8 the cliffs' cladding: a mesh actor a rock,
whose material the loader still builds at runtime, 16 with the CE light
under each rock); `standins`.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# MJOLNIRLevelLoader's Foliage.CULL and Foliage.GRASSY.
CULL = [5000, 9000]
GRASSY = {"grass", "short grass", "lip grass", "weeds", "tufts"}
PAKS = "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"


def leaf_group(swap):
    """The leaf-cluster group assemble appends (upgrade_ce_map.stage_assemble)."""
    group = {"mesh": swap["leaves"]["mesh"], "rule": "tree leaves", "cull": [20000, 45000], "shadow": True,
             "scalars": swap["leaves"].get("scalars")}
    for key in ("material", "static"):
        if swap["leaves"].get(key) is not None:
            group[key] = swap["leaves"][key]
    return group


def bakeable(d):
    """A swapped scenery piece the world can carry as it is: a game mesh with
    at most `scalars` (the loader's runtime material values) and `static`.
    Anything with its own materials, tint, pulse or capture role stays the
    loader's."""
    return (isinstance(d, dict) and isinstance(d.get("mesh"), str) and isinstance(d.get("id"), str)
            and isinstance(d.get("pos"), list) and d["mesh"].startswith(("/Game/Env/", "/Game/Megascans/"))
            and not any(k in d for k in ("materials", "tint", "pulse", "capture_only", "cast_shadow",
                                         "sort_priority")))


def mesh_info(mjolnir, paks, path):
    """The game mesh's bounds and slot names, from its cooked package."""
    pkg = path.split(".", 1)[0]
    out = subprocess.run([mjolnir, "ue", "get", "--paks", paks, "--package", pkg, "--export",
                          pkg.rsplit("/", 1)[-1]], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env=dict(os.environ, MSYS2_ARG_CONV_EXCL="*"))
    if out.returncode != 0:
        # --export names an export by index in some builds: find the mesh's.
        listing = subprocess.run([mjolnir, "ue", "get", "--paks", paks, "--package", pkg], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace").stdout
        idx = next((m.group(1) for m in re.finditer(r"export (\d+): \S+ : StaticMesh\b", listing)), None)
        if idx is None:
            sys.exit(f"{path}: no StaticMesh export in the game's package:\n{out.stderr[-500:]}")
        out = subprocess.run([mjolnir, "ue", "get", "--paks", paks, "--package", pkg, "--export", idx],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows = {}
    slots = {}
    for line in out.stdout.splitlines():
        m = re.match(r"\s*(\S+) = (.*?)\s{3}\(", line)
        if not m:
            continue
        key, value = m.groups()
        rows[key] = value
        s = re.match(r"StaticMaterials\[(\d+)\]\.MaterialSlotName$", key)
        if s:
            slots[int(s.group(1))] = value

    def vec(key):
        v = rows.get(key)
        if v is None:
            sys.exit(f"{path}: no {key} in the game's package")
        return [float(x) for x in v.split(",")] if "," in v else [0.0, 0.0, 0.0]

    return {"origin": vec("ExtendedBounds.Origin"), "extent": vec("ExtendedBounds.BoxExtent"),
            "slots": [slots[i] for i in sorted(slots)] or ["Slot0"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("work", help="the map's upgrade work dir (foliage/, swap.json)")
    ap.add_argument("out", help="the spec to write")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS", PAKS))
    ap.add_argument("--mjolnir", default=os.environ.get("MJOLNIR", "mjolnir"))
    ap.add_argument("--origin", default="0,0,0", help="the level's canvas origin (cm), which decor sits on")
    a = ap.parse_args()
    origin = [float(v) for v in a.origin.split(",")]

    fol = json.load(open(os.path.join(a.work, "foliage", "foliage.json"), encoding="utf-8"))
    groups = list(fol["groups"])
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    bin_path = os.path.join(out_dir, "foliage_bake.bin")
    shutil.copyfile(os.path.join(a.work, "foliage", "foliage.bin"), bin_path)
    swap_path = os.path.join(a.work, "swap.json")
    decor = []
    if os.path.exists(swap_path):
        swap = json.load(open(swap_path, encoding="utf-8"))
        decor = [d for d in swap.get("decor") or [] if bakeable(d)]
        leaves = (swap.get("leaves") or {}).get("records") or []
        if leaves:
            from upgrade_ce_map import append_foliage
            append_foliage(bin_path, leaves)
            groups.append(leaf_group(swap))

    spec_groups, meshes = [], {}
    for g in groups:
        mesh = g.get("mesh") if isinstance(g.get("mesh"), str) else ""
        cull = g.get("cull") if isinstance(g.get("cull"), list) else CULL
        flags = (1 if g.get("shadow") is not False else 0) | (2 if g.get("static") else 0) \
            | (4 if g.get("rule") in GRASSY else 0) | (8 if g.get("cliff") else 0) \
            | (16 if g.get("cliff") and g.get("lm") else 0)
        spec_groups.append({"mesh": mesh, "bands": max(1, int(g.get("bands") or 1)),
                            "cull": [float(cull[0]), float(cull[1])], "flags": flags})
        if mesh:
            meshes[mesh] = None
    spec_decor = []
    for d in decor:
        meshes[d["mesh"]] = None
        rot = list(d.get("rot") or [0, 0, 0]) + [0, 0, 0]
        scale = d.get("scale") if isinstance(d.get("scale"), list) and len(d["scale"]) >= 3 else [1, 1, 1]
        spec_decor.append({"id": d["id"], "mesh": d["mesh"], "loc": [origin[i] + d["pos"][i] for i in range(3)],
                           "rot": rot[:3], "scale": scale[:3], "flags": 2 if d.get("static") else 0})
    # The game meshes' bounds, kept between runs: one `ue get` a mesh.
    cache_path = os.path.join(out_dir, "mesh_info.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    standins = []
    for mesh in sorted(meshes):
        if not mesh.startswith(("/Game/Env/", "/Game/Megascans/")):
            sys.exit(f"{mesh}: not under a never-cooked stand-in folder (/Game/Env, /Game/Megascans)")
        if mesh not in cache:
            cache[mesh] = mesh_info(a.mjolnir, a.paks, mesh)
        standins.append(dict(cache[mesh], path=mesh))
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), indent=1)
    json.dump({"bin": bin_path.replace("\\", "/"), "actor": "MJOLNIR_Foliage", "groups": spec_groups,
               "decor": spec_decor, "standins": standins}, open(a.out, "w", encoding="utf-8"), indent=1)
    baked = sum(1 for g in spec_groups if g["mesh"])
    print(f"foliage bake: {baked} of {len(spec_groups)} group(s), {len(spec_decor)} decor piece(s), "
          f"{len(standins)} stand-in mesh(es) -> {a.out}")


if __name__ == "__main__":
    main()
