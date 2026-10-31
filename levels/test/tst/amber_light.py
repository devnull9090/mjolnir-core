"""Shared amber atlas material and reproducible map-owned CE shader.

Run with normal Python to write/read-back the derived shader under this source
folder. This does not invoke HEK, install a tag, or modify the stock atlas.
The ordinary rebuild stages this generated tag before compiling the structure.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_spec():
    spec = json.loads((ROOT / "amber_light.json").read_text(encoding="utf-8"))
    if spec.get("version") != 1:
        raise ValueError("Unsupported amber light specification")
    color = spec["color"]
    if len(color) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in color):
        raise ValueError("Amber RGB must contain three finite values in [0, 1]")
    if not any(color):
        raise ValueError("A zero CE material color is treated as the default white")
    spill = spec.get("preview_spill_color", color)
    if len(spill) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in spill):
        raise ValueError("Preview spill RGB must contain three finite values in [0, 1]")
    if not spec["material"].endswith("!"):
        raise ValueError("The light lens must retain the non-colliding detail suffix")
    width, height = spec["atlas_size"]
    x0, y0, x1, y1 = spec["atlas_pixels"]
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("Amber lens UV rectangle falls outside its stock atlas")
    return spec


def mark_material(material, spec=None):
    """Attach readable source metadata, independent of the preview graph."""
    spec = spec or load_spec()
    material["source_shader_tag"] = spec["tag"].replace("/", "\\")
    material["tst_light_atlas"] = True
    material["tst_authored_light"] = "amber_light.json"
    material["authored_light_color"] = spec["color"]
    material["preview_spill_color"] = spec.get("preview_spill_color", spec["color"])
    material["light_atlas_size"] = spec["atlas_size"]
    material["light_atlas_pixels"] = spec["atlas_pixels"]
    material["mjolnir_pcg_policy"] = "NONE"
    material.use_backface_culling = True


def build_tag(template, spec=None):
    spec = spec or load_spec()
    authored = copy.deepcopy(template)
    data = authored["Data"]
    color = dict(zip(("R", "G", "B"), spec["color"]))
    data["material color"] = color.copy()
    data["color of emitted light"] = color.copy()
    data["power"] = spec["radiosity_power"]
    # Halo Toolset's flat 'map' field is shader_environment's self-illum map.
    # It serializes the new dependency; no binary offsets or new bitmap.
    data["map"] = copy.deepcopy(data["base map"])
    data["map scale"] = 1.0
    for channel in ("primary", "secondary", "plasma"):
        rgb = color if channel == "primary" else {"R": 0.0, "G": 0.0, "B": 0.0}
        for state in ("on", "off"):
            data[f"{channel} {state} color"] = rgb.copy()
        data[f"{channel} animation function"]["value"] = 0  # constant 'one'
        data[f"{channel} animation period"] = 1.0
        data[f"{channel} animation phase"] = 0.0
    return authored


def verify_roundtrip(expected, actual):
    expected, actual = expected["Data"], actual["Data"]
    for key in ("material color", "color of emitted light") + tuple(
            f"{channel} {state} color" for channel in ("primary", "secondary", "plasma")
            for state in ("on", "off")):
        for component in ("R", "G", "B"):
            if not math.isclose(expected[key][component], actual[key][component], abs_tol=1e-7):
                raise ValueError(f"Amber shader roundtrip changed {key}.{component}")
    for key in ("base map", "map"):
        for field in ("path", "group name"):
            if expected[key][field] != actual[key][field]:
                raise ValueError(f"Amber shader roundtrip changed {key}.{field}")
    for key in ("map scale", "power"):
        if expected[key] != actual[key]:
            raise ValueError(f"Amber shader roundtrip changed {key}")
    for channel in ("primary", "secondary", "plasma"):
        if actual[f"{channel} animation function"]["value"] != 0:
            raise ValueError(f"Amber shader {channel} channel is not constant")


def main():
    from build_scenario import DEFAULT_ADDON, DEFAULT_HEK, load_toolset
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hek", type=Path, default=DEFAULT_HEK)
    parser.add_argument("--addon", type=Path, default=DEFAULT_ADDON)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    spec = load_spec()
    tags = args.hek / "tags"
    source = tags / (spec["stock_tag"] + ".shader_environment")
    output = args.output or ROOT / "tags" / (spec["tag"] + ".shader_environment")
    if output.resolve() == source.resolve():
        raise ValueError("The map-owned amber tag cannot overwrite its stock source")
    interface, common, definitions = load_toolset(args.addon)
    kwargs = {"engine_tag": common.EngineTag.H1Latest.value}
    template = interface.read_file(definitions, str(tags), str(source), **kwargs)
    authored = build_tag(template, spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    interface.write_file(definitions, copy.deepcopy(authored), interface.obfuscation_buffer_prepare(),
                         str(output), **kwargs)
    actual = interface.read_file(definitions, str(tags), str(output), **kwargs)
    verify_roundtrip(authored, actual)
    print(json.dumps({"shader": str(output.resolve()), "source": str(source.resolve()),
                      "color": spec["color"], "atlas_unchanged": True,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "roundtrip": "passed"}, indent=2))


if __name__ == "__main__":
    main()
