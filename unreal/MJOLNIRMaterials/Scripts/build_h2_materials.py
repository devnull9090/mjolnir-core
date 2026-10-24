"""Masters for Halo 2 shaders CE's have no equivalent of, under /Game/MJOLNIR/H2
in a chunk of their own (981), so they install beside the CE runtime pack
without touching it (docs/h2_map_conversion.md, "Plasma").

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_h2_materials.py

M_H2_PlasmaAlpha is `plasma_alpha` as its compiled pixel shader draws it
(docs/h2_cache_format.md): two scrolling noise maps differenced (noise A's
blue, noise B's red), banded into a sharp ridge where they meet and twice
more inside it, coloured between pixel constants 1 and 0 by the second band
plus constant 3 on the innermost, faded by the facing term constant 2's
alpha weights and the mask's alpha, added to the frame. Zanzibar's flywheel
lightning, the teleporters' beams, Lockout's grav lifts.
"""
import unreal

assets = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

ROOT = "/Game/MJOLNIR/H2"
CHUNK = 981
WHITE = "/Game/MJOLNIR/CE/T_CE_White.T_CE_White"

PLASMA_ALPHA_CODE = r"""
float2 ua = UV * XformA.xy + XformA.zw + ScrollA.xy * Time;
float2 ub = UV * XformB.xy + XformB.zw + ScrollB.xy * Time;
float2 um = UV * XformM.xy + XformM.zw + ScrollM.xy * Time;
float a = saturate(Texture2DSample(NoiseA, NoiseASampler, ua).b);
float b = saturate(Texture2DSample(NoiseB, NoiseBSampler, ub).r);
float m = saturate(Texture2DSample(Mask, MaskSampler, um).a);
// The compiled band: the smaller of (a - b + 0.502) and (b - a + 0.502),
// squared, times 4; then (2 sat(x) - 1)^2 three times, each kept only where
// the last rounds to 1.
float x = 0.501961 - abs(a - b);
x = x * x * 4.0;
float band0 = saturate(x);
float s = band0 * 2.0 - 1.0;
float b1 = round(x) * s * s;
float sb1 = saturate(b1);
s = sb1 * 2.0 - 1.0;
float b2 = round(b1) * s * s;
s = saturate(b2) * 2.0 - 1.0;
float b3 = saturate(round(b2) * s * s);
float3 col = saturate(band0 * saturate(sb1 * Color0.rgb + (1.0 - sb1) * Color1.rgb) + b3 * Color3.rgb);
// The vertex shader's facing term, weighted by constant 2's alpha.
float e = saturate(abs(dot(normalize(N), normalize(Cam - W))));
float f = 1.0 - e;
f = f * f;
float w = saturate(e * (1.0 - Fade) + (1.0 - f * f) * Fade) * m;
float3 frame = col * w;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return lerp(hi, lo, step(frame, 0.04045)) * Exposure;
"""


def fresh(path, name, cls, factory):
    full = f"{path}/{name}"
    if eal.does_asset_exist(full):
        eal.delete_asset(full)
    return assets.create_asset(name, path, cls, factory)


class Graph:
    def __init__(self, material):
        self.m = material
        self.y = 0

    def node(self, cls, x=-1400, **props):
        e = mel.create_material_expression(self.m, cls, x, self.y)
        self.y += 140
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    def scalar(self, name, default):
        return self.node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=default)

    def vector(self, name, default):
        return self.node(unreal.MaterialExpressionVectorParameter, parameter_name=name,
                         default_value=unreal.LinearColor(*default))

    def vector4(self, name, default):
        v = self.vector(name, default)
        a = self.node(unreal.MaterialExpressionAppendVector, x=-1200)
        mel.connect_material_expressions(v, "", a, "A")
        mel.connect_material_expressions(v, "A", a, "B")
        return a

    def texture_object(self, name, default):
        t = self.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name=name, texture=default,
                      sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        t.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
        return t


def build_label():
    label = fresh(ROOT, "PAL_MJOLNIR_H2", unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", CHUNK)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)


def build_plasma_alpha():
    m = fresh(ROOT, "M_H2_PlasmaAlpha", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    white = unreal.load_asset(WHITE)
    inputs = [
        ("UV", g.node(unreal.MaterialExpressionTextureCoordinate, x=-2000, coordinate_index=0), ""),
        ("Time", g.node(unreal.MaterialExpressionTime, x=-2000), ""),
        ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
        ("N", g.node(unreal.MaterialExpressionVertexNormalWS, x=-2000), ""),
        ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS, x=-2000), ""),
        ("NoiseA", g.texture_object("NoiseA", white), ""),
        ("NoiseB", g.texture_object("NoiseB", white), ""),
        ("Mask", g.texture_object("Mask", white), ""),
        # Each map's (u scale, v scale, u offset, v offset) and scroll
        # (u, v per second).
        ("XformA", g.vector4("XformA", (1.0, 1.0, 0.0, 0.0)), ""),
        ("XformB", g.vector4("XformB", (1.0, 1.0, 0.0, 0.0)), ""),
        ("XformM", g.vector4("XformM", (1.0, 1.0, 0.0, 0.0)), ""),
        ("ScrollA", g.vector4("ScrollA", (0.0, 0.0, 0.0, 0.0)), ""),
        ("ScrollB", g.vector4("ScrollB", (0.0, 0.0, 0.0, 0.0)), ""),
        ("ScrollM", g.vector4("ScrollM", (0.0, 0.0, 0.0, 0.0)), ""),
        # Pixel constants 0, 1 and 3 (gamma-space colours) and 2's alpha.
        ("Color0", g.vector4("Color0", (1.0, 1.0, 1.0, 1.0)), ""),
        ("Color1", g.vector4("Color1", (0.0, 0.0, 0.0, 1.0)), ""),
        ("Color3", g.vector4("Color3", (1.0, 1.0, 1.0, 1.0)), ""),
        ("Fade", g.scalar("Fade", 0.0), ""),
        ("Exposure", g.scalar("Exposure", 1.0), ""),
    ]
    c = g.node(unreal.MaterialExpressionCustom, x=-500, code=PLASMA_ALPHA_CODE,
               output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="H2 plasma_alpha")
    ins = []
    for name, _src, _pin in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", name)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    for name, src, pin in inputs:
        mel.connect_material_expressions(src, pin, c, name)
    # What the tonemapper receives, whatever the auto exposure (as the CE
    # transparent masters' to_screen).
    e = g.node(unreal.MaterialExpressionEyeAdaptationInverse, x=-100)
    for pin in ("Light Value Input", "LightValueInput", "Light Value", "LightValue"):
        if mel.connect_material_expressions(c, "", e, pin):
            break
    mel.connect_material_property(e, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


build_label()
build_plasma_alpha()
unreal.log("MJOLNIR H2 materials built")
