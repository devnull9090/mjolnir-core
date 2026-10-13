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
of the baked colour is drawn as the level's sun (SUN_WEIGHT_CODE), and, for
the game's own lights, the base colour can be topped up to its sunlit share
(DYNAMIC_ALBEDO_CODE); the transparent ones are unlit. The shading is CE's fixed-function math (docs/ce_map_conversion.md,
"Materials"), done in the bitmaps' own gamma space as the hardware did, then
divided by the display gain, decoded to linear and divided by the camera's
exposure (EyeAdaptationInverse). The level's post-process volume (spawned by
the loader) fixes the exposure and turns the filmic curve and local exposure
off, so on a converted map's own world nothing is left between material and
screen and `DisplayGain` is 1. (Inside B40's world the game's colour
correction multiplied the shown sRGB colour by about 0.6, which `DisplayGain`
used to undo: docs/re/fork_renderer.md.) CE's colours reach the screen as CE
drew them. There
are no static switches: one shader map per parent.
"""
import os
import struct
import zlib

import unreal

ROOT = "/Game/MJOLNIR/CE"
# A trial build of the masters (MJ_CE_ROOT=/Game/MJOLNIR/CETrial
# MJ_CE_CHUNK=983) goes in a folder and chunk of its own, labelled alone, so
# the runtime pack's 988 is left as it is; it builds only the environment
# masters, and MJOLNIRLevelLoader picks them up with
# `mjolnir_terrain_shadows lightmap` or `mjolnir_terrain_lights on`.
TRIAL_ROOT = os.environ.get("MJ_CE_ROOT")
if TRIAL_ROOT:
    ROOT = TRIAL_ROOT.rstrip("/")
CHUNK = int(os.environ.get("MJ_CE_CHUNK", "988"))
# The game-detail experiment (GAME_DETAIL_CODE) is in trial builds only.
GAME_DETAIL = bool(TRIAL_ROOT)

# What happens to the shown sRGB colour after the material. Inside B40's world
# the game's colour correction scaled it by 0.6 (docs/re/fork_renderer.md);
# a converted map runs on a world of its own (since 2026-09-11), where the
# path is identity: a debug view of 1.0 shows 255 and a lightmap of 0.91
# shows 0.91. At 0.6 every CE surface drew 1/0.6 too bright, and Death
# Island's base came out white where MCC draws it grey (2026-10-08).
DISPLAY_GAIN = 1.0

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


# CE's periodic functions (self-illumination and UV animation) as 0..1:
# one, zero, cosine (and variable period), diagonal wave (and variable),
# slide (and variable), noise, jitter, wander, spark
# (docs/ce_map_conversion.md, "Periodic functions"). Cosine is
# 0.5 + 0.5 cos 2 pi x, 1 at x = 0; diagonal is a triangle from 0 at x = 0;
# slide is frac(x). The variable-period forms use their nominal period, and
# noise, jitter and wander a smooth value noise at different rates (4, 8
# and 1 a period: jitter as a new random value 30 times a period strobed
# Damnation's volume lights, 0.6 s, at 50 Hz, 2026-10-09). Spark
# rises over the first 35% of the period and decays over the rest: a hard
# on/off blip made Gephyrophobia's energy ropes flash every 5 s where CE's
# pulse (2026-10-02).
#
# Their input is (time + phase) / period, phase in seconds. A negative period
# runs the function backwards (Damnation's and Timberland's waterfalls slide
# with periods of -2 s and -6 s); a zero period counts as 1.
WAVE = r"""
#define CE_HASH(n) frac(sin(n) * 43758.5453)
#define CE_VNOISE(x) lerp(CE_HASH(floor(x)), CE_HASH(floor(x) + 1.0), smoothstep(0.0, 1.0, frac(x)))
#define CE_WAVE(fn, x) ((fn) < 0.5 ? 1.0 : (fn) < 1.5 ? 0.0 : (fn) < 3.5 ? 0.5 + 0.5 * cos(6.2831853 * (x))     : (fn) < 5.5 ? 1.0 - abs(2.0 * frac(x) - 1.0) : (fn) < 7.5 ? frac(x) : (fn) < 8.5 ? CE_VNOISE((x) * 4.0)     : (fn) < 9.5 ? CE_VNOISE((x) * 8.0) : (fn) < 10.5 ? CE_VNOISE(x)     : (frac(x) < 0.35 ? smoothstep(0.0, 0.35, frac(x)) : 1.0 - smoothstep(0.35, 1.0, frac(x))))
#define CE_PHASE(anim, t) (((t) + (anim).z) / (abs((anim).y) > 1e-6 ? (anim).y : 1.0))
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
TEXTURE_PASS_CODE = r"""
float neutralD = (Func > 0.5 && Func < 1.5) ? 1.0 : 0.5;
float3 P = HasPrimary > 0.5 ? Primary.rgb : neutralD.xxx;
float3 Q = HasSecondary > 0.5 ? Secondary.rgb : neutralD.xxx;
float Pa = HasPrimary > 0.5 ? Primary.a : 1.0;
float Qa = HasSecondary > 0.5 ? Secondary.a : 1.0;
float pick = Type > 0.5 ? Base.a : Qa;
float3 D = lerp(Q, P, pick);
// shader_model (ModelShader): the multipurpose map's masks, in the PC
// order: r auxiliary, g self-illumination, b reflection, a change colour.
// Without a map nothing is masked off the reflection and nothing else is on.
float4 MP = HasMulti > 0.5 ? Multi : float4(0.0, 0.0, 1.0, 0.0);
bool model = ModelShader > 0.5;
if (model)
{
    // The detail mask: none, then reflection, self-illumination, change
    // colour and auxiliary, each inverted and plain.
    float dm = DetailMask;
    float mk = dm < 0.5 ? 1.0 : dm < 1.5 ? 1.0 - MP.b : dm < 2.5 ? MP.b : dm < 3.5 ? 1.0 - MP.g
        : dm < 4.5 ? MP.g : dm < 5.5 ? 1.0 - MP.a : dm < 6.5 ? MP.a : dm < 7.5 ? 1.0 - MP.r : MP.r;
    D = lerp(neutralD.xxx, P, mk);
}
float3 B = Base.rgb;
float3 R = Func < 0.5 ? 2.0 * B * D : (Func < 1.5 ? B * D : B + 2.0 * D - 1.0);
R = saturate(R);
float neutralM = (MicroFunc > 0.5 && MicroFunc < 1.5) ? 1.0 : 0.5;
float3 M = HasMicro > 0.5 ? Micro.rgb : neutralM.xxx;
float3 T = MicroFunc < 0.5 ? 2.0 * R * M : (MicroFunc < 1.5 ? R * M : R + 2.0 * M - 1.0);
T = saturate(T);
"""

ENVIRONMENT_CODE = WAVE + TEXTURE_PASS_CODE + r"""
// The specular mask: normal base.a * lerp(secondary.a, primary.a,
// secondary.a), blended lerp(secondary.a, primary.a, base.a), blended base
// specular base.a.
float specMask = Type < 0.5 ? Base.a * lerp(Qa, Pa, Qa) : Type < 1.5 ? lerp(Qa, Pa, Base.a) : Base.a;
specMask *= HasMicro > 0.5 ? Micro.a : 1.0;

bool bumpIsMask = BumpIsSpecMask > 0.5;
float3 N = BumpN;
float3 L = Incident.rgb * 2.0 - 1.0;
L *= rsqrt(max(dot(L, L), 1e-8));
float bumpTerm = lerp(1.0, saturate(dot(N, L)), IncidentWeight);
float3 lm = HasLightmap > 0.5 ? Lightmap.rgb : 1.0.xxx;
// The level's baked corners (lightmap_bake: red, on the lightmap's UVs),
// which CE's lightmaps are too coarse to hold.
if (HasBake > 0.5)
{
    lm *= pow(saturate(BakeRange.z), BakeAO);
}

float3 S = 0.0.xxx;
if (HasSelfIllum > 0.5)
{
    float3 primary = lerp(SelfOff0, SelfOn0, CE_WAVE(SelfAnim0.x, CE_PHASE(SelfAnim0, Time)));
    float3 secondary = lerp(SelfOff1, SelfOn1, CE_WAVE(SelfAnim1.x, CE_PHASE(SelfAnim1, Time)));
    // Plasma: a sharp ridge where the animated value meets the map's
    // alpha; its off colour is added whatever the ridge.
    float plasma = CE_WAVE(SelfAnim2.x, CE_PHASE(SelfAnim2, Time));
    float pr = 1.0 - 2.0 * abs(plasma - SelfIllum.a);
    pr *= pr;
    float q = pr * pr >= 0.5 ? (2.0 * pr * pr - 1.0) * (2.0 * pr * pr - 1.0) : 0.0;
    S = SelfIllum.r * primary + SelfIllum.g * secondary + SelfIllum.b * (q * SelfOn2 + SelfOff2);
}
if (model && HasModelSelfIllum > 0.5)
    S = MP.g * lerp(SelfOff1, SelfOn1, CE_WAVE(SelfAnim1.x, CE_PHASE(SelfAnim1, Time)))
        * (HasSICC > 0.5 ? SICC.rgb : 1.0.xxx);
float3 lit = lm * MaterialColor * bumpTerm + S;
// An object's change colour tints its light (self-illumination included)
// where the multipurpose map's alpha says.
if (model && ModelCC > 0.5)
    lit *= lerp(1.0.xxx, ObjCC.rgb, MP.a);
float3 light = saturate(lit);
// "Detail after reflection" leaves the detail for last.
bool detailAfter = model && DetailAfter > 0.5;
float3 frame = light * (detailAfter ? B : T);

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
    float reflMask = frameAlpha;
    // The reflection lightmap mask: reflections dim in dark lightmap areas.
    if (!model && HasLightmap > 0.5 && LightmapReflScale < 1.0)
        reflMask *= lerp(LightmapReflScale, 1.0, saturate(dot(lm, float3(0.502, 0.690, 0.314))));
    if (model)
    {
        // shader_model: the cube colour as it is, times the tint and
        // brightness between parallel and perpendicular, masked by the
        // multipurpose map, faded out between the falloff and cutoff
        // distances.
        refl = c * lerp(SpecParallel * ReflPara, SpecPerpendicular * ReflPerp, v);
        reflMask = MP.b;
        if (ReflCutoff > 0.0)
            reflMask *= saturate((Depth - ReflCutoff) / min(ReflFalloff - ReflCutoff, -1.0));
    }
    // A placed object's reflection takes the light around it (CE's
    // per-object reflection tint, in the object lighting page).
    if (ObjectPage > 0.5) refl *= ObjTint.rgb;
    frame += saturate(refl) * reflMask;
}
frame = saturate(frame);
if (detailAfter)
    frame = saturate(Func < 0.5 ? 2.0 * frame * D : (Func < 1.5 ? frame * D : frame + 2.0 * D - 1.0));
if (FogDensity > 0.0)
{
    float f = FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
    frame = lerp(frame, FogColor, f);
}
""" + SRGB_TO_LINEAR + WAVE_END

# A transparent map's texture coordinates (chicago and generic maps, and the
# shader_model base map). CE's texture-animation transform: u, v and rotation
# channels each animate as scale * wave(function, (t + phase) / period); the
# map's u/v scale applies to the incoming UV first, offsets and animation are
# added unscaled about the rotation centre c, and the rotation (map rotation
# plus its animation, in degrees) turns about c:
#   uv' = R(theta) ((su u, sv v) + (offset - c + anim)) + c
# Misc is (map rotation in degrees, centre u, centre v, map flags); map flags
# bit 2 / 3 clamp u / v. Map 0 alone: chicago flag bit 3 (first map is in
# screenspace) takes the screen position for UV, and bit 6 (scale first map
# with distance) multiplies its scale by the view depth in world units.
STAGE_UV_CODE = WAVE + r"""
float2 src = UV;
float2 scale = Xform.xy;
if (First > 0.5)
{
    int cf = (int)ChicagoFlags;
    if (cf & 8) src = Parameters.SvPosition.xy * View.ViewSizeAndInvSize.zw;
    if (cf & 64) scale *= Depth / 304.8;
}
float2 c = Misc.yz;
float2 anim = float2(UAnim.w * CE_WAVE(UAnim.x, CE_PHASE(UAnim, Time)),
                     VAnim.w * CE_WAVE(VAnim.x, CE_PHASE(VAnim, Time)));
float theta = radians(Misc.x + RAnim.w * CE_WAVE(RAnim.x, CE_PHASE(RAnim, Time)));
float2 p = src * scale + Xform.zw - c + anim;
float s = sin(theta), co = cos(theta);
float2 uv = float2(co * p.x - s * p.y, s * p.x + co * p.y) + c;
int mf = (int)Misc.w;
if (mf & 4) uv.x = clamp(uv.x, 0.0005, 0.9995);
if (mf & 8) uv.y = clamp(uv.y, 0.0005, 0.9995);
return uv;
""" + WAVE_END

# A chicago map 0 that is a cube map (first map type 1-3): the lookup
# direction, in CE's world space (Unreal's with y mirrored): 1 the eye vector
# reflected about the vertex normal, 2 from the object's origin to the
# surface, 3 from the camera to the surface.
FIRST_CUBE_CODE = r"""
float3 d;
if (Type < 1.5)
{
    float3 E = normalize(Cam);
    float3 N = normalize(VertexN);
    d = 2.0 * dot(N, E) * N - E;
}
else if (Type < 2.5) d = WorldPos - ObjectPos;
else d = WorldPos - CameraPos;
return float3(d.x, -d.y, d.z);
"""

# shader_transparent_chicago's colour and alpha chain (docs/ce_map_conversion.md,
# "Transparent shaders"). Map 0 starts the result; map k is folded in with
# map k-1's colour and alpha functions, so the last map's functions are never
# used: current, next map, multiply, double multiply, add, add signed current
# (next + 2 current - 1), add signed next (current + 2 next - 1), subtract
# current (next - current), subtract next (current - next), blend by the
# current or next map's alpha (and inverse). Map k-1's "alpha replicate"
# (map flag bit 1) reads the next map's alpha for its colour. A register read
# clamps to 0..1 at every stage.
#
# Then CE's fade stage, which takes each blend function to its neutral value
# as F goes to 0: the framebuffer fade (1 none, 1 - |N.V| fading when
# perpendicular, |N.V| when parallel), the atmospheric fog (queued
# transparents fade out in fog rather than taking its colour) and the alpha
# test (chicago flag bit 0: alpha must exceed 127/255). Alpha blend scales
# alpha, multiply and component min go to 1, double multiply to 0.5, add,
# subtract and component max scale the colour, alpha-multiply add both.
TRANSPARENT_CODE = r"""
float4 maps[4] = { M0, M1, M2, M3 };
float flags[4] = { S0.w, S1.w, S2.w, S3.w };
if (FirstType > 0.5) maps[0] = Cube;
float4 cur = saturate(maps[0]);
int count = (int)Count;
// MCC's shader_transparent_generic in place of the chicago chain (GENERIC_CODE).
if (GenCount > 0.5) { cur = saturate(Gen); count = 0; }
[unroll] for (int i = 0; i < 3; ++i)
{
    if (i + 1 >= count) break;
    float4 nxt = saturate(maps[i + 1]);
    float3 nc = ((int)flags[i] & 2) ? nxt.aaa : nxt.rgb;
    float cf = Fn[i], af = AFn[i];
    float3 c = cf < 0.5 ? cur.rgb : cf < 1.5 ? nc : cf < 2.5 ? cur.rgb * nc : cf < 3.5 ? 2.0 * cur.rgb * nc
        : cf < 4.5 ? cur.rgb + nc : cf < 5.5 ? nc + 2.0 * cur.rgb - 1.0 : cf < 6.5 ? cur.rgb + 2.0 * nc - 1.0
        : cf < 7.5 ? nc - cur.rgb : cf < 8.5 ? cur.rgb - nc : cf < 9.5 ? lerp(cur.rgb, nc, cur.a)
        : cf < 10.5 ? lerp(nc, cur.rgb, cur.a) : cf < 11.5 ? lerp(cur.rgb, nc, nxt.a) : lerp(nc, cur.rgb, nxt.a);
    float a = af < 0.5 ? cur.a : af < 1.5 ? nxt.a : af < 2.5 ? cur.a * nxt.a : af < 3.5 ? 2.0 * cur.a * nxt.a
        : af < 4.5 ? cur.a + nxt.a : af < 5.5 ? nxt.a + 2.0 * cur.a - 1.0 : af < 6.5 ? cur.a + 2.0 * nxt.a - 1.0
        : af < 7.5 ? nxt.a - cur.a : af < 8.5 ? cur.a - nxt.a : af < 9.5 ? lerp(cur.a, nxt.a, cur.a)
        : af < 10.5 ? lerp(nxt.a, cur.a, cur.a) : af < 11.5 ? lerp(cur.a, nxt.a, nxt.a) : lerp(nxt.a, cur.a, nxt.a);
    cur = saturate(float4(c, a));
}
float3 frame = cur.rgb * Tint;
float alpha = cur.a;

float F = 1.0;
float ndv = abs(dot(normalize(VertexN), normalize(Cam)));
if (FadeMode > 0.5) F = FadeMode < 1.5 ? 1.0 - ndv : ndv;
if (FogDensity > 0.0)
    F *= 1.0 - FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
// CE's planar fog fades a transparent out as the atmospheric fog does
// (PLANAR_FOG_CODE).
F *= 1.0 - PlanarF;
if (((int)ChicagoFlags & 1) && alpha <= 127.0 / 255.0) F = 0.0;
int blend = (int)Blend;
if (blend == 0) alpha *= F;
else if (blend == 1 || blend == 5) frame = lerp(1.0.xxx, frame, F);
else if (blend == 2) frame = lerp(0.5.xxx, frame, F);
else if (blend == 7) { frame *= F; alpha *= F; }
else frame *= F;
frame *= Premultiply > 0.5 ? alpha : 1.0;

frame = max(frame, 0.0) / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return float4(lerp(hi, lo, step(frame, 0.04045)) * Exposure, alpha);
"""

# shader_transparent_generic: the Xbox's register combiners, which the PC port
# replaced with chicago shaders; MCC's tags keep them (tools/level/mcc_tags.py,
# docs/ce_map_conversion.md "MCC's generic shaders"). A port of MCC's
# transparent_generic_shader.psh with the stages as parameters instead of
# compiled in. Registers R: t0-t3 (the maps), v0 (0, 0, 0, 1: no fog or fade
# here), v1 (|N.V| x3, 1 - |N.V|: CE's fade terms), r0 (alpha starts as t0's,
# as on the Xbox), r1, c0 and c1 (the stage's constants). Each stage reads
# four colour and four alpha inputs, each through its input mapping, forms
# A*B (or A.B) and C*D (or C.D) and their sum or mux (by r0's alpha), clamps,
# applies its output mapping and writes the three results to the registers
# its outputs name. The result is r0.
#
# Per stage s: GenCI/GenAI the colour and alpha inputs (input + 32 *
# mapping, inputs a-d); GenCO (ab output + 16 * ab function, cd output + 16 *
# cd function, ab-cd output, output mapping); GenAO (ab, cd and ab-cd
# outputs, output mapping); GenK0/GenK0Hi colour 0's animation bounds, RGBA;
# GenK1 colour 1; GenKA (colour 0's periodic function, its period, stage
# flags: 1 colour mux, 2 alpha mux).
GENERIC_STAGES = 7
GENERIC_CODE = WAVE + r"""
#define CEG_IN(v, m) ((m) == 0 ? max(v, 0.0) : (m) == 1 ? 1.0 - saturate(v) : (m) == 2 ? 2.0 * max(v, 0.0) - 1.0 \
    : (m) == 3 ? -2.0 * max(v, 0.0) + 1.0 : (m) == 4 ? max(v, 0.0) - 0.5 : (m) == 5 ? 0.5 - max(v, 0.0) \
    : (m) == 6 ? (v) : -(v))
#define CEG_OUT(v, m) ((m) == 1 ? (v) * 0.5 : (m) == 2 ? (v) * 2.0 : (m) == 3 ? (v) * 4.0 \
    : (m) == 4 ? (v) - 0.5 : (m) == 5 ? ((v) - 0.5) * 2.0 : (v))
// An output register's index in R, or -1 for discard.
#define CEG_REG(o) ((o) == 1 ? 6 : (o) == 2 ? 7 : (o) == 3 ? 4 : (o) == 4 ? 5 : (o) >= 5 && (o) <= 8 ? (o) - 5 : -1)
float4 CI[7] = { CI0, CI1, CI2, CI3, CI4, CI5, CI6 };
float4 AI[7] = { AI0, AI1, AI2, AI3, AI4, AI5, AI6 };
float4 CO[7] = { CO0, CO1, CO2, CO3, CO4, CO5, CO6 };
float4 AO[7] = { AO0, AO1, AO2, AO3, AO4, AO5, AO6 };
float4 K0[7] = { K00, K01, K02, K03, K04, K05, K06 };
float4 KH[7] = { KH0, KH1, KH2, KH3, KH4, KH5, KH6 };
float4 K1[7] = { K10, K11, K12, K13, K14, K15, K16 };
float4 KA[7] = { KA0, KA1, KA2, KA3, KA4, KA5, KA6 };
float4 t0 = FirstType > 0.5 ? Cube : M0;
float ndv = abs(dot(normalize(VertexN), normalize(Cam)));
float4 R[10] = { t0, M1, M2, M3, float4(0, 0, 0, 1), float4(ndv.xxx, 1.0 - ndv),
                 float4(0, 0, 0, t0.a), 0.0.xxxx, 0.0.xxxx, 0.0.xxxx };
int n = (int)GenCount;
[loop] for (int s = 0; s < 7; ++s)
{
    if (s >= n) break;
    float4 ka = KA[s];
    R[8] = lerp(K0[s], KH[s], CE_WAVE(ka.x, ka.y > 1e-6 ? Time / ka.y : 0.0));
    R[9] = K1[s];
    float3 cv[4];
    float av[4];
    [unroll] for (int k = 0; k < 4; ++k)
    {
        int id = (int)fmod(CI[s][k], 32.0), m = (int)(CI[s][k] / 32.0);
        float3 x = id == 0 ? 0.0.xxx : id == 1 ? 1.0.xxx : id == 2 ? 0.5.xxx : id == 3 ? -1.0.xxx
            : id == 4 ? -0.5.xxx : id <= 14 ? R[clamp(id - 5, 0, 9)].rgb : R[clamp(id - 15, 0, 9)].aaa;
        cv[k] = CEG_IN(x, m);
        int ida = (int)fmod(AI[s][k], 32.0), ma = (int)(AI[s][k] / 32.0);
        float y = ida == 0 ? 0.0 : ida == 1 ? 1.0 : ida == 2 ? 0.5 : ida == 3 ? -1.0 : ida == 4 ? -0.5
            : ida <= 14 ? R[clamp(ida - 5, 0, 9)].a : R[clamp(ida - 15, 0, 9)].b;
        av[k] = CEG_IN(y, ma);
    }
    int flags = (int)ka.z;
    int abo = (int)fmod(CO[s].x, 16.0), abf = (int)(CO[s].x / 16.0);
    int cdo = (int)fmod(CO[s].y, 16.0), cdf = (int)(CO[s].y / 16.0);
    int sumo = (int)CO[s].z, cm = (int)CO[s].w;
    float3 ab = abf == 1 ? dot(cv[0], cv[1]).xxx : clamp(cv[0] * cv[1], -1.0, 1.0);
    float3 cd = cdf == 1 ? dot(cv[2], cv[3]).xxx : clamp(cv[2] * cv[3], -1.0, 1.0);
    float3 abcd = clamp((flags & 1) ? (R[6].a >= 0.5 ? cd : ab) : ab + cd, -1.0, 1.0);
    ab = CEG_OUT(ab, cm); cd = CEG_OUT(cd, cm); abcd = CEG_OUT(abcd, cm);
    float aab = clamp(av[0] * av[1], -1.0, 1.0), acd = clamp(av[2] * av[3], -1.0, 1.0);
    float aabcd = clamp((flags & 2) ? (R[6].a >= 0.5 ? acd : aab) : aab + acd, -1.0, 1.0);
    int am = (int)AO[s].w;
    aab = CEG_OUT(aab, am); acd = CEG_OUT(acd, am); aabcd = CEG_OUT(aabcd, am);
    int r;
    r = CEG_REG(abo); if (r >= 0) R[r].rgb = ab;
    r = CEG_REG(cdo); if (r >= 0) R[r].rgb = cd;
    r = CEG_REG(sumo); if (r >= 0) R[r].rgb = abcd;
    r = CEG_REG((int)AO[s].x); if (r >= 0) R[r].a = aab;
    r = CEG_REG((int)AO[s].y); if (r >= 0) R[r].a = acd;
    r = CEG_REG((int)AO[s].z); if (r >= 0) R[r].a = aabcd;
}
#undef CEG_IN
#undef CEG_OUT
#undef CEG_REG
return R[6];
""" + WAVE_END


# Object shadows on a baked level. CE's colour T (what reaches the screen, the
# lightmap's sun included) is split in two: most of it stays emissive, and a
# share w is drawn as real sun light, base colour T*w*pi / (I * N.L * colour)
# lit by the level's directional light. Where the sun reaches, the two add up
# to T exactly; where a vehicle or a player blocks it, the share drops out and
# the shadow shows. AO 0 keeps the sky light and bounce off it, so nothing
# else changes. w fades out where the surface turns from the sun, and is
# capped so the base colour stays within 1. MJOLNIRLevelLoader sets the sun
# parameters from the level's environment.
#
# The lightmap already has the level's own shadows, so a share taken out
# where CE had none of its sun darkens them a second time (an object's shadow
# reaching through a platform, or the terrain casting at all). LightmapSun is
# the level's lightmap luminance in CE's shadow (x) and in its sun (y),
# measured from the lightmaps (tools/level/gen_ce_level.py): a texel near the
# shadow level gives up nothing, one in the sun gives up what takes it down to
# the shadow level, so an object's shadow is as dark as a baked one beside
# it. The lightmaps are gamma-space values; the colour is linear, hence the
# 2.2. Left at zero, the share is ShadowStrength everywhere, as before.
SUN_WEIGHT_CODE = r"""
float3 screen = max(Screen.rgb, 1e-4);
float ndl = saturate(dot(normalize(N), normalize(SunDir)));
float3 denom = max(SunIlluminance * ndl * SunColor.rgb, 1e-4);
float3 room = denom / (screen * 3.14159265);
float w = ShadowStrength * saturate(ndl * 4.0);
if (HasLightmap > 0.5 && LightmapSun.y > LightmapSun.x)
{
    float l = max(dot(Lightmap.rgb, float3(0.2126, 0.7152, 0.0722)), 1e-4);
    // Where the sun reached, traced (lightmap_bake: green) when the level
    // has it, else guessed from the lightmap's brightness, which takes lamp
    // light for sun.
    // With the terrain's shadow copy (SunVisBake), only where the whole
    // neighbourhood is in the sun (BakeRange.x, BAKE_RANGE_CODE): the copy's
    // sharp shadow edges and the bake's texel steps do not meet, and a share
    // taken out between them left black slivers (Blood Gulch's base wall,
    // 2026-10-05).
    float sunlit = HasBake > 0.5 ? (SunVisBake > 0.5 ? BakeRange.x : Bake.g)
        : smoothstep(0.5, 0.9, (l - LightmapSun.x) / (LightmapSun.y - LightmapSun.x));
    w = min(w, sunlit * (1.0 - pow(saturate(LightmapSun.x / l), 2.2)));
}
return min(w, min(room.r, min(room.g, room.b)));
"""

# CE's sun at a world position, from the level's sun mask (lightmap_bake's
# <stem>_sunmask, CE's lightmap luminance on the topmost upward surface per
# metre): 0 where CE had shade, 1 where it had sun, by the same guess the sun
# share makes from a lightmap (LightmapSun's shadow and sunlit levels); 1 off
# the mask or without one. The level's sun takes it as its light function
# (M_CE_SunLight), so objects stand in CE's shade, which is metres wide and
# soft where the traced geometry has none; the environment masters read it to
# know how much sun really reaches them.
SUN_MASK_CODE = r"""
if (HasSunMask < 0.5 || LightmapSun.y <= LightmapSun.x) return 1.0;
float2 uv = (WorldPos.xy - SunMaskXform.xy) * SunMaskXform.zw;
if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) return 1.0;
// Through a 3 x 3 tent a cell apart: bilinear alone, between 1 m cells and
// sharpened by the smoothstep below, drew a shadow's edge as scallops
// (Blood Gulch's base, 2026-10-06).
uint mw, mh;
SunMask.GetDimensions(mw, mh);
float2 cell = 1.0 / float2(max(mw, 1u), max(mh, 1u));
float4 m = 0.0.xxxx;
float mwt = 0.0;
[unroll] for (int i = -1; i <= 1; ++i)
[unroll] for (int j = -1; j <= 1; ++j)
{
    float4 t = Texture2DSampleLevel(SunMask, SunMaskSampler, uv + float2(i, j) * cell, 0.0);
    float wt = (i == 0 ? 2.0 : 1.0) * (j == 0 ? 2.0 : 1.0) * t.g;
    m += t * wt;
    mwt += wt;
}
if (mwt < 0.5) return 1.0;
m /= mwt;
// 0.15-0.55 of the way from shade to sun: a sunlit face CE drew dimmer
// than open ground (Blood Gulch's base roof, about halfway) is still sun.
return smoothstep(0.15, 0.55, (m.r - LightmapSun.x) / (LightmapSun.y - LightmapSun.x));
"""


def sun_mask_node(g, white):
    """SUN_MASK_CODE's node: the mask texture and its placement as
    parameters (MJOLNIRLevelLoader sets them, and LightmapSun)."""
    mask = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="SunMask",
                  texture=white, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    return g.custom(SUN_MASK_CODE, [
        ("WorldPos", g.node(unreal.MaterialExpressionWorldPosition), ""), ("SunMask", mask, ""),
        ("SunMaskXform", g.vector4("SunMaskXform", (0, 0, 0, 0)), ""),
        ("HasSunMask", g.scalar("HasSunMask", 0.0), ""),
        ("LightmapSun", g.vector("LightmapSun", (0.0, 0.0, 0.0, 0.0)), ""),
    ], output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="CE sun mask")


# The least and the most sun visibility (the bake's G) in a 3 x 3 texel
# neighbourhood, BakeMargin texels apart: CE's sun and shade with their
# edges pulled in by about that much. And the corners' occlusion (R) through
# a 3 x 3 tent a texel apart: unfiltered, a crease's darkest line followed
# the texels' steps and came out toothed (Blood Gulch's cliffs).
BAKE_RANGE_CODE = r"""
uint w, h;
Bake.GetDimensions(w, h);
float2 texel = 1.0 / float2(max(w, 1u), max(h, 1u));
float2 t = BakeMargin * texel;
// Only taps in this texel's chart (the bake's alpha, lightmap_bake
// chart_ids): a tap in the chart packed beside it on the page read another
// surface's values and drew the chart's edge as a line (Blood Gulch's
// cliffs, 2026-10-06). A bake without charts has 1 everywhere.
float id = Texture2DSampleLevel(Bake, BakeSampler, UV, 0.0).a;
float lo = 1.0, hi = 0.0, ao = 0.0, aw = 0.0;
[unroll] for (int i = -1; i <= 1; ++i)
[unroll] for (int j = -1; j <= 1; ++j)
{
    float4 s = Texture2DSampleLevel(Bake, BakeSampler, UV + float2(i, j) * t, 0.0);
    if (abs(s.a - id) < 0.5 / 255.0)
    {
        lo = min(lo, s.g);
        hi = max(hi, s.g);
    }
    float4 a = Texture2DSampleLevel(Bake, BakeSampler, UV + float2(i, j) * texel, 0.0);
    if (abs(a.a - id) < 0.5 / 255.0)
    {
        float tent = (i == 0 ? 2.0 : 1.0) * (j == 0 ? 2.0 : 1.0);
        ao += tent * a.r;
        aw += tent;
    }
}
if (hi < lo) { lo = hi = Texture2DSampleLevel(Bake, BakeSampler, UV, 0.0).g; }
return float4(lo, hi, aw > 0.0 ? ao / aw : 1.0, 0.0);
"""

# The terrain's debug view (DebugView, MJOLNIRLevelLoader's
# `mjolnir_terrain_debug`): one layer of the light, as a display value.
#  1 CE's lightmap  2 baked corners  3 the bake's sky visibility
#  4 the bake's sun visibility  5 the sun mask  6 the sun share drawn as
#  Unreal sun  7 the headlight top-up  8 the base colour Unreal lights
#  9 the bake's charts  (10 Unreal's light alone, 11 CE's alone: below)
DEBUG_CODE = r"""
int m = (int)round(DebugView);
float3 v = 0.0.xxx;
if (m == 1) v = Lightmap.rgb;
else if (m == 2) v = pow(saturate(BakeRange.z), BakeAO).xxx;
else if (m == 3) v = Bake.bbb;
else if (m == 4) v = Bake.ggg;
else if (m == 5) v = SunMaskS.xxx;
else if (m == 6) v = float3(saturate(W * SunMaskS), 0.0, 0.0);
else if (m == 12) v = SunShare.rgb;
else if (m == 14) v = Full.rgb;
else if (m == 15) v = Amb.rgb;
else if (m == 7) v = sqrt(saturate(Dyn.rgb));
else if (m == 8) v = sqrt(saturate(Base.rgb));
else if (m == 9)
{
    float a = Bake.a * 255.0;
    v = frac(float3(a * 0.137, a * 0.291, a * 0.453));
}
return pow(saturate(v), 2.2);
"""

SUN_BASE_CODE = r"""
float ndl = saturate(dot(normalize(N), normalize(SunDir)));
float3 denom = max(SunIlluminance * ndl * SunColor.rgb, 1e-4);
return saturate(Screen.rgb * W * 3.14159265 / denom);
"""

# W is the share the sun really draws: the base colour's share (SUN_WEIGHT_CODE)
# times the sun mask, which the level sun's light function applies too.
SUN_EMISSIVE_CODE = r"""
float3 e = Screen.rgb * (1.0 - W * SunMaskS);
// The sun's light on the dynamic albedo (DYNAMIC_ALBEDO_CODE) comes back out.
return max(e - Dyn.rgb * SunIlluminance * SunColor.rgb * Dyn.a / 3.14159265, 0.0);
"""

# Dynamic lights on a baked level. Every Unreal light multiplies the base
# colour, which holds only the sun's share (SUN_BASE_CODE): about the
# surface's colour where CE had sun, nothing where it had shade, so a
# headlight, muzzle flash or explosion lit only the sunny ground. This tops
# the base colour up to what the sun share would be if CE had the pixel in
# full sun: its colour taken to the lightmap's sunlit level (LightmapSun),
# shared as at that level, so a beam crossing from sun into shade keeps one
# strength (DynamicAlbedo scales it; 0 leaves the material as it was). Before
# 2026-10-06 the target was the texture's albedo, about twice the sunlit
# share, and the beam jumped where the top-up began.
#
# The sun must not light the top-up beyond what the emissive gives back.
# With the terrain's shadow copy (SunVisBake) and a bake: where the bake has
# shade all round (BakeRange.y) the copy keeps the sun off and nothing comes
# back; where it has sun the sun reaches as far as the sun mask lets it
# (SunMaskS) and the emissive gives that back, which caps the top-up; in
# between, by the bake's sun visibility there. Without the copy the sun reaches everywhere the
# surface faces it. Either way the level is unchanged where no other light
# falls. Returns the top-up and, in alpha, the sun's N.L times visibility on
# it.
DYNAMIC_ALBEDO_CODE = r"""
if (DynamicAlbedo <= 0.0 || HasLightmap < 0.5 || LightmapSun.y <= LightmapSun.x) return 0.0.xxxx;
float ndl = saturate(dot(normalize(N), normalize(SunDir)));
float l = max(dot(Lightmap.rgb, float3(0.2126, 0.7152, 0.0722)), 0.5 * LightmapSun.x);
float gain = pow(LightmapSun.y / l, 2.2);
float wFull = ShadowStrength * (1.0 - pow(saturate(LightmapSun.x / LightmapSun.y), 2.2));
float3 full = saturate(Screen.rgb * gain * wFull * 3.14159265
    / max(SunIlluminance * max(ndl, 0.3) * SunColor.rgb, 1e-4));
float3 a = max(full * DynamicAlbedo - Base.rgb, 0.0);
float lo = 1.0, hi = 1.0;
if (SunVisBake > 0.5)
{
    // Shade by the bake's own value, so no band is left without a top-up
    // (a black line along every shadow edge under a headlight, Blood
    // Gulch's base doorways, 2026-10-06). Sun only where the neighbourhood
    // has it all round (BakeRange.x), as the sun share has: by the bake's
    // own value, the light given back where the copy's shadow and the
    // bake's disagree left a dark line along a wall's foot (the base ramps).
    if (HasBake > 0.5) { lo = BakeRange.x; hi = saturate(Bake.g); }
    else lo = hi = smoothstep(0.5, 0.9, (l - LightmapSun.x) / (LightmapSun.y - LightmapSun.x));
}
float3 need = a * lo * SunIlluminance * SunMaskS * ndl * SunColor.rgb / 3.14159265;
float3 left = max(Screen.rgb * (1.0 - W * SunMaskS), 0.0);
float k = 1.0;
if (need.r > left.r) k = min(k, left.r / need.r);
if (need.g > left.g) k = min(k, left.g / need.g);
if (need.b > left.b) k = min(k, left.b / need.b);
float shade = SunVisBake > 0.5 ? 1.0 - hi : 0.0;
float sun = lo * k;
// The band between (the bake has sun here, but not all round): no sun share
// either (SUN_WEIGHT_CODE), so without a top-up of its own a headlight drew
// it as a black line. Nothing is given back for it, so where the sun does
// reach it would show as a bright strip (Blood Gulch's ramps, 2026-10-06):
// it fades out as much as the sun mask lets the sun fall on it, so it lives
// in CE's shade, where headlights matter, and leaves sunlit ground alone.
float band = max(hi - lo, 0.0) * (1.0 - SunMaskS * saturate(ndl * 1.5));
float share = shade + sun + band;
return float4(a * share, share > 0.0 ? sun * SunMaskS * ndl / share : 0.0);
"""


# Unreal-lit terrain (UnrealLit 1, MJOLNIRLevelLoader `mjolnir_terrain_lights
# unreal`): Unreal draws all the direct light, the sun, headlights, flashes
# and explosions alike, over the surface's own colour, and CE's lightmap
# keeps only its ambient light (the sky's fill, the bounce, its lamps).
#
# The colour (SUNLIT_CODE) is CE's texture pass as CE drew it in full sun:
# A x (lightmap sunlit level x material colour), its display gain undone and
# decoded, as screen colour, over the sun the material is told of
# (SunIlluminance) and flat ground's N.L, times AlbedoGain (0.5: the
# renderer's response is twice what the material assumes), so flat sunlit
# ground matches CE, and Unreal's own N.L, with CE's bump map as the normal,
# shades the rest.
#
# The emissive (UNREAL_AMBIENT_CODE) is CE's colour less what Unreal's sun
# adds unshadowed, so in the sun the frame is CE's; and never below CE's
# ambient: CE's colour with the lightmap taken
# down to what CE's sun did not give: where the lightmap is at its sunlit
# level, to its shadow level (LightmapSun.x, times AmbientGain); where it is
# darker (shade, a base interior's lamps), as it is; judged from the lightmap
# alone, not the bake, which knows shadows CE's coarse lightmap never held
# (by the bake, a cliff face Unreal shades but CE lit kept CE's full sun as
# its ambient and showed flat and bright, 2026-10-06). The baked corners stay
# in it, as ambient occlusion should. The terrain takes no Unreal sky or bounce
# light (ambient occlusion 0), which would count the ambient twice; its
# emissive still bounces onto everything else through Lumen.
SUNLIT_CODE = TEXTURE_PASS_CODE + r"""
float3 A = (model && DetailAfter > 0.5) ? B : T;
if (HasSunShare > 0.5)
{
    // The sun's part of CE's frame, per channel: the texture pass at the
    // solver's ambient page with the sky's sun (SunCE, colour x power) put
    // back at this texel's N.L, clamped as tool.exe clamps, less the pass at
    // the ambient page alone. Per channel because the lightmap adds in its
    // own space and the screen does not (a luma share drew a grey sun over a
    // blue ambient). The environment pass is not used for it: its bump
    // modulation against the baked incident direction darkens flat ground's
    // sun share by a third under a 40 degree sun (Blood Gulch, 2026-10-08).
    // N.L no lower than 0.3 (UNREAL_BASE_CODE divides by the same): this is
    // the colour every Unreal light multiplies, and at the texel's own N.L
    // a face turned from the sun had none, so headlights stopped at a hard
    // line on Death Island's cliffs (2026-10-08).
    float3 amb = saturate(SunShare.rgb);
    float cosl = max(dot(normalize(N), normalize(SunDir)), 0.3);
    float3 full = amb + SunCE.rgb * cosl;
    float mx = max(full.r, max(full.g, full.b));
    if (mx > 1.0) full /= mx;
    full = saturate(full);
    float3 f1 = saturate(A * saturate(full * MaterialColor)) / DisplayGain;
    float3 f0 = saturate(A * saturate(amb * MaterialColor)) / DisplayGain;
    float3 s1 = lerp(pow((f1 + 0.055) / 1.055, 2.4), f1 / 12.92, step(f1, 0.04045));
    float3 s0 = lerp(pow((f0 + 0.055) / 1.055, 2.4), f0 / 12.92, step(f0, 0.04045));
    return max(s1 - s0, 0.0) * Exposure;
}
// The lightmap level the surface takes in full sun: its own where the bake
// has it in the sun (CE drew some sunlit faces darker than others: the base
// roof at ~0.6 against the open ground's 0.97), the level's sunlit level
// where the bake has shade (there CE's lightmap holds no sun to go by).
// Taking the level's everywhere drew the roof nearly white (2026-10-06).
bool levels = LightmapSun.y > LightmapSun.x;
float l = HasLightmap > 0.5 ? max(dot(Lightmap.rgb, float3(0.2126, 0.7152, 0.0722)), 1e-4) : 1.0;
float reach = HasBake > 0.5 ? saturate(Bake.g) : 1.0;
// Where CE had sun (its own lightmap, as the sun mask judges it), its
// brightness there; where CE had shade, the level's sunlit level, for the
// headlights (the level's sun is masked off there, M_CE_SunLight).
float ceSun = levels ? smoothstep(0.15, 0.55, (l - LightmapSun.x) / (LightmapSun.y - LightmapSun.x)) : 1.0;
float level = levels ? lerp(LightmapSun.y, max(l, LightmapSun.x), ceSun * reach) : 1.0;
float shadeL = LightmapSun.x;
float3 frame = saturate(A * saturate(level * MaterialColor)) / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
// Only the sun's part of it: CE's ambient (its shadow level) stays CE's.
float share = levels ? 1.0 - pow(saturate(shadeL / level), 2.2) : 1.0;
return lerp(hi, lo, step(frame, 0.04045)) * Exposure * share;
"""

UNREAL_BASE_CODE = r"""
if (ObjectPage > 0.5) return 0.0.xxx;
float flat = max(normalize(SunDir).z, 0.3);
// With the solver's shares the sunlit colour already holds this texel's
// own N.L (the share was solved with it), so that is what Unreal's N.L
// must cancel, not flat ground's; no lower than the 0.3 SUNLIT_CODE took
// it at, so a face turned from the sun keeps its colour for the other
// lights (Unreal's sun adds nothing there by its own N.L).
if (HasSunShare > 0.5) flat = max(dot(normalize(N), normalize(SunDir)), 0.3);
return saturate(Sunlit.rgb * 3.14159265 / max(SunIlluminance * flat * SunColor.rgb, 1e-4) * AlbedoGain);
"""

UNREAL_AMBIENT_CODE = r"""
if (HasLightmap < 0.5) return Screen.rgb;
// A placed object (ObjectPage) draws CE's own lighting for it: the light
// sampled under it from the lightmap, the tree's soft shadow and all, shaded
// by its incident direction (merge_ce_scene.py). Unreal's sun does not
// light it (UNREAL_BASE_CODE): CE never shadowed scenery dynamically, and
// under the terrain copy's shadows a boulder under a tree drew half bright
// and half black, and boughs shadowed each other black (Danger Canyon,
// 2026-10-08).
if (ObjectPage > 0.5) return Screen.rgb;
if (HasSunShare > 0.5)
{
    // CE's frame drawn from the texel's light without the sun (Ambient:
    // the texture pass over the solver's ambient page): CE's ambient, fill
    // and bounce, which no shadow edge crosses. Unreal's sun and the terrain
    // copy's shadows draw the rest, so the lightmap's own shadow edge (its
    // texels, bilinear, scalloped at any scale) never shows inside the
    // crisp one (Blood Gulch's base roof, 2026-10-08).
    return Ambient.rgb * AmbientGain;
}
float l = max(dot(Lightmap.rgb, float3(0.2126, 0.7152, 0.0722)), 1e-4);
// CE's shade is brighter the less sky a surface sees (its radiosity): on
// Blood Gulch the lightmap in shade has a median of 0.18 open to the sky and
// 0.53 enclosed, against its shadow level of 0.19 (2026-10-06), so the level
// is scaled by the bake's sky visibility from x 2.8 down to x 1.
float skyShade = HasBake > 0.5 ? lerp(2.8, 1.0, smoothstep(0.05, 0.6, Bake.b)) : 1.0;
float global = LightmapSun.y > LightmapSun.x ? LightmapSun.x * skyShade : l;
// In the open, CE's shadow level, so a shadow on open sunlit ground is as
// dark as CE's shadows are.
float shadeOpen = global * AmbientGain;

// In the open, CE's ambient is its shade (what SUNLIT_CODE left out).
float3 floorO = Screen.rgb * pow(saturate(min(l, shadeOpen) / l), 2.2);
// What Unreal's sun adds here when nothing shadows it (SunResponse: the
// renderer's measured response, 2026-10-06: base colour x SunIlluminance / pi
// reaches the screen at about twice that), and CE's colour beyond it: in the
// sun the two add up to CE's frame exactly, steep faces and all; in Unreal's
// shadow the sun's part is gone, down to CE's shade.
float ndl = saturate(dot(normalize(N), normalize(SunDir)));
float flat = max(normalize(SunDir).z, 0.3);
float3 direct = saturate(Sunlit.rgb * 3.14159265 / max(SunIlluminance * flat * SunColor.rgb, 1e-4) * AlbedoGain)
    * SunIlluminance * ndl * SunColor.rgb / 3.14159265 * SunResponse * SunMaskS;
float3 open = max(Screen.rgb - direct, floorO);
// Where the geometry keeps the sun out (the bake's sun visibility), Unreal
// adds no sun and CE's colour stays as CE drew it, its lamps and its leaks
// alike (the lip under Blood Gulch's overhang). Until 2026-10-07 a leak next
// to CE's shade was taken down to that shade, judged from the darkest
// lightmap texel within two; but a page packs CE's charts edge to edge and
// many cliff triangles are charts of their own, so read across a chart's
// edge it took an unrelated surface's shade (Danger Canyon's cliffs: an L
// and a line along chart edges), and kept inside the chart it changed at
// every seam (whole triangles stepped dark). Knowing CE's shade nearby needs
// a neighbourhood on the surface, not on the page.
float reach = HasBake > 0.5 ? saturate(Bake.g) : 1.0;
return lerp(Screen.rgb, open, reach);
"""


def sun_split(g, screen, lightmap, has_lightmap, bake, has_bake, bake_range, sun_mask, dynamic=True,
              sunlit=None, bump_n=None, sunshare=None, has_sunshare=None, ambient=None, debug_extra=None):
    """Connects `screen` (the colour to_screen made) to emissive and base
    colour, split for object shadows (SUN_WEIGHT_CODE), with the base colour
    topped up for the other lights (DYNAMIC_ALBEDO_CODE) when `dynamic`.
    `bake_range` is BAKE_RANGE_CODE's node, `sun_mask` SUN_MASK_CODE's. With
    `sunlit` (SUNLIT_CODE's node, to_screen) and `bump_n`, UnrealLit switches
    the terrain to Unreal's direct light (UNREAL_BASE_CODE)."""
    n = g.node(unreal.MaterialExpressionVertexNormalWS)
    sun = [("SunDir", g.vector("SunDir", (0.0, 0.0, 1.0, 0.0)), ""),
           ("SunColor", g.vector("SunColor", (1.0, 1.0, 1.0, 1.0)), ""),
           ("SunIlluminance", g.scalar("SunIlluminance", 8.0), ""),
           ("ShadowStrength", g.scalar("ShadowStrength", 0.0), "")]
    mask = [("SunMaskS", sun_mask, "")]
    if sunshare is None:
        sunshare = g.node(unreal.MaterialExpressionConstant4Vector, x=-300, constant=unreal.LinearColor(0.0, 0.0, 0.0, 0.0))
    if has_sunshare is None:
        has_sunshare = g.node(unreal.MaterialExpressionConstant, x=-300, r=0.0)
    baked = [("Lightmap", lightmap, "RGB"), ("HasLightmap", has_lightmap, ""),
             ("LightmapSun", g.vector("LightmapSun", (0.0, 0.0, 0.0, 0.0)), ""),
             ("Bake", bake, "RGBA"), ("HasBake", has_bake, ""), ("BakeRange", bake_range, ""),
             ("SunVisBake", g.scalar("SunVisBake", 0.0), ""),
             ("SunShare", sunshare, "RGBA"), ("HasSunShare", has_sunshare, "")]
    w = g.custom(SUN_WEIGHT_CODE, [("Screen", screen, ""), ("N", n, "")] + sun + baked,
                 output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="CE sun share")
    base = g.custom(SUN_BASE_CODE, [("Screen", screen, ""), ("N", n, ""), ("W", w, "")] + sun,
                    description="CE sun base colour")
    if dynamic:
        dyn = g.custom(DYNAMIC_ALBEDO_CODE, [
            ("Screen", screen, ""), ("W", w, ""), ("N", n, ""), ("Base", base, ""),
            ("DynamicAlbedo", g.scalar("DynamicAlbedo", 0.0), ""),
        ] + sun + baked + mask, output=unreal.CustomMaterialOutputType.CMOT_FLOAT4, description="CE dynamic albedo")
        topped = g.custom("return saturate(Base.rgb + Dyn.rgb);", [("Base", base, ""), ("Dyn", dyn, "")],
                          description="CE base colour")
    else:
        dyn = g.node(unreal.MaterialExpressionConstant4Vector, x=-300, constant=unreal.LinearColor(0.0, 0.0, 0.0, 0.0))
        topped = base
    emissive = g.custom(SUN_EMISSIVE_CODE, [("Screen", screen, ""), ("W", w, ""), ("Dyn", dyn, "")] + sun[1:3] + mask,
                        description="CE baked share")
    if sunlit is not None:
        unreal_lit = g.scalar("UnrealLit", 0.0)
        albedo_gain = g.scalar("AlbedoGain", 0.5)
        u_base = g.custom(UNREAL_BASE_CODE, [("Sunlit", sunlit, ""), ("AlbedoGain", albedo_gain, ""), ("N", n, ""),
                                             ("HasSunShare", has_sunshare, ""), ("ObjectPage", g.scalar("ObjectPage", 0.0), "")]
                          + sun[:3], description="Unreal-lit base colour")
        if ambient is None:
            ambient = screen
        u_amb = g.custom(UNREAL_AMBIENT_CODE, [("Screen", screen, ""), ("AmbientGain", g.scalar("AmbientGain", 1.0), ""),
                         ("Sunlit", sunlit, ""), ("N", n, ""), ("AlbedoGain", albedo_gain, ""),
                         ("SunResponse", g.scalar("SunResponse", 2.0), ""), ("Ambient", ambient, ""),
                         ("ObjectPage", g.scalar("ObjectPage", 0.0), "")]
                         + baked + sun[:3] + mask, description="Unreal-lit ambient")
        pick = "return U > 0.5 ? A.rgb : B.rgb;"
        topped = g.custom(pick, [("U", unreal_lit, ""), ("A", u_base, ""), ("B", topped, "")], description="base, by mode")
        emissive = g.custom(pick, [("U", unreal_lit, ""), ("A", u_amb, ""), ("B", emissive, "")],
                            description="emissive, by mode")
        normal = g.custom("return U > 0.5 ? N.rgb : float3(0, 0, 1);", [("U", unreal_lit, ""), ("N", bump_n, "")],
                          description="CE bump normal, Unreal-lit only")
        mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    # CE's planar fog over the whole surface (PLANAR_FOG_CODE): the colour CE
    # draws fades to the fog's (as screen colour, like every CE colour), and
    # the share Unreal's lights draw fades with it.
    pf = planar_fog_node(g)
    fog_screen = g.to_screen(g.custom("float3 frame = PlanarFogColor.rgb;\n" + SRGB_TO_LINEAR, [
        ("PlanarFogColor", g.vector("PlanarFogColor", (0.0, 0.0, 0.0, 1.0)), ""),
        ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), ""), ("Exposure", g.scalar("Exposure", 1.0), ""),
    ], description="CE planar fog colour"))
    emissive = g.custom("return E.rgb * (1.0 - P) + C.rgb * P;", [("E", emissive, ""), ("P", pf, ""), ("C", fog_screen, "")],
                        description="CE planar fog over the emissive")
    topped = g.custom("return B.rgb * (1.0 - P);", [("B", topped, ""), ("P", pf, "")],
                      description="CE planar fog over the lit share")
    debug_view = g.scalar("DebugView", 0.0)
    debug = g.to_screen(g.custom(DEBUG_CODE, [
        ("DebugView", debug_view, ""), ("Lightmap", lightmap, "RGB"), ("Bake", bake, "RGBA"),
        ("BakeRange", bake_range, ""), ("BakeAO", g.scalar("BakeAO", 1.0), ""),
        ("W", w, ""), ("Dyn", dyn, ""), ("Base", topped, ""), ("SunShare", sunshare, "RGBA"),
    ] + mask + (debug_extra or [("Full", g.node(unreal.MaterialExpressionConstant4Vector, x=-300, constant=unreal.LinearColor(0.0, 0.0, 0.0, 0.0)), ""),
                                ("Amb", g.node(unreal.MaterialExpressionConstant4Vector, x=-300, constant=unreal.LinearColor(0.0, 0.0, 0.0, 0.0)), "")]),
    description="CE debug view"))
    # 10: Unreal's light alone (the base colour, no emissive); 11: CE's
    # alone (the emissive, no base colour).
    emissive = g.custom("""
int m = (int)round(DebugView);
return m == 0 || m == 11 ? E.rgb : (m == 10 ? 0.0.xxx : D.rgb);
""", [("DebugView", debug_view, ""), ("E", emissive, ""), ("D", debug, "")], description="CE debug emissive")
    topped = g.custom("""
int m = (int)round(DebugView);
return m == 0 || m == 10 ? B.rgb : 0.0.xxx;
""", [("DebugView", debug_view, ""), ("B", topped, "")], description="CE debug base")
    mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(topped, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for prop, value in ((unreal.MaterialProperty.MP_SPECULAR, 0.0), (unreal.MaterialProperty.MP_METALLIC, 0.0),
                        (unreal.MaterialProperty.MP_ROUGHNESS, 1.0), (unreal.MaterialProperty.MP_AMBIENT_OCCLUSION, 0.0)):
        c = g.node(unreal.MaterialExpressionConstant, x=-300, r=value)
        mel.connect_material_property(c, "", prop)


def build_sun_light(defaults):
    """M_CE_SunLight: the level sun's light function, CE's sun from the sun
    mask (SUN_MASK_CODE)."""
    m = fresh(ROOT, "M_CE_SunLight", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_LIGHT_FUNCTION)
    g = Graph(m)
    s = sun_mask_node(g, defaults["T_CE_White"])
    mel.connect_material_property(s, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


def build_linear_copy(defaults):
    """M_CE_LinearCopy: MJOLNIRLevelLoader draws a PNG it imported at runtime
    (ImportFileAsTexture2D, always sRGB) into a linear render target through
    this, re-encoding what the sampler decoded, so the target holds the
    file's own bytes. Drawn as it was, a bake page's 128 arrived as 55 and
    every runtime bake and sun mask read too dark (2026-10-06)."""
    m = fresh(ROOT, "M_CE_LinearCopy", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_UI)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    g = Graph(m)
    # The default must be sRGB too, as the runtime imports are (a Color
    # sampler over T_CE_White does not compile).
    srgb_default = unreal.load_asset("/Engine/EngineResources/DefaultTexture.DefaultTexture")
    t = g.node(unreal.MaterialExpressionTextureSampleParameter2D, x=-1100, parameter_name="Src",
               texture=srgb_default, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    link(g.node(unreal.MaterialExpressionTextureCoordinate, x=-1400), "", t, "UVs")
    c = g.custom(r"""
float3 c = saturate(C.rgb);
float3 lo = c * 12.92;
float3 hi = 1.055 * pow(c, 1.0 / 2.4) - 0.055;
return lerp(hi, lo, step(c, 0.0031308));
""", [("C", t, "RGBA")], description="sRGB encode")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# CE's planar fog (docs/ce_map_conversion.md, "Planar fog"; tools/level/ce_fog.py):
# below a plane (Damnation's shaft, Gephyrophobia's chasm, the water of Battle
# Creek, Chill Out and Death Island) a colour thickens with the point's depth
# under the plane (x, against the fog's opaque depth) and its distance from
# the eye (y, against the opaque distance), as MCC's environment_fog shaders
# do it: A = (1 - min((1-x)^2 + (1-y)^2, 1))^2 with the eye above the fog,
# B = (1 - (1-y)^2)^2 with it inside, mixed by the eye's own depth, times the
# maximum density. PlanarFogPlane is (normal, offset) in Unreal cm, the fog
# below it; PlanarFogParams (maximum density, opaque distance cm, opaque
# depth cm, on). Returns Pf, the fog's share of the pixel.
PLANAR_FOG_CODE = r"""
if (PlanarFogParams.w < 0.5) return 0.0;
float3 n = PlanarFogPlane.xyz;
float depth = max(PlanarFogPlane.w - dot(n, WorldPos), 0.0);
float eyeDepth = max(PlanarFogPlane.w - dot(n, CameraPos), 0.0);
float x = saturate(depth / max(PlanarFogParams.z, 1.0));
float y = saturate(distance(WorldPos, CameraPos) / max(PlanarFogParams.y, 1.0));
float ex = 1.0 - x, ey = 1.0 - y;
float a = 1.0 - min(ex * ex + ey * ey, 1.0);
a *= a;
float b = 1.0 - ey * ey;
b *= b;
float eye = saturate(eyeDepth / max(PlanarFogParams.z, 1.0));
return saturate((eye * (b - a) + a) * PlanarFogParams.x);
"""


def planar_fog_node(g):
    """PLANAR_FOG_CODE's node, Pf."""
    return g.custom(PLANAR_FOG_CODE, [
        ("PlanarFogPlane", g.vector4("PlanarFogPlane", (0, 0, 1, 0)), ""),
        ("PlanarFogParams", g.vector4("PlanarFogParams", (0, 1, 1, 0)), ""),
        ("WorldPos", g.node(unreal.MaterialExpressionWorldPosition), ""),
        ("CameraPos", g.node(unreal.MaterialExpressionCameraPositionWS), ""),
    ], output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="CE planar fog")


def fog_inputs(g):
    depth = g.node(unreal.MaterialExpressionPixelDepth)
    return [("Depth", depth, ""), ("FogColor", g.vector("FogColor", (0, 0, 0, 1)), ""),
            ("FogDensity", g.scalar("FogDensity", 0.0), ""), ("FogStart", g.scalar("FogStart", 0.0), ""),
            ("FogOpaque", g.scalar("FogOpaque", 1.0), "")]


# Game detail (trial builds, an experiment, 2026-10-11): a surface's detail
# maps can be the game's own Megascans surfaces (Campaign Evolved's B30 beach:
# its sand and grass) instead of CE's. The loader sets GamePrimary and
# GameSecondary (albedo), GamePrimaryN and GameSecondaryN (normal maps) and
# GameDetail 1 on the slots it picks. The albedo is sampled on world xy
# (GameTile cm a tile; a second, rotated and larger sample blended in over a
# smooth noise so the tiles don't repeat), taken to CE's gamma space and
# divided by its own mean (its last mip): a detail map averaging 0.5, which
# CE's blend doubles onto the base map, so the base map keeps the level's
# colours and the game's surface gives the grain. GameDetailStrength scales
# it about 0.5. CE's alpha (the detail's specular mask, and what picks
# primary or secondary) is kept from CE's own map.
#
# GamePrimaryKeep and GameSecondaryKeep (0..1) are how much of that CE
# colour stays, each detail map's own (B30's grass is a desaturated albedo
# for tinting, and lost Death Island's green at 0.2; its sand did best at
# that): at 0 the surface
# is the game's own albedo (times GameAlbedoGain), the detail map worked
# back from it (the colour over twice the base map, as CE's blend doubles
# it onto the base). Death Island's base map is a texel or two a metre over
# the whole island, and its painted blotches came through as smears on the
# new sand (2026-10-11). Sand within GameWet.y cm above GameWet.x (the sea,
# cm; 0 off) is wet: darker by GameWet.z, fading out over the band.
# GamePrimaryW / GamePrimaryWN (HasGamePrimaryW), the primary detail's
# rippled surface, takes over in a band from the sea up to GameRipple.x cm
# above it, its edge wandering GameRipple.y cm (B30's LL_RippledSand along
# its waterline).
# GamePrimaryB / GameSecondaryB, when set (HasGamePrimaryB), is a second
# surface blended in over patches tens of metres across (a plain sand
# looked flat over a whole beach).
GAME_NOISE = r"""
#define GD_HASH(p) frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453)
#define GD_NOISE(p) lerp(lerp(GD_HASH(floor(p)), GD_HASH(floor(p) + float2(1, 0)), smoothstep(0, 1, frac(p).x)), \
    lerp(GD_HASH(floor(p) + float2(0, 1)), GD_HASH(floor(p) + float2(1, 1)), smoothstep(0, 1, frac(p).x)), smoothstep(0, 1, frac(p).y))
float2 uv = World.xy / max(Tile, 1.0);
float2 uv2 = float2(uv.x * 0.8 - uv.y * 0.6, uv.x * 0.6 + uv.y * 0.8) * 0.37 + 0.31;
float w = smoothstep(0.25, 0.75, GD_NOISE(uv * 0.21));
// The rippled band above the sea (GameRipple: top cm above GameWet.x, the
// sea, and how far the edge wanders, cm), for the primary detail only.
float rh = World.z - Wet.x;
float rtop = Ripple.x + (GD_NOISE(uv * 0.6 + 7.1) - 0.5) * 2.0 * Ripple.y;
float rw = (Wet.x != 0.0 && HasW > 0.5) ? 1.0 - smoothstep(rtop - Ripple.y, rtop + Ripple.y, rh) : 0.0;
"""
GAME_DETAIL_CODE = r"""
if (GameDetail < 0.5 || Has < 0.5) return Ce;
""" + GAME_NOISE + r"""
float3 a = lerp(Texture2DSample(Tex, TexSampler, uv).rgb, Texture2DSample(Tex, TexSampler, uv2).rgb, w);
float3 mean = Texture2DSampleLevel(Tex, TexSampler, float2(0.5, 0.5), 13.0).rgb;
if (Primary > 0.5 && rw > 0.0)
{
    float2 ru = uv * 1.3 + 0.17;
    a = lerp(a, Texture2DSample(TexW, TexWSampler, ru).rgb, rw);
    mean = lerp(mean, Texture2DSampleLevel(TexW, TexWSampler, float2(0.5, 0.5), 13.0).rgb, rw);
}
if (HasB > 0.5)
{
    // A second surface over patches tens of metres across.
    float wb = smoothstep(0.35, 0.65, GD_NOISE(uv * 0.07 + 3.7));
    a = lerp(a, Texture2DSample(TexB, TexBSampler, uv * 0.83 + 0.5).rgb, wb);
    mean = lerp(mean, Texture2DSampleLevel(TexB, TexBSampler, float2(0.5, 0.5), 13.0).rgb, wb);
}
float3 ag = pow(max(a, 1e-4), 1.0 / 2.2);
float3 d = 0.5 * ag / max(pow(max(mean, 1e-4), 1.0 / 2.2), 1e-3);
d = lerp(0.5.xxx, d, Strength);
float3 own = ag * AlbedoGain * 0.5 / max(Base.rgb, 0.02);
d = lerp(own, d, saturate(BaseKeep));
if (Wet.x != 0.0)
    d *= lerp(1.0 - Wet.z, 1.0, smoothstep(Wet.x, Wet.x + max(Wet.y, 1.0), World.z));
return float4(max(d, 0.0), Ce.a);
#undef GD_NOISE
#undef GD_HASH
"""
# The game surfaces' normal maps (two channels, BC5) on the same world
# mapping, picked like the detail maps (base alpha for a blended shader,
# else the secondary's alpha), in world space (the tile's u along x, v
# along y); the graph takes it to tangent space (GAME_BUMP_CODE).
GAME_NORMAL_CODE = r"""
if (GameDetail < 0.5) return float3(0, 0, 1);
""" + GAME_NOISE + r"""
float2 p = lerp(Texture2DSample(PN, PNSampler, uv).rg, Texture2DSample(PN, PNSampler, uv2).rg, w) * 2.0 - 1.0;
if (rw > 0.0)
    p = lerp(p, Texture2DSample(PWN, PWNSampler, uv * 1.3 + 0.17).rg * 2.0 - 1.0, rw);
float2 s = lerp(Texture2DSample(SN, SNSampler, uv).rg, Texture2DSample(SN, SNSampler, uv2).rg, w) * 2.0 - 1.0;
float pick = Type > 0.5 ? Base.a : Qa;
float2 xy = lerp(HasS > 0.5 ? s : 0.0.xx, HasP > 0.5 ? p : 0.0.xx, pick) * Strength;
return normalize(float3(xy.x, -xy.y, 1.0));
#undef GD_NOISE
#undef GD_HASH
"""
# CE's bump normal (tangent space), tilted by the game surface's.
GAME_BUMP_CODE = r"""
if (GameDetail < 0.5) return CeN;
return normalize(CeN + float3(GameN.xy, 0.0));
"""


FOOT_CODE = r"""
// x: the print's depth here (the footprint map's tread height, as drawn);
// y, z: its slope, for the normal. Faded out towards the square's edge.
if (Strength <= 0.0) return float4(0.0, 0.0, 0.0, 0.0);
float2 uv = (W.xy - R.xy) / R.zw + 0.5;
float edge = saturate(min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y)) * 20.0);
if (edge <= 0.0) return float4(0.0, 0.0, 0.0, 0.0);
float d = Texture2DSampleLevel(Foot, FootSampler, uv, 0).r;
float l = Texture2DSampleLevel(Foot, FootSampler, uv - float2(Texel, 0.0), 0).r;
float r = Texture2DSampleLevel(Foot, FootSampler, uv + float2(Texel, 0.0), 0).r;
float b = Texture2DSampleLevel(Foot, FootSampler, uv - float2(0.0, Texel), 0).r;
float t = Texture2DSampleLevel(Foot, FootSampler, uv + float2(0.0, Texel), 0).r;
float k = Strength * edge;
return float4(d * k, (l - r) * k, (b - t) * k, 0.0);
"""

LAND_CUT_CODE = r"""
float m = AlphaTest > 0.5 ? Pick : 1.0;
if (LandCut < 0.5) return m;
float2 uv = (W.xy - R.xy) / R.zw;
if (any(uv < 0.0) || any(uv > 1.0)) return m;
// A texel a landscape vertex: vertex i of N sits at texel centre (i + 0.5) / N.
// Grown by Grow texels (the mask's most over a 3 x 3 spread): the mesh runs
// under the landscape's edge a metre or two, so a low view past that edge
// meets mesh, not the void under the landscape. At 1 quad the landscape's
// lift (8 cm) left a see-through seam at a base's door (Blood Gulch,
// 2026-10-12).
float2 c = (uv * (N - 1.0) + 0.5) / N;
float g = Grow / N;
float h = 0.0;
[unroll] for (int i = -1; i <= 1; i++)
    [unroll] for (int j = -1; j <= 1; j++)
        h = max(h, Texture2DSampleLevel(Mask, MaskSampler, c + float2(i, j) * g, 0).r);
// Short of half (Edge), so the mesh overlaps the landscape's edge (the
// landscape sits a few cm over it) rather than leaving pinholes where their
// interpolations, and the landscape's LODs, differ.
return m * saturate((h - Edge) * 100.0);
"""


# A structure's surface under Unreal's light (Surface.x on: a slot
# tools/level/upgrade_ce_map.py marks, the bases and their metal): CE drew
# its panels flat and matte, the seams and plates only in the texture. The
# normal comes from the base map's own relief (its luminance as a height,
# central differences a texel apart, Surface.y strength) and the micro
# detail's, over CE's bump map; seams (dark in the base) are rougher than
# plate; the Forerunner kit's scratch mask (Wear, world space, Surface.w)
# wears the plate brighter and smoother; rain streaks run down the walls.
# Roughness (Surface.z the plate's) and specular are the material's again
# (0 and 1 otherwise, CE's matte). Texture2DSample only (the hit shaders).
SURFACE_CODE = r"""
Rough = 1.0;
Spec = 0.0;
Wear = 0.0;
if (Surface.x <= 0.0) return BumpN;
float2 t = Texel.xy;
float3 lw = float3(0.299, 0.587, 0.114);
float c  = dot(Texture2DSample(BaseT, BaseTSampler, UV).rgb, lw);
float hx = dot(Texture2DSample(BaseT, BaseTSampler, UV + float2(t.x, 0)).rgb, lw)
         - dot(Texture2DSample(BaseT, BaseTSampler, UV - float2(t.x, 0)).rgb, lw);
float hy = dot(Texture2DSample(BaseT, BaseTSampler, UV + float2(0, t.y)).rgb, lw)
         - dot(Texture2DSample(BaseT, BaseTSampler, UV - float2(0, t.y)).rgb, lw);
float2 mt = Texel.zw;
float mx = dot(Texture2DSample(MicroT, MicroTSampler, MUV + float2(mt.x, 0)).rgb, lw)
         - dot(Texture2DSample(MicroT, MicroTSampler, MUV - float2(mt.x, 0)).rgb, lw);
float my = dot(Texture2DSample(MicroT, MicroTSampler, MUV + float2(0, mt.y)).rgb, lw)
         - dot(Texture2DSample(MicroT, MicroTSampler, MUV - float2(0, mt.y)).rgb, lw);
float2 slope = -float2(hx, hy) * Surface.y - float2(mx, my) * Surface.y * 0.35 * HasMicro;
float3 n = normalize(float3(BumpN.xy + slope, BumpN.z));
// Wear: the kit's scratches over the plate, from the side the wall faces.
float3 nw = normalize(Nw);
float3 bw = pow(abs(nw), 4.0); bw /= max(bw.x + bw.y + bw.z, 1e-4);
float s = Texture2DSample(WearT, WearTSampler, W.yz / 140.0).r * bw.x
        + Texture2DSample(WearT, WearTSampler, W.xz / 140.0).r * bw.y
        + Texture2DSample(WearT, WearTSampler, W.xy / 140.0).r * bw.z;
Wear = saturate(s * 1.6 - 0.25) * Surface.w;
float seam = 1.0 - smoothstep(0.08, 0.3, c);
// Paint stays matte: on a saturated base the sheen reflected the grey sky
// over it and Yoyorast's red trim drew rust (2026-10-12). Bare metal (grey
// in CE's map) takes the sheen.
float3 bc = Texture2DSample(BaseT, BaseTSampler, UV).rgb;
float mxc = max(bc.r, max(bc.g, bc.b));
float paint = smoothstep(0.15, 0.4, (mxc - min(bc.r, min(bc.g, bc.b))) / max(mxc, 1e-3));
Rough = saturate(lerp(lerp(Surface.z, 0.85, seam) - Wear * 0.25, 0.95, paint));
Spec = 0.35 * Surface.x * (1.0 - paint);
return n;
"""

# Wear and weathering into the base colour (Surface as SURFACE_CODE): the
# scratched plate brighter, a wall streaked darker below its ledges.
SURFACE_BASE_CODE = r"""
if (Surface.x <= 0.0) return B;
float3 nw = normalize(Nw);
float wall = 1.0 - smoothstep(0.35, 0.7, abs(nw.z));
float h = frac(sin(dot(floor(float2((W.x + W.y) / 45.0, 0.0)), float2(127.1, 311.7))) * 43758.5453);
float run = smoothstep(0.55, 0.95, h) * (0.6 + 0.4 * sin(W.z / 90.0 + h * 6.28));
float4 o = B;
o.rgb *= 1.0 - run * wall * 0.22 * Surface.x;
o.rgb = lerp(o.rgb, saturate(o.rgb * 1.35 + 0.06), Wear * 0.6);
return o;
"""


def build_environment(name, masked, defaults, two_sided=False, land=False):
    """`land`: the landscape master (tools/level/build_landscape.py). A
    landscape has no CE texture coordinates, so its base and lightmap UVs
    both come from world XY over the landscape's rectangle (LandRect: x, y,
    width, height in cm), and its Base, Lightmap, Bake and SunShare are the
    bakes build_landscape.py writes over that rectangle."""
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
    if land:
        land_uv = g.custom("return (W.xy - R.xy) / R.zw;", [
            ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
            ("R", g.vector4("LandRect", (0.0, 0.0, 50400.0, 50400.0)), "")],
            output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description="landscape uv")

    def uv(index):
        """A CE texture coordinate: the mesh's, or the landscape's world UV."""
        return land_uv if land else g.uv(index)

    # The base UV, transformed as CE does every pass of the surface: an
    # environment's texture scrolling (BaseUAnim/BaseVAnim, no phase), a
    # model's map scale and u, v and rotation animation (STAGE_UV_CODE). The
    # detail, micro, bump and self-illumination maps scale the transformed UV.
    time0 = g.node(unreal.MaterialExpressionTime)
    zero = g.node(unreal.MaterialExpressionConstant, x=-1900, r=0.0)
    uv0 = g.custom(STAGE_UV_CODE, [
        ("UV", uv(0), ""), ("Time", time0, ""), ("Depth", zero, ""),
        ("Xform", g.vector4("BaseXform", (1, 1, 0, 0)), ""),
        ("UAnim", g.vector4("BaseUAnim", (1, 0, 0, 0)), ""),
        ("VAnim", g.vector4("BaseVAnim", (1, 0, 0, 0)), ""),
        ("RAnim", g.vector4("BaseRAnim", (1, 0, 0, 0)), ""),
        ("Misc", g.vector4("BaseMisc", (0, 0, 0, 0)), ""), ("First", zero, ""), ("ChicagoFlags", zero, ""),
    ], output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description="CE base uv")

    def scaled(scale, aspect=None):
        """The base UV times a map's scale, its v also times `aspect` (a
        detail map's v scale or rescale)."""
        inputs = [("UV", uv0, ""), ("S", g.scalar(scale, 1.0), "")]
        inputs.append(("A", g.scalar(aspect, 1.0) if aspect else g.node(unreal.MaterialExpressionConstant, x=-1900, r=1.0), ""))
        return g.custom("return UV * float2(S, S * A);", inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                        description=f"CE {scale} uv")

    base = g.texture("Base", white, uv0)
    base_pin = "RGBA"
    if land:
        # Footprints (MJOLNIRLevelLoader Footprints): the players' steps drawn
        # into a render target (FootRT) over a square around the local player
        # (FootRect: centre x, y, size cm). The print darkens the ground and
        # bends its normal; off by default (FootStrength 0).
        foot = g.custom(FOOT_CODE, [
            ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
            ("R", g.vector4("FootRect", (0.0, 0.0, 4096.0, 4096.0)), ""),
            ("Foot", g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="FootRT",
                            texture=grey, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR), ""),
            ("Texel", g.scalar("FootTexel", 1.0 / 2048.0), ""),
            ("Strength", g.scalar("FootStrength", 0.0), "")],
            output=unreal.CustomMaterialOutputType.CMOT_FLOAT4, description="footprints")
        base = g.custom("return float4(B.rgb * (1.0 - Dark * F.x), B.a);",
                        [("B", base, "RGBA"), ("F", foot, ""), ("Dark", g.scalar("FootDark", 0.45), "")],
                        output=unreal.CustomMaterialOutputType.CMOT_FLOAT4, description="footprint shade")
        base_pin = ""
    primary = g.texture("Primary", grey, scaled("PrimaryScale", "PrimaryAspect"))
    secondary = g.texture("Secondary", grey, scaled("SecondaryScale", "SecondaryAspect"))
    micro = g.texture("Micro", grey, scaled("MicroScale", "MicroAspect"))
    bump = g.texture("Bump", flat, scaled("BumpScale"))
    lightmap = g.texture("Lightmap", white, uv(1))
    # tools: crates/ue-texture/examples/lightmap_bake.rs, on the same UVs.
    bake = g.texture("Bake", white, uv(1))
    has_bake = g.scalar("HasBake", 0.0)
    # The solver's sun shares on the lightmap's UVs (ce_material_spec.py
    # SunShare, from `mjolnir level lightmaps`): R the sun's share of the
    # texel's light, G its share with the sun unblocked.
    sunshare = g.texture("SunShare", white, uv(1))
    has_sunshare = g.scalar("HasSunShare", 0.0)
    # A placed object's lightmap is its block of the object lighting page
    # (tools/level/merge_ce_scene.py): its light in the first of eight
    # columns, its reflection tint in the second, change colours A-D in the
    # third to sixth. These read the same texture beside the first.
    obj_tint = g.texture("Lightmap", white, g.custom("return UV + float2(0.125, 0.0);", [("UV", uv(1), "")],
                                                      output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                                                      description="object reflection tint"))
    obj_cc = g.texture("Lightmap", white, g.custom("return UV + float2(CCOffset, 0.0);",
                                                    [("UV", uv(1), ""), ("CCOffset", g.scalar("CCOffset", 0.25), "")],
                                                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                                                    description="object change colour"))
    # shader_model's multipurpose map (read only with HasMulti).
    multi = g.texture("Multipurpose", white, uv0)
    self_illum = g.texture("SelfIllumMap", white, scaled("SelfIllumScale"))
    # A model's self-illumination colour source: a change colour of the
    # object lighting page, like CCOffset's.
    si_cc = g.texture("Lightmap", white, g.custom("return UV + float2(SICCOffset, 0.0);",
                                                   [("UV", uv(1), ""), ("SICCOffset", g.scalar("SICCOffset", 0.25), "")],
                                                   output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                                                   description="object self-illumination colour"))
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
    primary_in, secondary_in = (primary, "RGBA"), (secondary, "RGBA")
    if GAME_DETAIL:
        world = g.node(unreal.MaterialExpressionWorldPosition, x=-2000)
        tile = g.scalar("GameTile", 300.0)
        game_on = g.scalar("GameDetail", 0.0)
        strength = g.scalar("GameDetailStrength", 1.0)
        albedo_gain = g.scalar("GameAlbedoGain", 1.0)
        wet = g.vector4("GameWet", (0.0, 60.0, 0.35, 0.0))
        ripple = g.vector4("GameRipple", (120.0, 40.0, 0.0, 0.0))
        has_ripple = g.scalar("HasGamePrimaryW", 0.0)
        ripple_albedo = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="GamePrimaryW",
                               texture=unreal.load_asset("/Engine/EngineResources/DefaultTexture"),
                               sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        albedo_default = unreal.load_asset("/Engine/EngineResources/DefaultTexture")
        normal_default = unreal.load_asset("/Engine/EngineMaterials/DefaultNormal")

        def game_texture(pname, default, sampler):
            return g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name=pname,
                          texture=default, sampler_type=sampler)

        detail = []
        for ce, pname in ((primary, "GamePrimary"), (secondary, "GameSecondary")):
            detail.append(g.custom(GAME_DETAIL_CODE, [
                ("Ce", ce, "RGBA"), ("Tex", game_texture(pname, albedo_default, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR), ""),
                ("World", world, ""), ("Tile", tile, ""), ("GameDetail", game_on, ""),
                ("Has", g.scalar("Has" + pname, 0.0), ""), ("Strength", strength, ""),
                ("Base", base, base_pin), ("BaseKeep", g.scalar(pname + "Keep", 1.0), ""),
                ("AlbedoGain", albedo_gain, ""), ("Wet", wet, ""),
                ("TexB", game_texture(pname + "B", albedo_default, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR), ""),
                ("HasB", g.scalar("Has" + pname + "B", 0.0), ""),
                ("Primary", g.node(unreal.MaterialExpressionConstant, x=-1900, r=1.0 if pname == "GamePrimary" else 0.0), ""),
                ("TexW", ripple_albedo, ""), ("HasW", has_ripple, ""), ("Ripple", ripple, "")],
                output=unreal.CustomMaterialOutputType.CMOT_FLOAT4, description=f"game detail {pname}"))
        primary_in, secondary_in = (detail[0], ""), (detail[1], "")
        game_w = g.custom(GAME_NORMAL_CODE, [
            ("PN", game_texture("GamePrimaryN", normal_default, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL), ""),
            ("SN", game_texture("GameSecondaryN", normal_default, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL), ""),
            ("World", world, ""), ("Tile", tile, ""), ("GameDetail", game_on, ""),
            ("Base", base, base_pin), ("Qa", secondary, "A"), ("Type", g.scalar("Type", 0.0), ""),
            ("HasP", g.scalar("HasGamePrimary", 0.0), ""), ("HasS", g.scalar("HasGameSecondary", 0.0), ""),
            ("Strength", g.scalar("GameNormalStrength", 1.0), ""),
            ("PWN", game_texture("GamePrimaryWN", normal_default, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL), ""),
            ("HasW", has_ripple, ""), ("Ripple", ripple, ""), ("Wet", wet, "")], description="game detail normal")
        game_t = g.node(unreal.MaterialExpressionTransform, x=-800,
                        transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                        transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
        link(game_w, "", game_t, "")
        bump_n = g.custom(GAME_BUMP_CODE, [("CeN", bump_n, ""), ("GameN", game_t, ""), ("GameDetail", game_on, "")],
                          description="CE bump normal with game detail")
    bump_w = g.node(unreal.MaterialExpressionTransform, x=-800,
                    transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                    transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    if land:
        bump_n = g.custom("float3 n = N; n.xy += F.yz * Relief; return normalize(n);",
                          [("N", bump_n, ""), ("F", foot, ""), ("Relief", g.scalar("FootRelief", 1.0), "")],
                          description="footprint normal")
    # Structures (SURFACE_CODE): relief from the base map, roughness, wear.
    surface = g.vector4("Surface", (0.0, 3.0, 0.45, 0.6))
    world_pos = g.node(unreal.MaterialExpressionWorldPosition, x=-2000)
    nw_vertex = g.node(unreal.MaterialExpressionVertexNormalWS)
    base_t = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="Base", texture=white,
                    sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    micro_t = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="Micro", texture=grey,
                     sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    wear_t = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="SurfaceWear",
                    texture=defaults["T_CE_Grey"], sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    surf = g.custom(SURFACE_CODE, [
        ("BumpN", bump_n, ""), ("BaseT", base_t, ""), ("UV", uv0, ""), ("MicroT", micro_t, ""),
        ("MUV", scaled("MicroScale", "MicroAspect"), ""), ("HasMicro", g.scalar("HasMicro", 0.0), ""),
        ("Texel", g.vector4("SurfaceTexel", (1.0 / 256.0, 1.0 / 256.0, 1.0 / 128.0, 1.0 / 128.0)), ""),
        ("Surface", surface, ""), ("W", world_pos, ""), ("Nw", nw_vertex, ""), ("WearT", wear_t, "")],
        description="structure surface")
    outs = []
    for oname in ("Rough", "Spec", "Wear"):
        o = unreal.CustomOutput()
        o.set_editor_property("output_name", oname)
        o.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        outs.append(o)
    surf.set_editor_property("additional_outputs", outs)
    bump_n = surf
    base_tex = base
    base = g.custom(SURFACE_BASE_CODE, [("B", base, base_pin), ("Surface", surface, ""), ("W", world_pos, ""),
                                        ("Nw", nw_vertex, ""), ("Wear", surf, "Wear")],
                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT4, description="structure wear")
    base_pin = ""
    link(bump_n, "", bump_w, "")
    vertex_n = g.node(unreal.MaterialExpressionVertexNormalWS)
    reflect_flat = g.scalar("ReflectFlat", 0.0)
    direction = g.custom(REFLECT_CODE, [("Cam", cam, ""), ("BumpN", bump_w, ""), ("VertexN", vertex_n, ""),
                                        ("Flat", reflect_flat, "")], description="CE reflection vector")
    cube = g.cube("ReflectionCube", defaults["T_CE_BlackCube"], direction)
    time = g.node(unreal.MaterialExpressionTime)

    inputs = [
        ("Base", base, base_pin), ("Primary", *primary_in), ("Secondary", *secondary_in),
        ("Micro", micro, "RGBA"), ("Bump", bump, "RGBA"), ("Lightmap", lightmap, "RGBA"),
        ("SelfIllum", self_illum, "RGBA"), ("Incident", vc, ""), ("IncidentWeight", vc, "A"),
        ("Multi", multi, "RGBA"), ("ObjTint", obj_tint, "RGBA"), ("ObjCC", obj_cc, "RGBA"),
        ("SICC", si_cc, "RGBA"), ("HasSICC", g.scalar("HasSICC", 0.0), ""),
        ("LightmapReflScale", g.scalar("LightmapReflScale", 1.0), ""),
        ("Eye", eye, ""), ("Cam", cam, ""), ("BumpN", bump_n, ""), ("BumpW", bump_w, ""),
        ("VertexN", vertex_n, ""), ("Cube", cube, "RGB"), ("Time", time, ""),
        ("HasBump", has_bump, ""), ("BumpIsSpecMask", bump_is_mask, ""), ("ReflectFlat", reflect_flat, ""),
        ("Exposure", g.scalar("Exposure", 1.0), ""), ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), ""),
    ] + fog_inputs(g)
    has_lightmap = g.scalar("HasLightmap", 0.0)
    inputs.append(("HasLightmap", has_lightmap, ""))
    inputs += [("Bake", bake, "RGBA"), ("HasBake", has_bake, ""), ("BakeAO", g.scalar("BakeAO", 1.0), ""),
               ("SunShare", sunshare, "RGBA"), ("HasSunShare", has_sunshare, "")]
    for pname, default in (("Type", 0.0), ("Func", 0.0), ("MicroFunc", 0.0), ("HasPrimary", 0.0),
                           ("HasSecondary", 0.0), ("HasMicro", 0.0),
                           ("HasSelfIllum", 0.0), ("SpecLightmap", 0.0), ("ExtraShiny", 0.0),
                           ("Overbright", 0.0), ("SpecBrightness", 0.0), ("HasReflection", 0.0),
                           ("ReflPerp", 0.0), ("ReflPara", 0.0), ("HasMulti", 0.0), ("ModelShader", 0.0),
                           ("DetailMask", 0.0), ("DetailAfter", 0.0), ("ModelCC", 0.0),
                           ("HasModelSelfIllum", 0.0), ("ObjectPage", 0.0), ("ReflFalloff", 0.0),
                           ("ReflCutoff", 0.0)):
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
    bake_obj = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="Bake",
                      texture=white, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    bake_range = g.custom(BAKE_RANGE_CODE, [("Bake", bake_obj, ""), ("UV", uv(1), ""),
                                            ("BakeMargin", g.scalar("BakeMargin", 1.5), "")],
                          output=unreal.CustomMaterialOutputType.CMOT_FLOAT4, description="CE bake neighbourhood")
    inputs.append(("BakeRange", bake_range, ""))
    c = g.custom(ENVIRONMENT_CODE, inputs, description="CE shader_environment")
    by_name = {name: (src, pin) for name, src, pin in inputs}
    sunlit = g.to_screen(g.custom(SUNLIT_CODE, [(name, *by_name[name]) for name in (
        "Base", "Primary", "Secondary", "Micro", "Multi", "Type", "Func", "MicroFunc", "HasPrimary",
        "HasSecondary", "HasMicro", "HasMulti", "ModelShader", "DetailMask", "DetailAfter", "MaterialColor",
        "DisplayGain", "Exposure", "Lightmap", "HasLightmap", "Bake", "HasBake", "SunShare", "HasSunShare")]
        + [("LightmapSun", g.vector("LightmapSun", (0.0, 0.0, 0.0, 0.0)), ""),
           ("N", vertex_n, ""),
           ("SunDir", g.vector("SunDir", (0.0, 0.0, 1.0, 0.0)), ""),
           ("SunCE", g.vector("SunCE", (0.0, 0.0, 0.0, 0.0)), "")],
        description="CE sunlit colour"))
    # The same pass over the solver's ambient page (SunShare.rgb: the
    # texel's light without the sun): CE's frame as it is in the sun's
    # shadow, the terrain's emissive under Unreal's sun (UNREAL_AMBIENT_CODE).
    amb_raw = g.custom(ENVIRONMENT_CODE,
                       [(name, (sunshare if name == "Lightmap" else src), pin) for name, src, pin in inputs],
                       description="CE shader_environment, ambient")
    ambient = g.to_screen(amb_raw)
    sun_split(g, g.to_screen(c), lightmap, has_lightmap, bake, has_bake, bake_range, sun_mask_node(g, white),
              sunlit=sunlit, bump_n=bump_n, sunshare=sunshare, has_sunshare=has_sunshare, ambient=ambient,
              debug_extra=[("Full", sunlit, ""), ("Amb", amb_raw, "")])
    # A structure's own roughness and specular (SURFACE_CODE); sun_split
    # left CE's matte constants on them.
    mel.connect_material_property(surf, "Rough", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(surf, "Spec", unreal.MaterialProperty.MP_SPECULAR)
    if masked:
        # shader_environment tests the bump map's alpha; object shaders the
        # base map's (AlphaFromBase 1).
        pick = g.node(unreal.MaterialExpressionLinearInterpolate, x=-300)
        link(bump, "A", pick, "A")
        link(base_tex, "A", pick, "B")
        link(g.scalar("AlphaFromBase", 0.0), "", pick, "Alpha")
        # A ground slot a Landscape draws (MJOLNIRLevelLoader, LandCut 1,
        # AlphaTest 0): the mesh keeps only the landscape's holes, from the
        # same hole mask over the same rectangle (build_landscape.py
        # landmask.png, a texel a landscape vertex), so the two meet.
        mask = g.custom(LAND_CUT_CODE, [
            ("Pick", pick, ""), ("AlphaTest", g.scalar("AlphaTest", 1.0), ""),
            ("LandCut", g.scalar("LandCut", 0.0), ""),
            ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
            ("R", g.vector4("LandRect", (0.0, 0.0, 50400.0, 50400.0)), ""),
            ("N", g.scalar("LandMaskSize", 505.0), ""),
            ("Edge", g.scalar("LandCutEdge", 0.25), ""),
            ("Grow", g.scalar("LandCutGrow", 1.5), ""),
            ("Mask", g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="LandMask",
                            texture=defaults["T_CE_White"],
                            sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR), "")],
            output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="landscape cut")
        mel.connect_material_property(mask, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    elif land:
        # The landscape's holes (its visibility layer, build_landscape.py):
        # where the ground is a cliff or a plateau's overhanging lip, the
        # terrain mesh draws it.
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property("opacity_mask_clip_value", 0.5)
        holes = g.node(unreal.MaterialExpressionLandscapeVisibilityMask, x=-300)
        mel.connect_material_property(holes, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# A chicago decal (flag bit 1) is drawn with a depth bias over the surface it
# lies on. Not reproduced: sampling scene depth from these translucent
# materials crashed the game as they loaded (2026-10-04), and this editor's
# Python cannot connect world position offset.
# A machine's moving part (docs/ce_map_conversion.md, "Machines"): the
# device position animation moves one node, and the merged geometry hung on
# it is drawn moved, as a World Position Offset. DeviceMotion is (scale at
# the first frame, scale at the last, period in seconds, position): a gear
# runs its position from 0 to 1 over the period and starts again; a period
# of 0 holds it at the position. The node's offset runs from DeviceT0 to
# DeviceT1 (centimetres), its scale about DevicePivot, all from its rest
# pose, which the mesh holds.
DEVICE_WPO_CODE = r"""
float p = Motion.z > 0.0 ? frac(Time / Motion.z + Motion.w) : Motion.w;
float s = lerp(Motion.x, Motion.y, p);
return (WorldPos - Pivot.xyz) * (s - 1.0) + lerp(T0.xyz, T1.xyz, p);
"""


def device_offset(g, m):
    """Wire the device motion into the material's World Position Offset.
    Python cannot reach that input (MaterialProperty leaves it out): the
    project's MjolnirUIBuilder plugin connects it."""
    wpo = g.custom(DEVICE_WPO_CODE, [
        ("WorldPos", g.node(unreal.MaterialExpressionWorldPosition), ""),
        ("Time", g.node(unreal.MaterialExpressionTime), ""),
        ("Pivot", g.vector("DevicePivot", (0, 0, 0, 0)), ""),
        ("T0", g.vector("DeviceT0", (0, 0, 0, 0)), ""),
        ("T1", g.vector("DeviceT1", (0, 0, 0, 0)), ""),
        ("Motion", g.vector4("DeviceMotion", (1, 1, 0, 0)), ""),
    ], description="CE device position")
    if not unreal.MjolnirUIBuilderLibrary.connect_world_position_offset(m, wpo, ""):
        raise RuntimeError(f"cannot connect World Position Offset on {m.get_name()}")


# CE draws the sky around the camera: it moves with the eye, and only turns.
# Ours is a mesh kilometres out around the CE sky's origin (merge_ce_scene.py:
# the BSP's box centre, 525 m under Gephyrophobia's bridge, in its chasm),
# and seen from anywhere but that origin its layers part: the ring's strips
# and rails are quads at different depths that line up from the origin only.
# SkyFollow 1 (the spec's sky sections) moves the vertices with the camera,
# the origin onto the eye; SkyOrigin is the CE origin from the actor, in cm.
SKY_WPO_CODE = r"""
return SkyFollow * (CameraPos - (ActorPos + SkyOrigin.xyz));
"""


def sky_offset(g, m):
    """Wire SKY_WPO_CODE into the material's World Position Offset (through
    the MjolnirUIBuilder plugin, as device_offset)."""
    wpo = g.custom(SKY_WPO_CODE, [
        ("SkyFollow", g.scalar("SkyFollow", 0.0), ""),
        ("CameraPos", g.node(unreal.MaterialExpressionCameraPositionWS), ""),
        ("ActorPos", g.node(unreal.MaterialExpressionActorPositionWS), ""),
        ("SkyOrigin", g.vector4("SkyOrigin", (0, 0, 0, 0)), ""),
    ], description="CE sky around the camera")
    if not unreal.MjolnirUIBuilderLibrary.connect_world_position_offset(m, wpo, ""):
        raise RuntimeError(f"cannot connect World Position Offset on {m.get_name()}")


def build_transparent(name, blend, defaults, two_sided=False, device=False):
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("two_sided", two_sided)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    uv0 = g.uv(0)
    time = g.node(unreal.MaterialExpressionTime)
    depth = g.node(unreal.MaterialExpressionPixelDepth)
    cam = g.node(unreal.MaterialExpressionCameraVectorWS)
    vertex_n = g.node(unreal.MaterialExpressionVertexNormalWS)
    world_pos = g.node(unreal.MaterialExpressionWorldPosition)
    camera_pos = g.node(unreal.MaterialExpressionCameraPositionWS)
    object_pos = g.node(unreal.MaterialExpressionObjectPositionWS)
    chicago_flags = g.scalar("ChicagoFlags", 0.0)
    first_type = g.scalar("FirstMapType", 0.0)
    samples, miscs = [], []
    for i in range(4):
        misc = g.vector4(f"Stage{i}Misc", (0, 0, 0, 0))
        miscs.append(misc)
        first = g.node(unreal.MaterialExpressionConstant, x=-1900, r=1.0 if i == 0 else 0.0)
        uv = g.custom(STAGE_UV_CODE, [
            ("UV", uv0, ""), ("Time", time, ""), ("Depth", depth, ""),
            ("Xform", g.vector4(f"Stage{i}Xform", (1, 1, 0, 0)), ""),
            ("UAnim", g.vector4(f"Stage{i}UAnim", (1, 0, 0, 0)), ""),
            ("VAnim", g.vector4(f"Stage{i}VAnim", (1, 0, 0, 0)), ""),
            ("RAnim", g.vector4(f"Stage{i}RAnim", (1, 0, 0, 0)), ""),
            ("Misc", misc, ""), ("First", first, ""), ("ChicagoFlags", chicago_flags, ""),
        ], output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description=f"CE stage {i} uv")
        samples.append(g.texture(f"Map{i}", defaults["T_CE_White"], uv))
    direction = g.custom(FIRST_CUBE_CODE, [("Type", first_type, ""), ("Cam", cam, ""), ("VertexN", vertex_n, ""),
                                           ("WorldPos", world_pos, ""), ("ObjectPos", object_pos, ""),
                                           ("CameraPos", camera_pos, "")], description="CE first map cube direction")
    cube = g.cube("Map0Cube", defaults["T_CE_BlackCube"], direction)
    # MCC's shader_transparent_generic (GENERIC_CODE): GenericStages > 0 takes
    # the place of the chicago chain.
    gen_count = g.scalar("GenericStages", 0.0)
    gen_inputs = [(f"M{i}", s, "RGBA") for i, s in enumerate(samples)]
    gen_inputs += [("Cube", cube, "RGBA"), ("FirstType", first_type, ""), ("GenCount", gen_count, ""),
                   ("Time", time, ""), ("VertexN", vertex_n, ""), ("Cam", cam, "")]
    for prefix, param, default in (("CI", "GenCI", (0, 0, 0, 0)), ("AI", "GenAI", (0, 0, 0, 0)),
                                   ("CO", "GenCO", (0, 0, 0, 0)), ("AO", "GenAO", (0, 0, 0, 0)),
                                   ("K0", "GenK0", (0, 0, 0, 0)), ("KH", "GenK0Hi", (0, 0, 0, 0)),
                                   ("K1", "GenK1", (0, 0, 0, 0)), ("KA", "GenKA", (0, 0, 0, 0))):
        for s in range(GENERIC_STAGES):
            gen_inputs.append((f"{prefix}{s}", g.vector4(f"{param}{s}", default), ""))
    gen = g.custom(GENERIC_CODE, gen_inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
                   description="CE shader_transparent_generic")
    inputs = [(f"M{i}", s, "RGBA") for i, s in enumerate(samples)]
    inputs += [(f"S{i}", misc, "") for i, misc in enumerate(miscs)]
    inputs += [("Gen", gen, ""), ("GenCount", gen_count, ""), ("PlanarF", planar_fog_node(g), "")]
    inputs += [("Cube", cube, "RGBA"), ("FirstType", first_type, ""),
               ("Fn", g.vector4("StageColorFunctions", (0, 0, 0, 0)), ""),
               ("AFn", g.vector4("StageAlphaFunctions", (0, 0, 0, 0)), ""),
               ("Count", g.scalar("StageCount", 1.0), ""), ("Tint", g.vector("Tint"), ""),
               ("Premultiply", g.scalar("Premultiply", 0.0), ""),
               ("Blend", g.scalar("BlendFunction", 0.0), ""), ("FadeMode", g.scalar("FadeMode", 0.0), ""),
               ("ChicagoFlags", chicago_flags, ""), ("VertexN", vertex_n, ""), ("Cam", cam, "")]
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
    if device:
        device_offset(g, m)
    else:
        sky_offset(g, m)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# shader_transparent_water (docs/ce_map_conversion.md, "Water"), as CE's
# renderer draws it:
# - the ripple normal: up to four ripple layers, ripple k at
#   repeats_k * uv_b + t * velocity_k (cos, sin)(angle_k) + offset_k on the
#   surface's bump UV uv_b = ripple scale * uv + t * velocity (cos, sin)(angle),
#   blended by contribution (pairs 0+1 and 2+3, then the pairs by their sums)
#   and faded towards flat by mip level (ripple mipmap levels, fade factor,
#   detail bias);
# - the reflection: the cube map along the eye reflected about that normal,
#   lerp(c^8, c, tint), the tint between the parallel and perpendicular tint
#   by how squarely the camera looks down on the water (once per draw in CE:
#   the camera's forward vector against the surface normal);
# - flag 0 (base map alpha modulates reflection): times base alpha and the
#   brightness between parallel and perpendicular by the view angle;
# - flag 2 (atmospheric fog): times 1 - fog.
# It is added into the frame (sky water replaces it: M_CE_WaterSky). Flag 1
# (base map colour modulates background) is a pass of its own before this
# one: M_CE_WaterBackground, on a copy of the surface (merge_ce_scene.py).
WATER_UV_CODE = r"""
float2 ub = UV * Global.z + Time * Global.y * float2(cos(Global.x), sin(Global.x));
return ub * Ripple.w + Time * Ripple.z * float2(cos(Ripple.y), sin(Ripple.y)) + Offset.xy;
"""

WATER_NORMAL_CODE = r"""
float4 c = float4(R0c.x, R1c.x, R2c.x, R3c.x);
if (c.x + c.y <= 0.0) c.y = 1.0;
if (c.z + c.w <= 0.0) c.w = 1.0;
float3 n0 = R0.rgb * 2.0 - 1.0, n1 = R1.rgb * 2.0 - 1.0, n2 = R2.rgb * 2.0 - 1.0, n3 = R3.rgb * 2.0 - 1.0;
float3 P = (c.x * n0 + c.y * n1) / (c.x + c.y);
float3 Q = (c.z * n2 + c.w * n3) / (c.z + c.w);
float wP = (c.z + c.w) / (c.x + c.y + c.z + c.w);
float3 n = lerp(P, Q, wP);
// The generated ripple map's mip level here, faded towards flat.
float2 ub = UV * Global.z;
float2 fp = max(abs(ddx(ub)), abs(ddy(ub))) * 128.0;
float levels = clamp(Mip.x, 1.0, 4.0);
float lod = clamp(log2(max(max(fp.x, fp.y), 1e-6)) - Mip.z, 0.0, levels - 1.0);
if (levels > 1.0) n = lerp(n, float3(0.0, 0.0, 1.0), lod / (levels - 1.0) * Mip.y);
return n * rsqrt(max(dot(n, n), 1e-8));
"""

WATER_REFLECT_CODE = r"""
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
float3 R = 2.0 * dot(N, E) * N - E;
return float3(R.x, -R.y, R.z);
"""

WATER_CODE = r"""
float3 Nv = normalize(VertexN);
float r = saturate(-dot(View.ViewForward, Nv));
float3 tint = lerp(ParaTint.rgb, PerpTint.rgb, r);
float3 c = Cube.rgb;
float3 c8 = c * c; c8 *= c8; c8 *= c8;
float3 frame = lerp(c8, c, tint);
int flags = (int)Flags;
if (flags & 1)
{
    float f = saturate(dot(Nv, normalize(Cam)));
    frame *= Base.a * lerp(ParaBrightness, PerpBrightness, f);
}
if ((flags & 4) && FogDensity > 0.0)
    frame *= 1.0 - FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
frame = max(frame, 0.0) / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return float4(lerp(hi, lo, step(frame, 0.04045)) * Exposure, 1.0);
"""

# Water flag 1, base map colour modulates background: the frame times the
# base map's colour (clamped UV), faded towards white by the fog with flag 2.
WATER_BACKGROUND_CODE = r"""
float3 k = Base.rgb;
if (((int)Flags & 4) && FogDensity > 0.0)
    k = lerp(k, 1.0.xxx, FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0)));
// A factor on the linear frame: CE multiplied the gamma-space one.
float3 lo = k / 12.92;
float3 hi = pow((k + 0.055) / 1.055, 2.4);
return lerp(hi, lo, step(k, 0.04045));
"""


def build_water(defaults, name="M_CE_Water", blend=unreal.BlendMode.BLEND_ADDITIVE):
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    uv0 = g.uv(0)
    time = g.node(unreal.MaterialExpressionTime)
    glob = g.vector4("RippleGlobal", (0, 0, 1, 0))
    samples, contribs = [], []
    for k in range(4):
        ripple = g.vector4(f"Ripple{k}", (0, 0, 0, 1))
        uv = g.custom(WATER_UV_CODE, [("UV", uv0, ""), ("Time", time, ""), ("Global", glob, ""),
                                      ("Ripple", ripple, ""), ("Offset", g.vector4(f"Ripple{k}Offset", (0, 0, 0, 0)), "")],
                      output=unreal.CustomMaterialOutputType.CMOT_FLOAT2, description=f"CE ripple {k} uv")
        samples.append(g.texture(f"RippleMap{k}", defaults["T_CE_Flat"], uv))
        contribs.append(ripple)
    inputs = [(f"R{k}", s, "RGBA") for k, s in enumerate(samples)]
    inputs += [(f"R{k}c", c, "") for k, c in enumerate(contribs)]
    inputs += [("UV", uv0, ""), ("Global", glob, ""), ("Mip", g.vector4("RippleMip", (1, 0, 0, 0)), "")]
    n = g.custom(WATER_NORMAL_CODE, inputs, description="CE ripple normal")
    nw = g.node(unreal.MaterialExpressionTransform, x=-800,
                transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(n, "", nw, "")
    cam = g.node(unreal.MaterialExpressionCameraVectorWS)
    direction = g.custom(WATER_REFLECT_CODE, [("Cam", cam, ""), ("N", nw, "")], description="CE water reflection")
    cube = g.cube("ReflectionCube", defaults["T_CE_BlackCube"], direction)
    # The base map is clamped: one map across the surface.
    clamped = g.custom("return saturate(UV);", [("UV", uv0, "")], output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                       description="CE water base uv")
    base = g.texture("Base", defaults["T_CE_White"], clamped)
    vertex_n = g.node(unreal.MaterialExpressionVertexNormalWS)
    inputs = [("Cam", cam, ""), ("VertexN", vertex_n, ""), ("Cube", cube, "RGB"), ("Base", base, "RGBA"),
              ("PerpBrightness", g.scalar("PerpBrightness", 0.3), ""),
              ("ParaBrightness", g.scalar("ParaBrightness", 1.0), ""),
              ("PerpTint", g.vector("PerpTint"), ""), ("ParaTint", g.vector("ParaTint"), ""),
              ("Flags", g.scalar("WaterFlags", 0.0), ""),
              ("Exposure", g.scalar("Exposure", 1.0), ""), ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), "")]
    inputs += fog_inputs(g)
    c = g.custom(WATER_CODE, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
                 description="CE shader_transparent_water")
    mel.connect_material_property(g.to_screen(g.mask(c, r=True, g=True, b=True)), "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    sky_offset(g, m)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


def build_water_background(defaults):
    m = fresh(ROOT, "M_CE_WaterBackground", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MODULATE)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    clamped = g.custom("return saturate(UV);", [("UV", g.uv(0), "")], output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                       description="CE water base uv")
    base = g.texture("Base", defaults["T_CE_White"], clamped)
    inputs = [("Base", base, "RGBA"), ("Flags", g.scalar("WaterFlags", 0.0), "")] + fog_inputs(g)
    c = g.custom(WATER_BACKGROUND_CODE, inputs, description="CE water background")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# shader_transparent_glass (docs/ce_map_conversion.md, "Glass"): three passes
# in CE's order, each a master of its own on a copy of the surface
# (merge_ce_scene.py `with_passes`):
# - tint (M_CE_GlassTint, multiply): the frame times background tint map x
#   tint colour, when either is set;
# - reflection (M_CE_GlassReflection, add): the cube map along the eye
#   reflected about the bump normal (bumped cube map) or the vertex normal
#   (flat; also a bumped type with no bump map or with "bump map is specular
#   mask"), lerp(c^8, c, tint) x brightness, tint and brightness between
#   parallel and perpendicular by x^2, x the normal against the camera's
#   forward vector; times the bump map's colour with "bump map is specular
#   mask";
# - diffuse (M_CE_GlassDiffuse, alpha blend): 2 x diffuse x detail x the
#   surface's light (its lightmap), alpha diffuse.a x detail.a.
# Fog fades each towards its blend's neutral value, as CE's per-vertex fade
# does. Flag bit 2 (two-sided) is a master variant.
GLASS_TINT_CODE = r"""
float3 k = Tint.rgb * TintColor.rgb;
if (FogDensity > 0.0)
    k = lerp(k, 1.0.xxx, FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0)));
float3 lo = k / 12.92;
float3 hi = pow((k + 0.055) / 1.055, 2.4);
return lerp(hi, lo, step(k, 0.04045));
"""

GLASS_DIRECTION_CODE = r"""
float3 E = Cam * rsqrt(max(dot(Cam, Cam), 1e-8));
float3 N = Type < 0.5 ? normalize(BumpN) : normalize(VertexN);
float3 R = 2.0 * dot(N, E) * N - E;
return float3(R.x, -R.y, R.z);
"""

GLASS_REFLECTION_CODE = r"""
float3 N = Type < 0.5 ? normalize(BumpN) : normalize(VertexN);
float x = saturate(dot(N, -View.ViewForward));
x *= x;
float3 tint = lerp(ParaTint.rgb, PerpTint.rgb, x);
float bright = lerp(ParaBrightness, PerpBrightness, x);
float3 c = Cube.rgb;
float3 c8 = c * c; c8 *= c8; c8 *= c8;
float3 frame = lerp(c8, c, tint) * bright;
if ((int)Flags & 8) frame *= Bump.rgb;
if (FogDensity > 0.0)
    frame *= 1.0 - FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
frame = max(frame, 0.0) / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return lerp(hi, lo, step(frame, 0.04045)) * Exposure;
"""

GLASS_DIFFUSE_CODE = r"""
float3 light = HasLightmap > 0.5 ? Lightmap.rgb : 1.0.xxx;
float3 frame = saturate(2.0 * Diffuse.rgb * Detail.rgb * light);
float alpha = Diffuse.a * Detail.a;
if (FogDensity > 0.0)
    alpha *= 1.0 - FogDensity * saturate((Depth - FogStart) / max(FogOpaque - FogStart, 1.0));
frame = frame / DisplayGain;
float3 lo = frame / 12.92;
float3 hi = pow((frame + 0.055) / 1.055, 2.4);
return float4(lerp(hi, lo, step(frame, 0.04045)) * Exposure, alpha);
"""


def glass_material(name, blend, two_sided):
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("two_sided", two_sided)
    m.set_editor_property("used_with_static_lighting", False)
    return m, Graph(m)


def build_glass(defaults, two_sided):
    side = "TwoSided" if two_sided else ""
    white, grey, flat = defaults["T_CE_White"], defaults["T_CE_Grey"], defaults["T_CE_Flat"]

    m, g = glass_material(f"M_CE_GlassTint{side}", unreal.BlendMode.BLEND_MODULATE, two_sided)
    tint = g.texture("TintMap", white, g.uv(0, "TintScale"))
    c = g.custom(GLASS_TINT_CODE, [("Tint", tint, "RGBA"), ("TintColor", g.vector("TintColor"), "")] + fog_inputs(g),
                 description="CE glass tint")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)

    m, g = glass_material(f"M_CE_GlassReflection{side}", unreal.BlendMode.BLEND_ADDITIVE, two_sided)
    bump = g.texture("Bump", flat, g.uv(0, "BumpScale"))
    flags = g.scalar("GlassFlags", 0.0)
    bump_n = g.custom(NORMAL_CODE, [("Bump", bump, "RGBA"), ("HasBump", g.scalar("HasBump", 0.0), ""),
                                    ("BumpIsSpecMask", g.node(unreal.MaterialExpressionConstant, x=-1900, r=0.0), "")],
                      description="CE bump normal")
    bump_w = g.node(unreal.MaterialExpressionTransform, x=-800,
                    transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                    transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(bump_n, "", bump_w, "")
    cam = g.node(unreal.MaterialExpressionCameraVectorWS)
    vertex_n = g.node(unreal.MaterialExpressionVertexNormalWS)
    rtype = g.scalar("ReflectionType", 1.0)
    direction = g.custom(GLASS_DIRECTION_CODE, [("Cam", cam, ""), ("BumpN", bump_w, ""), ("VertexN", vertex_n, ""),
                                                ("Type", rtype, "")], description="CE glass reflection vector")
    cube = g.cube("ReflectionCube", defaults["T_CE_BlackCube"], direction)
    inputs = [("Cube", cube, "RGB"), ("Bump", bump, "RGBA"), ("BumpN", bump_w, ""), ("VertexN", vertex_n, ""),
              ("Type", rtype, ""), ("Flags", flags, ""),
              ("PerpBrightness", g.scalar("PerpBrightness", 0.0), ""),
              ("ParaBrightness", g.scalar("ParaBrightness", 0.0), ""),
              ("PerpTint", g.vector("PerpTint"), ""), ("ParaTint", g.vector("ParaTint"), ""),
              ("Exposure", g.scalar("Exposure", 1.0), ""),
              ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), "")] + fog_inputs(g)
    c = g.custom(GLASS_REFLECTION_CODE, inputs, description="CE glass reflection")
    mel.connect_material_property(g.to_screen(c), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)

    m, g = glass_material(f"M_CE_GlassDiffuse{side}", unreal.BlendMode.BLEND_TRANSLUCENT, two_sided)
    diffuse = g.texture("Diffuse", white, g.uv(0, "DiffuseScale"))
    detail = g.texture("Detail", grey, g.uv(0, "DetailScale"))
    lightmap = g.texture("Lightmap", white, g.uv(1))
    inputs = [("Diffuse", diffuse, "RGBA"), ("Detail", detail, "RGBA"), ("Lightmap", lightmap, "RGBA"),
              ("HasLightmap", g.scalar("HasLightmap", 0.0), ""),
              ("Exposure", g.scalar("Exposure", 1.0), ""),
              ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), "")] + fog_inputs(g)
    c = g.custom(GLASS_DIFFUSE_CODE, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
                 description="CE glass diffuse")
    mel.connect_material_property(g.to_screen(g.mask(c, r=True, g=True, b=True)), "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(g.mask(c, a=True), "", unreal.MaterialProperty.MP_OPACITY)
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
    folders = [ROOT.rsplit("/", 1)[-1]] if TRIAL_ROOT else LABELLED
    for folder in folders:
        label = fresh(f"/Game/MJOLNIR/{folder}", f"PAL_MJOLNIR_{folder}", unreal.PrimaryAssetLabel,
                      unreal.DataAssetFactory())
        rules = label.get_editor_property("rules")
        rules.set_editor_property("chunk_id", CHUNK)
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
# shader_model's two-sided flag on an opaque (not alpha-tested) model.
build_environment("M_CE_EnvironmentTwoSided", False, defaults, two_sided=True)
build_sun_light(defaults)
build_linear_copy(defaults)

LAND_PBR_CODE = r"""
// The ground as Campaign Evolved's B30 draws it: the game's Megascans
// surfaces, lit by Unreal (no CE lightmap). Layers: the flat sand, rippled
// sand in a band above the sea, ground grass where CE's base map says grass
// (its alpha: 1 sand, 0 grass), the wet edge of the sea. Each surface is
// read twice, the second turned and scaled, and the two blended by a slow
// noise so no tile repeats. Footprints (FootRT) shade as dents: their slope
// bends the normal, their depth occludes.
#define LP_HASH(p) frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453)
#define LP_NOISE(p) lerp(lerp(LP_HASH(floor(p)), LP_HASH(floor(p) + float2(1, 0)), smoothstep(0, 1, frac(p).x)), \
    lerp(LP_HASH(floor(p) + float2(0, 1)), LP_HASH(floor(p) + float2(1, 1)), smoothstep(0, 1, frac(p).x)), smoothstep(0, 1, frac(p).y))
#define LP_ROT(uv, k) (float2((uv).x * 0.8 - (uv).y * 0.6, (uv).x * 0.6 + (uv).y * 0.8) * (k) + 0.31)
#define LP_NRM(T, S, a, b, w) (lerp(Texture2DSample(T, S, a).rg, Texture2DSample(T, S, b).rg, w) * 2.0 - 1.0)

float2 luv = (W.xy - LandRect.xy) / LandRect.zw;
// The landscape reads the bakes over its rectangle; the terrain mesh
// (MeshUV) its own base map and lightmap page by its own UVs, which hold the
// right layer where a plateau overhangs the beach (the bakes hold the lower).
float4 ce = Texture2DSample(Base, BaseSampler, MeshUV > 0.5 ? TC0 : luv);
if (Plain > 0.5) ce = float4(0.533, 0.533, 0.533, 1.0); // plain sand, no tint
float cellNoise = LP_NOISE(W.xy / max(Tiles.w, 1.0));
float w = smoothstep(0.25, 0.75, cellNoise);

// Layer weights.
float grass = smoothstep(Mix.x, Mix.y, 1.0 - ce.a + (LP_NOISE(W.xy / 180.0) - 0.5) * 0.25);
// Ground CE paints green is grass too, whatever its alpha says (Death
// Island's mossy boulder top, its banks): green over red and blue, as
// scatter_foliage.py's "green" rule reads the base map.
grass = max(grass, smoothstep(0.03, 0.10, ce.g - max(ce.r, ce.b)));
// Banks are grass (Slope: normal z where grass starts, where it is all
// grass, strength): CE's base map split a steep bank into sand and grass
// stripes, smeared down the slope by the world mapping; the original drew
// it green, and sand does not lie on a 45 degree bank.
// The normal's z wanders by a two-scale noise (metres, then a hand
// across): the landscape's normal is linear over each 1 m triangle, so a
// plain threshold cut the bank's grass along triangle edges in a sawtooth
// (Blood Gulch, 2026-10-12).
float rag2 = LP_NOISE(W.xy / 160.0 + 1.7) * 0.65 + LP_NOISE(W.xy / 45.0 + 6.2) * 0.35 - 0.5;
float bankZ = normalize(Nw).z + rag2 * 0.14;
grass = max(grass, smoothstep(Slope.x, Slope.y, bankZ) * Slope.z);
float h = W.z - Sea.x; // cm over the sea
float hasSea = Sea.w > 0.5 ? 1.0 : 0.0;
float rtop = Sea.y * (0.75 + 0.5 * LP_NOISE(W.xy / 900.0 + 3.1));
float ripple = hasSea * (1.0 - grass) * (1.0 - smoothstep(rtop * 0.7, rtop, h));
float wet = hasSea * (1.0 - smoothstep(0.0, Sea.z, h));
// Inland the sand turns to earth (Inland: from, to cm over the sea, ragged
// cm, strength): a beach is sand by the water and packed dirt up the hill;
// a map with no sea (Blood Gulch) is earth throughout. The edge is ragged by
// a noise metres across, so the change wanders as a real one does.
float inland = 0.0;
if (Inland.w > 0.0)
{
    float wander = (LP_NOISE(W.xy / 1100.0 + 2.7) * 0.7 + LP_NOISE(W.xy / 260.0 + 8.3) * 0.3 - 0.5) * Inland.z;
    inland = (hasSea > 0.5 ? smoothstep(Inland.x, Inland.y, h + wander) : 1.0) * Inland.w * (1.0 - ripple);
}

// Depth (Par: sand depth cm, footprint depth cm, fade distance cm, steps):
// the sand's and the ripples' displacement maps and the footprints as one
// height field, the view ray marched down through it (parallax occlusion),
// so ripples and prints stand in relief at a low angle. In world XY, the
// landscape's tangent frame; near the camera only.
float2 P = W.xy;
PDO = 0.0;
float parD = (Par.x + Par.y) * (1.0 - grass) * (1.0 - smoothstep(Par.z * 0.5, Par.z, length(Cam - W)))
            * (1.0 - 0.7 * inland); // packed earth stands in less relief than sand
if (parD > 0.05 && Par.w >= 1.0)
{
    float3 V = normalize(Cam - W);
    float2 ray = -V.xy / max(V.z, 0.2) * parD; // xy travel down the whole depth
    float2 s0 = W.xy / max(Tiles.x, 1.0), s1 = LP_ROT(s0, 0.43);
    float2 r0 = W.xy / max(Tiles.y, 1.0), r1 = LP_ROT(r0, 0.61);
    float2 s0x = ddx(s0), s0y = ddy(s0), s1x = ddx(s1), s1y = ddy(s1);
    float2 r0x = ddx(r0), r0y = ddy(r0), r1x = ddx(r1), r1y = ddy(r1);
    float footOn = Foot.x > 0.0 ? 1.0 : 0.0;
    // The prints softened (four taps 2.5 texels out): the game's boot map has
    // a sharp outline, which the ray stood up as a wall; B30's sink in from
    // a soft edge.
    float2 fb = Foot.z * 2.5;
    #define LP_FOOT(f) (0.25 * (Texture2DSampleLevel(FootRT, FootRTSampler, (f) + fb, 0).r + Texture2DSampleLevel(FootRT, FootRTSampler, (f) - fb, 0).r + Texture2DSampleLevel(FootRT, FootRTSampler, (f) + float2(fb.x, -fb.y), 0).r + Texture2DSampleLevel(FootRT, FootRTSampler, (f) + float2(-fb.x, fb.y), 0).r))
    #define LP_H(q) ((lerp(lerp(Texture2DSampleGrad(SandO, SandOSampler, s0 + (q) / max(Tiles.x, 1.0), s0x, s0y).b,         Texture2DSampleGrad(SandO, SandOSampler, s1 + LP_ROT((q) / max(Tiles.x, 1.0), 0.43) - 0.31, s1x, s1y).b, w),         lerp(Texture2DSampleGrad(RipO, RipOSampler, r0 + (q) / max(Tiles.y, 1.0), r0x, r0y).b,         Texture2DSampleGrad(RipO, RipOSampler, r1 + LP_ROT((q) / max(Tiles.y, 1.0), 0.61) - 0.31, r1x, r1y).b, w), ripple) * Par.x         + (1.0 - footOn * LP_FOOT((W.xy + (q) - FootRect.xy) / FootRect.zw + 0.5)) * Par.y)         / max(Par.x + Par.y, 1e-3))
    int steps = (int)min(Par.w, 32.0);
    float layer = 1.0 / steps;
    float cur = 1.0, hgt = LP_H(float2(0.0, 0.0)), prevH = hgt, prevC = 1.0;
    float2 off = 0.0;
    [loop] for (int i = 0; i < steps && hgt < cur; i++)
    {
        prevH = hgt; prevC = cur;
        cur -= layer;
        off = ray * (1.0 - cur);
        hgt = LP_H(off);
    }
    // Between the last two steps, where the ray met the surface.
    float a = prevC - prevH, b = cur - hgt;
    float t = saturate(a / max(a - b, 1e-4));
    float sunk = 1.0 - lerp(prevC, cur, t);
    P = W.xy + ray * sunk;
    // The depth the sand is drawn at (pixel depth offset, view depth): rocks
    // and boots meet the sand where it shows, not on the flat surface above
    // it, which cut them off at a plane they seemed to float on.
    PDO = sunk * parD / max(V.z, 0.2) * max(dot(-V, View.ViewForward), 0.0);
    #undef LP_H
    #undef LP_FOOT
}

// Sand, flat and rippled.
float2 su = P / max(Tiles.x, 1.0); float2 su2 = LP_ROT(su, 0.43);
float3 sandA = lerp(Texture2DSample(SandD, SandDSampler, su).rgb, Texture2DSample(SandD, SandDSampler, su2).rgb, w);
float2 sandN = LP_NRM(SandN, SandNSampler, su, su2, w);
float4 sandO = lerp(Texture2DSample(SandO, SandOSampler, su), Texture2DSample(SandO, SandOSampler, su2), w);
// A second sand (B30's darker beach sand) over patches tens of metres
// across, and the grain's contrast raised (Look.y): at dusk the light is
// flat and the sand's own colour has to carry it.
float2 bu = P / max(Tiles.x * 1.3, 1.0) + 0.43;
float bw = smoothstep(0.3, 0.7, LP_NOISE(W.xy / 2400.0 + 5.3)) * Look.w;
float3 sandB = Texture2DSample(SandBD, SandBDSampler, bu).rgb;
float2 sandBN = Texture2DSample(SandBN, SandBNSampler, bu).rg * 2.0 - 1.0;
float3 sandMean = Texture2DSampleLevel(SandD, SandDSampler, float2(0.5, 0.5), 13.0).rgb;
sandA = max(sandMean + (sandA - sandMean) * Look.y, 0.0);
sandA = lerp(sandA, sandB, bw) * SandTint.rgb;
sandN = lerp(sandN, sandBN, bw);
// Far sand (Macro: strength, far start and end cm, scale): the same sand
// read Macro.w times larger, its colour against its mean over the whole
// beach (light and dark drifts tens of metres across), and in the distance
// its normal in place of the fine one, which mips away to nothing there.
float farW = smoothstep(Macro.y, Macro.z, length(Cam - W));
if (Macro.x > 0.0)
{
    float2 mu = P / max(Tiles.x * Macro.w, 1.0) + 0.27;
    float2 mu2 = LP_ROT(mu, 0.37);
    float3 mA = lerp(Texture2DSample(SandD, SandDSampler, mu).rgb, Texture2DSample(SandD, SandDSampler, mu2).rgb, 0.5);
    float3 rel = clamp(mA / max(sandMean, 1e-3), 0.6, 1.5);
    sandA *= lerp(1.0.xxx, rel, Macro.x * (0.35 + 0.65 * farW));
    sandN = lerp(sandN, LP_NRM(SandN, SandNSampler, mu, mu2, 0.5) * 1.5, farW * Macro.x);
}
float2 ru = P / max(Tiles.y, 1.0); float2 ru2 = LP_ROT(ru, 0.61);
float3 ripA = lerp(Texture2DSample(RipD, RipDSampler, ru).rgb, Texture2DSample(RipD, RipDSampler, ru2).rgb, w) * SandTint.rgb;
float2 ripN = LP_NRM(RipN, RipNSampler, ru, ru2, w);
float4 ripO = lerp(Texture2DSample(RipO, RipOSampler, ru), Texture2DSample(RipO, RipOSampler, ru2), w);
// Earth inland (DirtD: packed earth; MidD: sandy gravel, in the band where
// sand gives way and in patches; GravD: gravel in patches; Dirt: the sandy
// patches' share, the gravel's share, the patch cell cm, sandy share inland).
// Sampled only where there is earth.
float3 dirtA = 0.0; float2 dirtN = 0.0; float4 dirtO = float4(1.0, 0.8, 0.5, 0.0);
float dirtW = inland;
[branch] if (inland > 0.002)
{
    float2 du = P / max(Tiles.x * 1.6, 1.0) + 0.17; float2 du2 = LP_ROT(du, 0.47);
    dirtA = lerp(Texture2DSample(DirtD, DirtDSampler, du).rgb, Texture2DSample(DirtD, DirtDSampler, du2).rgb, w);
    dirtN = LP_NRM(DirtN, DirtNSampler, du, du2, w);
    dirtO = lerp(Texture2DSample(DirtO, DirtOSampler, du), Texture2DSample(DirtO, DirtOSampler, du2), w);
    // Sandy gravel: peaking where sand turns to earth, and in patches.
    float band = saturate(inland * (1.0 - inland) * 4.0) * Dirt.x;
    float pn = LP_NOISE(W.xy / max(Dirt.z, 1.0) + 4.4);
    float midW = max(band, smoothstep(0.55, 0.75, pn) * Dirt.w * inland);
    if (midW > 0.002)
    {
        float2 mu = P / max(Tiles.x * 1.2, 1.0) + 0.61;
        dirtA = lerp(dirtA, Texture2DSample(MidD, MidDSampler, mu).rgb, midW);
        dirtN = lerp(dirtN, Texture2DSample(MidN, MidNSampler, mu).rg * 2.0 - 1.0, midW);
        dirtO = lerp(dirtO, Texture2DSample(MidO, MidOSampler, mu), midW);
    }
    // Gravel over the earth in patches of their own.
    float gn = LP_NOISE(W.xy / max(Dirt.z * 0.7, 1.0) + 9.1);
    float gravW = smoothstep(0.6, 0.78, gn) * Dirt.y;
    if (gravW > 0.002)
    {
        float2 vu = P / max(Tiles.x * 0.9, 1.0) + 0.29;
        dirtA = lerp(dirtA, Texture2DSample(GravD, GravDSampler, vu).rgb, gravW);
        dirtN = lerp(dirtN, Texture2DSample(GravN, GravNSampler, vu).rg * 2.0 - 1.0, gravW);
        dirtO = lerp(dirtO, Texture2DSample(GravO, GravOSampler, vu), gravW);
    }
    dirtA *= DirtTint.rgb;
}
// Grass ground.
float2 gu = P / max(Tiles.z, 1.0); float2 gu2 = LP_ROT(gu, 0.53);
float3 grA = lerp(Texture2DSample(GrassD, GrassDSampler, gu).rgb, Texture2DSample(GrassD, GrassDSampler, gu2).rgb, w) * GrassTint.rgb;
float2 grN = LP_NRM(GrassN, GrassNSampler, gu, gu2, w);
float4 grO = lerp(Texture2DSample(GrassO, GrassOSampler, gu), Texture2DSample(GrassO, GrassOSampler, gu2), w);

// Where the ground meets a wall (the edge map, edge_bake): at a lip the
// grass wears through to earth in ragged patches; at a foot the sand is
// damper and darker and shaded where it meets the rock.
float lip = 0.0, foot = 0.0;
if (EdgeLook.w > 0.5)
{
    float4 ed = Edge.SampleLevel(EdgeSampler, luv, 0);
    // Only on ground that lies flat: on a bank or a boulder's top (the mesh's
    // ground beside a lip) the wear striped the grass with sand.
    float flat = smoothstep(0.85, 0.95, bankZ);
    lip = ed.g * flat; foot = ed.b;
}
grass *= 1.0 - lip * EdgeLook.x * smoothstep(0.25, 0.75, LP_NOISE(W.xy / 120.0 + 7.1));
// (Earth's ORHG: occlusion, roughness, height; the sand's ORDp alike.)
float3 albedo = lerp(lerp(lerp(sandA, ripA, ripple), dirtA, dirtW), grA, grass);
float2 nxy = lerp(lerp(lerp(sandN, ripN, ripple), dirtN, dirtW), grN, grass);
float rough = lerp(lerp(lerp(sandO.g, ripO.g, ripple), dirtO.g, dirtW), grO.b, grass);
float ao = lerp(lerp(lerp(sandO.r, ripO.r, ripple), dirtO.r, dirtW), grO.r, grass);

// CE's own colour, a little: the map's paths and patches.
float3 cel = pow(max(ce.rgb, 1e-3), 2.2);
float cell = max(dot(cel, float3(0.2126, 0.7152, 0.0722)), 1e-3);
// On grass no more than 1.15x: CE's pale path paint bleeding into a grass
// bank lifted the grass ground nearly white (Blood Gulch, 2026-10-12).
albedo *= lerp(1.0.xxx, clamp(cel / max(Mix.w, 1e-3), 0.5, lerp(1.8, 1.15, grass)), Mix.z);

// CE's baked light as occlusion (Look.z): the lightmap relative to its
// sunlit level, softened; it keeps the shade CE's lighting gave (trees,
// cliff feet) where Unreal's sky light alone is flat.
if (Look.z > 0.0 && LMLevels.y > LMLevels.x)
{
    float lm = dot(Texture2DSample(LM, LMSampler, MeshUV > 0.5 ? TC1 : luv).rgb, float3(0.2126, 0.7152, 0.0722));
    float occ = saturate((lm - LMLevels.x * 0.5) / max(LMLevels.y - LMLevels.x * 0.5, 1e-3));
    ao *= lerp(1.0, 0.35 + 0.65 * occ, Look.z);
}
nxy *= Look.x;
albedo *= lerp(1.0.xxx, float3(0.8, 0.68, 0.55), lip * EdgeLook.y * (1.0 - grass));
albedo *= 1.0 - foot * 0.15;
rough = lerp(rough, rough * 0.85, foot);
ao *= 1.0 - foot * EdgeLook.z;

// The wet edge: darker and glossier.
albedo *= lerp(1.0, Sea.z > 0.0 ? WetLook.x : 1.0, wet);
rough = lerp(rough, WetLook.y, wet);

// Footprints.
if (Foot.x > 0.0)
{
    float2 fuv = (P - FootRect.xy) / FootRect.zw + 0.5;
    float edge = saturate(min(min(fuv.x, 1.0 - fuv.x), min(fuv.y, 1.0 - fuv.y)) * 20.0);
    if (edge > 0.0)
    {
        // Slopes over 3 texels: as soft as the parallax's prints.
        float t = Foot.z * 3.0;
        float d = Texture2DSampleLevel(FootRT, FootRTSampler, fuv, 0).r;
        float dl = Texture2DSampleLevel(FootRT, FootRTSampler, fuv - float2(t, 0.0), 0).r;
        float dr = Texture2DSampleLevel(FootRT, FootRTSampler, fuv + float2(t, 0.0), 0).r;
        float db = Texture2DSampleLevel(FootRT, FootRTSampler, fuv - float2(0.0, t), 0).r;
        float dt = Texture2DSampleLevel(FootRT, FootRTSampler, fuv + float2(0.0, t), 0).r;
        float k = Foot.x * edge;
        nxy += float2(dr - dl, dt - db) * Foot.y * k;
        ao *= 1.0 - Foot.w * d * k;
        rough = lerp(rough, rough * 0.85, d * k);
    }
}

Normal = normalize(float3(nxy.x, -nxy.y, 1.0));
Emissive = 0.0;

// Steep ground is rock (Steep: normal z where it is all rock, where it
// starts, tile cm, strength): a beach shader CE ran up a wall (Death
// Island's) drew sand on it, black in the shade. The cliffs' rock
// (M_CE_CliffPBR's grain), from three sides, with their fill light.
float3 nw = normalize(Nw);
if (Steep.w > 0.0 && nw.z < Steep.y)
{
    float rag = LP_NOISE(float2(W.x + W.y, W.z) / 90.0);
    float st = smoothstep(Steep.y, Steep.x, nw.z + (rag - 0.5) * 0.25) * Steep.w;
    float3 sg = float3(nw.x < 0 ? -1.0 : 1.0, nw.y < 0 ? -1.0 : 1.0, nw.z < 0 ? -1.0 : 1.0);
    float3 bw = pow(abs(nw), 4.0);
    bw /= max(bw.x + bw.y + bw.z, 1e-4);
    float2 ux = float2(W.z * sg.x, W.y) / Steep.z, uy = float2(W.x * sg.y, W.z) / Steep.z, uz = float2(-W.x * sg.z, W.y) / Steep.z;
    float3 rA = Texture2DSample(RockD, RockDSampler, ux).rgb * bw.x + Texture2DSample(RockD, RockDSampler, uy).rgb * bw.y
              + Texture2DSample(RockD, RockDSampler, uz).rgb * bw.z;
    float3 tx = float3(Texture2DSample(RockN, RockNSampler, ux).rg * 2.0 - 1.0, 1.0);
    float3 ty = float3(Texture2DSample(RockN, RockNSampler, uy).rg * 2.0 - 1.0, 1.0);
    float3 tz = float3(Texture2DSample(RockN, RockNSampler, uz).rg * 2.0 - 1.0, 1.0);
    tx = float3(tx.xy + nw.zy, abs(nw.x) * tx.z);
    ty = float3(ty.xy + nw.xz, abs(nw.y) * ty.z);
    tz = float3(tz.xy + nw.xy, abs(nw.z) * tz.z);
    tx.z *= sg.x; ty.z *= sg.y; tz.z *= sg.z;
    float3 rN = normalize(tx.zyx * bw.x + ty.xzy * bw.y + tz.xyz * bw.z);
    // World to the surface's tangent space (TangentToWorld is orthonormal).
    float3 rT = normalize(mul(Parameters.TangentToWorld, rN));
    float3 rMean = Texture2DSampleLevel(RockD, RockDSampler, float2(0.5, 0.5), 13.0).rgb;
    float3 rock = rMean * RockTint.rgb * max(1.0 + (rA / max(rMean, 1e-3) - 1.0) * 1.3, 0.0);
    // In CE's colour as the ground around it: grey rock on Blood Gulch's red
    // banks drew pale, nearly white patches (2026-10-12).
    rock *= lerp(1.0.xxx, clamp(cel / max(Mix.w, 1e-3), 0.5, 1.5), Mix.z);
    albedo = lerp(albedo, rock, st);
    Normal = normalize(lerp(Normal, rT, st));
    rough = lerp(rough, 0.8, st);
}
// The fill on every face that leans (the sand's bounce): under an
// overhanging lip, the sand between the rock's ragged edge took none and
// went black in the shadow.
// Flat ground takes a share of it too (Slope.w): a cliff's shadow on the
// sand was lit by the sky alone, CE's deep blue, and drew a navy band.
{
    float lean = Steep.w > 0.0 ? max(saturate((0.95 - nw.z) * 2.0), 0.0) : 0.0;
    float share = max(lean * (0.75 - 0.35 * nw.z), Slope.w);
    Emissive = max(albedo, 0.0) * Fill.rgb * Fill.a * saturate(ao) * share;
}

// Grass is a diffuse surface: its ORHG roughness (about 0.7) still drew a
// sheen at Blood Gulch's low sun, the turf near white from across the
// valley (2026-10-12). Earth and sand keep their own.
Rough = saturate(lerp(rough, max(rough, 0.92), grass));
// Specular: grass all but matte (a slope lit from behind it by a low sun
// still drew a white sheen at the engine's 0.5, Blood Gulch, 2026-10-12);
// earth and sand a little.
// (At 0 Unreal's Fresnel drops its grazing term too: saturate(50 x F0).)
Spec = lerp(0.3, 0.0, grass);
AO = saturate(ao);
return max(albedo, 0.0);
#undef LP_HASH
#undef LP_NOISE
#undef LP_ROT
#undef LP_NRM
"""


GROUND_CUT_CODE = r"""
// The terrain mesh's ground under a landscape: only the landscape's holes
// (its hole mask, a texel a vertex), so the two meet in one look.
float2 uv = (W.xy - R.xy) / R.zw;
if (any(uv < 0.0) || any(uv > 1.0)) return 1.0;
// Grown by Grow texels (the mask's most over a 3 x 3 spread): the mesh runs
// under the landscape's edge a metre or two, so a low view past that edge
// meets mesh, not the void under the landscape. At 1 quad the landscape's
// lift (8 cm) left a see-through seam at a base's door (Blood Gulch,
// 2026-10-12).
float2 c = (uv * (N - 1.0) + 0.5) / N;
float g = Grow / N;
float h = 0.0;
[unroll] for (int i = -1; i <= 1; i++)
    [unroll] for (int j = -1; j <= 1; j++)
        h = max(h, Texture2DSampleLevel(Mask, MaskSampler, c + float2(i, j) * g, 0).r);
return saturate((h - Edge) * 100.0);
"""


def build_landscape_pbr(defaults, name="M_CE_LandscapePBR", land=True):
    """M_CE_LandscapePBR: a converted map's landscape drawn as B30's beach is
    (LAND_PBR_CODE): Unreal-lit Megascans layers, masked by the landscape's
    holes. MJOLNIRLevelLoader sets every texture (the game's own, which this
    project does not have) and the layer and sea parameters at runtime.
    land=False (M_CE_GroundPBR): the same ground for the terrain mesh's ground
    slots, drawn only in the landscape's holes."""
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("opacity_mask_clip_value", 0.5)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    white, grey, flat = defaults["T_CE_White"], defaults["T_CE_Grey"], defaults["T_CE_Flat"]

    def tex(name, default, sampler):
        return (name, g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name=name,
                             texture=default, sampler_type=sampler), "")

    colour, normal, linear = (unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
                              unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
                              unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    albedo_default = unreal.load_asset("/Engine/EngineResources/DefaultTexture")
    normal_default = unreal.load_asset("/Engine/EngineMaterials/DefaultNormal")
    edge_tex = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="LandEdge",
                      texture=white, sampler_type=linear)
    edge_tex.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS)
    rock_d = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="RockD",
                    texture=albedo_default, sampler_type=colour)
    rock_n = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="RockN",
                    texture=normal_default, sampler_type=normal)
    for t in (rock_d, rock_n):
        t.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
    inputs = [
        ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
        tex("Base", white, linear),
        ("LandRect", g.vector4("LandRect", (0.0, 0.0, 50400.0, 50400.0)), ""),
        tex("SandD", albedo_default, colour), tex("SandN", normal_default, normal), tex("SandO", white, linear),
        tex("RipD", albedo_default, colour), tex("RipN", normal_default, normal), tex("RipO", white, linear),
        tex("GrassD", albedo_default, colour), tex("GrassN", normal_default, normal), tex("GrassO", white, linear),
        ("GrassTint", g.vector4("GrassTint", (1.0, 1.0, 1.0, 1.0)), ""),
        # Tiles: cm a tile of sand, ripples, grass; the anti-tiling noise's cell.
        ("Tiles", g.vector4("LandTiles", (250.0, 250.0, 300.0, 700.0)), ""),
        # Sea: its height (cm), the ripple band and wet band (cm over it), has sea.
        ("Sea", g.vector4("LandSea", (0.0, 150.0, 40.0, 0.0)), ""),
        # Mix: grass share edges (lo, hi), CE colour strength, CE colour's mean.
        ("Mix", g.vector4("LandMix", (0.35, 0.65, 0.25, 0.25)), ""),
        ("WetLook", g.vector4("LandWet", (0.6, 0.35, 0.0, 0.0)), ""),
        tex("SandBD", albedo_default, colour), tex("SandBN", normal_default, normal),
        # Earth inland (LAND_PBR_CODE: Inland, Dirt): packed earth, sandy
        # gravel, gravel; off while Inland.w is 0.
        tex("DirtD", albedo_default, colour), tex("DirtN", normal_default, normal), tex("DirtO", white, linear),
        tex("MidD", albedo_default, colour), tex("MidN", normal_default, normal), tex("MidO", white, linear),
        tex("GravD", albedo_default, colour), tex("GravN", normal_default, normal), tex("GravO", white, linear),
        ("Inland", g.vector4("LandInland", (250.0, 700.0, 300.0, 0.0)), ""),
        ("Dirt", g.vector4("LandDirt", (0.8, 0.35, 1800.0, 0.3)), ""),
        ("DirtTint", g.vector4("DirtTint", (1.0, 1.0, 1.0, 1.0)), ""),
        ("SandTint", g.vector4("SandTint", (1.0, 1.0, 1.0, 1.0)), ""),
        # Look: normal strength, grain contrast, CE shading as occlusion, second sand.
        ("Look", g.vector4("LandLook", (1.5, 1.6, 0.6, 0.7)), ""),
        tex("LM", white, linear),
        # LMLevels: the lightmap's shadow and sunlit levels (the loader's LightmapSun).
        ("LMLevels", g.vector4("LandLMLevels", (0.0, 0.0, 0.0, 0.0)), ""),
        ("TC0", g.uv(0), ""), ("TC1", g.uv(1), ""),
        ("MeshUV", g.scalar("MeshUV", 0.0), ""), ("Plain", g.scalar("PlainSand", 0.0), ""),
        tex("FootRT", grey, linear),
        ("FootRect", g.vector4("FootRect", (0.0, 0.0, 4096.0, 4096.0)), ""),
        # Foot: strength, relief, texel, occlusion.
        ("Foot", g.vector4("FootParams", (0.0, 4.0, 1.0 / 4096.0, 0.6)), ""),
        ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS, x=-2000), ""),
        # Par: parallax depth of the sand (cm), of the footprints (cm), the
        # distance it fades out by (cm), ray steps; 0 depth is off.
        ("Par", g.vector4("LandParallax", (0.0, 0.0, 2500.0, 12.0)), ""),
        # Macro: far sand's strength, where it takes over (cm from, to), scale.
        ("Macro", g.vector4("LandMacro", (0.0, 1500.0, 6000.0, 9.0)), ""),
        # The edge map (edge_bake) over LandRect, by the shared clamped sampler
        # (the landscape master is at its own samplers' limit).
        ("Edge", edge_tex, ""),
        # Steep faces in the cliffs' rock (shared samplers: the landscape
        # master is at its own samplers' limit).
        ("Nw", g.node(unreal.MaterialExpressionVertexNormalWS, x=-2000), ""),
        ("RockD", rock_d, ""), ("RockN", rock_n, ""),
        ("RockTint", g.vector4("RockTint", (1.0, 1.0, 1.0, 1.0)), ""),
        # Steep: normal z where all rock, where rock starts, tile cm, strength.
        ("Steep", g.vector4("GroundSteep", (0.45, 0.75, 250.0, 0.0)), ""),
        # Slope: normal z where banks start to be grass, all grass, strength,
        # and the cliffs' fill's share on flat ground.
        ("Slope", g.vector4("GroundSlope", (0.92, 0.8, 0.0, 0.0)), ""),
        ("Fill", g.vector4("CliffFill", (1.0, 0.8, 0.62, 0.0)), ""),
        # EdgeLook: grass worn at a lip, earth tint there, foot shade, on.
        ("EdgeLook", g.vector4("LandEdgeLook", (0.0, 0.0, 0.0, 0.0)), ""),
    ]
    c = g.custom(LAND_PBR_CODE, inputs, description="B30 ground")
    outs = []
    for name, kind in (("Normal", unreal.CustomMaterialOutputType.CMOT_FLOAT3),
                       ("Rough", unreal.CustomMaterialOutputType.CMOT_FLOAT1),
                       ("AO", unreal.CustomMaterialOutputType.CMOT_FLOAT1),
                       ("PDO", unreal.CustomMaterialOutputType.CMOT_FLOAT1),
                       ("Spec", unreal.CustomMaterialOutputType.CMOT_FLOAT1),
                       ("Emissive", unreal.CustomMaterialOutputType.CMOT_FLOAT3)):
        o = unreal.CustomOutput()
        o.set_editor_property("output_name", name)
        o.set_editor_property("output_type", kind)
        outs.append(o)
    c.set_editor_property("additional_outputs", outs)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(c, "Normal", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(c, "Emissive", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(c, "Rough", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(c, "AO", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    # Python's MaterialProperty has no Pixel Depth Offset (the plugin's does).
    unreal.MjolnirUIBuilderLibrary.connect_pixel_depth_offset(m, c, "PDO")
    mel.connect_material_property(c, "Spec", unreal.MaterialProperty.MP_SPECULAR)
    if land:
        holes = g.node(unreal.MaterialExpressionLandscapeVisibilityMask, x=-300)
    else:
        holes = g.custom(GROUND_CUT_CODE, [
            ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
            ("R", g.vector4("LandRect", (0.0, 0.0, 50400.0, 50400.0)), ""),
            ("N", g.scalar("LandMaskSize", 505.0), ""),
            ("Edge", g.scalar("LandCutEdge", 0.25), ""),
            ("Grow", g.scalar("LandCutGrow", 1.5), ""),
            ("Mask", g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name="LandMask",
                            texture=white, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR), "")],
            output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="landscape cut")
    mel.connect_material_property(holes, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


CLIFF_PBR_CODE = r"""
// A converted map's cliffs drawn in the game's own rock (M_CE_CliffPBR).
// (Textures through Texture2DSample, never .Sample(): the ray tracing hit
// shaders cannot take derivatives, and the macro samples a level there.)
//
// CE's cliff base map is a 1024 x 256 strip stretched over 20 m walls, so
// the rock comes from Megascans surfaces mapped from three sides in world
// space (triplanar: nothing stretches on a vertical face), at two scales
// (RockA, the grain; RockB over metres, which breaks up CE's flat facets),
// lit by Unreal as the B30 ground is. CE's colours stay as a little banding
// (Look.y), its lightmap as soft occlusion (Look.z).
//
// Where the wall meets the ground it blends into it, from the landscape's
// edge map (build_landscape.py edge_bake: R the ground's height at the top
// of the wall, A at its foot, over EdgeRange): under the lip the plateau's
// grass runs over the edge as turf with a ragged hem, then a band of bare
// earth, then moss and water stains run down the rock; at the foot the sand
// banks up against it and the rock darkens where it meets it.
struct CLF
{
    static float noise(float2 p)
    {
        float2 i = floor(p), f = frac(p);
        f = f * f * (3.0 - 2.0 * f);
        float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
        float b = frac(sin(dot(i + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
        float c = frac(sin(dot(i + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
        float d = frac(sin(dot(i + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
        return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
    }
    // The three projections of world position W at T cm a tile, mirrored so
    // no face reads backwards.
    static void uvs(float3 W, float3 sgn, float T, out float2 ux, out float2 uy, out float2 uz)
    {
        ux = float2(W.z * sgn.x, W.y) / T;
        uy = float2(W.x * sgn.y, W.z) / T;
        uz = float2(-W.x * sgn.z, W.y) / T;
    }
    static float4 tri(Texture2D D, SamplerState S, float2 ux, float2 uy, float2 uz, float3 bw)
    {
        return Texture2DSample(D, S, ux) * bw.x + Texture2DSample(D, S, uy) * bw.y + Texture2DSample(D, S, uz) * bw.z;
    }
    // A normal map from three sides, whiteout-blended onto the surface's
    // normal n (Golus), in world space; k scales its slopes.
    static float3 triN(Texture2D N, SamplerState S, float2 ux, float2 uy, float2 uz, float3 bw, float3 n,
                       float3 sgn, float k)
    {
        float3 tx = float3((Texture2DSample(N, S, ux).rg * 2.0 - 1.0) * k, 1.0);
        float3 ty = float3((Texture2DSample(N, S, uy).rg * 2.0 - 1.0) * k, 1.0);
        float3 tz = float3((Texture2DSample(N, S, uz).rg * 2.0 - 1.0) * k, 1.0);
        tx = float3(tx.xy + n.zy, abs(n.x) * tx.z);
        ty = float3(ty.xy + n.xz, abs(n.y) * ty.z);
        tz = float3(tz.xy + n.xy, abs(n.z) * tz.z);
        tx.z *= sgn.x; ty.z *= sgn.y; tz.z *= sgn.z;
        return normalize(tx.zyx * bw.x + ty.xzy * bw.y + tz.xyz * bw.z);
    }
    // No visible repeat (Quilez's texture variation): a slow noise over the
    // tile coordinates picks, per region, a random offset of the tile, and
    // where the noise steps to the next offset the two blend along the
    // rock's own features (the colour difference). A whole cliff of one
    // Megascans tile read as a grid of the same boulders (2026-10-12).
    // The blend has no weight at a step, so the quad derivatives jumping
    // there leave no seam; no ddx, so the ray tracing hit shaders compile.
    // V: amount (0 plain tiling), noise frequency (per tile), steps.
    static void vary(float2 uv, float3 V, out float2 oa, out float2 ob, out float f)
    {
        float k = noise(uv * V.y) * V.z;
        float i = floor(k);
        f = frac(k);
        oa = frac(sin(float2(i, i + 0.37) * float2(127.1, 311.7)) * 43758.5453) * V.x;
        ob = frac(sin(float2(i + 1.0, i + 1.37) * float2(127.1, 311.7)) * 43758.5453) * V.x;
    }
    // One projection of a surface (albedo, ORHG, normal xy in -1..1), varied.
    static void one(Texture2D D, SamplerState DS, Texture2D O, SamplerState OS, Texture2D N, SamplerState NS,
                    float2 uv, float3 V, out float3 d, out float4 o, out float2 nxy)
    {
        float2 oa, ob; float f;
        vary(uv, V, oa, ob, f);
        float3 da = Texture2DSample(D, DS, uv + oa).rgb;
        float3 db = Texture2DSample(D, DS, uv + ob).rgb;
        float w = smoothstep(0.2, 0.8, f - 0.15 * dot(da - db, 1.0.xxx));
        d = lerp(da, db, w);
        o = lerp(Texture2DSample(O, OS, uv + oa), Texture2DSample(O, OS, uv + ob), w);
        nxy = lerp(Texture2DSample(N, NS, uv + oa).rg, Texture2DSample(N, NS, uv + ob).rg, w) * 2.0 - 1.0;
    }
    // A surface from three sides, varied; a side under 2% of the blend is
    // skipped (most of a wall faces one way) and the rest renormalised.
    static void rock(Texture2D D, SamplerState DS, Texture2D O, SamplerState OS, Texture2D N, SamplerState NS,
                     float2 ux, float2 uy, float2 uz, float3 bw, float3 n, float3 sgn, float k, float3 V,
                     out float3 d, out float4 o, out float3 nw)
    {
        float3 dx = 0, dy = 0, dz = 0;
        float4 ox = 0, oy = 0, oz = 0;
        float2 nx = 0, ny = 0, nz = 0;
        float3 w = bw * step(0.02, bw);
        w /= max(w.x + w.y + w.z, 1e-4);
        [branch] if (w.x > 0.0) one(D, DS, O, OS, N, NS, ux, V, dx, ox, nx);
        [branch] if (w.y > 0.0) one(D, DS, O, OS, N, NS, uy, V, dy, oy, ny);
        [branch] if (w.z > 0.0) one(D, DS, O, OS, N, NS, uz, V, dz, oz, nz);
        d = dx * w.x + dy * w.y + dz * w.z;
        o = ox * w.x + oy * w.y + oz * w.z;
        float3 tx = float3(nx * k, 1.0), ty = float3(ny * k, 1.0), tz = float3(nz * k, 1.0);
        tx = float3(tx.xy + n.zy, abs(n.x) * tx.z);
        ty = float3(ty.xy + n.xz, abs(n.y) * ty.z);
        tz = float3(tz.xy + n.xy, abs(n.z) * tz.z);
        tx.z *= sgn.x; ty.z *= sgn.y; tz.z *= sgn.z;
        nw = normalize(tx.zyx * w.x + ty.xzy * w.y + tz.xyz * w.z);
    }
};

float3 n = normalize(Nw);
float3 sgn = float3(n.x < 0 ? -1.0 : 1.0, n.y < 0 ? -1.0 : 1.0, n.z < 0 ? -1.0 : 1.0);
float3 bw = pow(abs(n), Tiles.w);
bw /= max(bw.x + bw.y + bw.z, 1e-4);

float2 ux, uy, uz;
float3 aA, aB, nA, nB;
float4 oA, oB;
CLF::uvs(W, sgn, Tiles.x, ux, uy, uz);
CLF::rock(RockAD, RockADSampler, RockAO, RockAOSampler, RockAN, RockANSampler, ux, uy, uz, bw, n, sgn, Look.x,
          Vary.xyz, aA, oA, nA);
// The large rock's variation on a noise of its own (offset), so the two
// scales do not step together.
CLF::uvs(W, sgn, Tiles.y, ux, uy, uz);
CLF::rock(RockBD, RockBDSampler, RockBO, RockBOSampler, RockBN, RockBNSampler, ux + 17.3, uy + 17.3, uz + 17.3,
          bw, n, sgn, Look.x, Vary.xyz, aB, oB, nB);

// The large rock over patches, the fine one in between, its shapes (normal)
// always under the grain's.
float patch = smoothstep(0.35, 0.65, CLF::noise(W.xy / Tiles.z + W.z / (Tiles.z * 1.7))) * Mix.x;
float3 meanA = Texture2DSampleLevel(RockAD, RockADSampler, float2(0.5, 0.5), 13.0).rgb;
float3 meanB = Texture2DSampleLevel(RockBD, RockBDSampler, float2(0.5, 0.5), 13.0).rgb;
float3 rel = lerp(aA / max(meanA, 1e-3), aB / max(meanB, 1e-3), patch);
// Far away the large rock read three times larger takes over (Far: from,
// to cm), so the grain's repeat does not show across a whole cliff face.
float far = smoothstep(Far.x, Far.y, length(Cam - W));
if (far > 0.0)
{
    CLF::uvs(W, sgn, Tiles.y * 3.0, ux, uy, uz);
    float3 aF = CLF::tri(RockBD, RockBDSampler, ux, uy, uz, bw).rgb;
    rel = lerp(rel, aF / max(meanB, 1e-3), far * 0.7);
}
rel = max(1.0 + (rel - 1.0) * Look.w, 0.0);
// Weathering: streaks running down the face metres wide, darker and lighter
// (Far.z strength), as rain and salt leave them.
float wx = (W.x + W.y) / 350.0 + n.x * 2.0;
float streaks = CLF::noise(float2(wx, W.z / 2500.0)) * 0.65 + CLF::noise(float2(wx * 3.1, W.z / 900.0)) * 0.35;
rel *= lerp(1.0, 0.7 + 0.55 * streaks, Far.z);
float3 Nr = normalize(nA + (nB - n) * Mix.y);

// CE's colour (its base map by its own UVs, gamma), as a little banding;
// RockTint the rest.
float3 ce = pow(max(Texture2DSample(Base, BaseSampler, TC0).rgb, 1e-3), 2.2);
float3 rockCol = lerp(lerp(meanA, meanB, patch) * RockTint.rgb, ce * Mix.z, Look.y);
float3 albedo = rockCol * rel;
// Roughness into RoughR's range: the surfaces' ORHG green read glossy (wet
// black patches in the shade).
float rough = lerp(RoughR.x, RoughR.y, lerp(oA.g, oB.g, patch));
float ao = lerp(oA.r, oB.r, patch);

// Where the wall meets the ground.
float turf = 0.0, soil = 0.0, streak = 0.0, sand = 0.0, contact = 0.0;
float rag = CLF::noise(float2((W.x + W.y) / 80.0, W.z / 60.0)) * 0.6 + CLF::noise(float2((W.x - W.y) / 23.0, W.z / 19.0)) * 0.4;
if (EdgeRange.y > EdgeRange.x)
{
    float4 e = Texture2DSampleLevel(Edge, EdgeSampler, (W.xy - EdgeRect.xy) / EdgeRect.zw, 0);
    float below = lerp(EdgeRange.x, EdgeRange.y, e.r) - W.z;   // cm under the lip
    float above = W.z - lerp(EdgeRange.x, EdgeRange.y, e.a);   // cm over the foot
    // A wall reaching above all the ground near it (a stack's crown) has no lip.
    // No lip within reach (R 0: a wall leaning back from the ground under
    // it), no drape; a wall reaching above its lip (a stack's crown) neither.
    // Only up to 60 cm above the lip: a wall rising from a plateau (a tower
    // over its lip) took turf as green slabs metres up.
    float lipOn = smoothstep(-60.0, -15.0, below) * step(0.004, e.r);
    float t = Drape.x * (0.3 + 1.4 * rag);
    // Only on a wall (steep) right under an edge (the lip mask): a sloping
    // rock face crossing the lip's height drew the rim as a green hairline.
    float wallness = 1.0 - smoothstep(0.45, 0.7, n.z);
    turf = (1.0 - smoothstep(t * 0.7, t, below)) * lipOn * wallness * smoothstep(0.25, 0.6, e.g);
    float d = Drape.y * (0.4 + 1.2 * rag);
    soil = (1.0 - smoothstep(d * 0.5, d, below)) * lipOn * (1.0 - turf);
    // Stains: runs straight down from the lip, fading over Drape.z.
    float run = CLF::noise(float2((W.x + W.y) / 38.0 + n.x * 3.0, W.z / 1400.0));
    streak = smoothstep(0.55, 0.9, run) * (1.0 - smoothstep(0.0, Drape.z, below)) * step(0.0, below) * lipOn
             * (1.0 - turf - soil);
    // The foot: sand banked against the rock, ragged, and contact shade;
    // only where the foot is well under the lip (a wall's top, the beach
    // too far out for the map, read its own plateau as the foot and was
    // painted as sand).
    float footOn = smoothstep(150.0, 300.0, below + above) * step(0.004, e.a) * step(0.004, e.r);
    float sb = Foot.x * (0.4 + 1.2 * rag);
    sand = (1.0 - smoothstep(sb * 0.6, sb, above)) * footOn;
    contact = (1.0 - smoothstep(0.0, Foot.y, above)) * footOn;
}
// Grass on ledges that look up (a boulder's top is all grass; a ledge
// part-way, its edge ragged), by the surface's own normal, not the rock's
// bumps (with them, every up-facing seam of the rock drew a green hairline).
turf = max(turf, smoothstep(0.7, 0.88, n.z + (rag - 0.5) * 0.2));
turf *= Drape.w; soil *= Drape.w; streak *= Drape.w; sand *= Foot.w;

if (turf + soil > 0.002)
{
    CLF::uvs(W, sgn, 300.0, ux, uy, uz);
    float3 gA = CLF::tri(GrassD, GrassDSampler, ux, uy, uz, bw).rgb * GrassTint.rgb;
    float3 gN = CLF::triN(GrassN, GrassNSampler, ux, uy, uz, bw, n, sgn, 1.0);
    CLF::uvs(W, sgn, 250.0, ux, uy, uz);
    float3 sA = CLF::tri(SoilD, SoilDSampler, ux, uy, uz, bw).rgb;
    float4 sO = CLF::tri(SoilO, SoilOSampler, ux, uy, uz, bw);
    float3 sN = CLF::triN(SoilN, SoilNSampler, ux, uy, uz, bw, n, sgn, 1.0);
    albedo = lerp(lerp(albedo, sA, soil), gA, turf);
    Nr = normalize(lerp(lerp(Nr, sN, soil), gN, turf));
    rough = lerp(lerp(rough, lerp(RoughR.x, RoughR.y, sO.g), soil), 0.85, turf);
    ao = lerp(lerp(ao, sO.r, soil), ao * 0.9, turf);
}
// Stains: darker, a little green, rougher where moss holds.
albedo *= lerp(1.0.xxx, float3(0.55, 0.6, 0.45), streak);
// The foot: the beach's own sand over the rock, on banks only (a flat
// colour on a vertical face read as a pale, featureless patch), and the
// shade where the two meet.
sand *= smoothstep(0.2, 0.5, n.z);
if (sand > 0.002)
{
    CLF::uvs(W, sgn, 250.0, ux, uy, uz);
    float3 sA = CLF::tri(SandD, SandDSampler, ux, uy, uz, bw).rgb * SandCol.rgb;
    albedo = lerp(albedo, sA, sand);
}
Nr = normalize(lerp(Nr, n, sand * 0.7));
rough = lerp(rough, 0.9, sand);
ao *= 1.0 - Foot.z * contact;

// CE's baked light: as occlusion (overhangs and clefts keep their shade),
// and its colour (CETint.x): the original's dusk light, purple in the shade
// and warm in the sun, which CE's own surfaces beside the rock (the bases,
// the arch) still carry. Its chroma only, so Unreal's sun still shades.
float occ = 1.0;
float3 ceLight = 1.0.xxx;
// A cladding rock with its own CE light (CladLight.a 2: scatter_foliage's
// lightmap sample where it sits, as custom primitive data 0..2) is shaded
// as the wall under it is, colour and shade; one colour a group (the k-means
// centre) left rocks in a wall's shade lit and tinted blue (2026-10-13).
bool cladLM = CladLight.a > 1.5;
if (LMLevels.y > LMLevels.x)
{
    float3 lmc = cladLM ? CladLM : Texture2DSample(LM, LMSampler, TC1).rgb;
    float lm = dot(lmc, float3(0.2126, 0.7152, 0.0722));
    occ = saturate((lm - LMLevels.x * 0.5) / max(LMLevels.y - LMLevels.x * 0.5, 1e-3));
    ao *= lerp(1.0, 0.3 + 0.7 * occ, Look.z);
    float3 lin = pow(max(lmc, 1e-3), 2.2);
    ceLight = clamp(lin / max(dot(lin, float3(0.2126, 0.7152, 0.0722)), 1e-3), 0.4, 2.0);
}
// A cladding rock (scatter_foliage's cladding: a mesh actor, no lightmap
// page) takes the CE light of the walls it sits on from its group
// (CladLight: rgb, negative when none). (Not instance data: this game's
// renderer drew our materials black on instanced meshes.)
if (CladLight.r >= 0.0 && !cladLM)
{
    ceLight = clamp(CladLight.rgb, 0.4, 2.0);
}
albedo *= lerp(1.0.xxx, ceLight, CETint.x);
// No albedo over 0.9: CE's light colour can lift a channel past 1, and Lumen
// bounced such a surface into a runaway orange flood over the whole scene
// (3,000 cladding rocks, 2026-10-12).
albedo = min(albedo, 0.9);

// Wet rock just over the sea.
if (Sea.w > 0.5)
{
    float wet = 1.0 - smoothstep(0.0, Sea.z, W.z - Sea.x);
    albedo *= lerp(1.0, 0.55, wet);
    rough = lerp(rough, 0.3, wet);
}

// Fill (Fill.rgb x Fill.a): the light the sunlit sand throws back onto the
// rock. This scene's sky light alone left a wall in shade black, where CE's
// lightmap had lit it; strongest on faces that look out and down, a little
// of CE's shade in it.
// FillDir: the fill's share on a wall, and its change towards faces that
// look up (negative: towards faces that look down, a bounce off the sand;
// on rocks part-way up a wall that lit their undersides brighter than the
// wall, 2026-10-13).
float facing = max(FillDir.x + FillDir.y * Nr.z, 0.0);
Emissive = max(albedo, 0.0) * Fill.rgb * Fill.a * facing * ao * lerp(1.0, 0.5 + 0.5 * occ, Look.z);

Normal = Nr;
Rough = saturate(rough);
AO = saturate(ao);
return max(albedo, 0.0);
"""


# Nanite tessellation's height for M_CE_CliffTess: the cliff rock's own
# height maps (ORHG blue) sampled as M_CE_CliffPBR samples their colour
# (CLF::uvs, CLF::vary, the same Tiles and Vary), so bumps sit under their
# own shading. The large rock leads (the grain's three-metre tile as height
# read as spikes). VC is the vertex colour: tools/level/cliff_mesh.py's
# distance from the cliffs' border, so nothing moves where the wall meets
# the ground. Disp: amount (0..1 of the material's magnitude), cm per mip
# step. Out 0..1 about the DisplacementScaling centre (0.5). Explicit mips:
# displacement runs in the rasterizer, with no derivatives.
CLIFF_DISPLACE_CODE = r"""
struct CLD
{
    static float noise(float2 p)
    {
        float2 i = floor(p), f = frac(p);
        f = f * f * (3.0 - 2.0 * f);
        float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
        float b = frac(sin(dot(i + float2(1, 0), float2(127.1, 311.7))) * 43758.5453);
        float c = frac(sin(dot(i + float2(0, 1), float2(127.1, 311.7))) * 43758.5453);
        float d = frac(sin(dot(i + float2(1, 1), float2(127.1, 311.7))) * 43758.5453);
        return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
    }
    static float h(Texture2D O, SamplerState S, float2 uv, float3 V, float mip)
    {
        float k = noise(uv * V.y) * V.z;
        float i = floor(k), f = frac(k);
        float2 oa = frac(sin(float2(i, i + 0.37) * float2(127.1, 311.7)) * 43758.5453) * V.x;
        float2 ob = frac(sin(float2(i + 1.0, i + 1.37) * float2(127.1, 311.7)) * 43758.5453) * V.x;
        float w = smoothstep(0.2, 0.8, f);
        return lerp(Texture2DSampleLevel(O, S, uv + oa, mip).b, Texture2DSampleLevel(O, S, uv + ob, mip).b, w);
    }
    static float tri(Texture2D O, SamplerState S, float3 W, float3 sgn, float3 bw, float T, float off, float3 V,
                     float mip)
    {
        float2 ux = float2(W.z * sgn.x, W.y) / T + off;
        float2 uy = float2(W.x * sgn.y, W.z) / T + off;
        float2 uz = float2(-W.x * sgn.z, W.y) / T + off;
        return h(O, S, ux, V, mip) * bw.x + h(O, S, uy, V, mip) * bw.y + h(O, S, uz, V, mip) * bw.z;
    }
};
float3 n = normalize(Nw);
float3 sgn = float3(n.x < 0 ? -1.0 : 1.0, n.y < 0 ? -1.0 : 1.0, n.z < 0 ? -1.0 : 1.0);
float3 bw = pow(abs(n), Tiles.w);
bw /= max(bw.x + bw.y + bw.z, 1e-4);
float mip = clamp(log2(max(length(Cam - W), 1.0) / max(Disp.y, 1.0)), 0.0, 10.0);
float hA = CLD::tri(RockAO, RockAOSampler, W, sgn, bw, Tiles.x, 0.0, Vary.xyz, mip);
float hB = CLD::tri(RockBO, RockBOSampler, W, sgn, bw, Tiles.y, 17.3, Vary.xyz, mip);
float hgt = lerp(hA, hB, 0.7);
return 0.5 + (hgt - 0.5) * Disp.x * saturate(VC.r);
"""


def cpd3(g):
    """Custom primitive data 0, 1 and 2 as a float3: a vector parameter
    reading the component's data (5.5 has no node of its own for it)."""
    return g.node(unreal.MaterialExpressionVectorParameter, x=-2000, parameter_name="CladLMData",
                  default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0), use_custom_primitive_data=True,
                  primitive_data_index=0)


def build_cliff_pbr(defaults, name="M_CE_CliffPBR", tessellate=False, shade_uv=False):
    """M_CE_CliffPBR (CLIFF_PBR_CODE): a converted map's cliff slots in the
    game's own rock, triplanar and lit by Unreal. MJOLNIRLevelLoader sets the
    rock surfaces (game textures) and each slot's own base map and lightmap
    page at runtime (Land.cliffs).

    With `tessellate`, M_CE_CliffTess: the same, for the cliffs as a Nanite
    mesh of their own (tools/level/cliff_mesh.py), displaced by the rock's
    height (CLIFF_DISPLACE_CODE), up to 50 cm either way (CliffDisp.x 1)."""
    m = fresh(ROOT, name, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    # The cladding rocks, B30's Uluwatu meshes, are Nanite (a cooked game
    # cannot add a usage flag at runtime).
    m.set_editor_property("used_with_nanite", True)
    m.set_editor_property("used_with_static_lighting", False)
    m.set_editor_property("two_sided", True)
    g = Graph(m)
    white = defaults["T_CE_White"]
    colour, normal, linear = (unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
                              unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
                              unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    albedo_default = unreal.load_asset("/Engine/EngineResources/DefaultTexture")
    normal_default = unreal.load_asset("/Engine/EngineMaterials/DefaultNormal")

    def tex(name, default, sampler):
        # Shared samplers (wrap, or clamp for the edge map): the master is
        # past the 16 a material may have of its own.
        t = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name=name,
                   texture=default, sampler_type=sampler)
        t.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS
                              if name == "Edge" else unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
        return (name, t, "")

    # The tessellated cliffs (`shade_uv`) shade by CE's own normals (UV2,
    # UV3; their vertex normals are welded for displacement, cliff_mesh.py),
    # the mesh unrotated at the origin, so object space is world space.
    if shade_uv:
        nxy = g.uv(2)
        nz = g.node(unreal.MaterialExpressionComponentMask, x=-1900, r=True)
        link(g.uv(3), "", nz, "")
        shade_n = g.node(unreal.MaterialExpressionAppendVector, x=-1800)
        link(nxy, "", shade_n, "A")
        link(nz, "", shade_n, "B")
    else:
        shade_n = g.node(unreal.MaterialExpressionVertexNormalWS, x=-2000)
    inputs = [
        ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
        ("Nw", shade_n, ""),
        tex("Base", white, linear), ("TC0", g.uv(0), ""), ("TC1", g.uv(1), ""),
        tex("RockAD", albedo_default, colour), tex("RockAN", normal_default, normal), tex("RockAO", white, linear),
        tex("RockBD", albedo_default, colour), tex("RockBN", normal_default, normal), tex("RockBO", white, linear),
        tex("GrassD", albedo_default, colour), tex("GrassN", normal_default, normal),
        tex("SoilD", albedo_default, colour), tex("SoilN", normal_default, normal), tex("SoilO", white, linear),
        ("GrassTint", g.vector4("GrassTint", (1.0, 1.0, 1.0, 1.0)), ""),
        ("RockTint", g.vector4("RockTint", (1.0, 1.0, 1.0, 1.0)), ""),
        # The landscape's edge map (edge_bake), its rectangle and height range
        # (cm; off while the range is empty).
        tex("Edge", white, linear),
        ("EdgeRect", g.vector4("EdgeRect", (0.0, 0.0, 50400.0, 50400.0)), ""),
        ("EdgeRange", g.vector4("EdgeRange", (0.0, 0.0, 0.0, 0.0)), ""),
        # Drape: turf and earth depth under the lip, stain length (cm), strength.
        ("Drape", g.vector4("CliffDrape", (30.0, 70.0, 700.0, 1.0)), ""),
        # Foot: sand bank height, contact shade height (cm), shade, strength.
        ("Foot", g.vector4("CliffFoot", (45.0, 150.0, 0.45, 1.0)), ""),
        # The foot's sand: the beach's albedo, tinted.
        tex("SandD", albedo_default, colour),
        ("SandCol", g.vector4("CliffSand", (1.0, 1.0, 1.0, 1.0)), ""),
        ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS, x=-2000), ""),
        # Far: the large rock takes over from, to (cm); weathering streaks.
        ("Far", g.vector4("CliffFar", (2500.0, 9000.0, 0.6, 0.0)), ""),
        # CETint: CE's light colour's share.
        ("CETint", g.vector4("CliffCETint", (0.0, 0.0, 0.0, 0.0)), ""),
        ("CladLight", g.vector4("CladLight", (-1.0, -1.0, -1.0, 0.0)), ""),
        # Tiles: cm a tile of the grain rock and of the large rock, the patch
        # noise's cell, triplanar blend sharpness.
        ("Tiles", g.vector4("CliffTiles", (300.0, 1200.0, 2500.0, 4.0)), ""),
        # Mix: the large rock's share of colour, of shape, CE colour gain, moss.
        ("Mix", g.vector4("CliffMix", (0.6, 1.0, 1.0, 1.0)), ""),
        # Look: normal strength, CE colour share, CE shade as occlusion, grain
        # contrast.
        ("Look", g.vector4("CliffLook", (1.0, 0.7, 0.6, 1.0)), ""),
        tex("LM", white, linear),
        ("LMLevels", g.vector4("LandLMLevels", (0.0, 0.0, 0.0, 0.0)), ""),
        ("Sea", g.vector4("LandSea", (0.0, 150.0, 40.0, 0.0)), ""),
        # Rough: the range the surfaces' roughness maps to.
        ("RoughR", g.vector4("CliffRough", (0.6, 1.0, 0.0, 0.0)), ""),
        # Vary: tile variation amount (0 plain tiling), its noise frequency
        # per tile, steps over the noise's range (CLF::vary).
        ("Vary", g.vector4("CliffVary", (1.0, 0.35, 6.0, 0.0)), ""),
        # Fill: the bounce light's colour and strength (scene units).
        ("Fill", g.vector4("CliffFill", (1.0, 0.8, 0.62, 0.0)), ""),
        # FillDir: the fill on a wall, its change with the normal's z.
        ("FillDir", g.vector4("CliffFillDir", (0.75, -0.35, 0.0, 0.0)), ""),
        # A cladding rock's own CE light (custom primitive data 0..2, gamma),
        # used when CladLight.a is 2.
        ("CladLM", cpd3(g), ""),
    ]
    c = g.custom(CLIFF_PBR_CODE, inputs, description="cliff rock")
    outs = []
    for name, kind in (("Normal", unreal.CustomMaterialOutputType.CMOT_FLOAT3),
                       ("Rough", unreal.CustomMaterialOutputType.CMOT_FLOAT1),
                       ("AO", unreal.CustomMaterialOutputType.CMOT_FLOAT1),
                       ("Emissive", unreal.CustomMaterialOutputType.CMOT_FLOAT3)):
        o = unreal.CustomOutput()
        o.set_editor_property("output_name", name)
        o.set_editor_property("output_type", kind)
        outs.append(o)
    c.set_editor_property("additional_outputs", outs)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(c, "Emissive", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    # The normal is worked out in world space; the material takes tangent space.
    tangent = g.node(unreal.MaterialExpressionTransform, x=-300,
                     transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                     transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
    link(c, "Normal", tangent, "")
    mel.connect_material_property(tangent, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(c, "Rough", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(c, "AO", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, x=-300, r=0.5), "",
                                  unreal.MaterialProperty.MP_SPECULAR)
    if tessellate:
        m.set_editor_property("enable_tessellation", True)
        m.set_editor_property("displacement_scaling", unreal.DisplacementScaling(magnitude=100.0, center=0.5))
        named = {n: (src, pin) for n, src, pin in inputs}
        # Heights by the welded normal (the shading one differs either side
        # of a crease, which would open it).
        d = g.custom(CLIFF_DISPLACE_CODE, [
            ("W", *named["W"]), ("Nw", g.node(unreal.MaterialExpressionVertexNormalWS, x=-2000), ""),
            ("Cam", *named["Cam"]),
            ("RockAO", *named["RockAO"]), ("RockBO", *named["RockBO"]),
            ("Tiles", *named["Tiles"]), ("Vary", *named["Vary"]),
            ("VC", g.node(unreal.MaterialExpressionVertexColor, x=-2000), ""),
            # Amount (0..1 of 100 cm, about the centre), cm per mip step.
            ("Disp", g.vector4("CliffDisp", (0.6, 400.0, 0.0, 0.0)), ""),
        ], output=unreal.CustomMaterialOutputType.CMOT_FLOAT1, description="cliff displacement")
        if not unreal.MjolnirUIBuilderLibrary.connect_displacement(m, d, ""):
            unreal.log_error(f"MJOLNIR: {name}: displacement not connected")
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


# shader_transparent_plasma (M_CE_Plasma), as MCC draws it
# (HCEEK/shaders/fx/transparent_plasma.psh, vsh/transparent_plasma_m.vsh):
# two volume noise maps, each at the surface's position in world units times
# its noise map scale, drifting along its animation direction once a period;
# their luminance (b) and alpha differenced into the plasma's veins; the tint
# between the parallel and the perpendicular colour (each times its
# brightness) by how squarely the surface faces the eye; added into the frame.
# The volumes are 2D atlases (mcc_tags.volume_atlas: slices as tiles with a
# wrapped border, Atlas = tile w, h, columns, slices), blended between
# slices here. Explicit levels: no derivatives in the ray tracing shaders.
PLASMA_CODE = r"""
struct PLS
{
    static float4 vol(Texture2D T, SamplerState S, float3 p, float4 A)
    {
        float cols = max(A.z, 1.0), d = max(A.w, 1.0);
        float rows = ceil(d / cols);
        float2 tile = A.xy + 2.0;
        float2 size = float2(cols, rows) * tile;
        p = frac(p);
        float z = p.z * d - 0.5;
        float z0 = floor(z), f = z - z0;
        float s0 = fmod(z0 + d, d), s1 = fmod(z0 + 1.0 + d, d);
        float2 inner = 1.0 + p.xy * A.xy;
        float2 c0 = (float2(fmod(s0, cols), floor(s0 / cols)) * tile + inner) / size;
        float2 c1 = (float2(fmod(s1, cols), floor(s1 / cols)) * tile + inner) / size;
        return lerp(Texture2DSampleLevel(T, S, c0, 0), Texture2DSampleLevel(T, S, c1, 0), f);
    }
};
float3 P = W / 304.8;
float3 pa = P * NoiseA.x + NoiseADir.xyz * (Time / max(abs(NoiseA.y), 1e-3)) * sign(NoiseA.y + 1e-6);
float3 pb = P * NoiseB.x + NoiseBDir.xyz * (Time / max(abs(NoiseB.y), 1e-3)) * sign(NoiseB.y + 1e-6);
float4 t0 = PLS::vol(NoiseAMap, NoiseAMapSampler, pa, AtlasA);
float4 t1 = PLS::vol(NoiseBMap, NoiseBMapSampler, pb, AtlasB);
float i1 = saturate(t0.b + 0.5 - t1.b);
float i2 = saturate(t1.a + 0.5 - t0.a);
float pl = i1 < 0.5 ? i1 : i2;
pl = saturate(pl * pl * 4.0);
float att = pl < 0.5 ? 0.0 : pow(2.0 * pl - 1.0, 2.0);
float ne = abs(dot(normalize(N), normalize(Cam - W)));
float3 tint = saturate(Para.rgb + ne * (Perp.rgb - Para.rgb));
float3 col = saturate(pl * tint + att * 0.5) * pl * pl;
return col * Bright.x * Exposure * DisplayGain;
"""


def build_plasma(defaults):
    """M_CE_Plasma (PLASMA_CODE): additive, unlit, two-sided. Its noise maps
    default to the plasma shield noise atlas (MJ_PLASMA_NOISE, written by
    mcc_tags.volume_atlas from MCC's tag), the one CE's plasma shaders use."""
    m = fresh(ROOT, "M_CE_Plasma", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    noise = defaults["T_CE_White"]
    atlas = os.environ.get("MJ_PLASMA_NOISE")
    if atlas and os.path.exists(atlas):
        noise = import_texture(atlas, ROOT, "T_CE_PlasmaNoise")
        # Raw values (the shader differences them), no compression, no mips
        # (the atlas's tiles would bleed into each other), wrapping.
        noise.set_editor_property("srgb", False)
        noise.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        noise.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        noise.set_editor_property("never_stream", True)
        eal.save_loaded_asset(noise)
    else:
        unreal.log_warning("MJOLNIR: no MJ_PLASMA_NOISE; M_CE_Plasma's noise defaults to white")

    def tex(name):
        t = g.node(unreal.MaterialExpressionTextureObjectParameter, x=-1100, parameter_name=name, texture=noise,
                   sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        t.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
        return (name, t, "")

    atlas_default = (32.0, 32.0, 8.0, 32.0)
    inputs = [
        ("W", g.node(unreal.MaterialExpressionWorldPosition, x=-2000), ""),
        ("N", g.node(unreal.MaterialExpressionVertexNormalWS, x=-2000), ""),
        ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS, x=-2000), ""),
        ("Time", g.node(unreal.MaterialExpressionTime, x=-2000), ""),
        tex("NoiseAMap"), tex("NoiseBMap"),
        # Scale (a world unit's share of the volume), period (s).
        ("NoiseA", g.vector4("PlasmaNoiseA", (1.0, 1.0, 0.0, 0.0)), ""),
        ("NoiseB", g.vector4("PlasmaNoiseB", (1.0, 1.0, 0.0, 0.0)), ""),
        ("NoiseADir", g.vector4("PlasmaNoiseADir", (0.0, 0.0, 0.0, 0.0)), ""),
        ("NoiseBDir", g.vector4("PlasmaNoiseBDir", (0.0, 0.0, 0.0, 0.0)), ""),
        ("AtlasA", g.vector4("PlasmaAtlasA", atlas_default), ""),
        ("AtlasB", g.vector4("PlasmaAtlasB", atlas_default), ""),
        # Each tint colour times its brightness.
        ("Perp", g.vector4("PlasmaPerpendicular", (0.0, 0.45, 0.9, 1.0)), ""),
        ("Para", g.vector4("PlasmaParallel", (0.3, 0.65, 1.0, 1.0)), ""),
        ("Bright", g.vector4("PlasmaBrightness", (1.0, 0.0, 0.0, 0.0)), ""),
        ("Exposure", g.scalar("Exposure", 1.0), ""),
        ("DisplayGain", g.scalar("DisplayGain", DISPLAY_GAIN), ""),
    ]
    c = g.custom(PLASMA_CODE, inputs, description="CE shader_transparent_plasma")
    mel.connect_material_property(g.to_screen(c), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


def build_hidden():
    """M_CE_Hidden: draws nothing, casts nothing. A terrain slot whose CE
    scenery B30's own assets replace (tools/level/scenery_swap.py) points
    at it: the scenery is baked into the terrain mesh, a slot a shader."""
    m = fresh(ROOT, "M_CE_Hidden", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("used_with_static_lighting", False)
    g = Graph(m)
    mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, x=-300, r=0.0), "",
                                  unreal.MaterialProperty.MP_OPACITY_MASK)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)


if TRIAL_ROOT:
    build_hidden()
    build_environment("M_CE_Landscape", False, defaults, land=True)
    build_landscape_pbr(defaults)
    build_landscape_pbr(defaults, "M_CE_GroundPBR", land=False)
    build_cliff_pbr(defaults)
    build_cliff_pbr(defaults, "M_CE_CliffTess", tessellate=True, shade_uv=True)
    # The cladding rocks tessellated: their own vertex normals.
    build_cliff_pbr(defaults, "M_CE_CladTess", tessellate=True)
    # Until the runtime pack carries it (MJOLNIRLevelLoader falls back here).
    build_plasma(defaults)
    # MJOLNIRLevelLoader takes only the environment masters from a trial
    # build (TRIAL_MASTERS); the rest stay the runtime pack's.
    unreal.log("MJOLNIR CE trial materials built")
else:
    # Every framebuffer blend, one- and two-sided (chicago flag bit 2: 38 stock
    # shaders, the teleporter fields).
    for blend_name, blend_mode in (("Add", unreal.BlendMode.BLEND_ADDITIVE),
                                   ("Alpha", unreal.BlendMode.BLEND_TRANSLUCENT),
                                   ("Mul", unreal.BlendMode.BLEND_MODULATE)):
        for two_sided in (False, True):
            for device in (False, True):
                build_transparent(f"M_CE_Transparent{blend_name}{'TwoSided' if two_sided else ''}"
                                  f"{'Device' if device else ''}",
                                  blend_mode, defaults, two_sided=two_sided, device=device)
    build_water(defaults)
    # Sky water replaces the frame rather than adding to it.
    build_water(defaults, "M_CE_WaterSky", unreal.BlendMode.BLEND_OPAQUE)
    build_water_background(defaults)
    for two_sided in (False, True):
        build_glass(defaults, two_sided)
    build_flare(defaults)
    build_plasma(defaults)
    unreal.log("MJOLNIR CE materials built")
