"""Build and verify the matched native render surfaces for Southwest Sweep."""

import json
import math
import os
from pathlib import Path
import struct
import sys

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_pwr_alpine_verges as verges
import pwr_wind_meadow as common

REVISION = int(os.environ.get("PWR_SWEEP_BANK_REVISION", "16"))
if REVISION not in (16, 17, 18):
    raise ValueError("Unknown bank geometry revision")
ART = common.ROOT / f"out/pwr/sweep-polish/round{REVISION}/verges"
FOLDER, LIB = common.FOLDER, common.LIB
MATERIAL, MESH = "M_PWR_SweepBank", "SM_PWR_SweepMossBanks"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def bank_assets(verify, extra=None, first=True):
    update_material = not verify and first
    masked = REVISION >= 17 and extra is None
    geo_file = extra["file"] if extra else "landform.json"
    leaf = extra["name"] if extra else MESH
    mat_name = "M_PWR_SweepLitter" if extra else MATERIAL
    art = read(ART / ("litter-textures.json" if extra else "bank-textures.json"))
    geo = read(ART / geo_file)
    textures = {}
    for mode, row in art["images"].items():
        path = ART / (row.get("filename") or row["file"])
        if verges.digest(path) != row["sha256"]:
            raise ValueError("Bank native source bitmap changed")
        name = ("T_PWR_SweepLitter_" if extra else "T_PWR_SweepBank_") + mode
        if update_material:
            task = ue.AssetImportTask()
            task.set_editor_properties(
                dict(
                    filename=str(path),
                    destination_path=FOLDER,
                    destination_name=name,
                    automated=True,
                    replace_existing=True,
                    save=False,
                )
            )
            common.ASSETS.import_asset_tasks([task])
        tex = ue.load_asset(FOLDER + "/" + name)
        if not tex:
            raise RuntimeError("Missing " + name)
        if update_material:
            tex.set_editor_properties(
                dict(
                    srgb=mode == "D",
                    virtual_texture_streaming=False,
                    compression_settings=ue.TextureCompressionSettings.TC_DEFAULT
                    if mode == "D"
                    else ue.TextureCompressionSettings.TC_NORMALMAP,
                    address_x=ue.TextureAddress.TA_CLAMP,
                    address_y=ue.TextureAddress.TA_CLAMP,
                )
            )
            if masked and mode == "D":
                tex.set_editor_properties(
                    dict(
                        compression_no_alpha=False,
                        mip_gen_settings=ue.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
                    )
                )
            common.save(tex)
        textures[mode] = tex
    mat = ue.load_asset(FOLDER + "/" + mat_name)
    if update_material:
        mat = mat or common.asset(mat_name, ue.Material, ue.MaterialFactoryNew)
        mat.set_editor_properties(
            dict(two_sided=True, used_with_instanced_static_meshes=True)
        )
        if masked:
            mat.set_editor_properties(
                dict(blend_mode=ue.BlendMode.BLEND_MASKED, opacity_mask_clip_value=0.48)
            )
        LIB.delete_all_material_expressions(mat)
    for i, (key, inp, sampler) in enumerate(
        (
            (
                "D",
                ue.MaterialProperty.MP_BASE_COLOR,
                ue.MaterialSamplerType.SAMPLERTYPE_COLOR,
            ),
            (
                "N",
                ue.MaterialProperty.MP_NORMAL,
                ue.MaterialSamplerType.SAMPLERTYPE_NORMAL,
            ),
        )
    ):
        if update_material:
            node = LIB.create_material_expression(
                mat, ue.MaterialExpressionTextureSample, -400, 320 * i
            )
            node.set_editor_properties(
                dict(texture=textures[key], sampler_type=sampler)
            )
            if not LIB.connect_material_property(node, "RGB", inp):
                raise RuntimeError("Cannot bind the bank scan")
            if (
                masked
                and key == "D"
                and not LIB.connect_material_property(
                    node, "A", ue.MaterialProperty.MP_OPACITY_MASK
                )
            ):
                raise RuntimeError("Bank toe lost its alpha connection")
        node = LIB.get_material_property_input_node(mat, inp)
        if node.get_editor_property("texture") != textures[key]:
            raise RuntimeError("Bank scan lost its material connection")
        if masked and key == "D":
            if (
                mat.get_editor_property("blend_mode") != ue.BlendMode.BLEND_MASKED
                or LIB.get_material_property_input_node(
                    mat, ue.MaterialProperty.MP_OPACITY_MASK
                )
                != node
            ):
                raise RuntimeError("Bank material has no persistent masked edge")
    if update_material:
        for value, inp in (
            (0.94 if REVISION >= 18 else 0.88, ue.MaterialProperty.MP_ROUGHNESS),
            (0.08 if REVISION >= 18 else 0.18, ue.MaterialProperty.MP_SPECULAR),
        ):
            node = LIB.create_material_expression(
                mat, ue.MaterialExpressionConstant, -180, int(700 * value)
            )
            node.set_editor_property("r", value)
            LIB.connect_material_property(node, "", inp)
        LIB.recompile_material(mat)
        common.save(mat)
    mesh_path = FOLDER + "/" + leaf + "." + leaf
    mesh = ue.load_asset(mesh_path)
    if not verify:
        mesh = mesh or ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(mesh_path)
        flat = [j for face in geo["faces"] for j in face]
        uv = [ue.Vector2D(*geo["uv"][i]) for i in flat]
        if not ue.MjolnirUIBuilderLibrary.build_static_mesh(
            mesh,
            [ue.Vector(*p) for p in geo["positions"]],
            [ue.Vector(*n) for n in geo["normals"]],
            flat,
            uv,
            uv,
            [0] * len(geo["faces"]),
            [ue.Name(extra["slot"] if extra else "ForestFloor")],
            [],
            [],
        ):
            raise RuntimeError("Native bank geometry did not build")
        mesh.set_material(0, mat)
        common.save(mesh)
    if mesh.get_material(0) != mat:
        raise RuntimeError("Native bank mesh material slot did not persist")
    return {
        "mesh": mesh.get_path_name(),
        "vertices": len(geo["positions"]),
        "faces": len(geo["faces"]),
        "geometry_sha256": verges.digest(ART / geo_file),
        "texture_sources": art["images"],
        "per_pixel_edge_mask": masked,
    }


def replace_legacy(verify):
    edit = read(ART / "legacy-edits.json")
    rock_path = edit["snowfree_material"]
    if not ue.load_asset(rock_path):
        if verify:
            raise RuntimeError("Cannot resolve native NoSnow import")
        # This package is supplied by Halo itself. The cook uses chunk 0 for the editor proxy.
        folder, name = rock_path.rsplit("/", 1)
        proxy = common.ASSETS.create_asset(
            name,
            folder,
            ue.MaterialInstanceConstant,
            ue.MaterialInstanceConstantFactoryNew(),
        )
        LIB.set_material_instance_parent(
            proxy, ue.load_asset("/Engine/EngineMaterials/DefaultMaterial")
        )
        common.save(proxy)
    actors = {(a.get_name(), c.get_name()): c for a, c in common.actor_components()}
    rock = actors["PWR_AlpineVerges", "PWRVerge_Outcrop"]
    moss = actors["PWR_SweepForestFloor", "PWRSweep_Moss"]
    if not verify and rock.get_instance_count() == 3:
        removing = [
            i
            for i in range(3)
            if any(
                math.dist(verges.pose(rock.get_instance_transform(i, True))[:3], p[:3])
                < 0.15
                for p in edit["snowfree_moved_outcrops"]
            )
        ]
        if len(removing) != 2:
            raise RuntimeError(
                "Cannot identify the two Southwest portions of the original outcrop group"
            )
        rock.modify()
        for i in sorted(removing, reverse=True):
            if not rock.remove_instance(i):
                raise RuntimeError("Cannot separate original Southwest instance")
    old = read(common.ROOT / "out/pwr/alpine-target/verges/verges.json")
    oi = next(i for i, g in enumerate(old["groups"], 1) if g["key"] == "Outcrop")
    baseline = struct.iter_unpack(
        "<10f",
        (common.ROOT / f"out/pwr/alpine-target/verges/verges.bin.xf{oi}").read_bytes(),
    )
    expected_teton = [
        p
        for p in baseline
        if all(math.dist(p[:3], r[:3]) > 0.15 for r in edit["snowfree_moved_outcrops"])
    ]
    if (
        rock.get_instance_count() != 1
        or len(expected_teton) != 1
        or math.dist(
            verges.pose(rock.get_instance_transform(0, True))[:3], expected_teton[0][:3]
        )
        > 0.08
    ):
        raise RuntimeError("Original Teton outcrop did not survive the component split")
    path = ART.parent / "floor"
    spec = read(path / "verges.json")
    i = next(i for i, row in enumerate(spec["groups"], 1) if row["key"] == "Moss")
    wanted = list(struct.iter_unpack("<10f", (path / f"verges.bin.xf{i}").read_bytes()))
    if not verify:
        moss.modify()
        moss.clear_instances()
        for p in wanted:
            t = ue.Transform()
            t.translation, t.rotation, t.scale3d = (
                ue.Vector(*p[:3]),
                ue.Quat(*p[3:7]),
                ue.Vector(*p[7:]),
            )
            moss.add_instance(t, world_space=True)
    if moss.get_instance_count() != len(wanted):
        raise RuntimeError("Incorrect retained moss count")
    for actual, source in zip(
        sorted(
            verges.pose(moss.get_instance_transform(i, True))
            for i in range(len(wanted))
        ),
        sorted(wanted),
    ):
        if (
            math.dist(actual[:3], source[:3]) > 0.08
            or math.dist(actual[7:], source[7:]) > 0.0001
        ):
            raise RuntimeError("Incorrect retained moss transforms")


def refresh_bank_instances():
    """Keep the map-owned actor and its native culling settings while replacing the revision's poses."""
    spec, _, groups = verges.load_input(ART / "verges.json", "PWR_SweepBanks")
    old = {
        c.get_name(): c
        for a, c in common.actor_components()
        if a.get_name() == "PWR_SweepBanks"
    }
    if not old:
        return
    for row, poses in zip(spec["groups"], groups):
        c = old["PWRSweepBank_" + row["key"]]
        c.modify()
        c.clear_instances()
        for p in poses:
            t = ue.Transform()
            t.translation, t.rotation, t.scale3d = (
                ue.Vector(*p[:3]),
                ue.Quat(*p[3:7]),
                ue.Vector(*p[7:]),
            )
            c.add_instance(t, world_space=True)


def main():
    verify = os.environ.get("PWR_VERGES_VERIFY") == "1"
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level(verges.WORLD):
        raise RuntimeError("Missing Southwest Sweep authoring world")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    receipt = bank_assets(verify)
    if REVISION == 18:
        receipt["litter_meshes"] = [
            bank_assets(verify, row, i == 0)
            for i, row in enumerate(read(ART / "litter.json")["meshes"])
        ]
        if not verify:
            owners = {
                a
                for a, c in common.actor_components()
                if a.get_name() == "PWR_SweepBanks"
            }
            for actor in owners:
                actor.rename("PWR_SupersededSweepBanks")
                if not ue.get_editor_subsystem(ue.EditorActorSubsystem).destroy_actor(
                    actor
                ):
                    raise RuntimeError(
                        "Unable to rebuild the bank actor for the new mesh palette"
                    )
    replace_legacy(verify)
    if not verify and REVISION == 17:
        refresh_bank_instances()
    verges.apply(world, ART / "verges.json", verify, "PWR_SweepBanks", "PWRSweepBank_")
    if not verify and not levels.save_current_level():
        raise RuntimeError("Native bank and corrected outcrop groups did not save")
    (
        ART / ("bank-editor-verified.json" if verify else "bank-editor-applied.json")
    ).write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
