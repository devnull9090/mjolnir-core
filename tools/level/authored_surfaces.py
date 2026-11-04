"""Opt-in map-owned PBR surfaces, keyed by exact source shader tags.

The Blender source and native cook consume the same versioned JSON palette.
Nothing is applied to a conversion unless its surface library is supplied.
"""
import json
import math
import re
from pathlib import Path


def load_library(path):
    path = Path(path).resolve(strict=True)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("version") != 1 or not isinstance(doc.get("surfaces"), dict):
        raise ValueError("Unsupported authored surface library")
    result = {}
    tags = set()
    for role, source in doc["surfaces"].items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", role):
            raise ValueError(f"Invalid surface role: {role}")
        spec = dict(source)
        tag = spec["tag"].replace(chr(92), "/").lower()
        if tag in tags:
            raise ValueError(f"Duplicate surface tag: {tag}")
        tags.add(tag)
        spec["tag"] = tag
        for key in ("albedo", "roughness_map"):
            spec[key] = str((path.parent / spec[key]).resolve(strict=True))
        if "normal_map" in spec:
            if not isinstance(spec["normal_map"], str) or not spec["normal_map"]:
                raise ValueError(f"Invalid normal_map for {role}")
            spec["normal_map"] = str((path.parent / spec["normal_map"]).resolve(strict=True))
            convention = spec.get("normal_convention", "opengl")
            if convention not in ("opengl", "directx"):
                raise ValueError(f"Invalid normal_convention for {role}: {convention}")
            spec["normal_convention"] = convention
            strength = spec.get("normal_strength", 1.0)
            if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= 1:
                raise ValueError(f"Invalid normal_strength for {role}: {strength}")
            spec["normal_strength"] = float(strength)
        elif "normal_convention" in spec:
            raise ValueError(f"normal_convention requires normal_map for {role}")
        elif "normal_strength" in spec:
            raise ValueError(f"normal_strength requires normal_map for {role}")
        for key, length in (("tint", 3), ("roughness", 2)):
            values = spec[key]
            if len(values) != length or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in values):
                raise ValueError(f"Invalid {key} for {role}")
        if not (0 <= spec["roughness"][0] <= spec["roughness"][1] <= 1 and
                0 <= spec["metallic"] <= 1 and 0 <= spec["soften"] <= 1):
            raise ValueError(f"Invalid PBR range for {role}")
        result[role] = spec
    return result


def apply_library(library, root, materials, slots, gltf_materials, textures):
    surfaces = load_library(library)
    by_tag = {s["tag"]: (role,s) for role,s in surfaces.items()}
    by_name = {m["name"].lower(): m for m in gltf_materials}
    used = set()
    for entry, slot in zip(materials, slots):
        name = slot["pattern"][:-1]
        source = by_name[name].get("extras", {}).get("halo", {})
        tag = source.get("tag_path", "").replace(chr(92), "/").lower()
        if tag not in by_tag:
            continue
        role, spec = by_tag[tag]
        used.add(role)
        parent = f"{root}/SurfaceMaterials/M_Authored_{role}"
        runtime = {"parent": parent + "." + parent.rsplit("/", 1)[-1]}
        entry.clear()
        entry.update(name=name, **runtime)
        slot["material"] = dict(runtime)
    missing = set(surfaces) - used
    if missing:
        raise ValueError(f"Authored surfaces missing exported shader slots: {sorted(missing)}")
    for role,spec in surfaces.items():
        for key in ("albedo", "roughness_map") + (("normal_map",) if "normal_map" in spec else ()):
            # Shared images import only once; color and data stay distinct.
            name = "T_Authored_" + Path(spec[key]).stem
            prior = textures.get(name)
            record = {"file": spec[key], "name": name, "authored_pbr": True, "srgb": key == "albedo"}
            if key == "normal_map":
                # Both consumers read the same tangent-space image. UE's
                # normal texture sampler expects DirectX (-Y); flip +Y at
                # import, once, instead of inverting it again in the graph.
                record.update(normal_map=True, compression="normalmap",
                              normal_convention=spec["normal_convention"],
                              flip_green_channel=spec["normal_convention"] == "opengl")
            if prior and prior != record:
                raise ValueError(f"Authored texture identity collision: {name}")
            textures[name] = record
            spec[key + "_asset"] = f"{root}/Textures/{name}"
    return surfaces
