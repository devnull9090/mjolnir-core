#!/usr/bin/env python3
"""Describe a staged CE map's materials for the Unreal project to build.

    ce_material_spec.py <staging dir> <map name> <spec.json> [scene.gltf ...] [--code CODE]

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
import json
import os
import re
import struct
import sys

CE = "/Game/MJOLNIR/CE"

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


def main():
    args = sys.argv[1:]
    code = None
    if "--code" in args:
        i = args.index("--code")
        code = args[i + 1].upper()
        del args[i:i + 2]
    staging, name, dest = args[0:3]
    scenes = args[3:] or [os.path.join(staging, "bsp", "bsp_0.gltf")]
    textures_dir = os.path.join(staging, "textures")
    # The materials of every mesh, each once, in mesh then slot order.
    gltf = {"materials": []}
    seen_names = set()
    for scene in scenes:
        for m in json.load(open(scene, encoding="utf-8"))["materials"]:
            if m["name"] not in seen_names:
                seen_names.add(m["name"])
                gltf["materials"].append(m)
    shaders = json.load(open(os.path.join(staging, "materials.json"), encoding="utf-8"))
    root = f"/Game/MJOLNIR/Maps/{code}" if code else f"/Game/MJOLNIR/Levels/{asset_name('', name)}"

    textures = {}
    fog = sky_fog(staging)
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

    def texture(png, lightmap=False):
        """The asset name a bitmap imports as, or None if it was not staged."""
        if not png:
            return None
        path = os.path.join(textures_dir, png)
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
            blend = s.get("framebuffer_blend_function", 0)
            entry["parent"] = master(f"M_CE_Transparent{BLEND_PARENTS.get(blend, 'Alpha')}")
            stages = [st for st in (s.get("chicago_stages") or []) if st.get("map")][:4]
            if not stages:
                stages = [{"map": s["base_map"]}]
            sc, vec = entry["scalars"], entry["vectors"]
            functions = [0.0] * 4
            alpha_functions = [0.0] * 4
            for i, st in enumerate(stages):
                entry["textures"][f"Map{i}"] = texture(st["map"])
                vec[f"Stage{i}Xform"] = [st.get("u_scale") or 1.0, st.get("v_scale") or 1.0,
                                         st.get("u_offset", 0.0), st.get("v_offset", 0.0)]
                for axis in ("u", "v"):
                    fn, period, phase, scale = st.get(f"{axis}_animation") or [0, 0.0, 0.0, 0.0]
                    vec[f"Stage{i}{axis.upper()}Anim"] = [fn, period, phase, scale]
                if st.get("rotation"):
                    sc[f"Stage{i}Rotation"] = st["rotation"]
                functions[i] = st.get("color_function", 0)
                alpha_functions[i] = st.get("alpha_function", 0)
            vec["StageColorFunctions"] = functions
            vec["StageAlphaFunctions"] = alpha_functions
            sc["StageCount"] = len(stages)
            if blend == 2:
                vec["Tint"] = [2.0, 2.0, 2.0, 1.0]
            if blend == 7:
                sc["Premultiply"] = 1.0
            if not any(entry["textures"].get(f"Map{i}") for i in range(len(stages))):
                # No bitmap on any stage (Danger Canyon's white_light: a null
                # reference). CE draws nothing there; the master's default
                # white map made it a solid white box. A zero tint adds
                # nothing, and the additive master keeps it out of the alpha.
                entry["parent"] = master("M_CE_TransparentAdd")
                vec["Tint"] = [0.0, 0.0, 0.0, 1.0]
        elif cls == "swat":
            # shader_transparent_water (M_CE_Water): the reflection cube seen
            # through rippling, view-tinted water. Its base map is a mask,
            # never a colour: drawn as one, the sea was an opaque white sheet.
            w = s.get("water") or {}
            entry["parent"] = master("M_CE_Water")
            sc, vec = entry["scalars"], entry["vectors"]
            maps = {"Base": texture(s.get("base_map")), "Ripple": texture(w.get("ripple_map"))}
            entry["textures"] = {k: v for k, v in maps.items() if v}
            cube_map = cube((s.get("reflection") or {}).get("cube_map"))
            if cube_map:
                entry["textures"]["ReflectionCube"] = cube_map
            sc["PerpBrightness"] = w.get("view_perp_brightness", 0.3)
            sc["ParaBrightness"] = w.get("view_para_brightness", 1.0)
            vec["PerpTint"] = list(w.get("view_perp_tint") or [1, 1, 1]) + [1.0]
            vec["ParaTint"] = list(w.get("view_para_tint") or [1, 1, 1]) + [1.0]
            sc["RippleAngle"] = w.get("ripple_animation_angle", 0.0)
            sc["RippleVelocity"] = w.get("ripple_animation_velocity", 0.0)
            sc["RippleRepeat"] = w.get("ripple_scale") or 1.0
            # Water flag 0: "base map alpha modulates reflection".
            sc["AlphaFromBase"] = 1.0 if w.get("flags", 0) & 1 and s.get("base_map_has_alpha") else 0.0
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
                two_sided = masked and mat_info.get("double_sided")
                entry["parent"] = master("M_CE_EnvironmentMaskedTwoSided" if two_sided else
                                         "M_CE_EnvironmentMasked" if masked else "M_CE_Environment")
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
        if halo.get("lightmap_index") == "objects":
            # A placed object: its light, reflection tint and change colours
            # are its block of the object lighting page (merge_ce_scene.py).
            entry["scalars"]["ObjectPage"] = 1.0
        if not halo.get("sky"):
            # CE fogs the level, not its sky.
            entry["scalars"].update(fog.get("scalars", {}))
            entry["vectors"].update(fog.get("vectors", {}))
        entry["textures"] = {k: f"{root}/Textures/{v}.{v}" for k, v in entry["textures"].items() if v}
        runtime = {k: entry[k] for k in ("parent", "textures", "scalars", "vectors") if entry[k]}
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

    json.dump({"root": root, "chunk": cook_chunk(code) if code else None,
               "textures": list(textures.values()), "materials": materials, "slots": slots},
              open(dest, "w", encoding="utf-8"), indent=1)
    print(f"{name}: {len(textures)} texture(s), {len(materials)} material(s) -> {dest}")


if __name__ == "__main__":
    main()
