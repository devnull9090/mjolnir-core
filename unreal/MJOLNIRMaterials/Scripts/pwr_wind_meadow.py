"""Author and read back the native PWR grass material, landscape varieties and PCG HISM."""

import hashlib
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path
import sys

import unreal as ue

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/level"))
import pcg_foliage as pcg

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable"
NAME = "PWR_WindMeadow"
GRAPH = "/Game/MJOLNIR/PCGAuthoring/PWRGroundLife/PCG_WindMeadow"
LIB = ue.MaterialEditingLibrary
EAL = ue.EditorAssetLibrary
ASSETS = ue.AssetToolsHelpers.get_asset_tools()
PROPS = ue.MaterialProperty
WIND = """
float h = saturate((BladeLocal.z - .7) / max(Height, 1.));
float w = h*h*(3.-2.*h);
float phase = dot(World.xy,float2(.0012,.00065))-Clock*1.74;
float gust = .48+.52*pow(.5+.5*sin(dot(World.xy,float2(.00027,.00014))-Clock*.9),2.);
float sway = Amp*w*gust*(sin(phase+Seed*.4)+.3*sin(phase*2.1+Seed*6.28));
float sidestep = Amp*.19*w*sin(Clock*3.1+World.y*.002+Seed*6.28);
float fade = 1.-smoothstep(NearDist, FarDist, distance(Eye.xyz, World.xyz));
return float3(.90*sway-.43*sidestep,.43*sway+.90*sidestep,-abs(sway)*.07)*fade;
"""
PALETTE = {
    "Canyon": (91.0, 12.0, 3200.0, 4750.0, 1.12),
    "B30": (31.0, 6.2, 3100.0, 4700.0, 1.20),
    "Tundra": (17.0, 3.8, 1750.0, 2750.0, 1.28),
}
# Density in instances per 100 square metres, scale and cull in centimetres.
VARIETIES = {
    "Canyon": (43.0, 0.43, 0.71, 4200, 6700),
    "Crab": (22.0, 0.67, 0.93, 3600, 5800),
    "Wild1": (32.0, 0.77, 1.13, 4400, 7400),
    "Wild12": (22.0, 0.76, 1.17, 4300, 7300),
    "Wild16": (15.0, 0.87, 1.26, 4200, 7000),
}


def save(obj):
    if not EAL.save_loaded_asset(obj, only_if_is_dirty=False):
        raise RuntimeError("Could not save " + obj.get_path_name())


def asset(name, cls, factory):
    return ue.load_asset(FOLDER + "/" + name) or ASSETS.create_asset(
        name, FOLDER, cls, factory()
    )


def graph_builder():
    module_spec = importlib.util.spec_from_file_location(
        "pwr_wind_graph_helpers", Path(__file__).with_name("build_ce_materials.py")
    )
    module = importlib.util.module_from_spec(module_spec)
    previous = os.environ.get("MJ_CE_LIBRARY")
    os.environ["MJ_CE_LIBRARY"] = "1"
    try:
        module_spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("MJ_CE_LIBRARY", None)
        else:
            os.environ["MJ_CE_LIBRARY"] = previous
    return module.Graph


def load_atlas(key, row):
    path = Path(row["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError("Grass UV atlas changed")
    name = "T_PWR_Wind_" + key
    task = ue.AssetImportTask()
    for k, v in dict(
        filename=str(path),
        destination_path=FOLDER,
        destination_name=name,
        automated=True,
        replace_existing=True,
        save=True,
    ).items():
        task.set_editor_property(k, v)
    ASSETS.import_asset_tasks([task])
    tex = ue.load_asset(FOLDER + "/" + name)
    tex.set_editor_property("srgb", True)
    tex.set_editor_property("virtual_texture_streaming", False)
    tex.set_editor_property("do_scale_mips_for_alpha_coverage", True)
    tex.set_editor_property("alpha_coverage_thresholds", ue.Vector4(0, 0, 0, 0.31))
    save(tex)
    return tex


def materials(spec, grounded=False):
    textures = {k: load_atlas(k, row) for k, row in spec["atlases"].items()}
    master = asset("M_PWR_WindBlade", ue.Material, ue.MaterialFactoryNew)
    for prop, val in dict(
        blend_mode=ue.BlendMode.BLEND_MASKED,
        two_sided=True,
        shading_model=ue.MaterialShadingModel.MSM_DEFAULT_LIT
        if grounded
        else ue.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE,
        tangent_space_normal=False,
        opacity_mask_clip_value=0.31,
        used_with_instanced_static_meshes=True,
        used_with_nanite=True,
        max_world_position_offset_displacement=19.0,
    ).items():
        master.set_editor_property(prop, val)
    LIB.delete_all_material_expressions(master)
    g = graph_builder()(master)
    tex = g.texture(
        "BladeAtlas", textures["B30"], g.uv(0), ue.MaterialSamplerType.SAMPLERTYPE_COLOR
    )
    seed = g.node(ue.MaterialExpressionPerInstanceRandom)
    bend = g.custom(
        WIND,
        [
            (
                "World",
                g.node(
                    ue.MaterialExpressionWorldPosition,
                    world_position_shader_offset=ue.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS,
                ),
                "",
            ),
            ("BladeLocal", g.node(ue.MaterialExpressionPreSkinnedPosition), ""),
            ("Eye", g.node(ue.MaterialExpressionCameraPositionWS), ""),
            ("Clock", g.node(ue.MaterialExpressionTime, ignore_pause=True), ""),
            ("Seed", seed, ""),
            ("Height", g.scalar("BladeHeight", 31.0), ""),
            ("Amp", g.scalar("TipSway", 6.2), ""),
            ("NearDist", g.scalar("WindNear", 3100.0), ""),
            ("FarDist", g.scalar("WindFar", 4700.0), ""),
        ],
        description="Root-pinned wind",
    )
    rgb_inputs = [
        ("Atlas", tex, "RGB"),
        ("Seed", seed, ""),
        ("Lift", g.scalar("PigmentLift", 1.20), ""),
    ]
    color = """float3 v=Atlas*lerp(float3(.90,1.02,.93),float3(1.11,1.01,.84),Seed);
return saturate(max(v, float3(.015,.022,.009))*Lift);"""
    if grounded:
        local = g.node(ue.MaterialExpressionPreSkinnedPosition)
        height = g.custom(
            "return saturate(P.z/max(H,1.));",
            [("P", local, ""), ("H", g.scalar("BladeHeight", 31.0), "")],
            output=ue.CustomMaterialOutputType.CMOT_FLOAT1,
        )
        varying = g.node(ue.MaterialExpressionVertexInterpolator)
        if not LIB.connect_material_expressions(height, "", varying, "VS"):
            raise RuntimeError("Could not interpolate blade roots")
        rgb_inputs.append(("Tip", varying, ""))
        color = """float luminance=dot(Atlas,float3(.2126,.7152,.0722));
float3 pigment=lerp(Atlas,luminance.xxx,.13)*lerp(float3(.88,.92,.84),float3(.96,.95,.83),Seed);
return saturate(pigment*Lift*lerp(.43,1.,smoothstep(.015,.84,Tip)));"""
    rgb = g.custom(color, rgb_inputs)
    sss = g.custom("return Leaf * float3(.44,.54,.24);", [("Leaf", rgb, "")])
    up = g.node(
        ue.MaterialExpressionConstant3Vector,
        constant=ue.LinearColor(0.0, 0.0, 1.0, 1.0),
    )
    outputs = [
        (tex, "A", PROPS.MP_OPACITY_MASK),
        (rgb, "", PROPS.MP_BASE_COLOR),
        (up, "", PROPS.MP_NORMAL),
        (
            g.scalar("BladeRoughness", 0.92 if grounded else 0.74),
            "",
            PROPS.MP_ROUGHNESS,
        ),
        (g.scalar("BladeSpecular", 0.025 if grounded else 0.20), "", PROPS.MP_SPECULAR),
    ]
    if not grounded:
        outputs.append((sss, "", PROPS.MP_SUBSURFACE_COLOR))
    for node, pin, prop in outputs:
        if not LIB.connect_material_property(node, pin, prop):
            raise RuntimeError("Grass output not connected: " + str(prop))
    if not ue.MjolnirUIBuilderLibrary.connect_world_position_offset(master, bend, ""):
        raise RuntimeError("Wind vertex offset input did not bind")
    LIB.recompile_material(master)
    save(master)
    instances = {}
    values_by_family = dict(PALETTE)
    if grounded:
        for k, lift in dict(Canyon=0.83, B30=0.83, Tundra=0.86).items():
            values_by_family[k] = (*PALETTE[k][:4], lift)
        values_by_family["Fescue"] = (17.0, 2.7, 1550.0, 2950.0, 0.77)
    for k, values in values_by_family.items():
        mi = asset(
            "MI_PWR_Wind_" + k,
            ue.MaterialInstanceConstant,
            ue.MaterialInstanceConstantFactoryNew,
        )
        LIB.set_material_instance_parent(mi, master)
        LIB.set_material_instance_texture_parameter_value(
            mi, "BladeAtlas", textures["Canyon" if k == "Fescue" else k]
        )
        for n, v in zip(
            ("BladeHeight", "TipSway", "WindNear", "WindFar", "PigmentLift"), values
        ):
            LIB.set_material_instance_scalar_parameter_value(mi, n, v)
        LIB.update_material_instance(mi)
        save(mi)
        instances[k] = mi
    return instances


def standin(row):
    mesh = ue.load_asset(row["mesh"])
    if mesh:
        return mesh
    mesh = ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(row["mesh"])
    o, e = row["origin"], row["extent"]
    positions = [
        ue.Vector(o[0] + x * e[0], o[1] + y * e[1], o[2] + z * e[2])
        for x in (-1, 1)
        for y in (-1, 1)
        for z in (-1, 1)
    ]
    faces = (
        (0, 1, 3, 2),
        (4, 6, 7, 5),
        (0, 4, 5, 1),
        (2, 3, 7, 6),
        (0, 2, 6, 4),
        (1, 5, 7, 3),
    )
    idx = [i for a, b, c, d in faces for i in (a, b, c, a, c, d)]
    uv = [ue.Vector2D(0, 0)] * len(idx)
    if not mesh or not ue.MjolnirUIBuilderLibrary.build_static_mesh(
        mesh,
        positions,
        [ue.Vector(0, 0, 1)] * 8,
        idx,
        uv,
        uv,
        [0] * 12,
        [ue.Name(n) for n in row["standin_slots"]],
        [],
        [],
    ):
        raise RuntimeError("Editor placeholder failed for " + row["mesh"])
    save(mesh)
    return mesh


def varieties(spec, instances):
    grass = ue.load_asset(FOLDER + "/GT_PWRPilot")
    crab = next(
        v
        for v in grass.get_editor_property("grass_varieties")
        if "crab" in v.get_editor_property("grass_mesh").get_name().lower()
    )
    result = []
    for key, (density, lo, hi, start, end) in VARIETIES.items():
        v = ue.GrassVariety()
        mesh = (
            crab.get_editor_property("grass_mesh")
            if key == "Crab"
            else standin(spec["meshes"][key])
        )
        v.set_editor_property("grass_mesh", mesh)
        mat = (
            [] if key == "Crab" else [instances["Canyon" if key == "Canyon" else "B30"]]
        )
        v.set_editor_property("override_materials", mat)
        for k, val in (
            ("grass_density", density),
            ("start_cull_distance", start),
            ("end_cull_distance", end),
        ):
            for field in (k, k + "_quality"):
                data = v.get_editor_property(field)
                data.set_editor_property("default", val)
                v.set_editor_property(field, data)
        interval = v.get_editor_property("scale_x")
        interval.set_editor_property("min", lo)
        interval.set_editor_property("max", hi)
        v.set_editor_property("scale_x", interval)
        for key2, value in dict(
            use_grid=False,
            random_rotation=True,
            align_to_surface=True,
            cast_dynamic_shadow=False,
            cast_contact_shadow=False,
            affect_distance_field_lighting=False,
            instance_world_position_offset_disable_distance=4800
            if key != "Crab"
            else 3500,
        ).items():
            v.set_editor_property(key2, value)
        result.append(v)
    grass.set_editor_property("grass_varieties", result)
    save(grass)


def actor_components():
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    return [
        (a, c)
        for a in actors.get_all_level_actors()
        for c in a.get_components_by_class(ue.HierarchicalInstancedStaticMeshComponent)
    ]


def apply(world, spec_path, verify=False):
    spec_path = Path(spec_path).resolve()
    folder = spec_path.parent
    spec = pcg.load(spec_path)
    if world.get_name() != "LPE":
        raise RuntimeError("Wind grass requires the authored LPE world")
    tags = {r["mesh"]: k for k, r in spec["meshes"].items()}
    if not verify:
        mat = materials(spec)
        varieties(spec, mat)
        points = folder / "points.json"
        generated = folder / "pcg-output.json"
        if not ue.MjolnirPCGLibrary.generate_points(
            world, str(points), GRAPH, str(generated), spec["seed"], 0.78, 1.14
        ):
            raise RuntimeError("Native grass graph failed")
        picked = pcg.adapt(points, generated, folder / "palette.json", folder, "wind")
        if not 0 < picked["selected_count"] <= spec["budget"]:
            raise ValueError("Grass PCG budget")
        groups = pcg.load(folder / "wind.json")["groups"]
        if not any(a.get_name() == NAME for a, c in actor_components()):
            count = ue.MjolnirUIBuilderLibrary.bake_foliage(
                world,
                str(folder / "wind.bin"),
                NAME,
                [g["mesh"] for g in groups],
                [1] * len(groups),
                [ue.Vector2D(*g["cull"]) for g in groups],
                [32] * len(groups),
            )
            if count != picked["selected_count"]:
                raise RuntimeError("World omitted selected grass")
        for actor, c in actor_components():
            mesh = c.get_editor_property("static_mesh")
            family = tags.get(mesh.get_path_name()) if mesh else None
            if actor.get_name() != NAME and family != "Tundra":
                continue
            key = family if family in ("Canyon", "Tundra") else "B30"
            c.set_material(0, mat[key])
            c.set_evaluate_world_position_offset(True)
            c.set_world_position_offset_disable_distance(
                2850 if key == "Tundra" else 4800
            )
        if not ue.get_editor_subsystem(ue.LevelEditorSubsystem).save_current_level():
            raise RuntimeError("Could not save LPE")
    picked = pcg.load(folder / "wind.selected.json")
    want = Counter(p["mesh"] for p in picked["instances"])
    actual = Counter()
    tundra = 0
    for actor, c in actor_components():
        mesh = c.get_editor_property("static_mesh")
        if not mesh:
            continue
        family = tags.get(mesh.get_path_name())
        if actor.get_name() != NAME and family != "Tundra":
            continue
        key = family if family in ("Canyon", "Tundra") else "B30"
        if c.get_material(
            0
        ).get_name() != "MI_PWR_Wind_" + key or not c.get_editor_property(
            "evaluate_world_position_offset"
        ):
            raise RuntimeError("Saved grass wind binding missing")
        count = c.get_instance_count()
        if actor.get_name() == NAME:
            if (
                c.get_collision_enabled() != ue.CollisionEnabled.NO_COLLISION
                or c.get_editor_property("instance_end_cull_distance") != 8800
            ):
                raise RuntimeError("Verge component cull or collision changed")
            actual[mesh.get_path_name()] += count
        else:
            tundra += count
    if actual != want or tundra < 1:
        raise RuntimeError("Live grass HISM readback differs from PCG")
    gt = ue.load_asset(FOLDER + "/GT_PWRPilot")
    native = [
        str(v.get_editor_property("grass_mesh").get_path_name())
        for v in gt.get_editor_property("grass_varieties")
    ]
    if len(native) != 5:
        raise RuntimeError("Landscape varieties did not persist")
    master = ue.load_asset(FOLDER + "/M_PWR_WindBlade")
    nodes = [
        node
        for node in ue.ObjectIterator(ue.MaterialExpressionCustom)
        if node.get_outer() == master
        and node.get_editor_property("code").strip() == WIND.strip()
    ]
    if len(nodes) != 1:
        raise RuntimeError("Wind graph changed")
    receipt = dict(
        count=picked["selected_count"],
        kind_counts=dict(actual),
        tundra_updated=tundra,
        landscape_varieties=native,
        culled_at_m=88,
        wind_stops_m=48,
        world=world.get_path_name(),
    )
    (folder / ("editor-saved.json" if verify else "editor-built.json")).write_text(
        json.dumps(receipt, indent=2)
    )
    return receipt
