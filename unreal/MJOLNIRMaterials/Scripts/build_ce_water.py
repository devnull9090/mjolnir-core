"""Build M_CE_Ocean, the water MJOLNIRLevelLoader draws a converted map's CE
water with (`mjolnir_water ocean`), and label its folder for chunk 982.

    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_water.py

Single Layer Water, Unreal's water shading model, so the sea reflects (Lumen,
then the sky light), refracts and absorbs what lies under it. Its waves are
its own: the game's Fluid Flux ocean draws its waves only beyond a few hundred
metres of the camera and leaves the water around the player to its runtime
mesh generator, which a converted map has no way to run (2026-10-10).

- Swell: four Gerstner waves (`Wave0`..`Wave3`: direction x, y, wavelength
  in cm, steepness), scaled by `WaveAmplitude` and run at `WaveSpeed`, move
  the vertices (World Position Offset) and give the normal analytically. The
  water mesh is refined to carry them (tools/level/refine_water_gltf.py).
- Detail: CE's own ripple maps, with M_CE_Water's parameter names
  (RippleGlobal, Ripple0..3, Ripple0..3Offset, RippleMap0..3, RippleMip), so
  the loader passes a map's water spec straight through; `DetailStrength`
  scales them on top of the swell.
- Look: `Absorption` and `Scattering` (Single Layer Water coefficients, per
  metre), `PhaseG`, `ColorScaleBehindWater`, `Roughness`, `Specular`.
  Defaults tuned on Death Island (2026-10-11): CE's ripple maps have hard
  edges, and above DetailStrength 0.05 or below Roughness 0.16 the beach
  reflected in them as sharp-edged blots.

The normal is worked out in world space (the swell's analytically, the
ripples' brought there) and handed over in tangent space. A material cooked
with tangent space normal off crashes the game as it loads, any shading
model, any graph (M_CE_OceanT1/T2, 2026-10-11): the CE masters, which load,
all keep it on.

A master of its own, in /Game/MJOLNIR/Water and chunk 982, beside the runtime
pack's 988 (build_ce_materials.py) rather than in it: it ships and is tested
without re-cooking the runtime pack.
"""
import os
import struct
import zlib

import unreal

ROOT = "/Game/MJOLNIR/Water"
CHUNK = 982

assets = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary


def link(src, pin, dst, dst_pin):
    if not mel.connect_material_expressions(src, pin, dst, dst_pin):
        raise RuntimeError(f"cannot connect {src.get_name()}.{pin!r} -> {dst.get_name()}.{dst_pin!r}")


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

    def scalar(self, name, default=0.0):
        return self.node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=default)

    def vector(self, name, default=(1.0, 1.0, 1.0, 1.0)):
        return self.node(unreal.MaterialExpressionVectorParameter, parameter_name=name,
                         default_value=unreal.LinearColor(*default))

    def vector4(self, name, default):
        v = self.vector(name, default)
        a = self.node(unreal.MaterialExpressionAppendVector, x=-1200)
        link(v, "", a, "A")
        link(v, "A", a, "B")
        return a

    def texture(self, name, default, uvs):
        t = self.node(unreal.MaterialExpressionTextureSampleParameter2D, x=-1100, parameter_name=name,
                      texture=default, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(uvs, "", t, "UVs")
        return t

    def custom(self, code, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="CE"):
        c = self.node(unreal.MaterialExpressionCustom, x=-500, code=code, output_type=output, description=description)
        ins = []
        for name, _src, _pin in inputs:
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", name)
            ins.append(ci)
        c.set_editor_property("inputs", ins)
        for name, src, pin in inputs:
            link(src, pin, c, name)
        return c


# Gerstner waves, in centimetres (g = 980 cm/s^2). Each wave: direction xy,
# wavelength L, steepness Q (0..1, crests sharpen towards 1). k = 2 pi / L,
# phase speed c = sqrt(g / k), amplitude a = Q / k. The sum is the offset of
# a point of the still surface (P.xy); the normal comes from the analytic
# derivatives of the same sum (GPU Gems 1, ch. 1).
GERSTNER = r"""
float4 W[4] = { W0, W1, W2, W3 };
// The swell dies over shallow water and at the waterline (Shore: TEXCOORD_1,
// metres to the shore and depth of the sea floor, refine_water_gltf.py
// bake_shore): a trough left sandbars dry, drawn flat green.
float damp = saturate((Shore.y - 0.05) / max(DampDepth, 0.01)) * saturate(Shore.x / 6.0);
float3 o = 0;
float3 nx = float3(1, 0, 0), ny = float3(0, 1, 0);
float t = Time * Speed;
[unroll] for (int i = 0; i < 4; i++)
{
    float L = max(W[i].z, 1.0);
    float k = 6.2831853 / L;
    float c = sqrt(980.0 / k);
    float2 d = W[i].xy;
    d = d * rsqrt(max(dot(d, d), 1e-6));
    float q = saturate(W[i].w * Amp * damp);
    float a = q / k;
    float f = k * (dot(d, P.xy) - c * t);
    float s = sin(f), co = cos(f);
    o += float3(d * a * co, a * s);
    // Tangent and binormal of the displaced surface.
    nx += float3(-d.x * d.x * q * s, -d.x * d.y * q * s, d.x * q * co);
    ny += float3(-d.x * d.y * q * s, -d.y * d.y * q * s, d.y * q * co);
}
"""

# Shore waves: bands that roll towards the beach within Reach metres of it,
# about Len metres apart, Freq a second, cresting up to Height cm high (S =
# Reach, Len, Freq, Height); they fade at the waterline itself (the last
# 1.5 m). A crest is where d / Len + Freq t (+ a shift) is a quarter past a
# whole number, so it moves to smaller d as time runs. Two smooth noises over
# the shore (world xy, cm) keep the bands from running as parallel stripes:
# one bends them (a shift of up to 1.6 bands over ~40 m), the other swells
# and fades each stretch of them as time goes (Death Island, 2026-10-11:
# fixed bands read as painted stripes).
SHORE_H = r"""
static float n2(float2 p)
{
    float2 i = floor(p), f = frac(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
    float b = frac(sin(dot(i + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
    float c = frac(sin(dot(i + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
    float e = frac(sin(dot(i + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
    return lerp(lerp(a, b, f.x), lerp(c, e, f.x), f.y);
}
static float phase(float d, float2 xy, float t, float4 S)
{
    float2 q = xy * 0.0001;
    return d / max(S.y, 0.1) + t * S.z + 1.6 * n2(q * 2.5 + t * 0.01);
}
static float strength(float2 xy, float t)
{
    return 0.3 + 0.7 * smoothstep(0.2, 0.75, n2(xy * 0.00017 + 17.0 + t * 0.03));
}
static float h(float d, float2 xy, float t, float4 S)
{
    float env = saturate(1.0 - d / max(S.x, 1.0)) * saturate(d / 1.5);
    float crest = 0.5 + 0.5 * sin(6.2831853 * phase(d, xy, t, S));
    return S.w * env * crest * crest * crest * strength(xy, t);
}
"""

GERSTNER_OFFSET = GERSTNER + "return o + float3(0, 0, ShoreFns::h(Shore.x, P.xy, Time, ShoreParams));\n"
# The shore waves' slope in the pixel shader: dh/dd from h either side, and
# the shore distance's world gradient from the screen derivatives of it and
# of the (unoffset) position, solved in the plane.
GERSTNER_NORMAL = GERSTNER + r"""
float3 n = normalize(cross(nx, ny));
float slope = (ShoreFns::h(Shore.x + 0.25, Flat.xy, Time, ShoreParams)
             - ShoreFns::h(Shore.x - 0.25, Flat.xy, Time, ShoreParams)) / 50.0;
float2 a = ddx(Flat.xy), b = ddy(Flat.xy);
float da = ddx(Shore.x), db = ddy(Shore.x);
float det = a.x * b.y - a.y * b.x;
float2 g = abs(det) > 1e-4 ? float2(da * b.y - db * a.y, a.x * db - b.x * da) / det * 100.0 : float2(0, 0);
float gl = length(g);
if (gl > 1.5) g *= 1.5 / gl;
return normalize(n + float3(-slope * g, 0));
"""

# Foam: on the shore waves' crests, where they are strong, and a swash at the
# waterline that runs up and back (1 to 4 m out, ~10 s a cycle, out of step
# along the shore); both broken by two octaves of noise drifting slowly, so
# they read as foam rather than a smooth white line.
FOAM = r"""
float d = Shore.x;
float2 xy = P.xy;
float env = saturate(1.0 - d / max(ShoreParams.x, 1.0));
float crest = saturate(0.5 + 0.5 * sin(6.2831853 * ShoreFns::phase(d, xy, Time, ShoreParams)));
float wave = env * pow(crest, 5.0) * ShoreFns::strength(xy, Time);
float reach = 1.0 + 3.0 * (0.5 + 0.5 * sin(Time * 0.6 + 6.2831853 * ShoreFns::n2(xy * 0.0003)));
float swash = saturate(1.0 - d / reach);
float n = 0.6 * ShoreFns::n2(xy * 0.004 + Time * 0.05) + 0.4 * ShoreFns::n2(xy * 0.017 - Time * 0.08);
float f = saturate((wave * 1.4 + swash) * 1.5 - (1.0 - n) * 0.9);
return saturate(f * Amount) * step(0.01, Shore.y + d);
"""

# M_CE_Water's ripple uv and normal (build_ce_materials.py), unchanged.
RIPPLE_UV = r"""
float2 ub = UV * Global.z + Time * Global.y * float2(cos(Global.x), sin(Global.x));
return ub * Ripple.w + Time * Ripple.z * float2(cos(Ripple.y), sin(Ripple.y)) + Offset.xy;
"""

RIPPLE_NORMAL = r"""
float4 c = float4(R0c.x, R1c.x, R2c.x, R3c.x);
if (c.x + c.y <= 0.0) c.y = 1.0;
if (c.z + c.w <= 0.0) c.w = 1.0;
float3 n0 = R0.rgb * 2.0 - 1.0, n1 = R1.rgb * 2.0 - 1.0, n2 = R2.rgb * 2.0 - 1.0, n3 = R3.rgb * 2.0 - 1.0;
float3 P = (c.x * n0 + c.y * n1) / (c.x + c.y);
float3 Q = (c.z * n2 + c.w * n3) / (c.z + c.w);
float3 n = lerp(P, Q, (c.z + c.w) / (c.x + c.y + c.z + c.w));
float2 ub = UV * Global.z;
float2 fp = max(abs(ddx(ub)), abs(ddy(ub))) * 128.0;
float levels = clamp(Mip.x, 1.0, 4.0);
float lod = clamp(log2(max(max(fp.x, fp.y), 1e-6)) - Mip.z, 0.0, levels - 1.0);
if (levels > 1.0) n = lerp(n, float3(0.0, 0.0, 1.0), lod / (levels - 1.0) * Mip.y);
return n * rsqrt(max(dot(n, n), 1e-8));
"""

# The swell's normal tilted by the ripples' (world space, the ripple map's
# flat being +z): the ripple's deviation from flat, scaled, added on.
COMBINE_NORMAL = r"""
float3 r = Ripple - float3(0, 0, 1);
float near = saturate(1.0 - Shore.x / 30.0) * step(0.01, Shore.x + Shore.y);
// Chop: two layers of the detail wave map (normal in rg), crossing.
float2 c = (C0.rg * 2.0 - 1.0) + (C1.rg * 2.0 - 1.0);
return normalize(Swell + r * Strength * (1.0 + NearShore * near) + float3(c * Chop, 0));
"""

# The chop layers' UVs: world xy over ChopScale.x cm, panning at ChopScale.y
# cm/s in two directions, the second layer rotated and 0.63 times the size.
CHOP_UV0 = r"""
return P.xy / max(S.x, 1.0) + Time * S.y / max(S.x, 1.0) * float2(0.8, 0.6);
"""
CHOP_UV1 = r"""
float2 q = float2(P.x * 0.6 - P.y * 0.8, P.x * 0.8 + P.y * 0.6);
return q / max(S.x * 0.63, 1.0) + Time * S.y / max(S.x * 0.63, 1.0) * float2(-0.7, 0.7);
"""


def with_shore(code):
    """`code` with SHORE_H's helpers (ShoreFns::h, phase, strength, n2): a
    Custom node's code is one function body, so they are static functions in
    a nested struct (the usual way to define them inside a Custom node)."""
    return "struct ShoreFns {" + SHORE_H + "};\n" + code


def build_ocean(flat, name="M_CE_Ocean", slw=True, wpo=True, graph=True):
    """M_CE_Ocean; the switches build the test variants (MJ_WATER_TESTS):
    without the water shading model, without the wave offset, or without
    the swell and ripple graph."""
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER if slw
                          else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    # The shore foam moves in the pixel shader, not with the geometry; TSR
    # smeared it into streaks until told so.
    try:
        m.set_editor_property("has_pixel_animation", True)
    except Exception as e:
        unreal.log_warning(f"has_pixel_animation: {e}")
    g = Graph(m)
    if not graph:
        mel.connect_material_property(g.vector("Up", (0, 0, 1, 1)), "", unreal.MaterialProperty.MP_NORMAL)
        if slw:
            build_water_output(g)
        else:
            mel.connect_material_property(g.vector("BaseColor", (0.05, 0.2, 0.25, 1)), "",
                                          unreal.MaterialProperty.MP_BASE_COLOR)
        mel.recompile_material(m)
        eal.save_loaded_asset(m)
        return
    time = g.node(unreal.MaterialExpressionTime)
    world = g.node(unreal.MaterialExpressionWorldPosition, x=-2000)
    still = g.node(unreal.MaterialExpressionWorldPosition, x=-2000,
                  world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    shore = g.node(unreal.MaterialExpressionTextureCoordinate, x=-2000, coordinate_index=1)
    shore_params = g.vector4("ShoreParams", (40.0, 14.0, 0.12, 22.0))
    waves = [("W0", g.vector4("Wave0", (1.0, 0.35, 6000.0, 0.10)), ""),
             ("W1", g.vector4("Wave1", (0.6, 1.0, 3100.0, 0.08)), ""),
             ("W2", g.vector4("Wave2", (-0.4, 1.0, 1700.0, 0.06)), ""),
             ("W3", g.vector4("Wave3", (1.0, -0.7, 900.0, 0.05)), "")]
    common = waves + [("P", world, ""), ("Time", time, ""),
                      ("Amp", g.scalar("WaveAmplitude", 1.0), ""), ("Speed", g.scalar("WaveSpeed", 1.0), ""),
                      ("Shore", shore, ""), ("ShoreParams", shore_params, ""),
                      ("DampDepth", g.scalar("DampDepth", 1.0), "")]
    offset = g.custom(with_shore(GERSTNER_OFFSET), common, description="Gerstner offset")
    swell_n = g.custom(with_shore(GERSTNER_NORMAL), common + [("Flat", still, "")], description="Gerstner normal")
    # World Position Offset has no MaterialProperty in the editor's Python;
    # MjolnirUIBuilder wires it (as build_ce_materials.py's sky_offset does).
    if wpo and not unreal.MjolnirUIBuilderLibrary.connect_world_position_offset(m, offset, ""):
        raise RuntimeError(f"cannot connect World Position Offset on {name}")

    uv0 = g.node(unreal.MaterialExpressionTextureCoordinate, x=-2000, coordinate_index=0)
    glob = g.vector4("RippleGlobal", (0, 0, 1, 0))
    samples, contribs = [], []
    for k in range(4):
        ripple = g.vector4(f"Ripple{k}", (0, 0, 0, 1))
        uv = g.custom(RIPPLE_UV, [("UV", uv0, ""), ("Time", time, ""), ("Global", glob, ""), ("Ripple", ripple, ""),
                                  ("Offset", g.vector4(f"Ripple{k}Offset", (0, 0, 0, 0)), "")],
                      output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description=f"ripple {k} uv")
        samples.append(g.texture(f"RippleMap{k}", flat, uv))
        contribs.append(ripple)
    inputs = [(f"R{k}", s, "RGBA") for k, s in enumerate(samples)]
    inputs += [(f"R{k}c", c, "") for k, c in enumerate(contribs)]
    inputs += [("UV", uv0, ""), ("Global", glob, ""), ("Mip", g.vector4("RippleMip", (1, 0, 0, 0)), "")]
    ripple_t = g.custom(RIPPLE_NORMAL, inputs, description="ripple normal")
    ripple_w = g.node(unreal.MaterialExpressionTransform, x=-800,
                      transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                      transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(ripple_t, "", ripple_w, "")
    chop_scale = g.vector4("ChopScale", (1100.0, 60.0, 0.0, 0.0))
    chops = []
    for k, code in enumerate((CHOP_UV0, CHOP_UV1)):
        uvc = g.custom(code, [("P", still, ""), ("Time", time, ""), ("S", chop_scale, "")],
                       output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description=f"chop {k} uv")
        chops.append(g.texture("DetailWave", flat, uvc))
    normal = g.custom(COMBINE_NORMAL, [("Swell", swell_n, ""), ("Ripple", ripple_w, ""),
                                       ("C0", chops[0], "RGBA"), ("C1", chops[1], "RGBA"),
                                       ("Chop", g.scalar("ChopStrength", 0.07), ""),
                                       ("Strength", g.scalar("DetailStrength", 0.05), ""),
                                       ("Shore", shore, ""), ("NearShore", g.scalar("NearShoreDetail", 3.0), "")],
                      description="water normal")
    tangent = g.node(unreal.MaterialExpressionTransform, x=-300,
                     transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                     transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
    link(normal, "", tangent, "")
    mel.connect_material_property(tangent, "", unreal.MaterialProperty.MP_NORMAL)
    foam = g.custom(with_shore(FOAM), [("Shore", shore, ""), ("Time", time, ""), ("ShoreParams", shore_params, ""),
                                       ("P", still, ""),
                           ("Ripple", ripple_t, ""), ("Amount", g.scalar("FoamAmount", 1.0), "")],
                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="shore foam")
    rough = g.node(unreal.MaterialExpressionLinearInterpolate, x=-300)
    link(g.scalar("Roughness", 0.16), "", rough, "A")
    link(g.scalar("FoamRoughness", 0.6), "", rough, "B")
    link(foam, "", rough, "Alpha")
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(g.vector("FoamColor", (0.8, 0.85, 0.85, 1.0)), "",
                                  unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(foam, "", unreal.MaterialProperty.MP_OPACITY)
    mel.connect_material_property(g.scalar("Specular", 0.5), "", unreal.MaterialProperty.MP_SPECULAR)
    if slw:
        build_water_output(g)
    else:
        mel.connect_material_property(g.vector("BaseColor", (0.05, 0.2, 0.25, 1)), "",
                                      unreal.MaterialProperty.MP_BASE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


def build_water_output(g):
    out = g.node(unreal.MaterialExpressionSingleLayerWaterMaterialOutput, x=-200)

    def to_output(src, names):
        """The output node's pins go by their display names, which carry
        units in some engine versions: try each spelling."""
        for name in names:
            if mel.connect_material_expressions(src, "", out, name):
                return
        raise RuntimeError(f"Single Layer Water output: none of {names}")

    to_output(g.vector("Scattering", (0.04, 0.16, 0.18, 1.0)),
              ("ScatteringCoefficients", "Scattering Coefficients", "Scattering Coefficients (per centimeter)",
               "Scattering Coefficients (per meter)"))
    to_output(g.vector("Absorption", (0.35, 0.08, 0.06, 1.0)),
              ("AbsorptionCoefficients", "Absorption Coefficients", "Absorption Coefficients (per centimeter)",
               "Absorption Coefficients (per meter)"))
    to_output(g.scalar("PhaseG", 0.3), ("PhaseG", "Phase G"))
    to_output(g.scalar("ColorScaleBehindWater", 1.0), ("ColorScaleBehindWater", "Color Scale Behind Water"))


def build_label():
    label = fresh(ROOT, "PAL_MJOLNIR_Water", unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", CHUNK)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)


def build_flat():
    """T_Water_Flat, a flat ripple: CE's ripple maps are colour textures the
    graph unpacks itself (BGRA8, no sRGB: build_ce_materials.py's
    ce_texture_settings), so the default is one of those too. The engine's
    FlatNormal is a normal map, and a linear-colour sampler refuses it."""
    scratch = os.path.join(unreal.Paths.project_saved_dir(), "ce_water")
    os.makedirs(scratch, exist_ok=True)
    file = os.path.join(scratch, "T_Water_Flat.png")
    row = b"\0" + bytes((128, 128, 255, 255)) * 4
    raw = zlib.compress(row * 4)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(file, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", raw))
        f.write(chunk(b"IEND", b""))
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", file)
    task.set_editor_property("destination_path", ROOT)
    task.set_editor_property("destination_name", "T_Water_Flat")
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    assets.import_asset_tasks([task])
    tex = unreal.load_asset(f"{ROOT}/T_Water_Flat")
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("never_stream", True)
    eal.save_loaded_asset(tex)
    return tex


build_label()
flat = build_flat()
build_ocean(flat)
if os.environ.get("MJ_WATER_TESTS"):
    build_ocean(flat, "M_CE_OceanT1", slw=False)
    build_ocean(flat, "M_CE_OceanT2", graph=False)
    build_ocean(flat, "M_CE_OceanT3", wpo=False)
unreal.log("MJOLNIR CE water built")
