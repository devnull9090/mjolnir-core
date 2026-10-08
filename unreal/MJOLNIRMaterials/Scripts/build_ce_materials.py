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
# A trial build of the masters (MJ_CE_ROOT=/Game/MJOLNIR/CETrial
# MJ_CE_CHUNK=983) goes in a folder and chunk of its own, labelled alone, so
# the runtime pack's 988 is left as it is; it builds only the environment
# masters, and MJOLNIRLevelLoader picks them up with
# `mjolnir_terrain_shadows lightmap` or `mjolnir_terrain_lights on`.
TRIAL_ROOT = os.environ.get("MJ_CE_ROOT")
if TRIAL_ROOT:
    ROOT = TRIAL_ROOT.rstrip("/")
CHUNK = int(os.environ.get("MJ_CE_CHUNK", "988"))

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


# CE's periodic functions (self-illumination and UV animation) as 0..1:
# one, zero, cosine (and variable period), diagonal wave (and variable),
# slide (and variable), noise, jitter, wander, spark
# (docs/ce_map_conversion.md, "Periodic functions"). Cosine is
# 0.5 + 0.5 cos 2 pi x, 1 at x = 0; diagonal is a triangle from 0 at x = 0;
# slide is frac(x). The variable-period forms use their nominal period, and
# noise, jitter and wander a smooth value noise at different rates. Spark
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
#define CE_WAVE(fn, x) ((fn) < 0.5 ? 1.0 : (fn) < 1.5 ? 0.0 : (fn) < 3.5 ? 0.5 + 0.5 * cos(6.2831853 * (x))     : (fn) < 5.5 ? 1.0 - abs(2.0 * frac(x) - 1.0) : (fn) < 7.5 ? frac(x) : (fn) < 8.5 ? CE_VNOISE((x) * 4.0)     : (fn) < 9.5 ? CE_HASH(floor((x) * 30.0)) : (fn) < 10.5 ? CE_VNOISE(x)     : (frac(x) < 0.35 ? smoothstep(0.0, 0.35, frac(x)) : 1.0 - smoothstep(0.35, 1.0, frac(x))))
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
    float3 amb = saturate(SunShare.rgb);
    float cosl = saturate(dot(normalize(N), normalize(SunDir)));
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
// must cancel, not flat ground's.
if (HasSunShare > 0.5) flat = max(dot(normalize(N), normalize(SunDir)), 0.05);
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

    # The base UV, transformed as CE does every pass of the surface: an
    # environment's texture scrolling (BaseUAnim/BaseVAnim, no phase), a
    # model's map scale and u, v and rotation animation (STAGE_UV_CODE). The
    # detail, micro, bump and self-illumination maps scale the transformed UV.
    time0 = g.node(unreal.MaterialExpressionTime)
    zero = g.node(unreal.MaterialExpressionConstant, x=-1900, r=0.0)
    uv0 = g.custom(STAGE_UV_CODE, [
        ("UV", g.uv(0), ""), ("Time", time0, ""), ("Depth", zero, ""),
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
    primary = g.texture("Primary", grey, scaled("PrimaryScale", "PrimaryAspect"))
    secondary = g.texture("Secondary", grey, scaled("SecondaryScale", "SecondaryAspect"))
    micro = g.texture("Micro", grey, scaled("MicroScale", "MicroAspect"))
    bump = g.texture("Bump", flat, scaled("BumpScale"))
    lightmap = g.texture("Lightmap", white, g.uv(1))
    # tools: crates/ue-texture/examples/lightmap_bake.rs, on the same UVs.
    bake = g.texture("Bake", white, g.uv(1))
    has_bake = g.scalar("HasBake", 0.0)
    # The solver's sun shares on the lightmap's UVs (ce_material_spec.py
    # SunShare, from `mjolnir level lightmaps`): R the sun's share of the
    # texel's light, G its share with the sun unblocked.
    sunshare = g.texture("SunShare", white, g.uv(1))
    has_sunshare = g.scalar("HasSunShare", 0.0)
    # A placed object's lightmap is its block of the object lighting page
    # (tools/level/merge_ce_scene.py): its light in the first of eight
    # columns, its reflection tint in the second, change colours A-D in the
    # third to sixth. These read the same texture beside the first.
    obj_tint = g.texture("Lightmap", white, g.custom("return UV + float2(0.125, 0.0);", [("UV", g.uv(1), "")],
                                                      output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                                                      description="object reflection tint"))
    obj_cc = g.texture("Lightmap", white, g.custom("return UV + float2(CCOffset, 0.0);",
                                                    [("UV", g.uv(1), ""), ("CCOffset", g.scalar("CCOffset", 0.25), "")],
                                                    output=unreal.CustomMaterialOutputType.CMOT_FLOAT2,
                                                    description="object change colour"))
    # shader_model's multipurpose map (read only with HasMulti).
    multi = g.texture("Multipurpose", white, uv0)
    self_illum = g.texture("SelfIllumMap", white, scaled("SelfIllumScale"))
    # A model's self-illumination colour source: a change colour of the
    # object lighting page, like CCOffset's.
    si_cc = g.texture("Lightmap", white, g.custom("return UV + float2(SICCOffset, 0.0);",
                                                   [("UV", g.uv(1), ""), ("SICCOffset", g.scalar("SICCOffset", 0.25), "")],
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
    bake_range = g.custom(BAKE_RANGE_CODE, [("Bake", bake_obj, ""), ("UV", g.uv(1), ""),
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
    inputs = [(f"M{i}", s, "RGBA") for i, s in enumerate(samples)]
    inputs += [(f"S{i}", misc, "") for i, misc in enumerate(miscs)]
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
if TRIAL_ROOT:
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
    unreal.log("MJOLNIR CE materials built")
