"""Build the master materials that draw converted Halo CE surfaces the way the
original renderer did.

    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_materials.py

Writes, under /Game/MJOLNIR/CE:
  M_CE_Environment        shader_environment, opaque
  M_CE_EnvironmentMasked  the same, alpha tested (the bump map's alpha for a
                          shader_environment, the base map's for an object)
  M_CE_EnvironmentMaskedTwoSided   ... drawn from both sides (foliage)
  M_CE_TransparentAdd     shader_transparent_chicago(_extended), drawn additively
  M_CE_TransparentAlpha   ... alpha blended
  M_CE_TransparentMul     ... multiplied into the frame
  M_CE_Water              shader_transparent_water: a rippling, view-tinted
                          reflection, added into the frame
  T_CE_White, T_CE_Grey, T_CE_Flat, T_CE_BlackCube   what an absent map samples
and PAL_MJOLNIR_CE, _Sounds and _Levels, the labels that put those folders in chunk 988:
the cook's container is pakchunk988, and its shader library is named after
the game's project and that chunk (Meteorite_Chunk988), which is what makes
the game open it when the container mounts.

Only materials and textures are cooked: the fork serializes material
instances and parameter collections differently from stock, so an instance
cooked here crashes the game's loader (docs/re/fork_renderer.md). The level
loader makes a dynamic instance of these masters per mesh slot instead, from
the parameters tools/level/ce_material_spec.py lists.

The light is CE's: CE lit its levels with baked lightmaps, sampled here on
UV1, and the game runs with r.AllowStaticLighting=0 so it would bake none of
its own. The opaque masters are lit only so objects can shadow them: a share
of the baked colour is drawn as the level's sun (SUN_WEIGHT_CODE), and the
transparent ones are unlit. The shading is CE's fixed-function math (docs/ce_map_conversion.md,
"Materials"), done in the bitmaps' own gamma space as the hardware did, then
divided by the display gain, decoded to linear and divided by the camera's
exposure (EyeAdaptationInverse). The level's post-process volume (spawned by
the loader) fixes the exposure and turns the filmic curve and local exposure
off, so the one transform left after the material is the game's own display
colour correction: at its default brightness that multiplies the displayed
(sRGB) colour by about 0.6 (measured: docs/re/fork_renderer.md), which
`DisplayGain` undoes, so CE's colours reach the screen as CE drew them. There
are no static switches: one shader map per parent.
"""
import os
import struct
import zlib

import unreal

ROOT = "/Game/MJOLNIR/CE"

# The game's display colour correction at its default brightness
# (ColorCorrectionBrightness 0.5) scales the shown sRGB colour by this much.
DISPLAY_GAIN = 0.6

assets = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary


def link(src, pin, dst, dst_pin):
    """connect_material_expressions, failing loudly: a pin name that does
    not exist would otherwise leave the input silently unconnected."""
    if not mel.connect_material_expressions(src, pin, dst, dst_pin):
        raise RuntimeError(f"cannot connect {src.get_name()}.{pin!r} -> {dst.get_name()}.{dst_pin!r}")


def fresh(path, name, cls, factory):
    full = f"{path}/{name}"
    if eal.does_asset_exist(full):
        eal.delete_asset(full)
    return assets.create_asset(name, path, cls, factory)


# --- default textures -------------------------------------------------------

def write_png(path, rgba, size=4):
    """A size x size PNG of one colour, written without any imaging library."""
    row = b"\0" + bytes(rgba) * size
    raw = zlib.compress(row * size)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", raw))
        f.write(chunk(b"IEND", b""))


def write_cube_dds(path, faces_bgra, size):
    """An uncompressed BGRA8 cube map DDS; `faces_bgra` in D3D face order
    (+X, -X, +Y, -Y, +Z, -Z). tools/level/ce_material_spec.py writes the
    levels' cube maps the same way."""
    header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIIII12x",
        b"DDS ", 124, 0x1007, size, size, size * 4, 0, 0, b"\0" * 44,
        32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
        0x1008, 0xFE00, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(header)
        for face in faces_bgra:
            f.write(face)


def import_texture(file, dest, name):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", file)
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    assets.import_asset_tasks([task])
    return unreal.load_asset(f"{dest}/{name}")


def ce_texture_settings(tex, lightmap=False):
    """CE bitmaps hold gamma-space values the math uses as they are: no sRGB
    decode, and no block compression on top of the original's (BGRA8)."""
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("never_stream", True)
    if lightmap:
        # Charts sit next to each other on a page: no mips to bleed across
        # them, and no wrap.
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)


def build_defaults():
    scratch = os.path.join(unreal.Paths.project_saved_dir(), "ce_defaults")
    os.makedirs(scratch, exist_ok=True)
    out = {}
    for name, rgba in (("T_CE_White", (255, 255, 255, 255)), ("T_CE_Grey", (128, 128, 128, 255)),
                       ("T_CE_Flat", (128, 128, 255, 255))):
        file = os.path.join(scratch, name + ".png")
        write_png(file, rgba)
        tex = import_texture(file, ROOT, name)
        ce_texture_settings(tex)
        eal.save_loaded_asset(tex)
        out[name] = tex
    file = os.path.join(scratch, "T_CE_BlackCube.dds")
    write_cube_dds(file, [bytes((0, 0, 0, 255)) * 16] * 6, 4)
    cube = import_texture(file, ROOT, "T_CE_BlackCube")
    ce_texture_settings(cube)
    eal.save_loaded_asset(cube)
    out["T_CE_BlackCube"] = cube
    return out


# --- graph helpers ----------------------------------------------------------

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
        """A vector parameter as a float4 (its default output is the RGB
        three; the alpha comes from its own pin)."""
        v = self.vector(name, default)
        a = self.node(unreal.MaterialExpressionAppendVector, x=-1200)
        link(v, "", a, "A")
        link(v, "A", a, "B")
        return a

    def uv(self, index, scale_param=None, default_scale=1.0):
        tc = self.node(unreal.MaterialExpressionTextureCoordinate, x=-2000, coordinate_index=index)
        if not scale_param:
            return tc
        s = self.scalar(scale_param, default_scale)
        mul = self.node(unreal.MaterialExpressionMultiply, x=-1700)
        link(tc, "", mul, "A")
        link(s, "", mul, "B")
        return mul

    def texture(self, name, default, uvs, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR):
        t = self.node(unreal.MaterialExpressionTextureSampleParameter2D, x=-1100, parameter_name=name,
                      texture=default, sampler_type=sampler)
        link(uvs, "", t, "UVs")
        return t

    def cube(self, name, default, direction):
        t = self.node(unreal.MaterialExpressionTextureSampleParameterCube, x=-1100, parameter_name=name,
                      texture=default, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(direction, "", t, "UVs")
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

    def mask(self, src, r=False, g=False, b=False, a=False):
        m = self.node(unreal.MaterialExpressionComponentMask, x=-200, r=r, g=g, b=b, a=a)
        link(src, "", m, "")
        return m

    def to_screen(self, linear):
        """Divides by the camera's exposure, so `linear` is the value the
        tonemapper receives however the game's auto exposure moves."""
        e = self.node(unreal.MaterialExpressionEyeAdaptationInverse, x=-100)
        # The input is the LightValueInput property; its pin name is the
        # property's display name (alpha is left at its default, 1).
        for pin in ("Light Value Input", "LightValueInput", "Light Value", "LightValue"):
            if mel.connect_material_expressions(linear, "", e, pin):
                return e
        raise RuntimeError("EyeAdaptationInverse: no light value pin")


# CE's periodic functions (self-illumination and UV animation), of
# x = time / period + phase, as 0..1: one, zero, cosine (and variable
# period), diagonal wave (and variable), slide (and variable), noise,
# jitter, wander, spark. The variable-period forms use their nominal period,
# and noise, jitter and wander a smooth value noise at different rates.
# Spark rises over the first 15% of the period and decays over the rest:
# a hard on/off blip made Gephyrophobia's energy ropes flash every 5 s where
# CE's pulse (2026-10-02).
WAVE = r"""
#define CE_HASH(n) frac(sin(n) * 43758.5453)
#define CE_VNOISE(x) lerp(CE_HASH(floor(x)), CE_HASH(floor(x) + 1.0), smoothstep(0.0, 1.0, frac(x)))
#define CE_WAVE(fn, x) ((fn) < 0.5 ? 1.0 : (fn) < 1.5 ? 0.0 : (fn) < 3.5 ? 0.5 - 0.5 * cos(6.2831853 * (x)) \
    : (fn) < 5.5 ? 1.0 - abs(2.0 * frac(x) - 1.0) : (fn) < 7.5 ? frac(x) : (fn) < 8.5 ? CE_VNOISE((x) * 4.0) \
    : (fn) < 9.5 ? CE_HASH(floor((x) * 30.0)) : (fn) < 10.5 ? CE_VNOISE(x) \
    : (frac(x) < 0.15 ? smoothstep(0.0, 0.15, frac(x)) : 1.0 - smoothstep(0.15, 1.0, frac(x))))
#define CE_PHASE(anim, t) ((anim).y > 0.0 ? (t) / (anim).y + (anim).z : (anim).z)
"""

WAVE_END = r"""
#undef CE_HASH
#undef CE_VNOISE
#undef CE_WAVE
#undef CE_PHASE
"""

SRGB_TO_LINEAR = r"""
frame /= DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return lerp(hi, lo, step(frame, 0.04045)) * Exposure;
"""

# Tangent-space bump normal, flat when there is no bump map or it is used as
# a specular mask.
NORMAL_CODE = r"""
if (HasBump < 0.5 || BumpIsSpecMask > 0.5) return float3(0, 0, 1);
float3 N = Bump.rgb * 2.0 - 1.0;
return N * rsqrt(max(dot(N, N), 1e-8));
"""

# The reflection lookup direction, in CE's world space (Unreal's with y
# mirrored): the eye vector reflected about the bump normal, or about the
# vertex normal for a flat cube map; CE's cube maps are in D3D face order.
REFLECT_CODE = r"""
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
float3 N = Flat > 0.5 ? VertexN : BumpN;
N *= rsqrt(max(dot(N, N), 1e-8));
float3 R = 2.0 * dot(N, E) * N - E;
return float3(R.x, -R.y, R.z);
"""

# The fixed-function passes of shader_environment, in one function. Inputs are
# raw (gamma-space) texels; `frame` is the colour CE would leave in the frame,
# still in gamma space, decoded to linear at the end.
#   texture pass: base, then the primary/secondary detail blend (by the base
#     alpha for blended types, by the secondary map's alpha for normal ones),
#     then the micro detail; functions 0 = 2BD, 1 = BD, 2 = B + 2D - 1, each
#     stage clamped as the combiners clamp their unsigned inputs;
#   lightmap pass: lightmap * material colour * mix(1, N.L, incident weight)
#     plus self-illumination (primary/secondary/plasma, each animating
#     between its off and on colour), clamped;
#   frame = lightmap pass * texture pass (no 2x);
#   specular lightmap (flag "lightmap") and the cube map reflection
#     (mix(c^8, c, tint) * brightness, tint and brightness between their
#     parallel and perpendicular values by the squared view term): added,
#     masked by the frame alpha (bump alpha * the texture pass's mask);
#   atmospheric fog over the result.
# Absent maps behave as neutral for their function (grey for the biased
# ones, white for multiply).
ENVIRONMENT_CODE = WAVE + r"""
float neutralD = (Func > 0.5 && Func < 1.5) ? 1.0 : 0.5;
float3 P = HasPrimary > 0.5 ? Primary.rgb : neutralD.xxx;
float3 Q = HasSecondary > 0.5 ? Secondary.rgb : neutralD.xxx;
float Pa = HasPrimary > 0.5 ? Primary.a : 1.0;
float Qa = HasSecondary > 0.5 ? Secondary.a : 1.0;
float pick = Type > 0.5 ? Base.a : Qa;
float3 D = lerp(Q, P, pick);
float3 B = Base.rgb;
float3 R = Func < 0.5 ? 2.0 * B * D : (Func < 1.5 ? B * D : B + 2.0 * D - 1.0);
R = saturate(R);
float neutralM = (MicroFunc > 0.5 && MicroFunc < 1.5) ? 1.0 : 0.5;
float3 M = HasMicro > 0.5 ? Micro.rgb : neutralM.xxx;
float3 T = MicroFunc < 0.5 ? 2.0 * R * M : (MicroFunc < 1.5 ? R * M : R + 2.0 * M - 1.0);
T = saturate(T);
float specMask = (Type > 0.5 && Type < 1.5) ? lerp(Qa, Pa, Base.a) : Base.a;
specMask *= HasMicro > 0.5 ? Micro.a : 1.0;

bool bumpIsMask = BumpIsSpecMask > 0.5;
float3 N = BumpN;
float3 L = Incident.rgb * 2.0 - 1.0;
L *= rsqrt(max(dot(L, L), 1e-8));
float bumpTerm = lerp(1.0, saturate(dot(N, L)), IncidentWeight);
float3 lm = HasLightmap > 0.5 ? Lightmap.rgb : 1.0.xxx;

float3 S = 0.0.xxx;
if (HasSelfIllum > 0.5)
{
    float3 primary = lerp(SelfOff0, SelfOn0, CE_WAVE(SelfAnim0.x, CE_PHASE(SelfAnim0, Time)));
    float3 secondary = lerp(SelfOff1, SelfOn1, CE_WAVE(SelfAnim1.x, CE_PHASE(SelfAnim1, Time)));
    float plasma = CE_WAVE(SelfAnim2.x, CE_PHASE(SelfAnim2, Time));
    float band = saturate(1.0 - abs(SelfIllum.a - plasma) * 8.0);
    S = SelfIllum.r * primary + SelfIllum.g * secondary + SelfIllum.b * (SelfOn2 * band + SelfOff2);
}
float3 light = saturate(lm * MaterialColor * bumpTerm + S);
float3 frame = light * T;

float frameAlpha = (HasBump > 0.5 ? Bump.a : 1.0) * specMask;
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
if (SpecLightmap > 0.5)
{
    float3 Et = Eye * rsqrt(max(dot(Eye, Eye), 1e-8));
    float ne = dot(N, Et);
    float3 Rv = 2.0 * ne * N - Et;
    float rl = saturate(dot(Rv, L));
    float lobe = ExtraShiny > 0.5 ? pow(rl, 32.0) : pow(rl, 8.0);
    float3 spec = lerp(SpecParallel, SpecPerpendicular, saturate(ne)) * SpecBrightness
        * (0.5 * (lm.r + lm.g + lm.b)) * saturate(8.0 * L.z) * saturate(8.0 * Et.z) * lobe;
    spec *= Overbright > 0.5 ? 2.0 : 1.0;
    if (bumpIsMask && HasBump > 0.5) spec *= Bump.rgb;
    frame += saturate(spec) * frameAlpha;
}
if (HasReflection > 0.5)
{
    float3 Vn = VertexN * rsqrt(max(dot(VertexN, VertexN), 1e-8));
    float3 Bn = BumpW * rsqrt(max(dot(BumpW, BumpW), 1e-8));
    float v = (ReflectFlat > 0.5 && HasBump > 0.5 && !bumpIsMask) ? saturate(dot(E, Bn)) : saturate(dot(Vn, E));
    v *= v;
    float3 c = Cube.rgb;
    float3 c8 = c * c; c8 *= c8; c8 *= c8;
    float3 refl = lerp(c8, c, lerp(SpecParallel, SpecPerpendicular, v)) * lerp(ReflPara, ReflPerp, v);
    if (bumpIsMask && HasBump > 0.5) refl *= Bump.rgb;
    frame += saturate(refl) * frameAlpha;
}
frame = saturate(frame);
if (FogDensity > 0.0)
{
    float f = FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
    frame = lerp(frame, FogColor, f);
}
""" + SRGB_TO_LINEAR + WAVE_END

# One chicago stage's texture coordinates: scale, offset, rotation about the
# map's centre, and the scrolling animation (offset += scale * wave).
STAGE_UV_CODE = WAVE + r"""
float2 uv = UV * Xform.xy + Xform.zw;
uv.x += UAnim.w * CE_WAVE(UAnim.x, CE_PHASE(UAnim, Time));
uv.y += VAnim.w * CE_WAVE(VAnim.x, CE_PHASE(VAnim, Time));
float s = sin(Rot), c = cos(Rot);
uv = float2(c * (uv.x - 0.5) - s * (uv.y - 0.5), s * (uv.x - 0.5) + c * (uv.y - 0.5)) + 0.5;
return uv;
""" + WAVE_END

# shader_transparent_chicago: map 0 is the running result; each stage's
# colour and alpha functions fold the next map into it: current, next map,
# multiply, double multiply, add, add signed (current / next), subtract
# (current / next), blend by the current or next map's alpha (and inverse).
# Each step is clamped as the combiners clamp.
TRANSPARENT_CODE = WAVE + r"""
float4 maps[4] = { M0, M1, M2, M3 };
float4 cur = maps[0];
int count = (int)Count;
[unroll] for (int i = 0; i < 3; ++i)
{
    if (i + 1 >= count) break;
    float4 nxt = maps[i + 1];
    float cf = Fn[i], af = AFn[i];
    float3 c = cf < 0.5 ? cur.rgb : cf < 1.5 ? nxt.rgb : cf < 2.5 ? cur.rgb * nxt.rgb : cf < 3.5 ? 2.0 * cur.rgb * nxt.rgb
        : cf < 4.5 ? cur.rgb + nxt.rgb : cf < 6.5 ? cur.rgb + nxt.rgb - 0.5 : cf < 7.5 ? cur.rgb - nxt.rgb
        : cf < 8.5 ? nxt.rgb - cur.rgb : cf < 9.5 ? lerp(cur.rgb, nxt.rgb, cur.a) : cf < 10.5 ? lerp(nxt.rgb, cur.rgb, cur.a)
        : cf < 11.5 ? lerp(cur.rgb, nxt.rgb, nxt.a) : lerp(nxt.rgb, cur.rgb, nxt.a);
    float a = af < 0.5 ? cur.a : af < 1.5 ? nxt.a : af < 2.5 ? cur.a * nxt.a : af < 3.5 ? 2.0 * cur.a * nxt.a
        : af < 4.5 ? cur.a + nxt.a : af < 6.5 ? cur.a + nxt.a - 0.5 : af < 7.5 ? cur.a - nxt.a
        : af < 8.5 ? nxt.a - cur.a : af < 9.5 ? lerp(cur.a, nxt.a, cur.a) : af < 10.5 ? lerp(nxt.a, cur.a, cur.a)
        : af < 11.5 ? lerp(cur.a, nxt.a, nxt.a) : lerp(nxt.a, cur.a, nxt.a);
    cur = saturate(float4(c, a));
}
float3 frame = cur.rgb * Tint;
float alpha = cur.a;
frame *= Premultiply > 0.5 ? alpha : 1.0;
if (FogDensity > 0.0)
{
    float f = FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
    frame *= 1.0 - f;
}
frame = max(frame, 0.0) / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return float4(lerp(hi, lo, step(frame, 0.04045)) * Exposure, alpha);
""" + WAVE_END


# Object shadows on a baked level. CE's colour T (what reaches the screen, the
# lightmap's sun included) is split in two: most of it stays emissive, and a
# share w is drawn as real sun light, base colour T*w*pi / (I * N.L * colour)
# lit by the level's directional light. Where the sun reaches, the two add up
# to T exactly; where a vehicle or a player blocks it, the share drops out and
# the shadow shows. AO 0 keeps the sky light and bounce off it, so nothing
# else changes. w fades out where the surface turns from the sun, and is
# capped so the base colour stays within 1. The terrain itself casts no
# shadows (its own are in the lightmap); MJOLNIRLevelLoader sets the sun
# parameters from the level's environment.
SUN_WEIGHT_CODE = r"""
float3 screen = max(Screen.rgb, 1e-4);
float ndl = saturate(dot(normalize(N), normalize(SunDir)));
float3 denom = max(SunIlluminance * ndl * SunColor.rgb, 1e-4);
float3 room = denom / (screen * 3.14159265);
float w = ShadowStrength * saturate(ndl * 4.0);
return min(w, min(room.r, min(room.g, room.b)));
"""

SUN_BASE_CODE = r"""
float ndl = saturate(dot(normalize(N), normalize(SunDir)));
float3 denom = max(SunIlluminance * ndl * SunColor.rgb, 1e-4);
return saturate(Screen.rgb * W * 3.14159265 / denom);
"""

SUN_EMISSIVE_CODE = r"""
return Screen.rgb * (1.0 - W);
"""


def sun_split(g, screen):
    """Connects `screen` (the colour to_screen made) to emissive and base
    colour, split for object shadows (SUN_WEIGHT_CODE)."""
    n = g.node(unreal.MaterialExpressionVertexNormalWS)
    sun = [("SunDir", g.vector("SunDir", (0.0, 0.0, 1.0, 0.0)), ""),
           ("SunColor", g.vector("SunColor", (1.0, 1.0, 1.0, 1.0)), ""),
           ("SunIlluminance", g.scalar("SunIlluminance", 8.0), ""),
           ("ShadowStrength", g.scalar("ShadowStrength", 0.0), "")]
    w = g.custom(SUN_WEIGHT_CODE, [("Screen", screen, ""), ("N", n, "")] + sun,
                 output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="CE sun share")
    base = g.custom(SUN_BASE_CODE, [("Screen", screen, ""), ("N", n, ""), ("W", w, "")] + sun,
                    description="CE sun base colour")
    emissive = g.custom(SUN_EMISSIVE_CODE, [("Screen", screen, ""), ("W", w, "")], description="CE baked share")
    mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for prop, value in ((unreal.MaterialProperty.MP_SPECULAR, 0.0), (unreal.MaterialProperty.MP_METALLIC, 0.0),
                        (unreal.MaterialProperty.MP_ROUGHNESS, 1.0), (unreal.MaterialProperty.MP_AMBIENT_OCCLUSION, 0.0)):
        c = g.node(unreal.MaterialExpressionConstant, x=-300, r=value)
        mel.connect_material_property(c, "", prop)


def fog_inputs(g):
    depth = g.node(unreal.MaterialExpressionPixelDepth)
    return [("Depth", depth, ""), ("FogColor", g.vector("FogColor", (0, 0, 0, 1)), ""),
            ("FogDensity", g.scalar("FogDensity", 0.0), ""), ("FogStart", g.scalar("FogStart", 0.0), ""),
            ("FogOpaque", g.scalar("FogOpaque", 1.0), "")]


def build_environment(name, masked, defaults, two_sided=False):
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    # Lit, for object shadows (SUN_WEIGHT_CODE); with ShadowStrength 0 the
    # output is the unlit one.
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("two_sided", two_sided)
    if masked:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        # CE's alpha reference is 0x7F with a GREATER test: 128/255 and up
        # pass, which is exactly UE's discard below 0.5 for 8-bit alpha.
        m.set_editor_property("opacity_mask_clip_value", 0.5)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    white, grey, flat = defaults["T_CE_White"], defaults["T_CE_Grey"], defaults["T_CE_Flat"]

    uv0 = g.uv(0)
    base = g.texture("Base", white, uv0)
    primary = g.texture("Primary", grey, g.uv(0, "PrimaryScale"))
    secondary = g.texture("Secondary", grey, g.uv(0, "SecondaryScale"))
    micro = g.texture("Micro", grey, g.uv(0, "MicroScale"))
    bump = g.texture("Bump", flat, g.uv(0, "BumpScale"))
    lightmap = g.texture("Lightmap", white, g.uv(1))
    self_illum = g.texture("SelfIllumMap", white, g.uv(0, "SelfIllumScale"))
    vc = g.node(unreal.MaterialExpressionVertexColor)
    cam = g.node(unreal.MaterialExpressionCameraVectorWS)
    eye = g.node(unreal.MaterialExpressionTransform, x=-1100,
                 transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                 transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
    link(cam, "", eye, "")
    has_bump = g.scalar("HasBump", 0.0)
    bump_is_mask = g.scalar("BumpIsSpecMask", 0.0)
    bump_n = g.custom(NORMAL_CODE, [("Bump", bump, "RGBA"), ("HasBump", has_bump, ""),
                                    ("BumpIsSpecMask", bump_is_mask, "")], description="CE bump normal")
    bump_w = g.node(unreal.MaterialExpressionTransform, x=-800,
                    transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                    transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(bump_n, "", bump_w, "")
    vertex_n = g.node(unreal.MaterialExpressionVertexNormalWS)
    reflect_flat = g.scalar("ReflectFlat", 0.0)
    direction = g.custom(REFLECT_CODE, [("Cam", cam, ""), ("BumpN", bump_w, ""), ("VertexN", vertex_n, ""),
                                        ("Flat", reflect_flat, "")], description="CE reflection vector")
    cube = g.cube("ReflectionCube", defaults["T_CE_BlackCube"], direction)
    time = g.node(unreal.MaterialExpressionTime)

    inputs = [
        ("Base", base, "RGBA"), ("Primary", primary, "RGBA"), ("Secondary", secondary, "RGBA"),
        ("Micro", micro, "RGBA"), ("Bump", bump, "RGBA"), ("Lightmap", lightmap, "RGBA"),
        ("SelfIllum", self_illum, "RGBA"), ("Incident", vc, ""), ("IncidentWeight", vc, "A"),
        ("Eye", eye, ""), ("Cam", cam, ""), ("BumpN", bump_n, ""), ("BumpW", bump_w, ""),
        ("VertexN", vertex_n, ""), ("Cube", cube, "RGB"), ("Time", time, ""),
        ("HasBump", has_bump, ""), ("BumpIsSpecMask", bump_is_mask, ""), ("ReflectFlat", reflect_flat, ""),
        ("Exposure", g.scalar("Exposure", 1.0), ""), ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), ""),
    ] + fog_inputs(g)
    for pname, default in (("Type", 0.0), ("Func", 0.0), ("MicroFunc", 0.0), ("HasPrimary", 0.0),
                           ("HasSecondary", 0.0), ("HasMicro", 0.0), ("HasLightmap", 0.0),
                           ("HasSelfIllum", 0.0), ("SpecLightmap", 0.0), ("ExtraShiny", 0.0),
                           ("Overbright", 0.0), ("SpecBrightness", 0.0), ("HasReflection", 0.0),
                           ("ReflPerp", 0.0), ("ReflPara", 0.0)):
        inputs.append((pname, g.scalar(pname, default), ""))
    for pname, default in (("MaterialColor", (1, 1, 1, 1)), ("SpecParallel", (1, 1, 1, 1)),
                           ("SpecPerpendicular", (1, 1, 1, 1)),
                           ("SelfOn0", (0, 0, 0, 1)), ("SelfOff0", (0, 0, 0, 1)), ("SelfAnim0", (0, 0, 0, 0)),
                           ("SelfOn1", (0, 0, 0, 1)), ("SelfOff1", (0, 0, 0, 1)), ("SelfAnim1", (0, 0, 0, 0)),
                           ("SelfOn2", (0, 0, 0, 1)), ("SelfOff2", (0, 0, 0, 1)), ("SelfAnim2", (0, 0, 0, 0))):
        # Animation vectors are (function, period, phase, -); their RGBA pin
        # keeps all four.
        node = g.vector4(pname, default) if pname.startswith("SelfAnim") else g.vector(pname, default)
        inputs.append((pname, node, ""))
    c = g.custom(ENVIRONMENT_CODE, inputs, description="CE shader_environment")
    sun_split(g, g.to_screen(c))
    if masked:
        # shader_environment tests the bump map's alpha; object shaders the
        # base map's (AlphaFromBase 1).
        pick = g.node(unreal.MaterialExpressionLinearInterpolate, x=-300)
        link(bump, "A", pick, "A")
        link(base, "A", pick, "B")
        link(g.scalar("AlphaFromBase", 0.0), "", pick, "Alpha")
        mel.connect_material_property(pick, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


def build_transparent(name, blend, defaults):
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    uv0 = g.uv(0)
    time = g.node(unreal.MaterialExpressionTime)
    samples = []
    for i in range(4):
        uv = g.custom(STAGE_UV_CODE, [
            ("UV", uv0, ""), ("Time", time, ""),
            ("Xform", g.vector4(f"Stage{i}Xform", (1, 1, 0, 0)), ""),
            ("UAnim", g.vector4(f"Stage{i}UAnim", (1, 0, 0, 0)), ""),
            ("VAnim", g.vector4(f"Stage{i}VAnim", (1, 0, 0, 0)), ""),
            ("Rot", g.scalar(f"Stage{i}Rotation", 0.0), ""),
        ], output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description=f"CE stage {i} uv")
        samples.append(g.texture(f"Map{i}", defaults["T_CE_White"], uv))
    inputs = [(f"M{i}", s, "RGBA") for i, s in enumerate(samples)]
    inputs += [("Fn", g.vector4("StageColorFunctions", (0, 0, 0, 0)), ""),
               ("AFn", g.vector4("StageAlphaFunctions", (0, 0, 0, 0)), ""),
               ("Count", g.scalar("StageCount", 1.0), ""), ("Tint", g.vector("Tint"), ""),
               ("Premultiply", g.scalar("Premultiply", 0.0), ""), ("Time", time, "")]
    # Multiplying into the frame is not exposed: the result is a factor.
    modulate = blend == unreal.BlendMode.BLEND_MODULATE
    inputs.append(("Exposure", g.scalar("Exposure" if not modulate else "Unity", 1.0), ""))
    # A multiply blend's result is a factor on the frame, not a colour shown.
    inputs.append(("DisplayGain", g.scalar("DisplayGain" if not modulate else "UnityGain",
                                           DISPLAY_GAIN if not modulate else 1.0), ""))
    inputs += fog_inputs(g)
    c = g.custom(TRANSPARENT_CODE, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
                 description="CE shader_transparent_chicago")
    rgb = g.mask(c, r=True, g=True, b=True)
    mel.connect_material_property(rgb if modulate else g.to_screen(rgb), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if blend == unreal.BlendMode.BLEND_TRANSLUCENT:
        mel.connect_material_property(g.mask(c, a=True), "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# shader_transparent_water: the reflection cube map seen through a rippling
# surface, tinted and faded by the view angle (a steep curve: CE water stays
# tinted and see-through until close to grazing). Looking straight down the
# surface takes the perpendicular brightness and tint (Death Island's sea:
# 0.1, a faint sheen), at a grazing angle the parallel ones (1.0, a mirror).
# The reflection is added over what is under the water, scaled by the
# brightness, and with water flag 0 ("base map alpha modulates reflection")
# by the base map's alpha. Brightness is not opacity: Battle Creek's water is
# 1.0 at every angle and its creek bed still shows. Flag 1 ("base map colour
# modulates background") has no additive equivalent and is not drawn. Water
# planes are horizontal, so the two ripple
# layers bend a world-up normal directly.
WATER_UV_CODE = r"""
float a = Angle + Layer * 1.5708;
float2 dir = float2(cos(a), sin(a));
return UV * (Layer > 0.5 ? 0.5 : 1.0) * Repeat + dir * Velocity * Time;
"""

WATER_NORMAL_CODE = r"""
float2 r = (R0.rg * 2.0 - 1.0) + (R1.rg * 2.0 - 1.0) * 0.5;
return normalize(float3(r * Strength, 1.0));
"""

WATER_REFLECT_CODE = r"""
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
float3 R = 2.0 * dot(N, E) * N - E;
return float3(R.x, -R.y, R.z);
"""

WATER_CODE = r"""
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
float t = pow(1.0 - saturate(abs(dot(N, E))), FresnelPower);
float brightness = lerp(PerpBrightness, ParaBrightness, t);
float3 tint = lerp(PerpTint.rgb, ParaTint.rgb, t);
float3 frame = Cube.rgb * tint * brightness * (AlphaFromBase > 0.5 ? Base.a : 1.0);
if (FogDensity > 0.0)
{
    float f = FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
    frame *= 1.0 - f;
}
frame = max(frame, 0.0) / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return float4(lerp(hi, lo, step(frame, 0.04045)) * Exposure, 1.0);
"""


def build_water(defaults):
    m = fresh(ROOT, "M_CE_Water", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    uv0 = g.uv(0)
    time = g.node(unreal.MaterialExpressionTime)
    angle = g.scalar("RippleAngle", 0.0)
    velocity = g.scalar("RippleVelocity", 0.0)
    repeat = g.scalar("RippleRepeat", 1.0)
    ripples = []
    for layer in (0.0, 1.0):
        uv = g.custom(WATER_UV_CODE, [("UV", uv0, ""), ("Time", time, ""), ("Angle", angle, ""),
                                      ("Velocity", velocity, ""), ("Repeat", repeat, ""),
                                      ("Layer", g.node(unreal.MaterialExpressionConstant, x=-1800, r=layer), "")],
                      output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description="CE ripple uv")
        ripples.append(g.texture("Ripple", defaults["T_CE_Flat"], uv))
    n = g.custom(WATER_NORMAL_CODE, [("R0", ripples[0], "RGBA"), ("R1", ripples[1], "RGBA"),
                                     ("Strength", g.scalar("RippleStrength", 0.08), "")],
                 description="CE ripple normal")
    cam = g.node(unreal.MaterialExpressionCameraVectorWS)
    direction = g.custom(WATER_REFLECT_CODE, [("Cam", cam, ""), ("N", n, "")], description="CE water reflection")
    cube = g.cube("ReflectionCube", defaults["T_CE_BlackCube"], direction)
    base = g.texture("Base", defaults["T_CE_White"], uv0)
    inputs = [("Cam", cam, ""), ("N", n, ""), ("Cube", cube, "RGB"), ("Base", base, "RGBA"),
              ("PerpBrightness", g.scalar("PerpBrightness", 0.3), ""),
              ("ParaBrightness", g.scalar("ParaBrightness", 1.0), ""),
              ("PerpTint", g.vector("PerpTint"), ""), ("ParaTint", g.vector("ParaTint"), ""),
              ("AlphaFromBase", g.scalar("AlphaFromBase", 0.0), ""),
              ("FresnelPower", g.scalar("FresnelPower", 3.0), ""),
              ("Exposure", g.scalar("Exposure", 1.0), ""), ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), "")]
    inputs += fog_inputs(g)
    c = g.custom(WATER_CODE, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
                 description="CE shader_transparent_water")
    mel.connect_material_property(g.to_screen(g.mask(c, r=True, g=True, b=True)), "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# A CE lens flare (a light's glow, e.g. a base beacon's): the flare bitmap
# drawn facing the camera, added into the frame. The loader puts it on
# /Engine/BasicShapes/Sphere at the light's marker, scaled to the flare's
# radius: each pixel of the sphere takes the flare texel at its offset from
# the centre across the view direction, over the sphere's radius, so the
# sprite reads the same from every side while walls still hide it.
FLARE_UV_CODE = """
float3 right = normalize(cross(float3(0, 0, 1), V));
float3 up = cross(V, right);
float2 uv = float2(dot(D, right), -dot(D, up)) / max(Radius, 0.001);
return uv * 0.5 + 0.5;
"""


def build_flare(defaults):
    m = fresh(ROOT, "M_CE_Flare", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    world = g.node(unreal.MaterialExpressionWorldPosition, x=-2200)
    centre = g.node(unreal.MaterialExpressionObjectPositionWS, x=-2200)
    d = g.node(unreal.MaterialExpressionSubtract, x=-2000)
    link(world, "", d, "A")
    link(centre, "", d, "B")
    # The direction to the camera gives the sprite's right and up (it only
    # degenerates looking straight down on a flare).
    view = g.node(unreal.MaterialExpressionCameraVectorWS, x=-2000)
    radius = g.node(unreal.MaterialExpressionObjectRadius, x=-2000)
    uv = g.custom(FLARE_UV_CODE, [("D", d, ""), ("V", view, ""), ("Radius", radius, "")],
                  output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description="CE flare uv")
    tex = g.texture("Flare", defaults["T_CE_White"], uv)
    tint = g.vector("Tint")
    gain = g.scalar("Brightness", DISPLAY_GAIN)
    rgb = g.mask(tex, r=True, g=True, b=True)
    mul = g.node(unreal.MaterialExpressionMultiply, x=-300)
    link(rgb, "", mul, "A")
    link(tint, "", mul, "B")
    out = g.node(unreal.MaterialExpressionMultiply, x=-150)
    link(mul, "", out, "A")
    link(gain, "", out, "B")
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# What chunk 988 (the CE runtime pack's container) holds: the masters and the
# shared textures (CE), the event sounds (Sounds), and maps converted before
# per-map chunks (Levels). Each is labelled on its own: a label at
# /Game/MJOLNIR also claimed every /Game/MJOLNIR/Maps/<CODE>, whose own label
# (build_ce_level.py) did not keep its map out, so 988 carried every map a
# second time (214 MB, 2026-10-01).
LABELLED = ("CE", "Sounds", "Levels")


def build_label():
    if eal.does_asset_exist("/Game/MJOLNIR/PAL_MJOLNIR"):
        eal.delete_asset("/Game/MJOLNIR/PAL_MJOLNIR")
    for folder in LABELLED:
        label = fresh(f"/Game/MJOLNIR/{folder}", f"PAL_MJOLNIR_{folder}", unreal.PrimaryAssetLabel,
                      unreal.DataAssetFactory())
        rules = label.get_editor_property("rules")
        rules.set_editor_property("chunk_id", 988)
        rules.set_editor_property("apply_recursively", True)
        rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
        label.set_editor_property("rules", rules)
        label.set_editor_property("label_assets_in_my_directory", True)
        eal.save_loaded_asset(label)


build_label()
defaults = build_defaults()
if eal.does_asset_exist(f"{ROOT}/MPC_CE"):
    eal.delete_asset(f"{ROOT}/MPC_CE")
build_environment("M_CE_Environment", False, defaults)
build_environment("M_CE_EnvironmentMasked", True, defaults)
build_environment("M_CE_EnvironmentMaskedTwoSided", True, defaults, two_sided=True)
build_transparent("M_CE_TransparentAdd", unreal.BlendMode.BLEND_ADDITIVE, defaults)
build_transparent("M_CE_TransparentAlpha", unreal.BlendMode.BLEND_TRANSLUCENT, defaults)
build_transparent("M_CE_TransparentMul", unreal.BlendMode.BLEND_MODULATE, defaults)
build_water(defaults)
build_flare(defaults)
unreal.log("MJOLNIR CE materials built")
