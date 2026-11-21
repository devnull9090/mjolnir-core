"""Seal the widened river outlet between the verified .35 map and its paired runtimes."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from zipfile import ZipFile
import numpy as np

from bases_v1.stage_base_polish import seal_release, unpack_map
from stage_headwater_lake import VERIFY_WORLD
from stage_world_playtest import LAND, ROOT, WORLD, jsonfile, sha, stage_name, world_entries, write_json

sys.path.insert(0, str(ROOT / "tools/level"))
from flux_heightfield import verify_state_files

BASE = ROOT / "out/pwr"
WORK = BASE / "river-apron"
PARENT = "6b34504b34fb9c593f33f43f2b2daec03235dc0f48e95d838a7c75037e0f3dbc"
BASIN_PARENT = "cf10cc58ed2a72a2a9f2433374be0215a29128149a832e0bdabc543e80a30da2"
LANDFILES = {
    "shaderarchive-meteorite_chunk965-pcd3d_sm6-pcd3d_sm6.ushaderbytecode",
    "mjolnir/grasspilot/playable/m_pwrpilot.uasset",
    "levels/halo1/solo/lpe/lpe.umap",
    "levels/halo1/solo/lpe/lpe.ubulk",
}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def checked_scene(work, level, dressing, previous_work):
    # The native scene compiler indexes its placement ledger against .31. Confirm
    # both ends of that relation before applying the resulting array to .35.
    source = BASE / "sweep-polish/round31/saturday.31"
    info = jsonfile(source / "receipt.json")
    with ZipFile(source / info["archive"]) as archive:
        original = json.loads(archive.read("map/level.json"))
    for name, key in [("map/level.json", "original_level_sha256"), ("map/foliage.bin", "original_foliage_sha256")]:
        check(info["members_sha256"][name] == dressing[key], "Dressing source mismatch for " + name)
    before = jsonfile(previous_work / "dressing/level-decor.json")
    check(level["decor"] == before, "Installed shoreline differs from its surveyed source")
    decor = jsonfile(work / "dressing/level-decor.json")
    rows = jsonfile(work / "dressing/decor-moves.json")["decor"]
    ledger = {r["id"]: r for r in rows}
    check(len(ledger) == len(rows) and len(original["decor"]) == len(decor), "Placement count changed")
    for index, (old, new) in enumerate(zip(original["decor"], decor)):
        entry = ledger.get(old["id"])
        if entry is None:
            check(old == new, "Unlisted placement change " + old["id"])
            continue
        check(entry["level_index"] == index and entry["mesh"] == old["mesh"] and
              entry["old_pos_ue_cm"] == old["pos"] and entry["new_pos_ue_cm"] == new["pos"] and
              dict(old, pos=new["pos"]) == new, "Different cooked rock transform for " + old["id"])
    check(set(ledger).issubset({p["id"] for p in decor}), "Unresolved rock ID")
    groups = jsonfile(work / "dressing/foliage.json")
    check(all(level["foliage"].get(k) == v for k, v in groups.items()), "Different packed instance groups")
    return decor


def checked_grading(work, terrain, previous_work, change_key):
    prior = previous_work / "terrain"
    current = work / "terrain"
    check(terrain["previous_erosion_sha256"] == sha(prior / "runtime-master.json"), "Unexpected grading baseline")
    def layer(folder, name):
        return np.load(folder / ("runtime-master." + name + ".npy"), mmap_mode="r")
    changed = layer(current, "heights") != layer(prior, "heights")
    check(0 < changed.sum() == terrain[change_key], "Different terrain revision")
    for name in ("road", "bases"):
        check(not np.any(changed & (layer(prior, name) > 0)), "Shore edits reached " + name)


def stage(args, folder):
    work = args.work
    inputs, info, hashes, manifest = unpack_map(args.baseline, folder)
    previous_work = WORK if args.basin else BASE / "river-erosion"
    if args.basin:
        check(info["sha256"] == BASIN_PARENT and info["baseline_sha256"] ==
              "dffdab938df584eae87ea0ca84b22dad7b098e4ab76f23ad08848066f01b9ca4" and
              info["archive"].endswith(".37.mjolnir"), "The basin requires the finished outlet and its accepted water settings")
    else:
        check(info["sha256"] == PARENT, "The apron was surveyed against a different map")
    original = dict(hashes)

    def replace(name, path):
        dest = inputs / stage_name(name)
        check(name in original, "Unexpected map member " + name)
        shutil.copyfile(path, dest)
        hashes[name] = sha(dest)

    terrain = jsonfile(work / "terrain/headwater-terrain.receipt.json")
    dressing = jsonfile(work / "dressing/dressing-receipt.json")
    native = jsonfile(work / "native/landscape-collision.json")
    water_dir = work / "water-fix"
    water = jsonfile(water_dir / "receipt.json")
    check(sha(water_dir / "flux.json") == water["descriptor_sha256"] and
          sha(water_dir / "river_flux_readback.lua") == water["gpu_probe_sha256"],
          "The water output or its live readback changed after baking")
    height_sha = sha(work / "terrain/runtime-master.json")
    check(height_sha == terrain["runtime_manifest_sha256"] == water["inputs"]["terrain"] == dressing["terrain_sha256"] and
          sha(work / "terrain/terrain.geometry.json") == water["inputs"]["geometry"] and
          sha(work / "terrain/runtime-master.r16") == terrain["r16_sha256"] == native["terrain_r16_sha256"],
          "Terrain, collision and water inputs disagree")
    checked_grading(work, terrain, previous_work, "basin_changed_vertices_vs_previous" if args.basin else "apron_changed_vertices_vs_previous")
    for name, digest in dressing["files_sha256"].items():
        check(sha(work / "dressing" / name) == digest, "Unverified instance file " + name)
    check(native["dressing_ledger_sha256"] == sha(work / "dressing/decor-moves.json") and
          water["inputs"]["rocks"] == sha(work / "dressing/flow-rocks.json") and
          water["same_wet_component"], "Flow obstacles differ from the scene")
    physics = jsonfile(work / native["physical_queries"])
    check(physics["root_and_definition_havok_queries"] and
          physics["compiled_bsp_sha256"] == sha(work / "native/physics/pwr.sbsp") == native["sbsp"],
          "Unverified native collision")
    bank = WORK / "finish37" if args.basin else work / "bank"
    surface = jsonfile(bank / "surface-verified.json")
    planting = jsonfile(bank / "editor-verified.json")
    design = jsonfile(bank / "survey.json")
    if args.basin:
        join = jsonfile(work / "native/physics/seam-survey.json")
        verges = jsonfile(work / "basin-verified.json")
        check(join["same_perimeter"] and join["count_join_larger_than_2cm"] == 0 and
              join["preserved_terrain_vertices_byte_identical"], "The two physical surfaces do not meet")
        check(verges["added"] == verges["placement"]["total"] and verges["added"] > 0 and
              verges["placement"]["terrain_manifest_sha256"] == height_sha and
              verges["plan_sha256"] == sha(work / "basin-plants.json"),
              "Shore planting was not verified on this basin")
        check(terrain["closed_sill_containment_verified"] and terrain["connected_lake_area_m2"] > terrain["previous_connected_lake_area_m2"] and
              terrain["apron_support_points_checked"] > 0 and terrain["obstacle_hull_vertices_checked"] > 0 and
              terrain["spring_grade_reserved_points"] > 0 and
              jsonfile(bank / "receipt.json")["parent_map_sha256"] == info["baseline_sha256"],
              "Basin containment or the outlet finish is unverified")
    else:
        check(surface["surface_sha256"] == sha(bank / "surface.json") and
              surface["support_sha256"] == sha(bank / "support.npz") and
              surface["triangles"] == design["faces"] and
              planting["transforms_read_back"] == design["planting"] and
              planting["source_plan_sha256"] == sha(bank / "planting.json") and
              design["terrain_sha256"] == native["terrain_r16_sha256"] and
              design["rock_ledger_sha256"] == native["dressing_ledger_sha256"],
              "Saved bank, plant instances and physical support differ from the surveyed design")

    changed_packages = {}
    cooked = work / "native/map-input"
    for stem in (WORLD, LAND):
        before = world_entries(inputs / (stem + ".utoc"))
        after = world_entries(cooked / (stem + ".utoc"))
        added = set(after) - before.keys()
        check(before.keys() <= after.keys(), "Removed a shipping package from " + stem)
        changed = sorted(k for k in before if before[k] != after[k])
        if stem == WORLD:
            names = {Path(k).name.lower() for k in changed}
            check(not added and {"pwr.umap", "bsp_01_1_start-scenario_structure_bsp.ubulk"} <= names <= VERIFY_WORLD,
                  "Unexpected change to native gameplay tags")
        else:
            check({k.lower() for k in changed} <= LANDFILES and any(k.endswith(".umap") for k in changed),
                  "Unexpected change to native shoreline assets")
            assets = {"mjolnir/grasspilot/playable/" + prefix + "_pwr_outletalluvium" + ext
                      for prefix in ("sm", "m") for ext in (".uasset", ".ubulk")}
            if args.basin:
                check(not added and {p for p in assets if p.endswith(".uasset")} <= {k.lower() for k in before},
                      "Basin changed the sealed bank mesh or material inventory")
            else:
                check({p for p in assets if p.endswith(".uasset")} <= {k.lower() for k in added} <= assets,
                      "Missing or unexpected new shoreline content")
        changed_packages[stem] = {"changed": changed, "added": sorted(added)}
        for ext in (".utoc", ".ucas"):
            filename = stem + ext
            check(sha(cooked / filename) == native["native_members"][filename], "Unverified cook " + filename)
            replace("content/" + filename, cooked / filename)

    level_path = inputs / "pwr.level.json"
    level = jsonfile(level_path)
    level["decor"] = checked_scene(work, level, dressing, previous_work)
    previous = level["flux"]
    flux = jsonfile(water_dir / "flux.json")
    check([d["id"] for d in flux["domains"]] == ["upper_river", "lower_lake"] and
          flux["domains"][1] == previous["domains"][1], "Changed southeast water")
    upper, old = flux["domains"][0], previous["domains"][0]
    check({k for k in upper.keys() | old.keys() if upper.get(k) != old.get(k)} <= {"state", "provenance", "sources"} and
          {k: v for k, v in flux.items() if k != "domains"} == {k: v for k, v in previous.items() if k != "domains"},
          "Unexpected change to the Timberland surface or water-domain layout")
    for domain in flux["domains"]:
        state = jsonfile(water_dir / "flux_state" / domain["id"] / "state.json")
        check(state == domain["state"], "Baked state differs from the map")
        verify_state_files(water_dir, state)
    check({"map/" + name for name in water["files"]} == {name for name in original if name.startswith("map/flux_state/")},
          "Incomplete water-state inventory")
    for name, digest in water["files"].items():
        check(sha(water_dir / name) == digest, "Unverified water file " + name)
        member = "map/" + name
        if name.startswith("flux_state/upper_river/"):
            replace(member, water_dir / name)
        else:
            check(name.startswith("flux_state/lower_lake/") and digest == original[member], "Changed water " + name)
    level["flux"] = flux
    write_json(level_path, level)
    hashes["map/level.json"] = sha(level_path)
    replace("map/foliage.bin", work / "dressing/foliage.bin")
    modified = sorted(k for k in hashes if hashes[k] != original[k])
    check(all("map/flux_state/upper_river/" + n in modified for n in ("ground.exr", "height.exr", "velocity.exr", "state.json")),
          "Missing revised north-river state")
    seal_release(args, folder, inputs, info, hashes, manifest, {
        "modified_members": modified, "world_packages": changed_packages, "level_sections": ["decor", "flux"],
        "headwater": {"terrain": terrain, "dressing": dressing, "water": water, "native": native,
                      "bank": design, "instanced_planting": planting, "bank_mesh": surface,
                      **({"basin_planting": verges, "basin_collision_perimeter": join} if args.basin else {})},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--basin", action="store_true", help="Integrate the contained basin on the sealed .37 outlet")
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    args = parser.parse_args()
    revision = "38" if args.basin else "36"
    args.work = args.work or (BASE / "river-basin" if args.basin else WORK)
    args.baseline = args.baseline or (WORK / "saturday.37" if args.basin else BASE / "river-erosion/saturday.35")
    args.out = args.out or args.work / ("saturday." + revision)
    args.version = args.version or ("0.1.0-playtest." + revision)
    if args.out.exists():
        parser.error("Choose a new release folder")
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        folder = Path(temp) / "release"
        folder.mkdir()
        stage(args, folder)
        folder.rename(args.out)
    print(args.out)
