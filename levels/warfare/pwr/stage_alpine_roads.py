"""Seal the UE alpine landscape and its ten native obstacles into the .13 playtest.

Run after a successful isolated Unreal cook and the verified collision build.
Each candidate is written to a temporary directory and made visible only after
the map, both paired runtimes and their gameplay variants pass readback.
"""

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

from stage_world_playtest import (
    ROOT,
    LAND,
    WORLD,
    SURFACES,
    jsonfile,
    sha,
    world_entries,
    write_json,
    load_container,
    read_chunk,
    verify_world,
)
from stage_ground_life import substitute_field, verify_pixels, OODLE
from package_landscape_revision import build, run
from bases_v1.stage_base_polish import unpack_map, seal_release
from visual_dressing.verify_distance_terrain import shader_receipt, load_name_batch
import struct

DRESSING = Path(__file__).resolve().parent / "visual_dressing"
sys.path.insert(0, str(DRESSING))
import verify_distance_colonies as hism
from verify_render_only_hism_cook import identity_ancestors, matrices, number, package

BASE = ROOT / "out/pwr/ground-life/saturday.13"
BASE_HASH = "393ee1f857746222f975d57088179357aa936540434cbefe1f6a04558d3b4cc7"
BASE_BSP = ROOT / "out/pwr/base-polish/rear-gate/physics/pwr.sbsp"
ART = ROOT / "out/pwr/alpine-target"
SBSP = "bsp_01_1_start-scenario_structure_bsp"
BSP_NAMES = {SBSP + ".uasset", SBSP + ".ubulk"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def compose_level(args):
    base = jsonfile(args.baseline / "map-input/pwr.level.json")
    level = deepcopy(base)
    (actor,) = jsonfile(args.ridges / "runtime_decor.json")["decor"]
    (row,) = [
        i
        for i, item in enumerate(level["decor"])
        if item.get("id") == actor["id"] == "pwr_distant_apron"
    ]
    old_actor = level["decor"][row]
    require(
        actor["materials"]
        == old_actor["materials"]
        == [jsonfile(args.ridges / "geology.material.json")],
        "Ridge lost its original material",
    )
    require(
        {k for k in actor.keys() | old_actor.keys() if actor.get(k) != old_actor.get(k)}
        <= {"pos", "scale"},
        "Ridge asset identity changed",
    )
    level["decor"][row] = actor
    env = jsonfile(args.art / "light/environment.json")
    for key in set(base["environment"]) - {"sun", "skylight"}:
        require(
            env[key] == base["environment"][key],
            "Unexpected environment change: " + key,
        )
    require(
        set(env) - set(base["environment"]) <= {"haze"},
        "Unexpected environment section",
    )
    level["environment"] = env
    require(
        {k for k in level if level[k] != base[k]} <= {"environment", "decor"},
        "Gameplay data changed",
    )
    write_json(args.art / "pwr.level.json", level)
    # The native scenario writer consumes only its own schema. The archive carries
    # these render/runtime sections from the original map in their entirety.
    scenario = {
        k: v
        for k, v in level.items()
        if k not in {"landscape", "waterfalls", "flux", "effects"}
    }
    write_json(args.art / "native-level.json", scenario)
    return level


def control_world(args):
    source = args.native / "native.json"
    if not source.exists():
        build(
            argparse.Namespace(
                staged=args.staged,
                baseline=args.baseline,
                level=args.art / "native-level.json",
                bsp=BASE_BSP,
                paks=args.paks,
                cook_log=args.art / "cook.log",
                out=args.native,
                cli=args.bake_cli,
            )
        )
    require(
        jsonfile(source)["sealed_baseline"] == BASE_HASH, "Mismatched control release"
    )
    for stem in ("global", "pakchunk965-Windows"):
        for ext in (".utoc", ".ucas"):
            leaf = stem + ext
            require(
                sha(args.staged / leaf) == sha(args.native / "stock" / leaf),
                "Control targeted a different cook: " + leaf,
            )


def cook_collision(args, control, scratch, base_bsp=BASE_BSP, expected_objects=10,
                   structural_folder=None, previous_bsp=None):
    structural_folder = structural_folder or args.art / "verges"
    physics_dir = structural_folder / "physics"
    candidate = physics_dir / "pwr.sbsp"
    proof = jsonfile(physics_dir / "collision-proof.json")
    require(
        proof["base_sbsp"] == sha(previous_bsp or base_bsp)
        and proof["sbsp"] == sha(candidate)
        and proof["source_structural_sha256"]
        == sha(structural_folder / "structural.json")
        and proof["source_arrays_prefix_exact"]
        and proof["root_and_definition_havok_verified_per_face"]
        and len(proof["objects"]) == expected_objects
        and proof["added_surfaces"] > 0,
        "Unverified collision cook",
    )
    out = scratch / "bsp-world"
    run(
        [
            args.bake_cli,
            "level",
            "bake",
            args.art / "native-level.json",
            "--paks",
            args.paks,
            "--standalone",
            "PWR",
            "--bsp",
            "8=" + str(candidate.resolve()),
            "--out-dir",
            out,
            "--world",
            args.native / "LPE.umap",
        ],
        scratch / "collision-bake.log",
    )
    before = world_entries(control)
    cooked = out / (WORLD + ".utoc")
    after = world_entries(cooked)
    require(set(before) == set(after), "Native collision changed world inventory")
    # Compare the non-sealed native control bake as scenario data is restored
    # separately by the original landscape packager.
    native_control = args.native / "world-bake" / cooked.name
    generated = world_entries(native_control)
    changes = {k for k in after if after[k] != generated[k]}
    require(
        {Path(k).name.lower() for k in changes} == BSP_NAMES,
        "Collateral native changes: " + str(changes),
    )
    (bulk,) = [k for k in changes if k.endswith(".ubulk")]

    def body_adjust(raw, toc):
        owner = load_container(toc)
        octets = read_chunk(owner, owner.chunks[owner.files[bulk]])
        wanted = np.memmap(raw, "u1", "r")
        require(len(octets) == len(wanted), "Collision payload length mismatch")
        encoded = np.frombuffer(octets, "u1")
        ix = np.flatnonzero(encoded != wanted)
        require(0 < len(ix) <= 16, "Unexpected native duplicate-shell adjustment")
        return [(int(i - ix[0]), int(wanted[i]), int(encoded[i])) for i in ix]

    require(
        body_adjust(base_bsp, native_control) == body_adjust(candidate, cooked),
        "Wrong native duplicate-shell adjustment",
    )
    temp = scratch / "collision-members"
    container = load_container(cooked)
    for key in changes:
        dest = temp / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(read_chunk(container, container.chunks[container.files[key]]))
    final = scratch / "complete-world"
    run(
        [ROOT / "target/release/examples/replace_members.exe", control, temp, final],
        scratch / "seal-bsp.log",
    )
    final = final / control.name
    require(
        world_entries(final)
        == {p: after[p] if p in changes else h for p, h in before.items()},
        "Collision assembly disturbed protected native scenario",
    )
    return final, proof, sorted(changes)


def inspect_foliage(
    args, current, scratch, component_prefix="PWRVerge_", *, folder=None, split=None, trimmed=None, extra_actors=()
):
    folder = folder or args.art / "verges"
    spec = jsonfile(folder / "verges.json")
    existing = args.baseline / "map-input" / (WORLD + ".utoc")

    def audit(toc, tag):
        rawfile = hism.world_from_container(toc, scratch / (tag + ".umap"))
        raw = rawfile.read_bytes()
        exports = hism.decode(rawfile, hism.GAME)["exports"]
        byid = {r["export"]: r for r in exports}
        legacy = {}
        new = {}
        split_groups = {}
        adjusted = {}
        groups = {
            component_prefix + g["key"]: (i, g) for i, g in enumerate(spec["groups"], 1)
        }
        for row in exports:
            if row["class"] != "HierarchicalInstancedStaticMeshComponent":
                continue
            props = row["properties"]
            count = int(number(props["NumBuiltInstances"]))
            mesh = package(row, "StaticMesh")
            m = hism.native_matrices(raw, row, count)
            key = (row["outer"], row["name"])
            if split and key in split:
                split_groups[key] = m
            if trimmed and key in trimmed:
                adjusted[key] = m
            if row["outer"] in extra_actors:
                # Each new actor has its own complete matrix/cull/material validation.
                require(tag == "candidate-PWR", "New vegetation actor was already present in the control")
                continue
            if split and row["outer"] == split[1][0]:
                # This separately audited actor owns the two relocated instances.
                continue
            if row["outer"] != spec["actor"]:
                legacy[key] = (
                    mesh,
                    count,
                    hashlib.sha256(m.tobytes()).hexdigest(),
                    package(row, "OverrideMaterials[0]"),
                    props.get("InstanceEndCullDistance"),
                    props.get("InstanceStartCullDistance"),
                    props.get("bEvaluateWorldPositionOffset"),
                )
                continue
            i, g = groups[row["name"]]
            side = folder / (spec["file"] + f".xf{i}")
            require(
                mesh == g["mesh"].split(".")[0]
                and count == g["count"]
                and sha(side) == g["transform_sha256"],
                "Native verge mesh or count changed",
            )
            require(
                [
                    int(number(props[k]))
                    for k in ("InstanceStartCullDistance", "InstanceEndCullDistance")
                ]
                == g["cull"],
                "Native cull changed",
            )
            identity_ancestors(row, byid)

            def ordered(v):
                return v[np.lexsort(tuple(v[:, 3, j] for j in (2, 1, 0)))]

            diff = np.abs(ordered(m) - ordered(matrices(side)))
            pos = float(diff[:, 3, :3].max())
            basis = float(diff[:, :3, :3].max())
            require(
                pos < 0.04 and basis < 0.00004,
                "Verge position or basis changed: " + row["name"],
            )
            new[row["name"]] = dict(count=count, mesh=mesh, max_cm=pos, max_basis=basis)
        return legacy, new, split_groups, adjusted

    a, base_new, original, earlier = audit(existing, "baseline-PWR")
    b, new, revised, later = audit(current, "candidate-PWR")
    if trimmed:
        require(trimmed.keys() == earlier.keys() == later.keys(), "Missing a trimmed native vegetation group")
        for key, removed in trimmed.items():
            before, after = earlier[key], later[key]
            # Authored placements and UE's cooked float matrices differ by a few ULPs.
            # Use tolerance only to locate the surveyed removals, then check every
            # retained native matrix byte for byte regardless of hierarchy reordering.
            require(0 < len(removed) < len(before) and len(before) == len(after) + len(removed), "Wrong native removal count " + repr(key))
            keep = np.ones(len(before), dtype=bool)
            for matrix in removed:
                same_position = np.max(np.abs(before[:,3,:3] - matrix[3,:3]),axis=1) < .04
                same_basis = np.max(np.abs(before[:,:3,:3] - matrix[:3,:3]),axis=(1,2)) < .00004
                matches = np.flatnonzero(same_position & same_basis & keep)
                require(len(matches) == 1, "Missing or ambiguous original surveyed native transform " + repr(key))
                keep[matches[0]] = False
            require(sorted(row.tobytes() for row in before[keep]) == sorted(row.tobytes() for row in after), "Retained native vegetation transform changed " + repr(key))
            require(a[key][0] == b[key][0] and a[key][3:] == b[key][3:], "Trim altered a vegetation asset, cull or material")
            a[key] = b[key]

    if split:
        stock, moved = split
        require(
            original.keys() == {stock} and revised.keys() == {stock, moved},
            "Outcrop split actor mismatch",
        )
        require(
            len(original[stock]) == 3
            and len(revised[stock]) == 1
            and len(revised[moved]) == 2,
            "Outcrop split count mismatch",
        )
        source = sorted(original[stock], key=lambda x: x[3, 0])
        # The Teton rock lies east of the two Southwest cut faces.
        require(np.array_equal(source[-1], revised[stock][0]), "Teton outcrop moved")
        delta = np.abs(
            np.asarray(source[:-1]) - sorted(revised[moved], key=lambda x: x[3, 0])
        )
        require(
            delta[:, 3, :3].max() < 0.03 and delta[:, :3, :3].max() < 2e-5,
            "Southwest outcrops moved",
        )
        old, new_stock = a[stock], b[stock]
        require(
            old[0] == new_stock[0] and old[3:] == new_stock[3:],
            "Existing outcrop mesh, material or culling changed",
        )
        a[stock] = new_stock
    require(
        not base_new and a == b and len(new) == len(spec["groups"]),
        "Existing HISM or coverage changed",
    )
    return dict(
        preserved_components=len(a),
        preserved_instances=sum(v[1] for v in a.values()),
        added_components=new,
        added_instances=sum(v["count"] for v in new.values()),
    )


def stage(args, out):
    inputs, old, expected, manifest = unpack_map(args.baseline, out)
    require(old["sha256"] == BASE_HASH, "Expected verified .13 release")
    control = args.native / "world-final" / (WORLD + ".utoc")
    world_proof = verify_world(inputs / (WORLD + ".utoc"), control)
    old_land = inputs / (LAND + ".utoc")
    (land,) = (args.native / "land").glob("*.utoc")
    a, b = world_entries(old_land), world_entries(land)
    added = set(b) - set(a)
    require(
        set(a) <= set(b)
        and {Path(p).name for p in added}
        == {"T_PWR_AlpineRoadbed.uasset", "T_PWR_AlpineRoadbed.ubulk"},
        "Unexpected cooked asset inventory: " + str(added),
    )
    changed = sorted(p for p in a if a[p] != b[p])
    allowed = {
        "M_PWRPilot.uasset",
        "T_PWR_ApronField.uasset",
        "T_PWR_ApronField.ubulk",
        "T_LandBase.uasset",
        "T_LandBase.ubulk",
        "LPE.umap",
        "LPE.ubulk",
        "MI_PWR_ExteriorCliffs_9c8b739f48f3.uasset",
    }
    for name in changed:
        require(
            Path(name).name in allowed or name.endswith(".ushaderbytecode"),
            "Out of scope cooked change " + name,
        )
    require(
        {"M_PWRPilot.uasset", "LPE.umap", "T_PWR_ApronField.ubulk"}
        <= {Path(p).name for p in changed}
        and any(p.endswith(".ushaderbytecode") for p in changed),
        "Cook omitted terrain shader, geology or foliage",
    )
    shaders = shader_receipt(land, OODLE)
    prior_shaders = shader_receipt(old_land, OODLE)
    for target in ("master", "landscape_world"):
        require(
            set(shaders[target]) != set(prior_shaders[target]),
            "Cook retained the old shader for " + target,
        )
        require(
            max(row.get("PS", 0) for row in shaders[target].values())
            >= max(row.get("PS", 0) for row in prior_shaders[target].values()),
            "Cook dropped a landscape pixel shader permutation",
        )
    c = load_container(land)
    (key,) = [k for k in c.files if k.endswith("/M_PWRPilot.uasset")]
    mat = read_chunk(c, c.chunks[c.files[key]], oodle_roots=[OODLE])
    names = load_name_batch(mat, struct.unpack_from("<i", mat, 48)[0])[0]
    require(
        "/Game/MJOLNIR/GrassPilot/Playable/T_PWR_AlpineRoadbed" in names,
        "Master lacks native alpine field",
    )
    art = jsonfile(args.ridges / "package.receipt.json")
    rr = jsonfile(args.ridges / "roundtrip.verification.json")
    contacts = jsonfile(args.ridges / "contact.verification.json")
    require(
        rr["package_receipt_sha256"] == sha(args.ridges / "package.receipt.json")
        and rr["geometry_receipt_sha256"]
        == contacts["geometry_sha256"]
        == sha(args.ridges / "receipt.json")
        and contacts["roundtrip_sha256"]
        == sha(args.ridges / "roundtrip.verification.json")
        and rr["triangles_do_not_enter_playable_square"],
        "Range lost its verified placement or contacts",
    )
    vista = Path(art["container_stem"]).with_suffix(".utoc")
    for ext in (".utoc", ".ucas"):
        require(
            art["files"][ext]["sha256"] == sha(vista.with_suffix(ext)),
            "Stale mountain geometry",
        )
    with tempfile.TemporaryDirectory(dir=out) as temp:
        tmp = Path(temp)
        surface = substitute_field(
            args.staged / "pakchunk956-Windows.utoc", inputs / (SURFACES + ".utoc"), tmp
        )
        surface_files = world_entries(surface)
        shared = set(b) & set(surface_files)
        require(
            any(k.endswith("/T_PWR_ApronField.ubulk") for k in shared)
            and all(b[k] == surface_files[k] for k in shared),
            "Mount-order-dependent ridge field",
        )
        textures = verify_pixels(args, tmp / "textures", land, surface)
        leaf = "T_PWR_AlpineRoadbed"
        for lod in (0, 2, 3):
            dest = tmp / "textures" / f"{leaf}-{lod}.png"
            subprocess.run(
                [
                    args.cli,
                    "texture",
                    "export",
                    "--paks",
                    dest.parent,
                    "--asset",
                    leaf,
                    "--mip",
                    str(lod),
                    "--out",
                    dest,
                ],
                check=True,
            )
            got = np.asarray(Image.open(dest).convert("RGBA"))
            reference = np.asarray(
                Image.open(args.art / "earth/alpine-roadbed.png").convert("RGBA")
            )
            size = (reference.shape[1] >> lod, reference.shape[0] >> lod)
            wanted = np.stack(
                [
                    np.asarray(Image.fromarray(ch).resize(size, Image.Resampling.BOX))
                    for ch in reference.transpose(2, 0, 1)
                ],
                axis=-1,
            )
            error = int(np.max(np.abs(got.astype(int) - wanted)))
            require(
                got.shape == wanted.shape and error <= (1 if lod else 0),
                "Roadbed does not match authored mip " + str(lod),
            )
            textures[leaf + f"-mip{lod}"] = dict(size=size, max_channel_error=error)
        finished, physics, bsp_members = cook_collision(args, control, tmp)
        foliage = inspect_foliage(args, finished, tmp)
        (old_vista,) = inputs.glob("pakchunk963-*.utoc")
        for src, dst in (
            (surface, inputs / (SURFACES + ".utoc")),
            (vista, old_vista),
            (land, old_land),
            (finished, inputs / (WORLD + ".utoc")),
        ):
            for ext in (".utoc", ".ucas"):
                target = dst.with_suffix(ext)
                shutil.copyfile(src.with_suffix(ext), target)
                expected["content/" + target.name] = sha(target)
        write_json(inputs / "pwr.level.json", compose_level(args))
        expected["map/level.json"] = sha(inputs / "pwr.level.json")
        updated = world_entries(inputs / (WORLD + ".utoc"))
        prior = world_entries(args.baseline / "map-input" / (WORLD + ".utoc"))
        native_changes = {k for k in updated if updated[k] != prior[k]}
        require(
            native_changes == set(world_proof["changed"]) | set(bsp_members),
            "Unauthorized world members changed",
        )
        world_proof["changed"] = sorted(native_changes)
        world_proof["preserved"] = {
            k: v for k, v in prior.items() if k not in native_changes
        }
        revision = dict(
            world_packages=world_proof,
            terrain_assets_added=sorted(added),
            terrain_assets_changed=changed,
            level_sections=["decor", "environment"],
            collision=physics,
            baseline_collision_sha256=old["collision"]["sbsp"],
            art_scene_sha256=old["art_scene_sha256"],
            native_gate_witnesses=old["native_gate_witnesses"],
            geology_pixels=textures,
            ridge_geometry=jsonfile(args.ridges / "receipt.json"),
            ridge_native=rr,
            foothill_contacts=contacts,
            ridge_material=old["ridge_material"],
            environment=jsonfile(args.art / "light/environment.json"),
            earth_finish=jsonfile(args.art / "earth/editor-verified.json"),
            shader_readback=shaders,
            alpine_foliage=foliage,
            baseline_map=old["archive"],
            fluid_flux_and_play_rules_preserved=True,
        )
        seal_release(args, out, inputs, old, expected, manifest, revision)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art", type=Path, default=ART)
    parser.add_argument("--baseline", type=Path, default=BASE)
    parser.add_argument(
        "--paks",
        type=Path,
        default=Path(
            "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"
        ),
    )
    parser.add_argument("--version", default="0.1.0-playtest.14")
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    parser.add_argument(
        "--bake-cli",
        type=Path,
        default=ROOT / "out/pwr/toolchain-grass-v7/r2/mjolnir.exe",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    args.art = args.art.resolve()
    args.staged = (
        args.art / "editor/Meteorite/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
    )
    args.ridges = args.art / "range"
    args.native = args.art / "native-control"
    args.out = args.out or args.art / "saturday.14"
    if args.out.exists():
        raise FileExistsError(args.out)
    compose_level(args)
    control_world(args)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        release = Path(temp) / "release"
        release.mkdir()
        stage(args, release)
        release.rename(args.out)


if __name__ == "__main__":
    main()
