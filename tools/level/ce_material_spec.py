#!/usr/bin/env python3
"""Describe a staged CE map's materials for the Unreal project to build.

    ce_material_spec.py <staging dir> <map name> <spec.json> [scene.gltf ...] [--code CODE]
                        [--bake DIR] [--lightmaps DIR]

With --lightmaps, a lightmap page is taken from that directory (`mjolnir
level lightmaps`: the shipped page's name at a multiple of its size) when it
is there, and from the staging otherwise.

With --code, the map's packages go under /Game/MJOLNIR/Maps/<CODE> and cook
into a chunk of their own (`cook_chunk`), which a map pack ships as
MJOLNIRCOOK-<CODE> (docs/map_distribution.md); a code is unique on the hub,
so two packs never claim the same package. Without it, the older
/Game/MJOLNIR/Levels/<map name>, cooked with the shared chunk 988.

Reads the halo2ue staging (materials.json, textures/, and bsp/bsp_0.gltf or
the scene tools/level/merge_ce_scene.py made from it, scenery and sky
included) and
writes the spec unreal/MJOLNIRMaterials/Scripts/build_ce_level.py consumes (every bitmap
a surface samples, lightmap pages included, to import and cook), and one
material per glTF material, i.e. per (shader, lightmap page), since the page
is a texture parameter. Each is a parent - one of the masters
Scripts/build_ce_materials.py makes - and the parameters that carry the CE
shader's fields over one to one (docs/ce_map_conversion.md, "Materials").
They are not cooked as instances (the fork's material instance serialization
differs from stock): the level loader makes each a dynamic instance.

Bitmaps import from the DDS halo2ue-export writes beside each PNG when there
is one: it holds the bitmap's own mip chain, and CE's detail maps fade their
smaller levels to neutral grey, which a regenerated chain would not.

The spec also lists the mesh slots in slot order: `{"name": <slot name>,
"pattern": "<gltf material>$", "material": <runtime material>}`, for
mesh_rewrite's --material and the level file.
"""
import glob
import json
import math
import os
import re
import struct
import sys

CE = "/Game/MJOLNIR/CE"

# The baked corners' strength (lightmap_bake's ambient occlusion, a power on
# the lightmap: 0 none, 1 as traced). Blood Gulch was approved at 2.5 and
# found a little dark across the maps (2026-10-04); with lightmap_bake's knee
# and curve (2026-10-06), 2.0 turned Blood Gulch's base interiors black at
# the wall foot, and 1.4 was chosen there.
BAKE_AO = 1.4

# shader_transparent_* framebuffer blend functions: alpha blend, multiply,
# double multiply, add, subtract, component min, component max, alpha-multiply
# add. Unreal has no subtract/min/max blend; those fall back to alpha blending.
BLEND_PARENTS = {0: "Alpha", 1: "Mul", 2: "Mul", 3: "Add", 4: "Alpha", 5: "Alpha", 6: "Alpha", 7: "Add"}


WU_TO_CM = 304.8


def write_cube_dds(path, faces):
    """An uncompressed BGRA8 cube map DDS from six face PNGs in D3D face order
    (+X, -X, +Y, -Y, +Z, -Z), the order CE's cube map data uses. Unreal
    imports it as a TextureCube."""
    from PIL import Image
    imgs = [Image.open(f).convert("RGBA") for f in faces]
    size = imgs[0].size[0]
    header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIIII12x",
        b"DDS ", 124, 0x1007, size, size, size * 4, 0, 0, bytes(44),
        32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
        0x1008, 0xFE00, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(header)
        for im in imgs:
            r, g, b, a = im.resize((size, size)).split()
            f.write(Image.merge("RGBA", (b, g, r, a)).tobytes())


def sky_fog(staging):
    """The scenario sky's outdoor fog as material parameters (cm), or {}."""
    try:
        placement = json.load(open(os.path.join(staging, "placement.json"), encoding="utf-8"))
    except FileNotFoundError:
        return {}
    for e in placement.get("entries", []):
        fog = e.get("outdoor_fog") if e.get("kind") == "sky" else None
        if fog and fog.get("max_density", 0) > 0:
            return {"scalars": {"FogDensity": fog["max_density"],
                                "FogStart": fog["start_distance"] * WU_TO_CM,
                                "FogOpaque": fog["opaque_distance"] * WU_TO_CM},
                    "vectors": {"FogColor": list(fog["color"]) + [1.0]}}
    return {}


def planar_fog(staging, delta):
    """The map's planar fog (ce_fog.py's fog.json) as material parameters, or
    {}: the plane in Unreal centimetres (normal, offset), the colour, and
    (maximum density, opaque distance cm, opaque depth cm, on). One plane per
    map is all the stock maps have; a second is left out."""
    try:
        planes = json.load(open(os.path.join(staging, "fog.json"), encoding="utf-8")).get("planes") or []
    except FileNotFoundError:
        return {}
    if not planes:
        return {}
    p = planes[0]
    i, j, k, d = p["plane"]
    n = [i, -j, k]
    p0 = [(i * d + delta[0]) * WU_TO_CM, -(j * d + delta[1]) * WU_TO_CM, (k * d + delta[2]) * WU_TO_CM]
    return {"PlanarFogPlane": n + [sum(a * b for a, b in zip(n, p0))],
            "PlanarFogColor": list(p["color"]) + [1.0],
            "PlanarFogParams": [p["max_density"], max(p["opaque_distance"], 1e-3) * WU_TO_CM,
                                max(p["opaque_depth"], 1e-3) * WU_TO_CM, 1.0]}


def master(name):
    return f"{CE}/{name}.{name}"


def asset_name(prefix, stem):
    """A package-safe asset name. A trailing `_<digits>` is how Unreal writes
    an FName's instance number, so `T_x_1` is stored as `T_x` number 2, and
    the game's package lookup does not find such a package by its path (every
    lightmap page past the first went missing); `_n<digits>` keeps it a plain
    name."""
    name = prefix + re.sub(r"[^A-Za-z0-9_]", "_", stem)
    return re.sub(r"_(\d+)$", r"_n\1", name)


def cook_chunk(code):
    """The cook chunk of a map's own packages: one per code, never 988 (the
    masters and their shader library) or a shipped chunk."""
    return 10000 + int(code, 36)


def model_shader(entry, s, texture):
    """shader_model's own terms on the environment master (ModelShader): the
    multipurpose map's masks (PC order: r auxiliary, g self-illumination,
    b reflection, a change colour), the detail mask, "detail after
    reflection" (flag bit 0), the object's change colour, the animated
    self-illumination colour and the reflection's distance fade. The
    reflection's tints and brightnesses come through the shared specular and
    reflection fields."""
    model = s.get("model") or {}
    sc, vec = entry["scalars"], entry["vectors"]
    sc["ModelShader"] = 1.0
    multi = texture(model.get("multipurpose"))
    if multi:
        entry["textures"]["Multipurpose"] = multi
        sc["HasMulti"] = 1.0
    sc["DetailMask"] = float(model.get("detail_mask", 0))
    sc["DetailAfter"] = 1.0 if s.get("shader_flags", 0) & 1 else 0.0
    source = model.get("change_color_source", 0)
    if 1 <= source <= 4:
        sc["ModelCC"] = 1.0
        # Columns 2-5 of the object lighting page hold change colours A-D.
        sc["CCOffset"] = (1 + source) / 8.0
    si = model.get("self_illum") or {}
    lower, upper = si.get("lower") or [0, 0, 0], si.get("upper") or [0, 0, 0]
    if multi and (any(lower) or any(upper)):
        sc["HasModelSelfIllum"] = 1.0
        vec["SelfOff1"] = list(lower) + [1.0]
        vec["SelfOn1"] = list(upper) + [1.0]
        vec["SelfAnim1"] = [si.get("function", 0), si.get("period", 1.0), 0.0, 0.0]
    if model.get("reflection_cutoff"):
        # World units to centimetres, as the master's pixel depth reads.
        sc["ReflFalloff"] = model.get("reflection_falloff", 0.0) * 304.8
        sc["ReflCutoff"] = model["reflection_cutoff"] * 304.8


def environment_tag(entry, s, cls):
    """The shader_environment and shader_model fields beyond the summary
    (halo2ue's `tag`, docs/ce_map_conversion.md, "Materials"): the base UV
    transform (an environment's texture scrolling; a model's map scale and
    u, v and rotation animation), the material colour, the detail maps'
    rescale and v scale, the reflection's lightmap brightness mask and a
    model's self-illumination colour source."""
    t = s.get("tag")
    if not t:
        return
    sc, vec = entry["scalars"], entry["vectors"]
    if cls == "senv":
        # Texture scrolling: no phase, no source, base-map repeats.
        vec["BaseUAnim"] = [t.get("u_animation_function", 0), t.get("u_animation_period", 0.0), 0.0,
                            t.get("u_animation_scale", 0.0)]
        vec["BaseVAnim"] = [t.get("v_animation_function", 0), t.get("v_animation_period", 0.0), 0.0,
                            t.get("v_animation_scale", 0.0)]
        mc = t.get("material_color") or [1.0, 1.0, 1.0]
        vec["MaterialColor"] = list(mc) + [1.0]
        # Diffuse flag bit 0, "rescale detail maps": each detail scale also
        # takes the base map's size over its own, per axis.
        base = t.get("base_map") or {}
        for key, param in (("primary_detail_map", "Primary"), ("secondary_detail_map", "Secondary"),
                           ("micro_detail_map", "Micro")):
            det = t.get(key) or {}
            if t.get("diffuse_flags", 0) & 1 and base.get("width") and det.get("width"):
                u = base["width"] / det["width"]
                v = base["height"] / det["height"]
                sc[f"{param}Scale"] = sc.get(f"{param}Scale", 1.0) * u
                sc[f"{param}Aspect"] = v / u
        # Reflections dim in dark lightmap areas below this scale.
        lbs = t.get("lightmap_brightness_scale", 1.0)
        if 0.0 <= lbs < 1.0:
            sc["LightmapReflScale"] = lbs
    elif cls == "soso":
        vec["BaseXform"] = [t.get("map_u_scale") or 1.0, t.get("map_v_scale") or 1.0, 0.0, 0.0]
        for axis, key in (("U", "u"), ("V", "v"), ("R", "rotation")):
            vec[f"Base{axis}Anim"] = [t.get(f"{key}_animation_function", 0), t.get(f"{key}_animation_period", 0.0),
                                      t.get(f"{key}_animation_phase", 0.0), t.get(f"{key}_animation_scale", 0.0)]
        centre = t.get("rotation_animation_center") or [0.0, 0.0]
        vec["BaseMisc"] = [0.0, centre[0], centre[1], 0.0]
        if t.get("detail_map_v_scale"):
            sc["PrimaryAspect"] = t["detail_map_v_scale"]
        # The self-illumination colour takes a change colour (A-D).
        source = t.get("self_illumination_color_source", 0)
        if 1 <= source <= 4 and sc.get("HasModelSelfIllum"):
            sc["SICCOffset"] = (1 + source) / 8.0
            sc["HasSICC"] = 1.0


def glass(entry, s, texture, cube, halo):
    """shader_transparent_glass (docs/ce_map_conversion.md, "Glass"): the pass
    this copy of the surface draws (merge_ce_scene.py `extra_passes`): tint
    (multiply), reflection (add), or the surface itself, the diffuse pass
    (alpha blend; nothing when the shader has no diffuse or detail map).
    Flag bit 2 (two-sided) picks the master variant."""
    t = s["tag"]
    sc, vec, tex = entry["scalars"], entry["vectors"], entry["textures"]
    flags = t.get("flags", 0)
    side = "TwoSided" if flags & 4 else ""
    pas = halo.get("pass")
    if pas == "tint":
        entry["parent"] = master(f"M_CE_GlassTint{side}")
        tm = texture((t.get("background_tint_map") or {}).get("file"))
        if tm:
            tex["TintMap"] = tm
        sc["TintScale"] = t.get("background_tint_map_scale") or 1.0
        vec["TintColor"] = list(t.get("background_tint_color") or [1, 1, 1]) + [1.0]
        return
    if pas == "reflection":
        entry["parent"] = master(f"M_CE_GlassReflection{side}")
        cube_map = cube((t.get("reflection_map") or {}).get("faces"))
        if cube_map:
            tex["ReflectionCube"] = cube_map
        bump = texture((t.get("bump_map") or {}).get("file"))
        if bump:
            tex["Bump"] = bump
            sc["HasBump"] = 1.0
        sc["BumpScale"] = t.get("bump_map_scale") or 1.0
        sc["GlassFlags"] = float(flags)
        # A bumped cube map draws flat without a bump map, or when the bump
        # map is a specular mask; a dynamic mirror (2) has no mirror here.
        rtype = t.get("reflection_type", 0)
        sc["ReflectionType"] = 0.0 if rtype == 0 and bump and not flags & 8 else 1.0
        sc["PerpBrightness"] = t.get("perpendicular_brightness", 0.0)
        sc["ParaBrightness"] = t.get("parallel_brightness", 0.0)
        vec["PerpTint"] = list(t.get("perpendicular_tint_color") or [1, 1, 1]) + [1.0]
        vec["ParaTint"] = list(t.get("parallel_tint_color") or [1, 1, 1]) + [1.0]
        return
    diffuse = texture((t.get("diffuse_map") or {}).get("file"))
    detail = texture((t.get("diffuse_detail_map") or {}).get("file"))
    if not diffuse and not detail:
        entry["parent"] = master(f"M_CE_TransparentAdd{side}")
        vec["Tint"] = [0.0, 0.0, 0.0, 1.0]
        return
    entry["parent"] = master(f"M_CE_GlassDiffuse{side}")
    if diffuse:
        tex["Diffuse"] = diffuse
    if detail:
        tex["Detail"] = detail
    sc["DiffuseScale"] = t.get("diffuse_map_scale") or 1.0
    sc["DetailScale"] = t.get("diffuse_detail_map_scale") or 1.0
    lm = texture(halo.get("lightmap_texture"), lightmap=True)
    if lm:
        tex["Lightmap"] = lm
        sc["HasLightmap"] = 1.0


def water(entry, s, texture, cube, halo):
    """shader_transparent_water (docs/ce_map_conversion.md, "Water"): the
    rippled cube reflection added into the frame (M_CE_Water), replacing it
    for sky water (M_CE_WaterSky), and with flag 1 the base map's colour
    multiplied into the frame first, on the copy of the surface
    merge_ce_scene.py makes for it (M_CE_WaterBackground). Every ripple
    layer (contribution, angle, velocity, offset, repeats, bitmap index),
    the global ripple animation and the ripple mipmap fade come from the
    tag (halo2ue's `tag`); a staging without it keeps the summary's one
    ripple."""
    t = s.get("tag") or {}
    w = s.get("water") or {}
    sc, vec, tex = entry["scalars"], entry["vectors"], entry["textures"]
    flags = t.get("flags", w.get("flags", 0))
    base = texture((t.get("base_map") or {}).get("file") or s.get("base_map"))
    if base:
        tex["Base"] = base
    if halo.get("pass") == "background":
        entry["parent"] = master("M_CE_WaterBackground")
        sc["WaterFlags"] = float(flags)
        return
    sky = bool(halo.get("sky"))
    entry["parent"] = master("M_CE_WaterSky" if sky else "M_CE_Water")
    # Sky water replaces the frame: no base alpha mask (that pass writes
    # only the destination alpha the reflection would have blended by).
    sc["WaterFlags"] = float(flags & ~1 if sky else flags)
    faces = (t.get("reflection_map") or {}).get("faces") or (s.get("reflection") or {}).get("cube_map")
    cube_map = cube(faces)
    if cube_map:
        tex["ReflectionCube"] = cube_map
    sc["PerpBrightness"] = t.get("view_perpendicular_brightness", w.get("view_perp_brightness", 0.3))
    sc["ParaBrightness"] = t.get("view_parallel_brightness", w.get("view_para_brightness", 1.0))
    vec["PerpTint"] = list(t.get("view_perpendicular_tint_color") or w.get("view_perp_tint") or [1, 1, 1]) + [1.0]
    vec["ParaTint"] = list(t.get("view_parallel_tint_color") or w.get("view_para_tint") or [1, 1, 1]) + [1.0]
    vec["RippleGlobal"] = [t.get("ripple_animation_angle", w.get("ripple_animation_angle", 0.0)),
                           t.get("ripple_animation_velocity", w.get("ripple_animation_velocity", 0.0)),
                           t.get("ripple_scale") or w.get("ripple_scale") or 1.0, 0.0]
    vec["RippleMip"] = [float(min(max(t.get("ripple_mipmap_levels", 1), 1), 4)),
                        t.get("ripple_mipmap_fade_factor", 0.0), t.get("ripple_mipmap_detail_bias", 0.0), 0.0]
    ripples = t.get("ripples") or []
    files = t.get("ripple_map_files") or {}
    if not ripples:
        ripples = [{"contribution_factor": 1.0, "map_repeats": 1, "map_index": 0}]
        files = {"0": {"file": w.get("ripple_map")}}
    for k, r in enumerate(ripples[:4]):
        vec[f"Ripple{k}"] = [r.get("contribution_factor", 0.0), r.get("animation_angle", 0.0),
                             r.get("animation_velocity", 0.0), float(max(r.get("map_repeats", 1), 1))]
        off = r.get("map_offset") or [0.0, 0.0]
        vec[f"Ripple{k}Offset"] = [off[0], off[1], 0.0, 0.0]
        f = (files.get(str(max(r.get("map_index", 0), 0))) or {}).get("file")
        rt = texture(f)
        if rt:
            tex[f"RippleMap{k}"] = rt


def chicago(entry, s, texture, cube):
    """shader_transparent_chicago(_extended) on the transparent masters, every
    field of the tag (halo2ue's `tag`, docs/ce_map_conversion.md,
    "Transparent shaders"): each map with its transform, animation and flags,
    the colour/alpha chain, the first map type, the framebuffer blend and
    fade, the alpha-test, decal and two-sided flags. An extended shader draws
    its four-stage maps, or its two-stage ones when it has none. A map with
    no bitmap keeps its place (CE binds a white default)."""
    t = s.get("tag") or {}
    blend = t.get("framebuffer_blend_function", s.get("framebuffer_blend_function", 0))
    # A staging from before halo2ue wrote `tag` has the flags as shader_flags.
    flags = t.get("flags", s.get("shader_flags", 0))
    # Two-sided (bit 2) is a master variant: an instance cannot change it.
    variant = "TwoSided" if flags & 4 else ""
    entry["parent"] = master(f"M_CE_Transparent{BLEND_PARENTS.get(blend, 'Alpha')}{variant}")
    maps = t.get("maps") or t.get("four_stage_maps") or t.get("two_stage_maps") or []
    if not t:
        # A staging from before halo2ue wrote `tag`: its stage summary.
        for st in s.get("chicago_stages") or []:
            u, v = st.get("u_animation") or [0, 0, 0, 0], st.get("v_animation") or [0, 0, 0, 0]
            maps.append({"map": {"file": st.get("map")}, "color_function": st.get("color_function", 0),
                         "alpha_function": st.get("alpha_function", 0),
                         "map_u_scale": st.get("u_scale"), "map_v_scale": st.get("v_scale"),
                         "map_u_offset": st.get("u_offset", 0.0), "map_v_offset": st.get("v_offset", 0.0),
                         "map_rotation": st.get("rotation", 0.0),
                         "u_animation_function": u[0], "u_animation_period": u[1],
                         "u_animation_phase": u[2], "u_animation_scale": u[3],
                         "v_animation_function": v[0], "v_animation_period": v[1],
                         "v_animation_phase": v[2], "v_animation_scale": v[3]})
    maps = maps[:4]
    sc, vec, tex = entry["scalars"], entry["vectors"], entry["textures"]
    if not maps:
        maps = [{"map": {"file": s.get("base_map")}}]
    functions, alpha_functions = [0.0] * 4, [0.0] * 4
    for i, m in enumerate(maps):
        tex[f"Map{i}"] = texture((m.get("map") or {}).get("file"))
        vec[f"Stage{i}Xform"] = [m.get("map_u_scale") or 1.0, m.get("map_v_scale") or 1.0,
                                 m.get("map_u_offset", 0.0), m.get("map_v_offset", 0.0)]
        for axis, key in (("U", "u"), ("V", "v"), ("R", "rotation")):
            vec[f"Stage{i}{axis}Anim"] = [m.get(f"{key}_animation_function", 0), m.get(f"{key}_animation_period", 0.0),
                                          m.get(f"{key}_animation_phase", 0.0), m.get(f"{key}_animation_scale", 0.0)]
        centre = m.get("rotation_animation_center") or [0.0, 0.0]
        vec[f"Stage{i}Misc"] = [m.get("map_rotation", 0.0), centre[0], centre[1], float(m.get("flags", 0))]
        functions[i] = m.get("color_function", 0)
        alpha_functions[i] = m.get("alpha_function", 0)
    vec["StageColorFunctions"] = functions
    vec["StageAlphaFunctions"] = alpha_functions
    sc["StageCount"] = len(maps)
    sc["ChicagoFlags"] = float(flags)
    sc["BlendFunction"] = float(blend)
    sc["FadeMode"] = float(t.get("framebuffer_fade_mode", 0))
    first = t.get("first_map_type", 0)
    if first:
        cube_map = cube((maps[0].get("map") or {}).get("faces"))
        if cube_map:
            sc["FirstMapType"] = float(first)
            tex["Map0Cube"] = cube_map
    if blend == 2:
        vec["Tint"] = [2.0, 2.0, 2.0, 1.0]
    if blend == 7:
        sc["Premultiply"] = 1.0
    if not any(tex.get(f"Map{i}") for i in range(len(maps))) and not tex.get("Map0Cube"):
        # No bitmap on any map (Danger Canyon's white_light: a null
        # reference). CE draws nothing there; the master's default white map
        # made it a solid white box. A zero tint adds nothing, and the
        # additive master keeps it out of the alpha.
        entry["parent"] = master(f"M_CE_TransparentAdd{variant}")
        sc["BlendFunction"] = 3.0
        vec["Tint"] = [0.0, 0.0, 0.0, 1.0]
    for k in [k for k, v in tex.items() if not v]:
        del tex[k]


def argb_to_rgba(c):
    """A tag's ARGB colour (a, r, g, b) as RGBA."""
    c = list(c or [0.0, 0.0, 0.0, 0.0])
    return [c[1], c[2], c[3], c[0]]


def generic(entry, tag_path, texture, textures_dir):
    """MCC's shader_transparent_generic for a chicago shader the PC port made
    of it (mcc_tags.py; docs/ce_map_conversion.md, "MCC's generic shaders"),
    on the same transparent masters (GENERIC_CODE): each map's bitmap from
    MCC's tags (exported beside the map's own as `mcc_...`), transform and
    animation as a chicago map's, and every combiner stage. False, and the
    entry untouched, when MCC has no such shader or a map's bitmap cannot be
    exported (a cube map, a missing tag): the chicago shader is drawn."""
    import mcc_tags
    if os.environ.get("MCC_GENERIC", "1") == "0" or not tag_path:
        return False
    try:
        t = mcc_tags.generic_shader(tag_path)
    except (OSError, ValueError, struct.error) as e:
        print(f"  MCC generic {tag_path}: {e}", file=sys.stderr)
        return False
    if not t or not t.get("stages") or t.get("first_map_type", 0):
        return False
    # A stage whose colour 0 follows one of the object's functions (source A-D
    # out: the field generator's shield, the power-ups, the holo controls)
    # needs the object's live state, which the material cannot read: drawn
    # without it the shield came out white or red where Halo PC's chicago
    # stand-in and MCC both draw it purple (Gephyrophobia, 2026-10-09). The
    # chicago shader is drawn instead.
    if any(st.get("color0_source") for st in t["stages"]):
        return False
    maps = (t.get("maps") or [])[:4]
    files = []
    for m in maps:
        ref = (m.get("map") or {}).get("path")
        if not ref:
            files.append(None)
            continue
        stem = mcc_tags.stem_for(ref)
        png = stem + ".png"
        if not os.path.exists(os.path.join(textures_dir, png)):
            png = mcc_tags.write_bitmap(ref, textures_dir, stem)
        if not png:
            print(f"  MCC generic {tag_path}: bitmap {ref} not exported, drawn as chicago", file=sys.stderr)
            return False
        files.append(png)
    blend = t.get("framebuffer_blend_function", 0)
    flags = t.get("flags", 0)
    variant = "TwoSided" if flags & 4 else ""
    entry["parent"] = master(f"M_CE_Transparent{BLEND_PARENTS.get(blend, 'Alpha')}{variant}")
    sc, vec, tex = entry["scalars"], entry["vectors"], entry["textures"]
    for i, (m, png) in enumerate(zip(maps, files)):
        if png:
            tex[f"Map{i}"] = texture(png)
        vec[f"Stage{i}Xform"] = [m.get("map_u_scale") or 1.0, m.get("map_v_scale") or 1.0,
                                 m.get("map_u_offset", 0.0), m.get("map_v_offset", 0.0)]
        for axis, key in (("U", "u"), ("V", "v"), ("R", "rotation")):
            vec[f"Stage{i}{axis}Anim"] = [m.get(f"{key}_animation_function", 0), m.get(f"{key}_animation_period", 0.0),
                                          m.get(f"{key}_animation_phase", 0.0), m.get(f"{key}_animation_scale", 0.0)]
        centre = m.get("rotation_animation_center") or [0.0, 0.0]
        # A generic map's flags are unfiltered, u-clamped, v-clamped (bits
        # 0-2); the masters read a chicago map's (clamps at bits 2 and 3).
        mf = m.get("flags", 0)
        vec[f"Stage{i}Misc"] = [m.get("map_rotation", 0.0), centre[0], centre[1],
                                float((mf & 1) | ((mf & 6) << 1))]
    stages = t["stages"][:7]
    for s, st in enumerate(stages):
        packed = lambda kind: [float(st[f"{kind}_input_{x}"] + 32 * st[f"{kind}_input_{x}_mapping"]) for x in "abcd"]
        vec[f"GenCI{s}"] = packed("color")
        vec[f"GenAI{s}"] = packed("alpha")
        vec[f"GenCO{s}"] = [float(st["color_output_ab"] + 16 * st["color_output_ab_function"]),
                            float(st["color_output_cd"] + 16 * st["color_output_cd_function"]),
                            float(st["color_output_ab_cd_mux_sum"]), float(st["color_output_mapping"])]
        vec[f"GenAO{s}"] = [float(st["alpha_output_ab"]), float(st["alpha_output_cd"]),
                            float(st["alpha_output_ab_cd_mux_sum"]), float(st["alpha_output_mapping"])]
        vec[f"GenK0{s}"] = argb_to_rgba(st["color0_animation_lower_bound"])
        vec[f"GenK0Hi{s}"] = argb_to_rgba(st["color0_animation_upper_bound"])
        vec[f"GenK1{s}"] = argb_to_rgba(st["color1"])
        vec[f"GenKA{s}"] = [float(st["color0_animation_function"]), st["color0_animation_period"],
                            float(st["flags"]), 0.0]
    sc["GenericStages"] = float(len(stages))
    sc["StageCount"] = float(len(maps))
    sc["ChicagoFlags"] = float(flags)
    sc["BlendFunction"] = float(blend)
    # MCC's generic pixel shader applies no framebuffer fade of its own; a
    # stage that wants one reads v1.
    sc["FadeMode"] = 0.0
    if blend == 2:
        vec["Tint"] = [2.0, 2.0, 2.0, 1.0]
    if blend == 7:
        sc["Premultiply"] = 1.0
    for k in [k for k, v in tex.items() if not v]:
        del tex[k]
    return True


def device(entry, motion, part, mesh, delta):
    """A machine's moving part (merge_ce_scene.py device_motion) on the
    device variant of its master: the motion in Unreal centimetres, and the
    bounds scale its mesh needs to stay drawn wherever the part goes (a
    World Position Offset moves it outside the mesh's own bounds). `part`
    and `mesh` are the glTF boxes (min, max) of the part and of its mesh."""
    def ue(v, offset=True):
        # glTF metres (x, y, z) are Unreal (x, z, y) x 100; the map's own
        # move (its sbsp transform's delta, CE world units) on positions.
        out = [v[0] * 100.0, v[2] * 100.0, v[1] * 100.0]
        if offset:
            out = [out[0] + delta[0] * 304.8, out[1] - delta[1] * 304.8, out[2] + delta[2] * 304.8]
        return out
    entry["parent"] = master(entry["parent"].rsplit(".", 1)[-1] + "Device")
    vec = entry["vectors"]
    vec["DevicePivot"] = ue(motion["pivot"]) + [0.0]
    vec["DeviceT0"] = ue(motion["t0"], False) + [0.0]
    vec["DeviceT1"] = ue(motion["t1"], False) + [0.0]
    vec["DeviceMotion"] = [motion["s0"], motion["s1"], motion["period"], motion["position"]]
    pivot = [motion["pivot"][i] for i in range(3)]
    lo, hi = [list(v) for v in mesh]
    for sc in (motion["s0"], motion["s1"], 1.0):
        for t in (motion["t0"], motion["t1"]):
            for corner in (part[0], part[1]):
                for i in range(3):
                    v = pivot[i] + (corner[i] - pivot[i]) * sc + t[i]
                    lo[i], hi[i] = min(lo[i], v), max(hi[i], v)
    centre = [(a + b) / 2 for a, b in zip(*mesh)]
    half = [max((b - a) / 2, 1.0) for a, b in zip(*mesh)]
    need = max(max(c - l, h - c) / e for c, l, h, e in zip(centre, lo, hi, half))
    entry["bounds_scale"] = round(max(1.0, need) + 0.05, 2)


def gltf_boxes(scene):
    """Each material's box and the whole mesh's, glTF metres, from the
    POSITION accessors' bounds."""
    g = json.load(open(scene, encoding="utf-8"))
    boxes, lo, hi = {}, [math.inf] * 3, [-math.inf] * 3
    for mesh in g.get("meshes", []):
        for prim in mesh["primitives"]:
            acc = g["accessors"][prim["attributes"]["POSITION"]]
            if "min" not in acc:
                continue
            name = g["materials"][prim["material"]]["name"] if "material" in prim else None
            b = boxes.setdefault(name, [[math.inf] * 3, [-math.inf] * 3])
            for i in range(3):
                b[0][i], b[1][i] = min(b[0][i], acc["min"][i]), max(b[1][i], acc["max"][i])
                lo[i], hi[i] = min(lo[i], acc["min"][i]), max(hi[i], acc["max"][i])
    return boxes, (lo, hi)


def main():
    args = sys.argv[1:]
    code = None
    if "--code" in args:
        i = args.index("--code")
        code = args[i + 1].upper()
        del args[i:i + 2]
    bake_dir = None
    if "--bake" in args:
        i = args.index("--bake")
        bake_dir = args[i + 1]
        del args[i:i + 2]
    lightmaps_dir = None
    if "--lightmaps" in args:
        i = args.index("--lightmaps")
        lightmaps_dir = args[i + 1]
        del args[i:i + 2]
    staging, name, dest = args[0:3]
    scenes = args[3:] or [os.path.join(staging, "bsp", "bsp_0.gltf")]
    textures_dir = os.path.join(staging, "textures")
    # The materials of every mesh, each once, in mesh then slot order.
    gltf = {"materials": []}
    seen_names = set()
    boxes = {}
    for scene in scenes:
        parts, mesh_box = gltf_boxes(scene)
        for m in json.load(open(scene, encoding="utf-8"))["materials"]:
            if m["name"] not in seen_names:
                seen_names.add(m["name"])
                gltf["materials"].append(m)
                if m["name"] in parts:
                    boxes[m["name"]] = (parts[m["name"]], mesh_box)
    # The map's own move, CE world units (convert_ce_map.sh writes the
    # transform beside the spec): machines' pivots are world positions.
    delta = [0.0, 0.0, 0.0]
    transform = os.path.join(os.path.dirname(os.path.abspath(dest)), f"{name}.sbsp.transform.json")
    if os.path.exists(transform):
        delta = json.load(open(transform, encoding="utf-8")).get("delta", delta)
    shaders = json.load(open(os.path.join(staging, "materials.json"), encoding="utf-8"))
    root = f"/Game/MJOLNIR/Maps/{code}" if code else f"/Game/MJOLNIR/Levels/{asset_name('', name)}"

    textures = {}
    fog = sky_fog(staging)
    planar = planar_fog(staging, delta)
    cubes_dir = os.path.join(os.path.dirname(os.path.abspath(dest)), "cubes")

    def cube(faces):
        """A cube map's asset name, its six faces written as one DDS."""
        if not faces or len(faces) != 6:
            return None
        paths = [os.path.join(textures_dir, f) for f in faces]
        if not all(os.path.exists(p) for p in paths):
            return None
        stem = re.sub(r"__face0$", "", os.path.splitext(faces[0])[0])
        t = asset_name("TC_", stem)
        if t not in textures:
            os.makedirs(cubes_dir, exist_ok=True)
            dds = os.path.join(cubes_dir, t + ".dds")
            write_cube_dds(dds, paths)
            textures[t] = {"file": dds, "name": t, "lightmap": False, "cube": True}
        return t

    lightmap_png = {}

    def texture(png, lightmap=False):
        """The asset name a bitmap imports as, or None if it was not staged."""
        if not png:
            return None
        path = os.path.join(textures_dir, png)
        if lightmap and lightmaps_dir and os.path.exists(os.path.join(lightmaps_dir, png)):
            path = os.path.join(lightmaps_dir, png)
            lightmap_png[asset_name("T_", os.path.splitext(png)[0])] = png
        if not os.path.exists(path):
            print(f"  missing {png}", file=sys.stderr)
            return None
        t = asset_name("T_", os.path.splitext(png)[0])
        mips = os.path.splitext(path)[0] + ".dds"
        if not lightmap and os.path.exists(mips):
            textures.setdefault(t, {"file": os.path.abspath(mips), "name": t, "lightmap": False, "mips": True})
        else:
            textures.setdefault(t, {"file": os.path.abspath(path), "name": t, "lightmap": lightmap})
        return t

    def sunshare(lightmap):
        """The sun's shares that go with a solved lightmap page (`mjolnir
        level lightmaps`: <page>_sunshare.png beside it), as a texture of its
        own, or None. The masters then draw CE's ambient and bounce and leave
        every sun shadow on the terrain to Unreal (HasSunShare)."""
        png = lightmap_png.get(lightmap)
        if not png or not lightmaps_dir:
            return None
        path = os.path.join(lightmaps_dir, os.path.splitext(png)[0] + "_sunshare.png")
        if not os.path.exists(path):
            return None
        t = lightmap + "_sunshare"
        textures.setdefault(t, {"file": os.path.abspath(path), "name": t, "lightmap": True})
        return t

    def baked(lightmap):
        """The bake that goes with a lightmap page (lightmap_bake names its
        output for the page's texture), as a texture of its own, or None."""
        png = os.path.join(bake_dir, lightmap + ".png") if bake_dir and lightmap else None
        if not png or not os.path.exists(png):
            return None
        t = lightmap + "_bake"
        textures.setdefault(t, {"file": os.path.abspath(png), "name": t, "bake": True})
        return t

    materials, slots = [], []
    for mat in gltf["materials"]:
        halo = mat.get("extras", {}).get("halo", {})
        mat_info = shaders.get(halo.get("material", ""), {})
        s = mat_info.get("shader")
        if s is None:
            continue
        mi = asset_name("", mat["name"])
        cls = s["shader_class"]
        entry = {"name": mi, "scalars": {}, "vectors": {}, "textures": {}}
        if cls in ("schi", "scex"):
            # MCC's original where the PC port left a chicago stand-in.
            if not generic(entry, mat_info.get("tag_path") or s.get("tag_path"), texture, textures_dir):
                chicago(entry, s, texture, cube)
        elif cls == "swat":
            water(entry, s, texture, cube, halo)
        elif cls == "sgla" and s.get("tag"):
            glass(entry, s, texture, cube, halo)
        else:
            flags = s.get("shader_flags", 0)
            if cls == "senv":
                # Alpha tested on the bump map's alpha.
                entry["parent"] = master(f"M_CE_Environment{'Masked' if flags & 1 else ''}")
            else:
                # Object shaders (soso, scenery): alpha tested on the base
                # map's alpha, and often two-sided (foliage). Their flag bits
                # mean other things, so none of the senv flag reads below
                # apply.
                masked = mat_info.get("alpha_mode") == "MASK"
                two_sided = mat_info.get("double_sided")
                entry["parent"] = master("M_CE_Environment" + ("Masked" if masked else "") +
                                         ("TwoSided" if two_sided else ""))
                if masked:
                    entry["scalars"]["AlphaFromBase"] = 1.0
                flags = 0
            d = s["detail"]
            bump = s.get("bump") or {}
            spec = s.get("specular") or {}
            si = s.get("self_illum") or {}
            maps = {
                "Base": texture(s["base_map"]),
                "Primary": texture(d.get("primary")),
                "Secondary": texture(d.get("secondary")),
                "Micro": texture(d.get("micro")),
                "Bump": texture(bump.get("map")),
                "Lightmap": texture(halo.get("lightmap_texture"), lightmap=True),
                "SelfIllumMap": texture(si.get("map")),
            }
            entry["textures"] = {k: v for k, v in maps.items() if v}
            bake = baked(maps["Lightmap"])
            if bake:
                entry["textures"]["Bake"] = bake
                entry["scalars"]["HasBake"] = 1.0
                entry["scalars"]["BakeAO"] = BAKE_AO
            share = sunshare(maps["Lightmap"])
            if share:
                entry["textures"]["SunShare"] = share
                entry["scalars"]["HasSunShare"] = 1.0
            sc = entry["scalars"]
            sc["Type"] = s.get("shader_type", 0)
            sc["Func"] = d.get("function", 0)
            sc["MicroFunc"] = d.get("micro_function", 0)
            sc["PrimaryScale"] = d.get("primary_scale") or 1.0
            sc["SecondaryScale"] = d.get("secondary_scale") or 1.0
            sc["MicroScale"] = d.get("micro_scale") or 1.0
            sc["BumpScale"] = bump.get("scale") or 1.0
            sc["SelfIllumScale"] = si.get("map_scale") or 1.0
            for key, param in (("Primary", "HasPrimary"), ("Secondary", "HasSecondary"), ("Micro", "HasMicro"),
                               ("Bump", "HasBump"), ("Lightmap", "HasLightmap"), ("SelfIllumMap", "HasSelfIllum")):
                sc[param] = 1.0 if maps[key] else 0.0
            sc["BumpIsSpecMask"] = 1.0 if flags & 2 else 0.0
            sf = spec.get("flags", 0)
            sc["Overbright"] = 1.0 if sf & 1 else 0.0
            sc["ExtraShiny"] = 1.0 if sf & 2 else 0.0
            sc["SpecLightmap"] = 1.0 if sf & 4 else 0.0
            sc["SpecBrightness"] = spec.get("brightness", 0.0)
            vec = entry["vectors"]
            vec["SpecPerpendicular"] = list(spec.get("perpendicular_color") or [1, 1, 1]) + [1.0]
            vec["SpecParallel"] = list(spec.get("parallel_color") or [1, 1, 1]) + [1.0]
            if maps["SelfIllumMap"]:
                for i, ch in enumerate(si.get("channels") or [{"on": si.get("on_color", [0, 0, 0])}]):
                    vec[f"SelfOn{i}"] = list(ch.get("on", [0, 0, 0])) + [1.0]
                    vec[f"SelfOff{i}"] = list(ch.get("off", [0, 0, 0])) + [1.0]
                    vec[f"SelfAnim{i}"] = [ch.get("function", 0), ch.get("period", 0.0), ch.get("phase", 0.0), 0.0]
            refl = s.get("reflection") or {}
            cube_map = cube(refl.get("cube_map"))
            if cube_map and (refl.get("perp_brightness", 0) > 0 or refl.get("para_brightness", 0) > 0):
                maps["ReflectionCube"] = cube_map
                entry["textures"]["ReflectionCube"] = cube_map
                sc["HasReflection"] = 1.0
                sc["ReflPerp"] = refl.get("perp_brightness", 0.0)
                sc["ReflPara"] = refl.get("para_brightness", 0.0)
                # A flat cube map, or a bumped type without a usable bump map.
                flat = refl.get("type") == 1 or not maps["Bump"] or flags & 2
                sc["ReflectFlat"] = 1.0 if flat else 0.0
            if cls == "soso":
                model_shader(entry, s, texture)
            environment_tag(entry, s, cls)
        motion = halo.get("device")
        leaf = entry.get("parent", "").rsplit(".", 1)[-1]
        if motion and leaf.startswith("M_CE_Transparent") and mat["name"] in boxes:
            device(entry, motion, *boxes[mat["name"]], delta)
        elif motion:
            print(f"  {mat['name']}: a moving machine part on {entry.get('parent')}, drawn still", file=sys.stderr)
        if halo.get("lightmap_index") == "objects":
            # A placed object: its light, reflection tint and change colours
            # are its block of the object lighting page (merge_ce_scene.py).
            entry["scalars"]["ObjectPage"] = 1.0
        if not halo.get("sky"):
            # CE fogs the level, not its sky.
            entry["scalars"].update(fog.get("scalars", {}))
            entry["vectors"].update(fog.get("vectors", {}))
            # The planar fog (ce_fog.py): the masters that draw it.
            if leaf.startswith(("M_CE_Environment", "M_CE_Transparent")):
                entry["vectors"].update(planar)
        entry["textures"] = {k: f"{root}/Textures/{v}.{v}" for k, v in entry["textures"].items() if v}
        runtime = {k: entry[k] for k in ("parent", "textures", "scalars", "vectors", "bounds_scale") if entry.get(k)}
        materials.append(entry)
        slots.append({"name": mi, "pattern": mat["name"].lower() + "$", "material": runtime})

    # The lens flares of the lights placed objects carry (halo2ue's
    # placement.json `lights`): gen_ce_level.py draws them with M_CE_Flare,
    # which samples the flare bitmap, so each is cooked with the map's own.
    placement_path = os.path.join(staging, "placement.json")
    if os.path.exists(placement_path):
        for e in json.load(open(placement_path, encoding="utf-8")).get("entries", []):
            for light in e.get("lights", []):
                for r in (light.get("lens_flare") or {}).get("reflections", []):
                    texture(r.get("bitmap"))

    # lightmap_bake's sun mask (<page 0>_sunmask.png): cooked with the map,
    # read by M_CE_SunLight through the level's environment.sun_mask
    # (gen_ce_level.py).
    for png in sorted(glob.glob(os.path.join(bake_dir, "*_sunmask.png"))) if bake_dir else []:
        t = os.path.splitext(os.path.basename(png))[0]
        textures.setdefault(t, {"file": os.path.abspath(png), "name": t, "sunmask": True})

    json.dump({"root": root, "chunk": cook_chunk(code) if code else None,
               "textures": list(textures.values()), "materials": materials, "slots": slots},
              open(dest, "w", encoding="utf-8"), indent=1)
    print(f"{name}: {len(textures)} texture(s), {len(materials)} material(s) -> {dest}")


if __name__ == "__main__":
    main()
