"""Seal the native outlet art onto the verified .36 Pelican Warfare map."""
import argparse
from pathlib import Path
import shutil
import tempfile

from bases_v1.stage_base_polish import seal_release, unpack_map
from stage_world_playtest import LAND, ROOT, WORLD, jsonfile, load_container, sha, world_entries, write_json


WORK = ROOT / "out/pwr/river-apron"
PARENT = "dffdab938df584eae87ea0ca84b22dad7b098e4ab76f23ad08848066f01b9ca4"
PLAYABLE = "MJOLNIR/GrassPilot/Playable/"
SHORE_ASSETS = {
    PLAYABLE + "M_PWRPilot.uasset",
    PLAYABLE + "M_PWR_OutletAlluvium.uasset",
    PLAYABLE + "SM_PWR_OutletAlluvium.uasset",
}
ALLOWED = {
    LAND: SHORE_ASSETS | {
        "ShaderArchive-Meteorite_Chunk965-PCD3D_SM6-PCD3D_SM6.ushaderbytecode",
        "Levels/Halo1/Solo/LPE/LPE.umap",
        "Levels/Halo1/Solo/LPE/LPE.ubulk",
    },
    WORLD: {"Meteorite/Content/Levels/Halo1/Solo/PWR/PWR." + ext for ext in ("umap", "ubulk")},
}


def asset_layout(stem, toc):
    container = load_container(toc)
    named = set(container.files.values())
    structural = {"ContainerHeader", "ShaderCode"} if stem == LAND else {"ContainerHeader"}
    extra = {c.type_name for c in container.chunks if c.index not in named} - structural
    if extra:
        raise ValueError(f"Unlisted native package data in {stem}: {sorted(extra)}")
    addresses = {}
    for name, index in container.files.items():
        chunk = container.chunks[index]
        addresses[name] = (chunk.chunk_id, chunk.chunk_index, chunk.chunk_type)
    return container.mount_point, container.container_id, addresses


def check_assets(stem, before, after):
    if before.keys() != after.keys():
        raise ValueError(f"Package inventory changed in {stem}: {sorted(before.keys() ^ after.keys())}")
    changed = {name: [before[name], digest] for name, digest in after.items() if before[name] != digest}
    unexpected = changed.keys() - ALLOWED[stem]
    if unexpected:
        raise ValueError(f"Unexpected changes to {stem}: {sorted(unexpected)}")
    if stem == LAND and not SHORE_ASSETS.intersection(changed):
        raise ValueError("The native shoreline mesh and materials all match .36")
    return {"changed": changed, "preserved_count": len(before) - len(changed)}


def apply_tested_ripple(level_file):
    trial = WORK.parent / "alpine-target/bench/river-apron-36/water"
    capture = jsonfile(trial / "photos.json")
    if capture["release"]["map_sha256"] != PARENT:
        raise ValueError("The optical trial was run against a different release")
    optics = WORK / "water-optics"
    evidence = [trial / "surface-on.png", trial / "detail-wave-trial.png", trial / "detail-wave-study.log",
                trial / "detail-wave-restored.log", trial / "photos.json", optics / "detail-wave.lua",
                optics / "measurement.json"]
    digests = {path.name: sha(path) for path in evidence}
    if (digests["surface-on.png"] != "4c4a36bf760e2f47e39836921e82ed01134e5ea22639e44b24871fd96cdc996c" or
            digests["detail-wave-trial.png"] != "7b1a462c6140db97a352ea46073ee6e7fbe1614e22b747315a6b3d507885f5ad" or
            "PWR_WAVE_STUDY PASS" not in (trial / "detail-wave-study.log").read_text() or
            "PWR_WAVE_RESTORE PASS" not in (trial / "detail-wave-restored.log").read_text()):
        raise ValueError("The registered .36 material comparison or live readbacks differ")
    measurement = jsonfile(optics / "measurement.json")
    if (measurement["camera"] != capture["views"]["outlet"] or
            measurement["frames"] != {"stock": digests["surface-on.png"], "trial": digests["detail-wave-trial.png"]}):
        raise ValueError("Wave-contrast measurement refers to a different camera or frame")
    original = jsonfile(level_file)
    level = jsonfile(level_file)
    domains = level["flux"]["domains"]
    if [d["id"] for d in domains] != ["upper_river", "lower_lake"] or "surface_scalars" in domains[0]:
        raise ValueError("The upper river differs from the stock .36 optical control")
    domains[0]["surface_scalars"] = {"DetailWaveHeight": 3}
    write_json(level_file, level)
    readback = jsonfile(level_file)
    scalars = readback["flux"]["domains"][0].pop("surface_scalars")
    if scalars != {"DetailWaveHeight": 3} or readback != original:
        raise ValueError("The material change reached other level settings")
    return {"domain": "upper_river", "surface_scalars": scalars, "original_native_detail_wave_height": 14,
            "trial_map_sha256": PARENT, "comparison": measurement, "trial_sha256": digests}


def stage(args, folder):
    art = jsonfile(args.art / "receipt.json")
    if art["parent_map_sha256"] != PARENT:
        raise ValueError("The native finish was cooked against a different map")
    cooked = args.art / "map-input"
    digests = art["native_members"]
    land_files = {LAND + ext for ext in (".ucas", ".utoc")}
    world_files = {WORLD + ext for ext in (".ucas", ".utoc")}
    if set(digests) not in (land_files, land_files | world_files):
        raise ValueError("The native receipt must contain complete landscape and optional world containers")
    if {f.name for f in cooked.iterdir()} != set(digests):
        raise ValueError("Cooked files differ from the native receipt")

    inputs, previous, hashes, manifest = unpack_map(args.baseline, folder)
    if previous["sha256"] != PARENT:
        raise ValueError("The finish requires the sealed .36 playtest")
    original = dict(hashes)
    packages = {}
    for stem in (LAND, WORLD):
        toc = stem + ".utoc"
        if toc not in digests:
            continue
        layout = asset_layout(stem, inputs / toc)
        before = world_entries(inputs / toc)
        for ext in (".ucas", ".utoc"):
            name = stem + ext
            dest = inputs / name
            shutil.copyfile(cooked / name, dest)
            digest = sha(dest)
            if digest != digests[name]:
                raise ValueError("Staged native file differs from the cook receipt: " + name)
            hashes["content/" + name] = digest
        if asset_layout(stem, inputs / toc) != layout:
            raise ValueError("Cook changed package names or load addresses in " + stem)
        packages[stem] = check_assets(stem, before, world_entries(inputs / toc))

    ripple = apply_tested_ripple(inputs / "pwr.level.json")
    hashes["map/level.json"] = sha(inputs / "pwr.level.json")
    seal_release(args, folder, inputs, previous, hashes, manifest, {
        "modified_members": sorted(k for k in hashes if hashes[k] != original[k]),
        "world_packages": packages,
        "shore_finish": art,
        "level_sections": ["flux"],
        "upper_river_optics": ripple,
        "native_art_receipt_sha256": sha(args.art / "receipt.json"),
        "retained_terrain_manifest_sha256": previous["headwater"]["terrain"]["runtime_manifest_sha256"],
        "retained_bsp_sha256": previous["headwater"]["native"]["sbsp"],
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=WORK / "saturday.36")
    parser.add_argument("--art", type=Path, default=WORK / "finish37")
    parser.add_argument("--out", type=Path, default=WORK / "saturday.37")
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    args = parser.parse_args()
    args.version = "0.1.0-playtest.37"
    if args.out.exists():
        parser.error("Choose a new release folder")
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
        folder = Path(temporary) / "release"
        folder.mkdir()
        stage(args, folder)
        folder.rename(args.out)
    print(args.out)
