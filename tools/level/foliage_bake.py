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
under each rock, 32 exact transforms in <bin>.xf<group>: the leaf
clusters, mirrored as B30 places them, 64 four custom floats an instance in
<bin>.xc<group>: each cluster's tree pivot and size); `standins`.
"""
import argparse
from pathlib import Path
import json
import math
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
ROCK_MATERIALS = {
    f"/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_{v}/SM_Rock_Uluwatu_Med_{v}.SM_Rock_Uluwatu_Med_{v}":
    f"/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_{v}/{folder}MI_Rock_Uluwatu_Med_{v}.MI_Rock_Uluwatu_Med_{v}"
    for v, folder in (("A", ""), ("B", "Materials/"), ("C", ""))
}


def rock_material(mesh, roughness, palette=None):
    """Optional dry-rock MIC, cooked on the component, never made through UE4SS.

    Uluwatu's native base layer remaps roughness from -2 to 1. Outside B30
    that glossy surface catches blue sky reflections across the boulders.
    Keep its native textures/layers, with a map-specific roughness floor.
    """
    if roughness is None and palette is None:
        return None
    if palette not in (None, "coastal"):
        raise SystemExit("unknown rock palette")
    if roughness is None:
        roughness = 0.65
    if isinstance(roughness, bool) or not isinstance(roughness, (int, float)) or not 0 <= roughness <= 1:
        raise SystemExit("rock_roughness must be a number between 0 and 1")
    parent = ROCK_MATERIALS.get(mesh)
    if parent:
        material = {"parent": parent, "scalars": {f"Roughness Remap {end}#{layer}": float(value)
                    for layer in (0, 1) for end, value in (("Low", roughness), ("High", 1.0))}}
        return material
    # Preserve the native layer-to-layer variation: these colors are neutral
    # luminance remaps of the shipped Top/Mid/Bottom values. Do not guess at
    # Color Adjustment/Color Tint semantics or flatten every layer to one color.
    if palette == "coastal" and mesh:
        for variant in ("A", "C"):
            name = f"Rock_Desert_Cliff_{variant}"
            if mesh == f"/Game/Env/Bio/Rock/Desert/{name}/SM_{name}.SM_{name}":
                return {"parent": f"/Game/Env/Bio/Rock/Desert/{name}/Materials/MI_{name}.MI_{name}",
                        "scalars": {}, "vectors": json.loads(
                            Path(__file__).with_name("coastal_rock_colors.json").read_text())[variant]}
    return None


def decor_spec(d, origin, roughness=None, palette=None):
    rot = list(d.get("rot") or [0, 0, 0]) + [0, 0, 0]
    scale = d.get("scale") if isinstance(d.get("scale"), list) and len(d["scale"]) >= 3 else [1, 1, 1]
    entry = {"id": d["id"], "mesh": d["mesh"], "loc": [origin[i] + d["pos"][i] for i in range(3)],
             "rot": rot[:3], "scale": scale[:3], "flags": 2 if still(d) else 0}
    material = rock_material(d["mesh"], roughness, palette)
    if material:
        entry["material"] = material
    return entry


def runtime_decor(decor, roughness=None, palette=None):
    """Leave completed baked MICs alone: no runtime baked-component reads."""
    rock_material(None, roughness)
    return [d for d in decor if not (bakeable(d) and rock_material(d["mesh"], roughness, palette))]


def bakeable(d):
    """A swapped scenery piece the world can carry as it is: a game mesh with
    at most `scalars` (the loader's runtime material values) and `static`.
    Anything with its own materials, tint, pulse or capture role stays the
    loader's."""
    return (isinstance(d, dict) and isinstance(d.get("mesh"), str) and isinstance(d.get("id"), str)
            and isinstance(d.get("pos"), list) and d["mesh"].startswith(("/Game/Env/", "/Game/Megascans/"))
            and not any(k in d for k in ("materials", "tint", "pulse", "capture_only", "cast_shadow",
                                         "sort_priority")))


def still(d):
    """A decor item the loader keeps without wind: `static`, or a swapped
    tree's piece with the calm values (no sway). Each piece would bend about
    its own pivot and the tree come apart; baked still, the world needs no
    runtime switch (Infinity's small trees swayed when the loader's one
    missed, 2026-10-19)."""
    s = d.get("scalars")
    return bool(d.get("static")) or (isinstance(s, dict) and s.get("Wind Sway Max Angle") == 0)


def exact_transform(m):
    """A row-vector 3 x 3 (rows: where X, Y and Z go, with scale) as an
    FTransform's rotation (x, y, z, w) and scale. A mirrored one (B30's leaf
    clusters, every one) keeps its mirror as a negative Y scale."""
    s = [math.sqrt(sum(v * v for v in row)) for row in m]
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
           + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    if det < 0:
        s[1] = -s[1]
    r = [[m[i][j] / s[i] for j in range(3)] for i in range(3)]
    c = [[r[j][i] for j in range(3)] for i in range(3)]  # column-vector rotation
    t = c[0][0] + c[1][1] + c[2][2]
    if t > 0:
        k = math.sqrt(t + 1) * 2
        q = ((c[2][1] - c[1][2]) / k, (c[0][2] - c[2][0]) / k, (c[1][0] - c[0][1]) / k, 0.25 * k)
    elif c[0][0] > c[1][1] and c[0][0] > c[2][2]:
        k = math.sqrt(1 + c[0][0] - c[1][1] - c[2][2]) * 2
        q = (0.25 * k, (c[0][1] + c[1][0]) / k, (c[0][2] + c[2][0]) / k, (c[2][1] - c[1][2]) / k)
    elif c[1][1] > c[2][2]:
        k = math.sqrt(1 + c[1][1] - c[0][0] - c[2][2]) * 2
        q = ((c[0][1] + c[1][0]) / k, 0.25 * k, (c[1][2] + c[2][1]) / k, (c[0][2] - c[2][0]) / k)
    else:
        k = math.sqrt(1 + c[2][2] - c[0][0] - c[1][1]) * 2
        q = ((c[0][2] + c[2][0]) / k, (c[1][2] + c[2][1]) / k, 0.25 * k, (c[1][0] - c[0][1]) / k)
    return q, s


def write_exact(path, records):
    """Ten floats a record: location, rotation (x, y, z, w), scale."""
    import struct
    out = bytearray()
    for r in records:
        m = [r[7:10], r[10:13], r[13:16]]
        q, s = exact_transform(m)
        out += struct.pack("<10f", r[0], r[1], r[2], *q, *s)
    open(path, "wb").write(bytes(out))


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

    def vec(key, default=None):
        v = rows.get(key, default)
        if v is None:
            sys.exit(f"{path}: no {key} in the game's package")
        return [float(x) for x in v.split(",")] if "," in v else [0.0, 0.0, 0.0]

    # A cooked property at its default is left out: bounds centred on the
    # pivot carry no Origin at all (SM_SmallStonesPack__Snow, Ice Fields).
    return {"origin": vec("ExtendedBounds.Origin", "0"), "extent": vec("ExtendedBounds.BoxExtent"),
            "slots": [slots[i] for i in sorted(slots)] or ["Slot0"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("work", help="the map's upgrade work dir (foliage/, swap.json)")
    ap.add_argument("out", help="the spec to write")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS", PAKS))
    ap.add_argument("--mjolnir", default=os.environ.get("MJOLNIR", "mjolnir"))
    ap.add_argument("--origin", default="0,0,0", help="the level's canvas origin (cm), which decor sits on")
    ap.add_argument("--rock-roughness", type=float, help="bake native Uluwatu MICs with this roughness floor (0..1)")
    ap.add_argument("--rock-palette", choices=("coastal",), help="map-owned neutral coastal rock materials")
    a = ap.parse_args()
    rock_material(None, a.rock_roughness)  # Validate before writing output.
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
        from upgrade_ce_map import append_foliage, leaf_groups
        for records, group in leaf_groups(swap):
            append_foliage(bin_path, records)
            groups.append(group)
            if all(len(r) >= 16 for r in records):
                # Exact transforms beside the file (flag 32): group N's in
                # <bin>.xfN, read by BakeFoliage instead of the records.
                write_exact(f"{bin_path}.xf{len(groups)}", records)
                group["exact"] = True
            if all(len(r) >= 20 for r in records):
                # Four custom floats an instance (the tree's pivot and size)
                # beside them: <bin>.xcN.
                import struct
                open(f"{bin_path}.xc{len(groups)}", "wb").write(
                    b"".join(struct.pack("<4f", *r[16:20]) for r in records))
                group["custom"] = True

    spec_groups, meshes = [], {}
    for g in groups:
        mesh = g.get("mesh") if isinstance(g.get("mesh"), str) else ""
        cull = g.get("cull") if isinstance(g.get("cull"), list) else CULL
        flags = (1 if g.get("shadow") is not False else 0) | (2 if g.get("static") else 0) \
            | (4 if g.get("rule") in GRASSY else 0) | (8 if g.get("cliff") else 0) \
            | (16 if g.get("cliff") and g.get("lm") else 0) | (32 if g.get("exact") else 0) \
            | (64 if g.get("custom") else 0)
        spec_groups.append({"mesh": mesh, "bands": max(1, int(g.get("bands") or 1)),
                            "cull": [float(cull[0]), float(cull[1])], "flags": flags})
        if mesh:
            meshes[mesh] = None
    spec_decor = []
    for d in decor:
        meshes[d["mesh"]] = None
        spec_decor.append(decor_spec(d, origin, a.rock_roughness, a.rock_palette))
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
