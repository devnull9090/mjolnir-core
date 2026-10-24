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
        for key in ("albedo", "roughness_map"):
            # Shared images import only once; color and data stay distinct.
            name = "T_Authored_" + Path(spec[key]).stem
            prior = textures.get(name)
            record = {"file": spec[key], "name": name, "authored_pbr": True, "srgb": key == "albedo"}
            if prior and prior != record:
                raise ValueError(f"Authored texture identity collision: {name}")
            textures[name] = record
            spec[key + "_asset"] = f"{root}/Textures/{name}"
    return surfaces
