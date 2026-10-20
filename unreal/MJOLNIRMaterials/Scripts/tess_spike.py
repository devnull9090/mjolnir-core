"""Spike (2026-10-12): does Nanite tessellation work in the game?

Builds, under /Game/MJOLNIR/CETrial (chunk 983):
  M_CE_TessTest  a Nanite material with tessellation on, its displacement a
                 world-space sine (TessAmp scales it, TessCell is the period
                 in cm), so a displaced surface is unmistakable;
  SM_TessTest    /Engine/BasicShapes/Plane duplicated with Nanite enabled: does
                 a stock-cooked Nanite static mesh load at all?

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/tess_spike.py
"""
import unreal

ROOT = "/Game/MJOLNIR/CETrial"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log("MJOLNIR tess spike: " + msg)


def fresh(name, cls, factory):
    path = f"{ROOT}/{name}"
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, ROOT, cls, factory)


def build_material(name="M_CE_TessTest", tessellate=True, wpo=False):
    m = fresh(name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("used_with_nanite", True)
    m.set_editor_property("used_with_static_lighting", False)
    m.set_editor_property("two_sided", True)
    for name, value in (("enable_tessellation", tessellate),):
        try:
            m.set_editor_property(name, value)
            log(f"{name} = {m.get_editor_property(name)}")
        except Exception as e:  # noqa: BLE001
            log(f"no property {name}: {e}")
    try:
        m.set_editor_property("displacement_scaling", unreal.DisplacementScaling(magnitude=60.0, center=0.5))
        log(f"displacement_scaling = {m.get_editor_property('displacement_scaling')}")
    except Exception as e:  # noqa: BLE001
        log(f"no displacement_scaling: {e}")
    y = 0

    def node(cls, **props):
        nonlocal y
        e = mel.create_material_expression(m, cls, -900, y)
        y += 150
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    wp = node(unreal.MaterialExpressionWorldPosition)
    amp = node(unreal.MaterialExpressionScalarParameter, parameter_name="TessAmp", default_value=1.0)
    cell = node(unreal.MaterialExpressionScalarParameter, parameter_name="TessCell", default_value=150.0)
    c = node(unreal.MaterialExpressionCustom, code="return saturate(0.5 + 0.5 * Amp * sin(W.x * 6.2831853 / Cell) "
                                                    "* sin(W.y * 6.2831853 / Cell));",
             output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="sine height")
    ins = []
    for n in ("W", "Amp", "Cell"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    mel.connect_material_expressions(wp, "", c, "W")
    mel.connect_material_expressions(amp, "", c, "Amp")
    mel.connect_material_expressions(cell, "", c, "Cell")
    ok = unreal.MjolnirUIBuilderLibrary.connect_displacement(m, c, "")
    log(f"displacement connected: {ok}")
    if wpo:
        # The same sine as a vertex offset along z: Nanite's programmable
        # raster without tessellation.
        lift = node(unreal.MaterialExpressionCustom, code="return float3(0, 0, (H - 0.5) * 60.0);",
                    output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="sine lift")
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", "H")
        lift.set_editor_property("inputs", [ci])
        mel.connect_material_expressions(c, "", lift, "H")
        log(f"wpo connected: {unreal.MjolnirUIBuilderLibrary.connect_world_position_offset(m, lift, '')}")
    col = node(unreal.MaterialExpressionVectorParameter, parameter_name="Colour",
               default_value=unreal.LinearColor(0.8, 0.3, 0.1, 1.0))
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m


def build_mesh(material):
    path = f"{ROOT}/SM_TessTest"
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    mesh = eal.duplicate_asset("/Engine/BasicShapes/Plane", path)
    settings = mesh.get_editor_property("nanite_settings")
    settings.set_editor_property("enabled", True)
    mesh.set_editor_property("nanite_settings", settings)
    mesh.set_material(0, material)
    eal.save_loaded_asset(mesh)
    log(f"mesh nanite = {mesh.get_editor_property('nanite_settings').get_editor_property('enabled')}")


build_mesh(build_material())
build_material("M_CE_TessCtrl", tessellate=False)
build_material("M_CE_TessWPO", tessellate=False, wpo=True)
log("built")
