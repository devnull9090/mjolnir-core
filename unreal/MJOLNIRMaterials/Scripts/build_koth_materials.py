"""Build the client-only King of the Hill field and beacon, shader chunk 966.

Run via tools/ue/build_koth.ps1. The CE plasma masters are not modified.
The texture source and generation prompt live in assets/koth.
"""
import importlib.util
import os
from pathlib import Path

import unreal

ROOT = "/Game/MJOLNIR/KOTH"
CHUNK = 966
SOURCE = Path(__file__).resolve().parents[3] / "assets/koth/plasma-filaments.png"

# Library mode only imports graph helpers; no CE assets or labels are built.
os.environ["MJ_CE_LIBRARY"] = "1"
module_spec = importlib.util.spec_from_file_location(
    "koth_ce_graphs", Path(__file__).with_name("build_ce_materials.py"))
ce = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(ce)

FIELD_CODE = r"""
// Plane local X is vertical; local Y follows the polygon edge. Using the
// world angle for the texture and markings keeps them continuous at seams.
float h = saturate(Local.x * 0.01 + 0.5);
float arc = atan2(W.y - Center.y, W.x - Center.x) / 6.2831853 + 0.5;
float base = Profile.y / max(Profile.x, 1.0) + 0.025;
float top = 0.95;
float v = saturate((h - base) / (top - base));
float aa = clamp(length(Cam - W) * 0.0006, 0.8, 4.0) / max(Profile.x, 1.0);
float lower = exp2(-2.0 * pow((h - base) / aa, 2.0));
float upper = exp2(-2.0 * pow((h - top) / aa, 2.0));
float inside = smoothstep(base - 0.008, base + 0.025, h)
             * (1.0 - smoothstep(top - 0.025, top + 0.008, h));
float dash = step(0.22, frac(arc * 64.0));
float dashedRail = exp2(-2.0 * pow((h - base - 0.055) / (aa * 0.7), 2.0)) * dash;
float tickX = abs(frac(arc * 16.0 + 0.5) - 0.5);
float tick = (1.0 - smoothstep(0.004, 0.010, tickX))
           * (1.0 - smoothstep(0.24, 0.29, v));
float crossbar = (1.0 - smoothstep(0.025, 0.045, tickX))
               * exp2(-2.0 * pow((v - 0.15) / (aa * 1.2), 2.0));
float scan = pow(0.5 + 0.5 * cos(v * 48.0 * 6.2831853), 12.0) * 0.10;
float columns = pow(0.5 + 0.5 * cos(arc * 256.0 * 6.2831853), 28.0) * 0.025;
float2 cell = floor(float2(arc * 256.0, v * 48.0 - Time * 2.0));
float cellHash = frac(sin(dot(cell, float2(127.1, 311.7))) * 43758.5453);
float glyph = step(0.988, cellHash) * 0.26;

// The authored mask supplies organic branching; two differently moving
// samples prevent each geometric panel looking like a repeated sprite.
float2 flow = float2(arc * 4.0 - Time * 0.018, v * 0.28 - Time * 0.035);
// Explicit distance LOD also compiles in ray-tracing permutations, where
// pixel derivatives are unavailable. Fine filaments must not crawl at range.
float lod = clamp(log2(max(length(Cam - W) * 0.0005 * 1024.0 * 0.28 / max(Profile.x, 1.0), 1.0)), 0.0, 5.0);
float p0 = Texture2DSampleLevel(Plasma, PlasmaSampler, flow, lod).r;
float p1 = Texture2DSampleLevel(Plasma, PlasmaSampler,
    float2(arc * 4.0 + Time * 0.011 + 0.37, v * 0.33 + Time * 0.026 + 0.43), max(lod, 1.0)).r;
// Lift selected branch cores, not the whole veil. Quiet gaps are essential
// to distinguishing plasma arcs from a uniform watery surface.
float plasma = pow(saturate((max(p0, p1 * 0.3) - 0.025) * 3.2), 1.15);
float drift = 0.72 + 0.28 * sin(arc * 6.2831853 * 3.0 - Time * 1.2);
float plasmaEnvelope = sin(v * 3.14159265) * inside;
float pulse = 1.0 + State.x * (0.20 + 0.20 * sin(Time * 4.712389));
// A broad lower halo and a visible veil retain the hill's silhouette in
// bright outdoor maps. Fine scanlines preserve the holographic surface.
float railGlow = exp2(-2.0 * pow((h - base) / 0.055, 2.0)) * 0.65;
float topGlow = exp2(-2.0 * pow((h - top) / 0.028, 2.0)) * 0.18;
float rails = lower * 1.65 + upper * 0.95 + dashedRail * 0.40 + railGlow + topGlow;
float details = inside * (tick * 0.72 + crossbar * 0.36 + scan + columns + glyph);
float energy = plasma * plasmaEnvelope * drift * (1.05 + State.x * 0.35);
float3 tint = lerp(Color.rgb, Accent.rgb, saturate(energy * 0.7 + lower * 0.15));
float veil = inside * (0.09 + 0.13 * pow(1.0 - v, 2.0));
float opacity = saturate(inside * (0.16 + 0.09 * pow(1.0 - v, 3.0)) + rails * 0.20 + energy * 0.12);
float3 light = (tint * (rails + details + energy * 1.45 + veil)
             + float3(1.0, 0.72, 0.30) * energy * 0.08) * State.y * pulse;
// Preserve emissive energy under alpha compositing. Actual opacity gives
// the veil body against pale terrain without a solid wall blocking players.
return float4(light / max(opacity, 0.001), opacity);
"""

BEACON_CODE = r"""
float z = max(W.z - Center.z, 0.0);
float azimuth = atan2(W.y - Center.y, W.x - Center.x) / 6.2831853 + 0.5;
float facing = saturate(abs(dot(normalize(N), normalize(Cam - W))));
// The cylinder's end caps must not become glowing discs.
float side = 1.0 - smoothstep(0.15, 0.75, abs(N.z));
float core = pow(facing, 12.0);
float braid = pow(saturate(0.5 + 0.5 * sin(azimuth * 18.849556 - z * 0.012 + Time * 1.6)), 20.0);
float plasma = Texture2DSampleLevel(Plasma, PlasmaSampler,
    float2(azimuth * 2.0 + Time * 0.025, z / 850.0 - Time * 0.13),
    clamp(log2(max(length(Cam - W) / 850.0, 1.0)), 0.0, 5.0)).r;
float lift = pow(saturate(0.5 + 0.5 * sin(z * 0.017 - Time * 3.0)), 32.0);
float fade = 1.0 - smoothstep(Profile.z * 0.65, Profile.z, z);
float foot = 1.0 - smoothstep(0.0, 120.0, z);
float pulse = 1.0 + State.x * (0.15 + 0.15 * sin(Time * 4.712389));
float sheath = pow(facing, 2.5) * 0.34;
float2 sparkUV = float2(azimuth * 48.0, z / 26.0 - Time * 4.0);
float2 sparkCell = floor(sparkUV);
float sparkHash = frac(sin(dot(sparkCell, float2(127.1, 311.7))) * 43758.5453);
float2 sparkLocal = frac(sparkUV) - 0.5;
float spark = step(0.975, sparkHash) * exp2(-dot(sparkLocal * float2(9.0, 5.0), sparkLocal * float2(9.0, 5.0)));
float power = core * 1.3 + braid * 0.56 + plasma * 0.55 + sheath
            + lift * facing * 0.16 + foot * 0.40 + spark * 1.6;
// A single flat plane at the beacon's foot shares this MID. Broken brackets
// anchor the objective without a solid disc (the cylinder caps stay empty).
float radial = length(W.xy - Center.xy);
float bracket = step(0.20, frac(azimuth * 4.0 + 0.10));
float groundRail = exp2(-2.0 * pow((radial - 76.0) / 1.5, 2.0)) * bracket;
float innerRail = exp2(-2.0 * pow((radial - 60.0) / 1.0, 2.0)) * bracket;
float notch = (1.0 - smoothstep(0.02, 0.045, abs(frac(azimuth * 4.0) - 0.5)))
            * smoothstep(56.0, 60.0, radial) * (1.0 - smoothstep(78.0, 82.0, radial));
float anchor = (groundRail * 0.75 + innerRail * 0.3 + notch * 0.5) * (1.0 - side);
return (lerp(Color.rgb, lerp(Accent.rgb, float3(1.0, 1.0, 1.0), 0.32), core * 0.8) * power * side * fade
    + Accent.rgb * anchor) * State.y * pulse;
"""


def build_material(name, code, texture):
    material = ce.fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    field = name == "M_KOTH_Field"
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT if field else unreal.BlendMode.BLEND_ADDITIVE)
    material.set_editor_property("two_sided", name == "M_KOTH_Field")
    material.set_editor_property("used_with_static_lighting", False)
    g = ce.Graph(material)
    tex = g.node(unreal.MaterialExpressionTextureObjectParameter,
                 parameter_name="PlasmaMask", texture=texture,
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    world_position = g.node(unreal.MaterialExpressionWorldPosition)
    local_position = g.node(unreal.MaterialExpressionTransformPosition,
        transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD,
        transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
    ce.link(world_position, "", local_position, "")
    inputs = [
        ("W", world_position, ""),
        ("Local", local_position, ""),
        ("N", g.node(unreal.MaterialExpressionVertexNormalWS), ""),
        ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS), ""),
        ("Time", g.node(unreal.MaterialExpressionTime), ""),
        ("Plasma", tex, ""),
        ("Color", g.vector4("FieldColor", (1.0, 0.55, 0.08, 1.0)), ""),
        ("Accent", g.vector4("AccentColor", (1.0, 0.8, 0.25, 1.0)), ""),
        ("Center", g.vector4("FieldCenter", (0.0, 0.0, 0.0, 800.0)), ""),
        ("State", g.vector4("FieldState", (0.0, 1.0, 0.0, 0.0)), ""),
        ("Profile", g.vector4("FieldProfile", (170.0, 35.0, 7000.0, 0.0)), ""),
    ]
    shader = g.custom(code, inputs, description="KOTH " + name,
        output=unreal.CustomMaterialOutputType.CMOT_FLOAT4 if field else unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    emission = g.mask(shader, r=True, g=True, b=True) if field else shader
    ce.mel.connect_material_property(g.to_screen(emission), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if field:
        ce.mel.connect_material_property(g.mask(shader, a=True), "", unreal.MaterialProperty.MP_OPACITY)
    ce.mel.recompile_material(material)
    ce.eal.save_loaded_asset(material)


if not SOURCE.is_file():
    raise FileNotFoundError(SOURCE)
texture = ce.import_texture(str(SOURCE), ROOT, "T_KOTH_PlasmaFilaments")
if texture is None:
    raise RuntimeError("KOTH filament texture import failed")
texture.set_editor_property("srgb", False)
texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
# Imagegen's source dimensions need not be powers of two. Let the normal
# texture build resample it for wrapping mipmaps; preserve the original PNG.
texture.set_editor_property("power_of_two_mode", unreal.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO)
texture.set_editor_property("max_texture_size", 1024)
texture.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
texture.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
texture.set_editor_property("address_y", unreal.TextureAddress.TA_WRAP)
ce.eal.save_loaded_asset(texture)

build_material("M_KOTH_Field", FIELD_CODE, texture)
build_material("M_KOTH_Beacon", BEACON_CODE, texture)
label = ce.fresh(ROOT, "PAL_KOTH", unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", CHUNK)
rules.set_editor_property("priority", 20)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
ce.eal.save_loaded_asset(label)
unreal.log("MJOLNIR KOTH materials ready: " + ROOT + " chunk " + str(CHUNK))
