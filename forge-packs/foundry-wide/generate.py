"""Derive Foundry Wide from the versioned original source; never write Foundry.

Only X and Y coordinates change. Z, topology, materials and cosmetic bevel
widths are preserved. The source fingerprint makes upstream changes explicit.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "foundry" / "source" / "geometry.json"
VERSION = "0.1.0"
BASE_SHA256 = "e52d920cceeb9c4f8249033fe582d29b0a9cc6b0ad5c20d31ed4adc6dd9ec156"
IDS = (
    "block_1x1", "block_1x2", "floor_1x1", "floor_1x2", "floor_2x2",
    "bridge_straight", "bridge_corner", "ramp", "ramp_shallow", "wall",
    "wall_half", "wall_corner", "doorway", "window", "railing", "column",
    "cover", "stairs",
)


def source_fingerprint(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_original():
    source = json.loads(BASE.read_text(encoding="utf-8"))
    if source_fingerprint(source) != BASE_SHA256:
        raise ValueError("Foundry 0.2.0 source changed; review the Wide derivation before updating its provenance pin.")
    return source


def scale_mesh(mesh):
    mesh["vertices"] = [[round(x * 2, 9), round(y * 2, 9), z] for x, y, z in mesh["vertices"]]


def build_source():
    base = load_original()
    originals = {piece["id"]: piece for piece in base["pieces"]}
    pieces = []
    for ident in IDS:
        piece = copy.deepcopy(originals[ident])
        piece["name"] = "Wide " + piece["name"]
        x, y, z = piece["dimensions_m"]
        piece["dimensions_m"] = [x * 2, y * 2, z]
        piece["render_distance_m"] = 200
        scale_mesh(piece["collision"])
        for hull in piece["collision"]["hulls"]:
            scale_mesh(hull)
        for part in piece["visual"]:
            scale_mesh(part)
        piece["notes"] = {
            "ramp": "Low end -Y, high end +Y; exact 2 m rise over 8 m run (1:4), zero-height nose.",
            "ramp_shallow": "Low end -Y, high end +Y; exact 2 m rise over 16 m run (1:8), zero-height nose.",
            "doorway": "Clear opening 4 m wide by 2.5 m high; no collision across opening.",
            "window": "Open aperture 4 m wide, from Z=1 m to Z=2.5 m; no glass or collision in aperture.",
            "stairs": "Eight 0.25 m rises and 1 m treads; low end -Y. Collision follows the visible steps.",
        }.get(ident, piece["notes"])
        if ident == "ramp":
            piece["name"] = "Wide Ramp 1 : 4"
        elif ident == "ramp_shallow":
            piece["name"] = "Wide Ramp 1 : 8"
        pieces.append(piece)
    used = {part["material"] for piece in pieces for part in piece["visual"]}
    return {
        "schema_version": 1, "units": "meters", "axes": "right_handed_z_up",
        "license": "MIT", "module_m": 4,
        "provenance": {"pack_id": "foundry", "version": "0.2.0",
                       "source": "../foundry/source/geometry.json",
                       "canonical_json_sha256": source_fingerprint(base),
                       "transform": {"scale_xyz": [2, 2, 1]}, "piece_ids": list(IDS)},
        "materials": {name: copy.deepcopy(spec) for name, spec in base["materials"].items() if name in used},
        "pieces": pieces,
    }


def write_sources():
    source = build_source()
    catalog = {
        "schema_version": 1, "name": "Foundry Wide", "version": VERSION,
        "type": "content", "license": "MIT",
        "summary": "18 modular structural pieces with twice Foundry's footprint and unchanged heights.",
        "description": "A separate 4 m-module construction kit: wider platforms, bridges, ramps, walls and cover. Original Foundry maps retain their scale.",
        "forge_pack": {"schema_version": 1, "id": "foundry-wide", "blocks": [
            {"id": p["id"], "name": p["name"], "tag": "objects\\mjolnir\\forge\\foundry-wide\\" + p["id"],
             "category": p["category"], "dimensions_m": p["dimensions_m"], "snap_m": 0.5}
            for p in source["pieces"]]},
    }
    (ROOT / "source").mkdir(parents=True, exist_ok=True)
    (ROOT / "source" / "geometry.json").write_text(json.dumps(source, separators=(",", ":")) + "\n", encoding="utf-8")
    (ROOT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return source


if __name__ == "__main__":
    result = write_sources()
    print(f"Generated {len(result['pieces'])} Foundry Wide pieces; Foundry source was read only.")
