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
             ("amber", MATERIAL_ROOT + "Bronze_Light")]


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
        mesh = f"/Game/MJOLNIR/Forge/{slug}/SM_{ident}"
        actor = f"/Game/MJOLNIR/Forge/{slug}/BP_{ident}"
        mesh_file, actor_file = work / f"SM_{ident}.uasset", work / f"BP_{ident}.uasset"
        spec = []
        for k, (mat, path) in enumerate(MATERIALS):
            spec.extend(["--material", f"{mat}={path}={'*' if k == 0 else mat}"])
        run(a.examples / "mesh_rewrite.exe", a.paks, "basicshapes/cube", pack / f"build/models/{ident}.gltf",
            mesh_file, "--offset", "0,0,0", "--rename", mesh, *spec)
        # mesh_rewrite centres/normalizes the mesh; restore the floor-centred
        # source transform on the synchronized component (Blender Y -> UE -Y).
        points = [v for part in piece["visual"] for v in part["vertices"]]
        lo = [min(v[k] for v in points) for k in range(3)]
        hi = [max(v[k] for v in points) for k in range(3)]
        centre = [(lo[k] + hi[k]) * 50 for k in range(3)]
        centre[1] *= -1
        scale = max(hi[k] - lo[k] for k in range(3))
        run(a.examples / "forge_actor.exe", a.paks, actor, mesh, actor_file,
            ",".join(map(str, centre)), scale, *[path for _, path in MATERIALS])
        packages.extend(["--package", f"{mesh}={mesh_file}", "--package", f"{actor}={actor_file}"])
        coll = pack / f"build/blam-collision/{ident}.collision_model"
        physics = pack / f"build/blam-collision/{ident}.physics_model"
        if not coll.is_file() or not physics.is_file():
            raise FileNotFoundError(f"build collision/physics first: {ident}")
        new("collision_model", tag, ident + "-coll", "--payload", coll)
        new("physics_model", tag, ident + "-phmo", "--payload", physics)
        new("model", tag, ident + "-model", "--set", f"physics_model=phmo:{tag}",
            "--set", f"collision model=coll:{tag}")
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
    manifest["forge_pack"]["blocks"] = selected
    (out / "mjolnir.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "changes.json").write_text(json.dumps({"schema_version": 1, "tags": [], "new_tags": changes}, indent=2) + "\n", encoding="utf-8")
    print(f"Pack inputs: {out}")


if __name__ == "__main__":
    main()
