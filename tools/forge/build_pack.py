#!/usr/bin/env python3
"""Build original Forge visuals and tags from a generated Blender pack.

Requires local game files; produces new namespaced packages, never modifies
the game. Run the collision build first, then this tool. See docs/forge_packs.md.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import struct

ROOT = Path(__file__).resolve().parents[2]
DONOR = "crate_space_a/crate_space_a"
MATERIAL_ROOT = "/Game/Env/HS/FR/Gen/+Materials/MI_FR_Gen_Metal_Simple_01_"
MATERIALS = [("concrete", MATERIAL_ROOT + "Grey_MidLight"),
             ("deck", MATERIAL_ROOT + "Grey_MidDark"),
             ("gunmetal", MATERIAL_ROOT + "Grey_Dark_Glossy"),
             ("amber", MATERIAL_ROOT + "Bronze_Light"),
             ("light_lens", "/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_White_Warm"),
             ("light_lens_red", "/Game/Env/HS/UNSC/Gen/+Materials/+Temp/MI_UNSC_EMIS_Red"),
             ("light_lens_blue", "/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_Blue_Dark")]


def surface_materials(slug, block):
    """Keep the old seven-slot build byte-for-byte for ordinary pieces."""
    if not block.get("surfaces"):
        return list(MATERIALS)
    from build_materials import PROFILE_MATERIALS, validate_slug
    validate_slug(slug)
    seen = set()
    for surface in block["surfaces"]:
        if set(surface) != {"slot", "profile"} or surface["profile"] not in PROFILE_MATERIALS:
            raise ValueError("Unsupported Forge surface profile")
        slot = surface["slot"]
        if isinstance(slot, bool) or slot != PROFILE_MATERIALS[surface["profile"]][0] or slot in seen:
            raise ValueError("This builder reserves slots 7/8 for glass/portal profiles")
        seen.add(slot)
    return list(MATERIALS) + [(key, f"/Game/MJOLNIR/Forge/{slug}/Materials/{master}")
                              for _, key, master in PROFILE_MATERIALS.values()]


def model_bounds(piece):
    """Enclose the original visual and collision geometry in Blam axes/units.

    Model bounds use a local centre offset, unlike the object's origin-centred
    bounding radius. They must not inherit the donor crate's dimensions.
    """
    points = [v for part in piece["visual"] for v in part["vertices"]]
    points.extend(piece["collision"]["vertices"])
    lo = [min(v[k] for v in points) for k in range(3)]
    hi = [max(v[k] for v in points) for k in range(3)]
    centre = [(lo[k] + hi[k]) / (2 * 3.048) for k in range(3)]
    radius = math.sqrt(sum(((hi[k] - lo[k]) / 2) ** 2 for k in range(3))) / 3.048
    return centre, radius


def model_bounds_args(piece):
    centre, radius = model_bounds(piece)
    return ("--set", f"runtime bounding radius={radius}",
            "--set", "runtime bounding offset=(" + ", ".join(map(str, centre)) + ")")


def write_pak_stub(path):
    """Emit the empty v11 mount sibling used by ue_iostore::pak::write_stub.

    The hash seed is immaterial for an empty archive; zero keeps this pure
    stdlib implementation deterministic. Index hashes and offsets are real.
    """
    path_hash, directory = bytes(8), bytes(4)
    index = struct.pack("<i2siQ", 2, b"/\0", 0, 0)
    index += struct.pack("<IQQ", 1, 106, 8) + hashlib.sha1(path_hash).digest()
    index += struct.pack("<IQQ", 1, 114, 4) + hashlib.sha1(directory).digest()
    index += struct.pack("<ii", 0, 0)
    if len(index) != 106:
        raise ValueError("invalid empty pak index size")
    footer = bytes(17) + struct.pack("<IIQQ", 0x5A6F12E1, 11, 0, 106)
    footer += hashlib.sha1(index).digest() + bytes(160)
    path.write_bytes(index + path_hash + directory + footer)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pack", type=Path)
    p.add_argument("--paks", type=Path, required=True)
    p.add_argument("--cli", type=Path, default=ROOT / "target/debug/mjolnir.exe")
    p.add_argument("--examples", type=Path, default=ROOT / "target/debug/examples")
    p.add_argument("--only", help="One block ID for a local diagnostic build")
    a = p.parse_args()
    pack = a.pack.resolve()
    manifest = json.loads((pack / "catalog.json").read_text(encoding="utf-8"))
    source = json.loads((pack / "source/geometry.json").read_text(encoding="utf-8"))
    pieces = {x["id"]: x for x in source["pieces"]}
    slug = manifest["forge_pack"]["id"]
    selected = [x for x in manifest["forge_pack"]["blocks"] if not a.only or x["id"] == a.only]
    if not selected:
        p.error("no matching blocks")
    out = pack / "build/game" / (a.only or "all")
    content, work = out / "content", out / "work"
    content.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    # new-tag resolves preload dependencies from its source index. Newly
    # built coll/phmo/model tags must be visible to the subsequent step.
    # Hardlinks make a read-only local view without copying the game itself.
    view = work / "paks"
    view.mkdir(exist_ok=True)
    for src in a.paks.resolve().iterdir():
        if src.is_file() and src.suffix in (".utoc", ".ucas"):
            dst = view / src.name
            if not dst.exists():
                os.link(src, dst)
    if any(block.get("surfaces") for block in selected):
        from build_materials import verified_content
        import shutil
        for src in verified_content(pack, slug):
            dst = content / src.name
            # copyfile replaces an existing hardlink's bytes. Retire our
            # previous destination so an old read-only build view stays intact.
            if dst.exists():
                dst.unlink()
            shutil.copyfile(src, dst)
            if src.suffix in (".utoc", ".ucas"):
                linked = view / src.name
                if linked.exists():
                    linked.unlink()
                os.link(dst, linked)

    def run(exe, *args):
        command = [str(exe), *map(str, args)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        with (out / "build.log").open("a", encoding="utf-8") as f:
            f.write("\n" + repr(command) + "\n" + result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"{exe}: {result.stderr[-3000:]}\n{result.stdout[-3000:]}")
        return result.stdout

    def new(group, tag, stem, *args):
        result = run(a.cli, "new-tag", "--paks", view, "--group", group,
                   "--from", DONOR, "--to", tag, "--out-dir", content,
                   "--name", f"pakchunk987-FORGE-{slug}-{stem}", *args)
        for src in content.glob(f"pakchunk987-FORGE-{slug}-{stem}_P.*"):
            if src.suffix in (".utoc", ".ucas"):
                dst = view / src.name
                if dst.exists():
                    dst.unlink()
                os.link(src, dst)
        return result

    packages = []
    changes = []
    for block in selected:
        ident, tag = block["id"], block["tag"]
        piece = pieces[ident]
        materials = surface_materials(slug, block)
        mesh = f"/Game/MJOLNIR/Forge/{slug}/SM_{ident}"
        actor = f"/Game/MJOLNIR/Forge/{slug}/BP_{ident}"
        mesh_file, actor_file = work / f"SM_{ident}.uasset", work / f"BP_{ident}.uasset"
        spec = []
        for k, (mat, path) in enumerate(materials):
            # mesh_rewrite takes the first matching pattern. Anchor names so
            # light_lens cannot consume light_lens_red or light_lens_blue.
            spec.extend(["--material", f"{mat}={path}={'*' if k == 0 else mat + '$'}"])
        run(a.examples / "mesh_rewrite.exe", a.paks, "basicshapes/cube", pack / f"build/models/{ident}.gltf",
            mesh_file, "--offset", "0,0,0", "--rename", mesh, *spec,
            *(["--asset-imports"] if block.get("surfaces") else []))
        # mesh_rewrite centres/normalizes the mesh; restore the authored
        # origin on the synchronized component (Blender Y -> UE -Y). This
        # also supports Roadworks' entry-anchored roads and asymmetric curves.
        points = [v for part in piece["visual"] for v in part["vertices"]]
        lo = [min(v[k] for v in points) for k in range(3)]
        hi = [max(v[k] for v in points) for k in range(3)]
        centre = [(lo[k] + hi[k]) * 50 for k in range(3)]
        centre[1] *= -1
        scale = max(hi[k] - lo[k] for k in range(3))
        run(a.examples / "forge_actor.exe", a.paks, actor, mesh, actor_file,
            ",".join(map(str, centre)), scale, *[path for _, path in materials])
        packages.extend(["--package", f"{mesh}={mesh_file}", "--package", f"{actor}={actor_file}"])
        coll = pack / f"build/blam-collision/{ident}.collision_model"
        physics = pack / f"build/blam-collision/{ident}.physics_model"
        if not coll.is_file() or not physics.is_file():
            raise FileNotFoundError(f"build collision/physics first: {ident}")
        visibility = []
        if "render_distance_m" in piece:
            distance = piece["render_distance_m"]
            if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or not 0 < distance <= 1000:
                raise ValueError(f"{ident}: render_distance_m must be finite and in (0, 1000]")
            # CU4 interprets zero as a short default distance, not unlimited.
            # Long road sections need an explicit finite model draw distance.
            visibility = ["--set", f"disappear distance={distance / 3.048}"]
        new("collision_model", tag, ident + "-coll", "--payload", coll)
        new("physics_model", tag, ident + "-phmo", "--payload", physics)
        new("model", tag, ident + "-model", "--set", f"physics_model=phmo:{tag}",
            "--set", f"collision model=coll:{tag}", *model_bounds_args(piece), *visibility)
        radius = math.sqrt(sum(max(abs(lo[k]), abs(hi[k])) ** 2 for k in range(3))) / 3.048
        new("crate", tag, ident + "-crate", "--asset-reference", actor,
            "--set", f"object.model=hlmt:{tag}", "--set", f"object.bounding radius={radius}")
        changes.extend({"group": g, "tag": tag, "from": DONOR}
                       for g in ("collision_model", "physics_model", "model", "crate"))
        print(f"Built {ident}: new mesh/actor + collision/physics/model/crate", flush=True)
    visual_name = f"pakchunk987-FORGE-{slug}-visuals_P"
    run(a.examples / "package_add.exe", a.paks, content, "--name", visual_name, *packages)
    # IoStore pairs are discovered through this sibling; package_add itself
    # only produces .utoc/.ucas and cannot mount the visuals without it.
    write_pak_stub(content / (visual_name + ".pak"))
    # The completed view can also bake maps using this pack. Refresh visuals
    # after package_add replaces its files, just as new() refreshes tag pairs.
    for extension in (".utoc", ".ucas"):
        src = content / (visual_name + extension)
        dst = view / src.name
        if dst.exists():
            dst.unlink()
        os.link(src, dst)
    manifest["forge_pack"]["blocks"] = selected
    (out / "mjolnir.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "changes.json").write_text(json.dumps({"schema_version": 1, "tags": [], "new_tags": changes}, indent=2) + "\n", encoding="utf-8")
    print(f"Pack inputs: {out}")


if __name__ == "__main__":
    main()
