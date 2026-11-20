"""Bind PWR's alpine backdrop, outcrops, and paving to their map-owned material cook."""
import argparse
import json
from pathlib import Path


SURFACES = "/Game/MJOLNIR/World/PWR/Surfaces"
TRIAL = "/Game/MJOLNIR/CETrial"
MATERIALS = ("M_CE_AlpineApron", "M_CE_PWRRock", "M_CE_PWRPaving")
TEXTURES = ("T_PWR_ApronField", "T_PWR_PavingGraphic")


def reference(root, name):
    return f"{root}/{name}.{name}"


def bind(level):
    """Update a level in place. Leave stock texture bindings and all placements intact."""
    replacements = {reference(TRIAL, name): reference(SURFACES, name) for name in (*MATERIALS, *TEXTURES)}
    for piece in level["decor"]:
        for spec in piece.get("materials", []):
            if not isinstance(spec, dict):
                continue  # Direct material paths already specify the asset to render.
            parent = spec.get("parent")
            if parent in replacements:
                spec["parent"] = replacements[parent]
            for key, texture in spec.get("textures", {}).items():
                if texture in replacements:
                    spec["textures"][key] = replacements[texture]
    apron = [piece for piece in level["decor"] if piece.get("id") == "pwr_distant_apron"]
    if len(apron) != 1 or not any(
        isinstance(spec, dict) and spec.get("parent") == reference(SURFACES, "M_CE_AlpineApron")
        and spec.get("textures", {}).get("ApronField") == reference(SURFACES, "T_PWR_ApronField")
        for spec in apron[0]["materials"]
    ):
        raise ValueError("PWR distant terrain must bind its own alpine material and erosion field")
    return level


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("level", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    updated = bind(json.loads(args.level.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(updated, separators=(",", ":")) + "\n", encoding="utf-8")
