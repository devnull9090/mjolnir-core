"""Place tools/level/forerunner_bridges.py output in the open level: one generated deck shell per
bridge, and 343's shipped bridge pieces through never-cooked stand-ins (/Game/Env), so the cooked
level imports the game's own meshes. Render only: no collision on anything placed here.

    MJ_BRIDGES=<dir with bridges.json>  MJ_BRIDGES_VERIFY=0|1  MJ_BRIDGES_WORLD=/Game/...
"""
import hashlib
import json
import math
import os
from pathlib import Path

import unreal as ue

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
PREFIX = "MJOLNIR_ForerunnerBridge_"
# Self-contained, like the spring cascade's material: no parent from another chunk (the map's
# M_CE_PWRPaving is not loaded in game, so instances of it drew the engine's checker).
# Forerunner alloy plates, world-projected: (tint rgb, _), (plate x cm, plate y cm, seam cm, seam strength),
# (roughness, metallic, variation, _).
DECK = ((0.46, 0.48, 0.50, 1), (1500, 500, 6, 0.9), (0.42, 0.85, 0.03, 0))
TRIM = ((0.20, 0.22, 0.24, 1), (1500, 250, 4, 0.6), (0.36, 0.9, 0.02, 0))
LIGHT = (0.015, 0.45, 1.0)      # the Forerunner blue of the map's strip lights
LIGHT_STRENGTH = 4000.0    # physical units (the map's B40 strips run ~700 x 32); 14 drew black, 12000 washed the banks blue

PLATES = r"""
struct Plates {
    float4 layout(float2 p, float2 size, float joint, float variation) {
        float row = floor(p.y / size.y);
        float2 q = p - float2(fmod(abs(row), 2.0) * size.x * .5, 0);
        float2 id = floor(q / size);
        float2 local = (frac(q / size) - .5) * size;
        float2 h = size * .5;
        float bevel = min(size.x, size.y) * .05;
        float edge = min(min(h.x - abs(local.x), h.y - abs(local.y)), (h.x + h.y - bevel - abs(local.x) - abs(local.y)) * .70710678);
        float aa = max(max(length(ddx(p)), length(ddy(p))), 1.0);
        float seam = 1.0 - smoothstep(joint * .5 - aa, joint * .5 + aa, edge);
        float inset = (1.0 - smoothstep(2.0 - aa, 2.0 + aa, abs(edge - 65.0)));
        float hash = frac(sin(dot(id, float2(127.1, 311.7))) * 43758.5453);
        return float4(lerp(1.0 - variation, 1.0 + variation, hash), seam, inset * step(.72, hash), hash);
    }
};
Plates P;
// The deck's direction rides in the vertex colour (r, g = axis * .5 + .5): plates run along any deck.
float2 ax = normalize(Col.rg * 2.0 - 1.0);
float2 px = float2(-ax.y, ax.x);
W = float3(dot(W.xy, ax), dot(W.xy, px), W.z);
float3 nw = normalize(Nw);
nw = float3(dot(nw.xy, ax), dot(nw.xy, px), nw.z);
float3 w = pow(abs(nw), 8.0); w /= max(dot(w, 1.0.xxx), 1e-5);
float2 size = max(Layout.xy, 100.0.xx);
float4 k = P.layout(W.yz, size, Layout.z, Finish.z) * w.x + P.layout(W.xz, size, Layout.z, Finish.z) * w.y
         + P.layout(float2(W.x, -W.y), size, Layout.z, Finish.z) * w.z;
float seam = saturate(k.y * Layout.w);
Rough = clamp(Finish.x + seam * .18 + (k.w - .5) * .06, .15, .95);
Metal = saturate(Finish.y * (1.0 - seam * .7));
return Tint.rgb * lerp(1.0, k.x, Layout.w) * (1.0 - seam * .4) * (1.0 - k.z * .08);
"""


def metal_material(name, spec):
    tint, layout, finish = spec
    m = ue.load_asset(FOLDER + name) or ue.AssetToolsHelpers.get_asset_tools().create_asset(
        name, FOLDER.rstrip("/"), ue.Material, ue.MaterialFactoryNew())
    lib = ue.MaterialEditingLibrary
    lib.delete_all_material_expressions(m)
    m.set_editor_property("shading_model", ue.MaterialShadingModel.MSM_DEFAULT_LIT)
    node = lib.create_material_expression(m, ue.MaterialExpressionCustom, -300, 0)
    ty = ue.CustomMaterialOutputType
    node.set_editor_properties(dict(code=PLATES, output_type=ty.CMOT_FLOAT3))
    pins = []
    for pin_name in ("W", "Nw", "Col", "Tint", "Layout", "Finish"):
        pin = ue.CustomInput(); pin.set_editor_property("input_name", pin_name); pins.append(pin)
    node.set_editor_property("inputs", pins)
    outs = []
    for out_name in ("Rough", "Metal"):
        o = ue.CustomOutput(); o.set_editor_properties(dict(output_name=out_name, output_type=ty.CMOT_FLOAT1)); outs.append(o)
    node.set_editor_property("additional_outputs", outs)
    wp = lib.create_material_expression(m, ue.MaterialExpressionWorldPosition, -800, -200)
    assert lib.connect_material_expressions(wp, "", node, "W")
    nn = lib.create_material_expression(m, ue.MaterialExpressionVertexNormalWS, -800, -50)
    assert lib.connect_material_expressions(nn, "", node, "Nw")
    vc = lib.create_material_expression(m, ue.MaterialExpressionVertexColor, -800, 0)
    assert lib.connect_material_expressions(vc, "", node, "Col")
    for i, (pin_name, v) in enumerate((("Tint", tint), ("Layout", layout), ("Finish", finish))):
        c = lib.create_material_expression(m, ue.MaterialExpressionConstant4Vector, -800, 100 + 150 * i)
        c.set_editor_property("constant", ue.LinearColor(*v))
        assert lib.connect_material_expressions(c, "", node, pin_name)
    prop = ue.MaterialProperty
    for out_name, dest in (("", prop.MP_BASE_COLOR), ("Rough", prop.MP_ROUGHNESS), ("Metal", prop.MP_METALLIC)):
        assert lib.connect_material_property(node, out_name, dest)
    lib.recompile_material(m)
    assert ue.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def light_material():
    """Default lit, black base and an emissive glow (an unlit material drew dark in game)."""
    name = "M_FR_BridgeLight"
    m = ue.load_asset(FOLDER + name) or ue.AssetToolsHelpers.get_asset_tools().create_asset(
        name, FOLDER.rstrip("/"), ue.Material, ue.MaterialFactoryNew())
    lib = ue.MaterialEditingLibrary
    lib.delete_all_material_expressions(m)
    m.set_editor_property("shading_model", ue.MaterialShadingModel.MSM_DEFAULT_LIT)
    c = lib.create_material_expression(m, ue.MaterialExpressionConstant3Vector, -400, 0)
    c.set_editor_property("constant", ue.LinearColor(*(v * LIGHT_STRENGTH for v in LIGHT), 1))
    assert lib.connect_material_property(c, "", ue.MaterialProperty.MP_EMISSIVE_COLOR)
    base = lib.create_material_expression(m, ue.MaterialExpressionConstant3Vector, -400, -150)
    base.set_editor_property("constant", ue.LinearColor(0.01, 0.02, 0.03, 1))
    assert lib.connect_material_property(base, "", ue.MaterialProperty.MP_BASE_COLOR)
    lib.recompile_material(m)
    assert ue.EditorAssetLibrary.save_loaded_asset(m, False)
    return m


def yaw_of(r):
    if abs(r[2][2] - 1) > 1e-4 or abs(r[0][2]) > 1e-4 or abs(r[1][2]) > 1e-4:
        raise RuntimeError("Only yaw rotations are placed")
    return math.degrees(math.atan2(r[1][0], r[0][0]))


def no_collision(actor, shadow=True):
    comp = actor.get_editor_property("static_mesh_component")
    comp.set_mobility(ue.ComponentMobility.STATIC)
    actor.set_actor_enable_collision(False)
    comp.set_collision_profile_name("NoCollision")
    comp.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
    comp.set_editor_property("generate_overlap_events", False)
    comp.set_editor_property("cast_shadow", shadow)
    return comp


def standin(path, info):
    """An editor-only box of the game mesh's bounds with its slots, at its path (build_ce_landscape.standin).
    Never cooked (/Game/Env): in game the level's reference resolves to the game's own mesh."""
    mesh = ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(path)
    if not mesh or mesh.get_path_name() != path:
        raise RuntimeError("stand-in %s came out as %s" % (path, mesh.get_path_name() if mesh else None))
    (ox, oy, oz), (ex, ey, ez) = info["origin"], info["extent"]
    corners = [ue.Vector(ox + sx * ex, oy + sy * ey, oz + sz * ez) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    normals = [ue.Vector(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    quads = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    indices = [i for a, b, c, d in quads for i in (a, b, c, a, c, d)]
    uv = [ue.Vector2D(0, 0)] * len(indices)
    if not ue.MjolnirUIBuilderLibrary.build_static_mesh(mesh, corners, normals, indices, uv, uv, [0] * (len(indices) // 3),
                                                        [ue.Name(s) for s in info["slots"]], [], []):
        raise RuntimeError("stand-in %s did not build" % path)
    assert ue.EditorAssetLibrary.save_loaded_asset(mesh, False)
    return mesh


def build_shell(b, mats):
    name = "SM_FR_Bridge_" + b["id"]
    path = FOLDER + name + "." + name
    mesh = ue.load_asset(path) or ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(path)
    m = b["mesh"]
    P = [ue.Vector(*p) for p in m["positions"]]
    N = [ue.Vector(*n) for n in m["normals"]]
    # The deck metal is world-projected; UVs only keep tangents sane: metres along the plan.
    uvs = [ue.Vector2D(m["positions"][i][0] / 100.0, m["positions"][i][1] / 100.0) for i in m["indices"]]
    ax = m["axis"]
    col = ue.LinearColor(ax[0] * 0.5 + 0.5, ax[1] * 0.5 + 0.5, 0.0, 1.0)
    assert ue.MjolnirUIBuilderLibrary.build_static_mesh(mesh, P, N, m["indices"], uvs, uvs, m["sections"],
                                                        [ue.Name(s) for s in m["slots"]], [col] * len(P), [])
    for i, mat in enumerate(mats):
        mesh.set_material(i, mat)
    assert ue.EditorAssetLibrary.save_loaded_asset(mesh, False)
    return mesh


def apply(work, verify):
    doc = json.loads((Path(work) / "bridges.json").read_text())
    world = os.environ.get("MJ_BRIDGES_WORLD", "/Game/Levels/Halo1/Solo/LPE/LPE")
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    if editor.get_editor_world().get_path_name().split(".")[0] != world:
        assert levels.load_level(world)
    if not verify:
        # The deck wears the Forerunner floor master the bases use (pwr_forerunner_floor.py): one family.
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import pwr_forerunner_floor as floor
        master, _ = floor.ensure_master(os.environ.get("MJ_FR_TEXTURES", os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "../../../out/pwr/base-ground/textures")))
        mats = [floor.instance("MI_FR_BridgeDeck", master, dict(FloorTint=(0.34, 0.36, 0.38, 1), FloorAxis=(1, 0, 0, 0),
                                                                FloorLayout=(1500, 500, 5, 0.7))),
                floor.instance("MI_FR_BridgeTrim", master, dict(FloorTint=(0.16, 0.18, 0.2, 1), FloorAxis=(1, 0, 0, 0),
                                                                FloorFinish=(0.2, 0.5, 0.9, 0.5), FloorLayout=(1500, 250, 4, 0.5))),
                light_material()]
        for a in actors.get_all_level_actors():
            if a.get_actor_label().startswith(PREFIX):
                actors.destroy_actor(a)
        for b in doc["bridges"]:
            mesh = build_shell(b, mats)
            shell = actors.spawn_actor_from_class(ue.StaticMeshActor, ue.Vector(*b["origin_cm"]))
            shell.set_actor_label(PREFIX + b["id"])
            comp = no_collision(shell)
            comp.set_static_mesh(mesh)
            # The glow strips light themselves only: as a Lumen light source they washed banks and posts blue.
            comp.set_editor_property("affect_dynamic_indirect_lighting", False)
            for i, p in enumerate(b["placements"]):
                sm = ue.load_asset(p["path"])
                if not sm or sm.get_num_lods() == 0 or sm.get_num_triangles(0) == 0:
                    sm = standin(p["path"], doc["standins"][p["path"]])
                if not p["path"].startswith("/Game/Env/"):
                    raise RuntimeError("Shipped pieces must come from the never-cooked /Game/Env: " + p["path"])
                a = actors.spawn_actor_from_class(ue.StaticMeshActor, ue.Vector(*p["t"]), ue.Rotator(0, 0, yaw_of(p["r"])))
                a.set_actor_label("%s%s_%02d" % (PREFIX, b["id"], i))
                a.set_actor_scale3d(ue.Vector(*p["s"]))
                no_collision(a).set_static_mesh(sm)
        assert levels.save_current_level()
    # Readback: every shell and piece where the plan put it, no collision anywhere.
    placed = {a.get_actor_label(): a for a in actors.get_all_level_actors() if a.get_actor_label().startswith(PREFIX)}
    expected = sum(1 + len(b["placements"]) for b in doc["bridges"])
    errors = []
    if len(placed) != expected:
        errors.append("placed %d of %d" % (len(placed), expected))
    for b in doc["bridges"]:
        rows = [(PREFIX + b["id"], b["origin_cm"], "/Game/MJOLNIR/GrassPilot/Playable/SM_FR_Bridge_" + b["id"], 0.0)]
        rows += [("%s%s_%02d" % (PREFIX, b["id"], i), p["t"], p["path"].split(".")[0], yaw_of(p["r"]))
                 for i, p in enumerate(b["placements"])]
        for label, t, mesh, yaw in rows:
            a = placed.get(label)
            if not a:
                errors.append("missing " + label); continue
            comp = a.get_editor_property("static_mesh_component")
            sm = comp.get_editor_property("static_mesh")
            loc = a.get_actor_location()
            if not sm or sm.get_path_name().split(".")[0] != mesh:
                errors.append(label + " mesh " + (sm.get_path_name() if sm else "none"))
            if max(abs(loc.x - t[0]), abs(loc.y - t[1]), abs(loc.z - t[2])) > 0.5:
                errors.append(label + " moved")
            if abs(((a.get_actor_rotation().yaw - yaw) + 180) % 360 - 180) > 0.05:
                errors.append(label + " turned")
            if a.get_actor_enable_collision() or comp.get_collision_enabled() != ue.CollisionEnabled.NO_COLLISION:
                errors.append(label + " collides")
    proof = dict(bridges=[b["id"] for b in doc["bridges"]], actors=len(placed), errors=errors,
                 plan_sha256=hashlib.sha256((Path(work) / "bridges.json").read_bytes()).hexdigest())
    (Path(work) / ("bridges-verified.json" if verify else "bridges-built.json")).write_text(json.dumps(proof, indent=1))
    ue.log("forerunner bridges: " + json.dumps(proof)[:600])
    if errors:
        raise RuntimeError("Forerunner bridges readback failed: " + "; ".join(errors[:6]))


apply(os.environ["MJ_BRIDGES"], os.environ.get("MJ_BRIDGES_VERIFY") == "1")
