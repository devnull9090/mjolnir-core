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
`groups`, per group its mesh ("" for groups left to the loader: the cliffs'
cladding rocks, whose material the loader builds at runtime), bands, cull
and flags (1 shadow, 2 static, 4 grassy: thinned by quality); `standins`.
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
    a = ap.parse_args()

    fol = json.load(open(os.path.join(a.work, "foliage", "foliage.json"), encoding="utf-8"))
    groups = list(fol["groups"])
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    bin_path = os.path.join(out_dir, "foliage_bake.bin")
    shutil.copyfile(os.path.join(a.work, "foliage", "foliage.bin"), bin_path)
    swap_path = os.path.join(a.work, "swap.json")
    if os.path.exists(swap_path):
        swap = json.load(open(swap_path, encoding="utf-8"))
        leaves = (swap.get("leaves") or {}).get("records") or []
        if leaves:
            from upgrade_ce_map import append_foliage
            append_foliage(bin_path, leaves)
            groups.append(leaf_group(swap))

    spec_groups, meshes = [], {}
    for g in groups:
        mesh = g.get("mesh") if isinstance(g.get("mesh"), str) and not g.get("cliff") else ""
        cull = g.get("cull") if isinstance(g.get("cull"), list) else CULL
        flags = (1 if g.get("shadow") is not False else 0) | (2 if g.get("static") else 0) \
            | (4 if g.get("rule") in GRASSY else 0)
        spec_groups.append({"mesh": mesh, "bands": max(1, int(g.get("bands") or 1)),
                            "cull": [float(cull[0]), float(cull[1])], "flags": flags})
        if mesh:
            meshes[mesh] = None
    standins = []
    for mesh in sorted(meshes):
        if not mesh.startswith(("/Game/Env/", "/Game/Megascans/")):
            sys.exit(f"{mesh}: not under a never-cooked stand-in folder (/Game/Env, /Game/Megascans)")
        info = mesh_info(a.mjolnir, a.paks, mesh)
        standins.append(dict(info, path=mesh))
    json.dump({"bin": bin_path.replace("\\", "/"), "actor": "MJOLNIR_Foliage", "groups": spec_groups,
               "standins": standins}, open(a.out, "w", encoding="utf-8"), indent=1)
    baked = sum(1 for g in spec_groups if g["mesh"])
    print(f"foliage bake: {baked} of {len(spec_groups)} group(s), {len(standins)} stand-in mesh(es) -> {a.out}")


if __name__ == "__main__":
    main()
