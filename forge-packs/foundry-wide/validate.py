"""Portable geometric checks for Foundry Wide; no Blender/game dependency."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load_module("foundry_wide_generator_for_validation", ROOT / "generate.py")
checks = load_module("foundry_hull_checks", ROOT.parent / "foundry" / "validate.py")


def verify_scaled(actual, original, label):
    expected = [[round(x * 2, 9), round(y * 2, 9), z] for x, y, z in original["vertices"]]
    assert actual["vertices"] == expected, f"Not exact 2x XY / unchanged Z: {label}"
    assert actual["triangles"] == original["triangles"], f"Changed topology: {label}"


def solid_at(piece, point):
    return any(checks.inside_hull(point, hull) for hull in piece["collision"]["hulls"])


def main():
    source = json.loads((ROOT / "source" / "geometry.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    catalog = manifest["forge_pack"]["blocks"]
    base = gen.load_original()
    originals = {p["id"]: p for p in base["pieces"]}
    assert source == gen.build_source(), "Generated source has drifted from the pinned original/transform."
    assert source["units"] == "meters" and source["axes"] == "right_handed_z_up"
    assert source["module_m"] == 4 and source["provenance"]["canonical_json_sha256"] == gen.BASE_SHA256
    assert manifest["version"] == "0.1.0" and manifest["type"] == "content"
    assert manifest["forge_pack"]["id"] == "foundry-wide"
    assert [p["id"] for p in source["pieces"]] == [p["id"] for p in catalog] == list(gen.IDS)
    hull_count = triangle_count = probe_count = 0
    bounds = {}
    for piece, block in zip(source["pieces"], catalog):
        ident = piece["id"]
        original = originals[ident]
        assert piece["origin"] == "bottom_center" and piece["snap_m"] == block["snap_m"] == 0.5
        assert piece["name"] == block["name"] and block["name"].startswith("Wide ")
        assert block["tag"] == "objects\\mjolnir\\forge\\foundry-wide\\" + ident
        assert piece["dimensions_m"] == block["dimensions_m"]
        assert piece["category"] == block["category"] and "light" not in piece and "light" not in block
        distance = piece["render_distance_m"]
        assert isinstance(distance, (int, float)) and not isinstance(distance, bool)
        assert math.isfinite(distance) and 0 < distance <= 1000 and distance == 200
        assert "render_distance_m" not in block, "Native draw distance is source-only metadata."
        verify_scaled(piece["collision"], original["collision"], ident)
        assert len(piece["collision"]["hulls"]) == len(original["collision"]["hulls"]) <= 256
        assert len(piece["collision"]["triangles"]) <= 4096
        vertices, triangles = [], []
        for index, (hull, old) in enumerate(zip(piece["collision"]["hulls"], original["collision"]["hulls"])):
            verify_scaled(hull, old, f"{ident}/hull/{index}")
            volume = checks.verify_hull(hull, f"{ident}/hull/{index}")
            old_volume = checks.verify_hull(old, f"original/{ident}/{index}")
            assert math.isclose(volume, old_volume * 4, rel_tol=1e-8, abs_tol=1e-9)
            offset = len(vertices)
            vertices.extend(hull["vertices"])
            triangles.extend([[i + offset for i in tri] for tri in hull["triangles"]])
            hull_count += 1
            triangle_count += len(hull["triangles"])
        assert vertices == piece["collision"]["vertices"] and triangles == piece["collision"]["triangles"]
        lo = [min(v[k] for v in vertices) for k in range(3)]
        hi = [max(v[k] for v in vertices) for k in range(3)]
        assert all(abs(hi[k]-lo[k]-piece["dimensions_m"][k]) < 1e-8 for k in range(3))
        assert lo[2] == 0 and all(abs(lo[k]+hi[k]) < 1e-8 for k in (0, 1))
        bounds[ident] = (lo, hi)
        assert len(piece["visual"]) == len(original["visual"])
        for index, (part, old) in enumerate(zip(piece["visual"], original["visual"])):
            verify_scaled(part, old, f"{ident}/visual/{index}")
            checks.verify_hull(part, f"{ident}/visual/{index}")
            assert part["material"] == old["material"] and part["bevel_m"] == old["bevel_m"]
            assert all(lo[k]-1e-6 <= v[k] <= hi[k]+1e-6 for v in part["vertices"] for k in range(3))
    pieces = {p["id"]: p for p in source["pieces"]}
    # Actual aperture interiors, jamb/header solids and L-shaped missing corners.
    for ident, zs in (("doorway", (0.02, 1.0, 2.48)), ("window", (1.02, 1.75, 2.48))):
        for x in (-1.99, -1, 0, 1, 1.99):
            for y in (-0.49, 0, 0.49):
                for z in zs:
                    assert not solid_at(pieces[ident], [x, y, z]), f"Blocked {ident} opening"
                    probe_count += 1
        assert solid_at(pieces[ident], [2.01, 0, 1.5]) and solid_at(pieces[ident], [0, 0, 2.51])
    assert solid_at(pieces["window"], [0, 0, 0.99])
    assert not solid_at(pieces["bridge_corner"], [2, 2, 0.25])
    assert not solid_at(pieces["wall_corner"], [1, 1, 1.5])
    assert bounds["floor_1x1"] == ([-2, -2, 0], [2, 2, 0.5])
    assert bounds["block_1x1"][1][2] == 2 and bounds["cover"][1][2] == 1
    for ident, run in (("ramp", 8), ("ramp_shallow", 16)):
        hull = pieces[ident]["collision"]["hulls"][0]
        # Sample the whole slope, including the exact nose and top seam shared
        # with a 2m block. Side-by-side ramps abut at X=+-2 with no gap/overlap.
        for i in range(33):
            y, top = -run / 2 + run * i / 32, 2 * i / 32
            for x in (-2, -1, 0, 1, 2):
                assert checks.inside_hull([x, y, top], hull)
                assert not checks.inside_hull([x, y, top + 0.01], hull)
                probe_count += 2
        assert bounds[ident][0] == [-2, -run/2, 0] and bounds[ident][1] == [2, run/2, 2]
        assert {tuple(v) for v in hull["vertices"] if v[1] == run/2 and v[2] == 2} == {(-2, run/2, 2), (2, run/2, 2)}
    for step in range(8):
        y, top = -3.5 + step, (step + 1) * 0.25
        assert solid_at(pieces["stairs"], [0, y, top])
        assert not solid_at(pieces["stairs"], [0, y, top + 0.01])
        probe_count += 2
    print(f"PASS: 18 exact XY-scaled pieces; {hull_count} closed convex hulls; {triangle_count} collision triangles; {probe_count} opening/slope/step probes; unchanged Z and topology.")


if __name__ == "__main__":
    main()
