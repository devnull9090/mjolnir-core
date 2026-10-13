"""Build M_CE_Ocean, the water MJOLNIRLevelLoader draws a converted map's CE
water with (`mjolnir_water ocean`), and label its folder for chunk 982.

    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_water.py

Thin Translucent (lit per pixel, Surface ForwardShading), so the sea floor
shows through it: what lies behind is dimmed by the water between it and the
surface, read from the depth buffer, per colour (`Absorption`), and the
water's own colour builds up over the same depth (`Clarity`); both go to
nothing exactly where the water meets the sand. Unreal's Single Layer Water
does that through refraction, which the game forces off
(r.Water.SingleLayer.Refraction stays 0): it drew the water opaque to the
shore, and every fade on top of it left a line along the beach (Death
Island, 2026-10-11).

The reflection is CE's own, worked out in the material: the level's water
cube map (`ReflectionCube`, CE's `PerpBrightness`/`ParaBrightness` and
`PerpTint`/`ParaTint`), at full strength however clear the water under it
is. The engine's reflections on translucency came back black in this game,
whatever the sky light held: Lumen's radiance cache and front layer, and the
sky light's cube map (CE's sky is a mesh the sky light never captures).

Its waves are its own: the game's Fluid Flux ocean draws its waves only
beyond a few hundred metres of the camera and leaves the water around the
player to its runtime mesh generator, which a converted map has no way to
run (2026-10-10).

- Swell: four Gerstner waves (`Wave0`..`Wave3`: direction x, y, wavelength
  in cm, steepness), scaled by `WaveAmplitude` and run at `WaveSpeed`, move
  the vertices (World Position Offset) and give the normal analytically. The
  water mesh is refined to carry them (tools/level/refine_water_gltf.py).
- Detail: CE's own ripple maps, with M_CE_Water's parameter names
  (RippleGlobal, Ripple0..3, Ripple0..3Offset, RippleMap0..3, RippleMip), so
  the loader passes a map's water spec straight through; `DetailStrength`
  scales them on top of the swell.
- Look: `Absorption` (per metre of water along the view, per colour),
  `WaterColor` (the water's own colour where it is deep), `Clarity` (metres
  of water along the view that turn 63% of it to WaterColor), `Roughness`,
  `Specular` (thinned over the first `EdgeFilm` metres of water, so the
  waterline is not a reflective edge), and the shore foam's `FoamColor`.
  Defaults tuned on Death Island (2026-10-11): CE's ripple maps have hard
  edges, and above DetailStrength 0.05 or below Roughness 0.16 the beach
  reflected in them as sharp-edged blots.

The normal is worked out in world space (the swell's analytically, the
ripples' brought there) and handed over in tangent space. A material cooked
with tangent space normal off crashes the game as it loads, any shading
model, any graph (test masters, 2026-10-11): the CE masters, which load, all
keep it on.

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
float damp = saturate((Shore.y - 0.05) / max(DampDepth, 0.01)) * saturate(Shore.x / 20.0);
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
    float env = saturate(1.0 - d / max(S.x, 1.0)) * smoothstep(2.0, 10.0, d);
    float crest = 0.5 + 0.5 * sin(6.2831853 * phase(d, xy, t, S));
    return S.w * env * crest * crest * crest * strength(xy, t);
}
"""

# The waterline stays where CE drew it: no vertical motion in the last 5 m
# (the swell and shore waves lifting the edge cut a staircase into a gentle
# beach, and showed the water mesh's edge as a blue wall, 2026-10-11).
GERSTNER_OFFSET = GERSTNER + (
    "return (o + float3(0, 0, ShoreFns::h(Shore.x, P.xy, Time, ShoreParams))) * saturate(Shore.x / 5.0);\n")
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

# Foam: on the shore waves' crests, where they are strong, broken by three
# octaves of noise down to ~15 cm so it reads as lacy foam. No swash foam at
# the waterline: drawn on the flat surface it was a pale band, and from a
# player's eye the sand's crest cut it off in a straight line along the beach
# (Death Island, 2026-10-11).
FOAM = r"""
float d = Shore.x;
float2 xy = P.xy;
float env = saturate(1.0 - d / max(ShoreParams.x, 1.0));
float crest = saturate(0.5 + 0.5 * sin(6.2831853 * ShoreFns::phase(d, xy, Time, ShoreParams)));
float wave = env * pow(crest, 8.0) * ShoreFns::strength(xy, Time);
float n = 0.5 * ShoreFns::n2(xy * 0.01 + Time * 0.05) + 0.3 * ShoreFns::n2(xy * 0.031 - Time * 0.08)
        + 0.2 * ShoreFns::n2(xy * 0.07 + Time * 0.11);
float f = saturate(wave * 3.2 - (1.0 - n) * 1.4);
// It fades out with the waves themselves (SHORE_H's envelope): foam run up
// to the waterline drew a hard white edge along the sand.
return saturate(f * Amount) * step(0.01, Shore.y + d) * smoothstep(2.0, 8.0, d);
"""

# Two lengths. First, the metres of water along the view ray between the
# surface and what lies behind it: scene depth less the water's own (both
# along the camera's axis), stretched to the ray. Shallows give nothing at the waterline; deep water,
# or water seen at a grazing angle, a lot.
#
# The second: the same, with the sea taken to be at least Shelf.x metres
# deep (rising as 1 - exp(-d / Shelf.y) from Shelf.z metres out), whatever
# is under it: CE's seas are a metre or two deep to the horizon (Death
# Island, Yoyorast), and the sand showed through all of it like a wading
# pool. It deepens the water's colour only: the reflection, faded by the
# real path, came on at once where the shelf started at the waterline, and
# drew the line along the beach again.
WATER_PATH = r"""
float behind = max(Scene - Pixel, 0.0);
float ray = length(P - Cam) / max(Pixel, 1.0);
float real = behind * ray * 0.01;
float shelf = Shelf.x * (1.0 - exp(-max(Shore.x - Shelf.z, 0.0) / max(Shelf.y, 0.01)))
    * step(0.01, Shore.x + Shore.y);
float up = max(abs(normalize(Cam - P).z), 0.05);
return float2(real, max(real, shelf / up));
"""
# What gets through, per colour (Beer's law). Thin Translucent stretches it
# by 1 / N.V itself (a sheet's thickness); the path is the whole ray already.
WATER_TRANSMITTANCE = r"""
float nv = saturate(abs(dot(Parameters.WorldNormal, Parameters.CameraVector)) + 1e-5);
return exp(-Absorption.rgb * L.y * nv) * (1.0 - Foam);
"""
# How much of the surface is the water's own colour (and foam, which hides
# all), never below MinCover: the reflection rides on it (WATER_EMISSIVE).
WATER_OPACITY = "return max(saturate(max(1.0 - exp(-L.y / max(Clarity, 0.01)), Foam)), MinCover);\n"

# The reflection: CE's own (build_ce_materials.py, WATER_CODE): its cube map
# along the reflected view, brightened from PerpBrightness looking straight
# down to ParaBrightness at a grazing angle, tinted from PerpTint to
# ParaTint, in CE's gamma space and then made linear. Nothing below the
# horizon or just at it: the ripples reflected the cube's lower half as
# dark (Death Island) or saturated blue (Yoyorast) blots.
#
# The view goes into CE's axes (y flipped: Unreal's y is CE's -y), and then
# to the slot that holds each face: CE stores its faces +X, +Y, -X, -Y, +Z,
# -Z, and the converter writes them as they come into a cube Unreal reads
# as +X, -X, +Y, -Y, ... (ce_material_spec.py write_cube_dds), so CE's -X
# face sits in the +Y slot and its +Y face in the -X slot. A view towards
# -X is turned to look up the +Y slot at the same face coordinates, and one
# towards +Y to look up the -X slot. (Yoyorast's water, 2026-10-11: the sky
# on one half of the sea, a saturated blue face on the other, a hard seam.)
REFLECT_DIR = r"""
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
float3 R = 2.0 * dot(N, E) * N - E;
R.z = max(R.z, 0.08);
float3 d = normalize(float3(R.x, -R.y, R.z));
float3 a = abs(d);
if (a.x >= a.y && a.x >= a.z && d.x < 0.0) return float3(d.z, -d.x, -d.y);
if (a.y >= a.x && a.y >= a.z && d.y > 0.0) return float3(-d.y, -d.z, d.x);
return d;
"""
REFLECTION = r"""
float f = saturate(dot(N, normalize(Cam)));
float3 tint = lerp(ParaTint.rgb, PerpTint.rgb, f);
float3 c = Cube.rgb;
float3 c8 = c * c; c8 *= c8; c8 *= c8;
float3 frame = lerp(c8, c, tint) * lerp(ParaBrightness, PerpBrightness, f) * Strength;
frame = max(frame, 0.0);
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
float3 lin = lerp(hi, lo, step(frame, 0.04045));
// Towards grey by 1 - Saturation: CE's cube is a painted blue sky, and a
// sea of waves tilting into it flashed neon blue under Yoyorast's pale one.
lin = lerp(dot(lin, float3(0.2126, 0.7152, 0.0722)).xxx, lin, Saturation);
// A film of water a few centimetres deep reflects as faintly as it tints:
// at full strength, sand just under the surface showed as blue puddles.
return lin * (1.0 - Foam) * smoothstep(0.0, max(Film, 0.001), L.x);
"""
# Thin Translucent scales the emissive by the opacity (it is a layer of
# colour on the water); the reflection is not, so it goes in divided by it.
WATER_EMISSIVE = "return R / max(C, 1e-3);\n"

# M_CE_Water's ripple uv and normal (build_ce_materials.py), unchanged.
RIPPLE_UV = r"""
float2 ub = UV * Global.z + Time * Global.y * float2(cos(Global.x), sin(Global.x));
return ub * Ripple.w + Time * Ripple.z * float2(cos(Ripple.y), sin(Ripple.y)) + Offset.xy;
"""

# The ripples' own UV: the mesh's (CE's), or with RippleWorld (cm a UV
# unit) the world's x and -y. CE's UVs on Death Island's water change
# direction from triangle to triangle, and the ripple normals, turned by
# those tangents, drew every triangle edge across the sea; its distant water
# matched it nowhere (2026-10-13).
RIPPLE_BASE_UV = r"""
return RW > 0.0 ? float2(P.x, -P.y) / RW : UV;
"""

# The ripple normal in world space: by the mesh's tangents, or with
# RippleWorld the world's own axes (x, -y, z), as its UV is.
RIPPLE_WORLD_NORMAL = r"""
return RW > 0.0 ? normalize(float3(RT.x, -RT.y, RT.z)) : RWN;
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
// The swell's slopes fade out with distance (SwellFade: from, to cm, what is
// kept): four regular waves alias into stripes along the horizon (Death
// Island from its plateaus), where their shape is lost to the pixel anyway.
float far = smoothstep(SwellFade.x, SwellFade.y, length(Cam - P)) * (1.0 - SwellFade.z);
Swell = normalize(lerp(Swell, float3(0, 0, 1), far));
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


def set_optional(m, prop, value):
    """A material property some engine versions lack: warn, don't fail."""
    try:
        m.set_editor_property(prop, value)
    except Exception as e:
        unreal.log_warning(f"{prop}: {e}")


def build_ocean(flat, black_cube, name="M_CE_Ocean"):
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_THIN_TRANSLUCENT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    # Surface ForwardShading (TLM_SURFACE is Surface TranslucencyVolume,
    # which drew the water with no reflection at all): Thin Translucent
    # needs it, and Lumen's front layer translucency reflections draw for it.
    m.set_editor_property("translucency_lighting_mode",
                          unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    # The shore foam moves in the pixel shader, not with the geometry; TSR
    # smeared it into streaks until told so.
    set_optional(m, "has_pixel_animation", True)
    g = Graph(m)
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
    if not unreal.MjolnirUIBuilderLibrary.connect_world_position_offset(m, offset, ""):
        raise RuntimeError(f"cannot connect World Position Offset on {name}")

    ripple_world = g.scalar("RippleWorld", 0.0)
    uv0 = g.custom(RIPPLE_BASE_UV, [("UV", g.node(unreal.MaterialExpressionTextureCoordinate, x=-2000,
                                                     coordinate_index=0), ""),
                                    ("P", still, ""), ("RW", ripple_world, "")],
                   output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description="ripple base uv")
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
    ripple_w = g.custom(RIPPLE_WORLD_NORMAL, [("RT", ripple_t, ""), ("RWN", ripple_w, ""), ("RW", ripple_world, "")],
                        description="ripple world normal")
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
                                       ("Shore", shore, ""), ("NearShore", g.scalar("NearShoreDetail", 3.0), ""),
                                       ("P", still, ""),
                                       ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS, x=-2000), ""),
                                       ("SwellFade", g.vector4("SwellFade", (3000.0, 20000.0, 0.15, 0.0)), "")],
                      description="water normal")
    tangent = g.node(unreal.MaterialExpressionTransform, x=-300,
                     transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                     transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
    link(normal, "", tangent, "")
    mel.connect_material_property(tangent, "", unreal.MaterialProperty.MP_NORMAL)
    foam = g.custom(with_shore(FOAM), [("Shore", shore, ""), ("Time", time, ""), ("ShoreParams", shore_params, ""),
                                       ("P", still, ""),
                           ("Ripple", ripple_t, ""), ("Amount", g.scalar("FoamAmount", 0.7), "")],
                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="shore foam")
    rough = g.node(unreal.MaterialExpressionLinearInterpolate, x=-300)
    link(g.scalar("Roughness", 0.16), "", rough, "A")
    link(g.scalar("FoamRoughness", 0.6), "", rough, "B")
    link(foam, "", rough, "Alpha")
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    color = g.node(unreal.MaterialExpressionLinearInterpolate, x=-300)
    link(g.vector("WaterColor", (0.02, 0.11, 0.12, 1.0)), "", color, "A")
    link(g.vector("FoamColor", (0.8, 0.85, 0.85, 1.0)), "", color, "B")
    link(foam, "", color, "Alpha")
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    path = g.custom(WATER_PATH, [("Scene", g.node(unreal.MaterialExpressionSceneDepth, x=-2000), ""),
                                 ("Pixel", g.node(unreal.MaterialExpressionPixelDepth, x=-2000), ""),
                                 ("P", world, ""),
                                 ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS, x=-2000), ""),
                                 ("Shore", shore, ""), ("Shelf", g.vector4("Shelf", (6.0, 40.0, 5.0, 0.0)), "")],
                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description="water path")
    film = g.scalar("EdgeFilm", 1.0)
    spec = g.custom("return Specular * smoothstep(0.0, max(Film, 0.001), L.x);",
                    [("Specular", g.scalar("Specular", 0.5), ""), ("Film", film, ""),
                     ("L", path, "")],
                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="waterline specular")
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    opacity = g.custom(WATER_OPACITY, [("L", path, ""), ("Clarity", g.scalar("Clarity", 6.0), ""), ("Foam", foam, ""),
                                       ("MinCover", g.scalar("MinCover", 0.05), "")],
                       output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="water opacity")
    mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)
    # The reflection is the material's own: in this game the engine's for
    # translucency (Lumen's radiance cache, its front layer, the sky light)
    # came back black whatever the sky light held (Death Island, 2026-10-11).
    cam = g.node(unreal.MaterialExpressionCameraVectorWS, x=-2000)
    direction = g.custom(REFLECT_DIR, [("Cam", cam, ""), ("N", normal, "")], description="reflection direction")
    cube = g.node(unreal.MaterialExpressionTextureSampleParameterCube, x=-1100, parameter_name="ReflectionCube",
                  texture=black_cube, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    link(direction, "", cube, "UVs")
    # One mip, set: REFLECT_DIR's face remapping jumps between faces, and the
    # derivatives across the jump picked the smallest mip, a dark line down
    # the sea from the horizon (Death Island, 2026-10-11).
    cube.set_editor_property("mip_value_mode", unreal.TextureMipValueMode.TMVM_MIP_LEVEL)
    cube.set_editor_property("const_mip_value", 0)
    reflection = g.custom(REFLECTION, [("Cam", cam, ""), ("N", normal, ""), ("Cube", cube, "RGB"),
                                       ("PerpBrightness", g.scalar("PerpBrightness", 0.1), ""),
                                       ("ParaBrightness", g.scalar("ParaBrightness", 1.0), ""),
                                       ("PerpTint", g.vector("PerpTint"), ""), ("ParaTint", g.vector("ParaTint"), ""),
                                       ("Strength", g.scalar("ReflectionStrength", 1.0), ""), ("Foam", foam, ""),
                                       ("Saturation", g.scalar("ReflectionSaturation", 0.35), ""),
                                       ("L", path, ""), ("Film", film, "")],
                          description="CE reflection")
    screen = g.node(unreal.MaterialExpressionEyeAdaptationInverse, x=-300)
    if not any(mel.connect_material_expressions(reflection, "", screen, pin)
               for pin in ("Light Value Input", "LightValueInput", "Light Value", "LightValue")):
        raise RuntimeError("EyeAdaptationInverse: no light value pin")
    emissive = g.custom(WATER_EMISSIVE, [("R", screen, ""), ("C", opacity, "")], description="reflection, emissive")
    mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    transmittance = g.custom(WATER_TRANSMITTANCE, [("L", path, ""),
                                                   ("Absorption", g.vector("Absorption", (0.45, 0.12, 0.09, 1.0)), ""),
                                                   ("Foam", foam, "")], description="water transmittance")
    out = g.node(unreal.MaterialExpressionThinTranslucentMaterialOutput, x=-200)
    if not any(mel.connect_material_expressions(transmittance, "", out, pin)
               for pin in ("TransmittanceColor", "Transmittance Color")):
        raise RuntimeError("Thin Translucent output: no Transmittance Color pin")
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


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
    return import_ce(file, "T_Water_Flat")


def build_black_cube():
    """T_Water_BlackCube, the reflection cube's default: CE's cube maps are
    imported like its other bitmaps (BGRA8, no sRGB), so this one is too,
    an uncompressed BGRA8 cube DDS (build_ce_materials.py's T_CE_BlackCube,
    which lives in the runtime pack's chunk, not this one)."""
    scratch = os.path.join(unreal.Paths.project_saved_dir(), "ce_water")
    os.makedirs(scratch, exist_ok=True)
    file = os.path.join(scratch, "T_Water_BlackCube.dds")
    size = 4
    header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIIII12x",
        b"DDS ", 124, 0x1007, size, size, size * 4, 0, 0, b"\0" * 44,
        32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
        0x1008, 0xFE00, 0, 0, 0)
    with open(file, "wb") as f:
        f.write(header)
        for _ in range(6):
            f.write(bytes((0, 0, 0, 255)) * size * size)
    return import_ce(file, "T_Water_BlackCube")


def import_ce(file, name):
    """Import `file` as `name` with CE's bitmap settings: no sRGB decode, no
    block compression, never streamed."""
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", file)
    task.set_editor_property("destination_path", ROOT)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    assets.import_asset_tasks([task])
    tex = unreal.load_asset(f"{ROOT}/{name}")
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("never_stream", True)
    eal.save_loaded_asset(tex)
    return tex


build_label()
flat = build_flat()
build_ocean(flat, build_black_cube())
unreal.log("MJOLNIR CE water built")
