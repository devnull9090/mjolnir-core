"""Check and seal the lake contact and shore-plant draw distances for the .39 rehearsal."""
import argparse
import copy
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from scipy.ndimage import distance_transform_edt

from bases_v1.stage_base_polish import seal_release, unpack_map
from stage_apron_finish import asset_layout
from stage_world_playtest import LAND, ROOT, WORLD, jsonfile, load_container, read_chunk, sha, stage_name, world_entries, write_json

sys.path[:0] = [str(ROOT / "tools/level"), str(Path(__file__).resolve().parent / "terrain")]
from audit_flux_state import texture
from flux_heightfield import state_matches, verify_state_files
from outlet_apron import coordinates

WORK = ROOT / "out/pwr/river-basin"
PARENT = "6cbce87c3f0153aaf46538eea8db27e1cb1acbbe122eca54c65c3275ada3b60f"
UPPER = "flux_state/upper_river/"
ALLOWED_MAPS = {LAND: "Levels/Halo1/Solo/LPE/LPE", WORLD: "Meteorite/Content/Levels/Halo1/Solo/PWR/PWR"}


def check(value, message):
    if not value:
        raise ValueError(message)


def check_dry_texels(before, after, velocity, state):
    old, new, depth = texture(before), texture(after), texture(velocity)[:, :, 2]
    check(old.shape == new.shape == (*depth.shape, 4) and np.isfinite(new).all(), "Invalid upper height texture")
    check(np.array_equal(old[:, :, 2:], new[:, :, 2:]), "Contact pass changed the packed height B/A channels")
    changed = np.any(old != new, axis=-1)
    check(changed.any() and not np.any(changed & (depth != 0)), "Contact pass touched wet height samples")
    spacing = state["cell"] / 100
    cols = state["centre"][0]/100 + (np.arange(state["res"][0]) + .5 - state["res"][0]/2)*spacing
    rows = -state["centre"][1]/100 - (np.arange(state["res"][1]) + .5 - state["res"][1]/2)*spacing
    x, y = np.meshgrid(cols, rows)
    forward, _ = coordinates(np.stack((x, y), axis=-1))
    lake_height = (old[:, :, 0] + state["capture"])/100
    pool = (depth > 1.8) & (abs(lake_height - 142.4) < .04) & (forward > 54) & (x > -490) & (x < -240) & (y > 815)
    distance = distance_transform_edt(~pool)*spacing
    check(np.all((distance[changed] < 28) & (forward[changed] > 55)), "Dry height changes extend beyond the shore")
    return {"changed_zero_depth_texels": int(changed.sum()), "wet_texels_checked": int((depth > 0).sum()),
            "farthest_changed_texel_from_pool_m": float(distance[changed].max())}


def visual_trial(repair, height_sha):
    trial = WORK.parent / "alpine-target/bench/river-basin-38/water"
    photos = jsonfile(trial / "photos.json")
    proof = jsonfile(trial / "shore-trial-proof.json")
    measures = jsonfile(trial / "shore-trial-measurements.json")
    pose = proof["pose"]
    check(photos["release"]["map_sha256"] == PARENT and pose == photos["views"]["outlet"] and
          proof["height_sha256"] == height_sha and proof["descriptor_sha256"] == repair["descriptor_sha256"],
          "Live .38 comparison does not reference the packed repair")
    frames = {}
    for mode in ("control", "corrected", "restored"):
        frame = proof["frames"][mode]
        digest = sha(trial / ("shore-trial-" + mode + ".png"))
        check(digest == frame["sha256"] == measures["images"][mode] and
              all(frame[k][:6] == pose for k in ("camera_before", "camera_after")),
              "Changed trial frame or camera in " + mode)
        frames[mode] = digest
    for mode, marker in (("apply", "PWR_SHORE_TEST PASS"), ("restore", "PWR_SHORE_RESTORED PASS")):
        check(marker in (trial / ("shore-trial-" + mode + ".log")).read_text(), "Missing live " + mode)
    return {"map_sha256": PARENT, "camera": pose, "images_sha256": frames, "measurements": measures,
            "trial_proof_sha256": sha(trial / "shore-trial-proof.json")}


def apply_water(work, folder, inputs, hashes):
    repair = jsonfile(folder / "receipt.json")
    current = jsonfile(inputs / "pwr.level.json")
    before = current["flux"]
    after = jsonfile(folder / "flux.json")
    source_descriptor = work / "water-fix/flux.json"
    check(jsonfile(source_descriptor) == before and sha(source_descriptor) == repair["dry_contact"]["source_descriptor_sha256"],
          "The original water descriptor differs from sealed .38")
    check(sha(folder / "flux.json") == repair["descriptor_sha256"] and
          sha(folder / "river_flux_readback.lua") == repair["gpu_probe_sha256"], "Stale repair receipt or readback")
    check([d["id"] for d in before["domains"]] == ["upper_river", "lower_lake"], "Unexpected .38 domain inventory")
    upper = before["domains"][0]
    check(upper["surface_scalars"] == {"DetailWaveHeight": 3}, "The .37 optical setting is missing")
    expected = copy.deepcopy(before)
    new = expected["domains"][0]
    source = Path(__file__).resolve().parent / "terrain/repair_basin_shore.py"
    new["provenance"]["dry_shore_height_source_sha256"] = sha(source)
    state = new["state"]
    state["provenance"] = dict(new["provenance"])
    state["height_sha256"] = sha(folder / state["height"])
    check(after == expected and jsonfile(folder / (UPPER + "state.json")) == state and state_matches(state, new),
          "The correction changed water settings outside the upper height map and provenance")
    verify_state_files(folder, state)
    files = repair["files"]
    check({"map/" + name for name in files} == {name for name in hashes if name.startswith("map/flux_state/")},
          "Unexpected candidate water inventory")
    delta = set()
    for name, digest in files.items():
        check(sha(folder / name) == digest, "Water receipt mismatch for " + name)
        if digest != hashes["map/" + name]:
            delta.add(name)
    check(delta == {UPPER + "height.exr", UPPER + "state.json"}, "Water payload differs outside dry heights")
    result = check_dry_texels(inputs / state["height"], folder / state["height"], inputs / state["velocity"], state)
    check(result["changed_zero_depth_texels"] == repair["dry_contact"]["changed_cells"] and
          repair["dry_contact"]["wet_state_changes"] == 0, "Different dry contact survey")
    for name in sorted(delta):
        member = "map/" + name
        destination = inputs / stage_name(member)
        shutil.copyfile(folder / name, destination)
        hashes[member] = sha(destination)
        check(hashes[member] == files[name], "Staging readback failed for " + name)
    current["flux"] = after
    write_json(inputs / "pwr.level.json", current)
    hashes["map/level.json"] = sha(inputs / "pwr.level.json")
    return {"checks": result, "recipe_sha256": sha(folder / "receipt.json"), "gpu_probe_sha256": repair["gpu_probe_sha256"],
            "descriptor_sha256": repair["descriptor_sha256"], "contact": repair["dry_contact"],
            "source_baseline_descriptor_sha256": sha(source_descriptor), "live_comparison": visual_trial(repair, state["height_sha256"])}


def apply_plants(folder, inputs, hashes, previous):
    proof = jsonfile(folder / "receipt.json")
    check(proof["parent_map_sha256"] == PARENT and proof["retained_bsp_sha256"] == previous["headwater"]["native"]["sbsp"],
          "The shore plants were cooked against another map or BSP")
    editor = proof["editor_readback"]
    check(jsonfile(folder / "editor-verified.json") == editor, "The reopened editor proof differs")
    names = jsonfile(folder / "protected-names.json")
    check(names == {"prefix": "PWRShore_", "components": 24}, "Local components lack unique loader names")
    groups = editor["groups"]
    counts = jsonfile(folder.parent.parent / "basin-plant-counts.json")
    check(set(groups) == {"fine_a", "fine_b", "sedge"}, "Unexpected plant species in the shore fix")
    for species, group in groups.items():
        cohorts = group["cohorts"]
        check(group["count"] == counts[species]["added"] == sum(c["count"] for c in cohorts) and
              group["retained_source_instances"] == counts[species]["before"] and
              all(0 < c["start_m"] < c["end_m"] and c["end_m"] > group["original_cull_m"][1] for c in cohorts),
              "Reopened range or instance count differs for " + species)
    check(sum(len(g["cohorts"]) for g in groups.values()) == editor["max_new_hism"] == 24 and
          sum(g["count"] for g in groups.values()) == editor["points"] == 3646,
          "Incorrect total plant or HISM count")
    candidate = folder / "map-input"
    files = proof["native_members"]
    check(set(files) == {stem + ext for stem in (WORLD, LAND) for ext in (".utoc", ".ucas")} ==
          {p.name for p in candidate.iterdir()}, "Unexpected landscape cook inventory")
    packages = {}
    for stem, map_path in ALLOWED_MAPS.items():
        toc = stem + ".utoc"
        layout = asset_layout(stem, inputs / toc)
        before_shaders = shader_chunks(inputs / toc)
        before = world_entries(inputs / toc)
        for ext in (".ucas", ".utoc"):
            name = stem + ext
            shutil.copyfile(candidate / name, inputs / name)
            digest = sha(inputs / name)
            check(files[name] == digest, "Shore plant package differs from receipt: " + name)
            hashes["content/" + name] = digest
        after = world_entries(inputs / toc)
        check(asset_layout(stem, inputs / toc) == layout and before.keys() == after.keys(), "Native inventory changed")
        check(before_shaders == shader_chunks(inputs / toc), "Shore foliage changed shader bytecode")
        changed = {key: [before[key], after[key]] for key in before if before[key] != after[key]}
        check(map_path + ".umap" in changed and changed.keys() <= {map_path + ".umap", map_path + ".ubulk"},
              "Unexpected native change in " + stem)
        packages[stem] = {"changed": changed, "preserved_count": len(before) - len(changed),
                          "unchanged_shader_chunks": len(before_shaders)}
    return {"receipt": proof, "receipt_sha256": sha(folder / "receipt.json"), "world_packages": packages,
            "protected_component_names": names, "live_readback_sha256": sha(folder / "shore-foliage-readback.lua")}


def shader_chunks(toc):
    container = load_container(toc)
    return {(c.chunk_type, c.chunk_id, c.chunk_index): hashlib.sha256(read_chunk(container, c)).digest()
            for c in container.chunks if c.type_name in ("ShaderCode", "ShaderCodeLibrary")}


def run(args, folder):
    inputs, previous, hashes, manifest = unpack_map(args.baseline, folder)
    check(previous["sha256"] == PARENT, "The contact fix requires sealed .38")
    original = dict(hashes)
    water = apply_water(args.work, args.work / "shore-contact/water-fix", inputs, hashes)
    print("Dry shore checks:", water["checks"], flush=True)
    if args.water_check:
        return
    art = apply_plants(args.work / "shore-contact/native", inputs, hashes, previous)
    if args.check_only:
        print("Shore plant changes:", art["world_packages"], flush=True)
        return
    seal_release(args, folder, inputs, previous, hashes, manifest, {
        "modified_members": sorted(k for k in hashes if hashes[k] != original[k]),
        "level_sections": ["flux"], "shore_contact": water, "shore_plant_draw_distances": art,
        "retained_bsp_sha256": previous["headwater"]["native"]["sbsp"],
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=WORK / "saturday.38")
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--out", type=Path, default=WORK / "saturday.39")
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    parser.add_argument("--water-check", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    args.version = "0.1.0-playtest.39"
    if args.out.exists() and not (args.water_check or args.check_only):
        parser.error("Choose a new release folder")
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
        folder = Path(temporary) / "release"
        folder.mkdir()
        run(args, folder)
        if not (args.water_check or args.check_only):
            folder.rename(args.out)
            print(args.out)
