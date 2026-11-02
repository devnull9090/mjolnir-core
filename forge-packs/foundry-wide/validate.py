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


def ray_hits(piece, start, end):
    """Intersect the exported triangle surfaces, independent of hull containment."""
    direction = checks.sub(end, start)
    vertices = piece["collision"]["vertices"]
    hits = []
    for tri in piece["collision"]["triangles"]:
        a, b, c = [vertices[i] for i in tri]
        e1, e2 = checks.sub(b, a), checks.sub(c, a)
        h = checks.cross(direction, e2)
        det = checks.dot(e1, h)
        if abs(det) < 1e-10:
            continue
        s = checks.sub(start, a)
        u = checks.dot(s, h) / det
        q = checks.cross(s, e1)
        v = checks.dot(direction, q) / det
        t = checks.dot(e2, q) / det
        if -1e-9 <= u <= 1+1e-9 and -1e-9 <= v and u+v <= 1+1e-9 and -1e-9 <= t <= 1+1e-9:
            hits.append([start[k]+t*direction[k] for k in range(3)])
    return hits


def verify_lift_walkups(piece):
    """Probe actual triangles along all four ground-to-centre routes.

    The former full 0.5 m slab fails at each nose. These checks also catch
    gaps at the ramp/deck seam, reversed slopes, and corner housings entering
    the four-metre approaches; a dimension-only check would miss all three.
    """
    probes = 0
    for quarter in range(4):
        def point(across, distance, z):
            x, y = across, -distance
            for _ in range(quarter):
                x, y = -y, x
            return [x, y, z]
        for across in (-1.99, -1, 0, 1, 1.99):
            previous = None
            for i in range(33):
                distance = 4-i/8
                top = min(.5, (4-distance)/4)
                p = point(across, distance, top)
                hits = ray_hits(piece, [p[0], p[1], 4], [p[0], p[1], -1])
                assert hits and math.isclose(max(h[2] for h in hits), top, abs_tol=1e-7), "Lift walk-up discontinuity"
                assert solid_at(piece, p)
                assert not ray_hits(piece, [p[0],p[1],top+.001], [p[0],p[1],top+1.9812]), "Blocked standing lift approach"
                probes += 3
                if previous is not None:
                    for height in (.02, 1.9812):
                        assert not ray_hits(piece, [previous[0],previous[1],previous[2]+height],
                                            [p[0],p[1],top+height]), "Vertical lip on lift approach"
                        probes += 1
                previous = p
    return probes


def verify_extensions(pieces):
    probes = 0
    # Trace all glazed openings, both directions: panes must block while
    # preserving the original frame's apparent aperture and view dimensions.
    for ident, xs, zs in (("glass_wall", (-3.4, -2, 0, 2, 3.4), (.3, 1.5, 2.7)),
                           ("window_glazed", (-1.9, 0, 1.9), (1.05, 1.75, 2.45))):
        for x in xs:
            for z in zs:
                assert solid_at(pieces[ident], [x, 0, z])
                for sign in (-1, 1):
                    assert ray_hits(pieces[ident], [x, sign*2, z], [x, -sign*2, z])
                    probes += 1
    # Standing infantry and full stock Warthog envelopes traverse the actual
    # frame triangle openings. Jamb/header rays are controls against false misses.
    for ident, half, height, entity_half, entity_height in (
        ("doorway_tall", 2, 3.5, .5334, 1.9812),
        ("doorway_vehicle", 4, 5.5, 1.625, 2.43),
        ("teleporter_housing", 2, 3.5, .5334, 1.9812),
    ):
        piece = pieces[ident]
        for x in (-half+.01, -entity_half, 0, entity_half, half-.01):
            for z in (.01, entity_height, height-.01):
                assert not ray_hits(piece, [x, -2, z], [x, 2, z]), f"Blocked {ident} throat"
                probes += 1
        assert ray_hits(piece, [half+.01, -2, 1], [half+.01, 2, 1])
        assert ray_hits(piece, [0, -2, height+.01], [0, 2, height+.01])
        # No threshold under the feet and no solid hanging into the opening.
        for x in (-entity_half, 0, entity_half):
            assert not ray_hits(piece, [x, 0, height-.01], [x, 0, -.01])
            probes += 1
    assert pieces["teleporter_housing"]["collision"] == pieces["doorway_tall"]["collision"]
    for ident, half, height, travel in (("door_panel", 2, 3.5, 4), ("door_vehicle_panel", 4, 5.5, 6)):
        panel = pieces[ident]
        for x in (-half+.01, 0, half-.01):
            for z in (.01, height/2, height-.01):
                # Closed panel is solid; open panel's local query is below it.
                assert ray_hits(panel, [x, -2, z], [x, 2, z])
                assert not ray_hits(panel, [x, -2, z-travel], [x, 2, z-travel])
                probes += 2
        assert panel["dimensions_m"][1] == .5
    for ident in ("ramp_wide", "ramp_high", "ramp_wide_high", "ramp_wide_shallow"):
        piece = pieces[ident]
        width, run, rise = piece["dimensions_m"]
        for i in range(33):
            y, top = -run/2+run*i/32, rise*i/32
            for x in (-width/2+.01, -width/4, 0, width/4, width/2-.01):
                hits = ray_hits(piece, [x, y, rise+1], [x, y, -1])
                assert hits and math.isclose(max(p[2] for p in hits), top, abs_tol=1e-7)
                assert solid_at(piece, [x, y, top]) and not solid_at(piece, [x, y, top+.01])
                probes += 3
        # A 0.5m landing starts exactly at the high edge and at rise-0.5 Z.
        landing = {"collision": gen.combine([gen.primitives().box(width, 4, .5, 0, run/2+2, rise-.5)])}
        for x in (-width/2+.01, 0, width/2-.01):
            before = ray_hits(piece, [x, run/2-.01, rise+1], [x, run/2-.01, -1])
            after = ray_hits(landing, [x, run/2+.01, rise+1], [x, run/2+.01, -1])
            assert math.isclose(max(p[2] for p in before), rise-.01*rise/run, abs_tol=1e-7)
            assert math.isclose(max(p[2] for p in after), rise, abs_tol=1e-7)
            probes += 2
    for ident, present, absent in (
        ("bridge_t", [(-5,4), (5,4), (0,-5), (0,4)], [(-4,-4),(4,-4)]),
        ("bridge_cross", [(0,0),(-5,0),(5,0),(0,-5),(0,5)], [(-4,-4),(4,-4),(-4,4),(4,4)]),
        ("bridge_corner_wide", [(-4,4),(-4,-4),(4,-4)], [(4,4)]),
        ("glass_corner", [(-3.5,0),(0,-3.5)], [(0,0),(3,3)]),
    ):
        z = 1.5 if ident == "glass_corner" else .25
        for x, y in present:
            assert solid_at(pieces[ident], [x,y,z]), f"Missing {ident} arm"
            probes += 1
        for x, y in absent:
            assert not solid_at(pieces[ident], [x,y,z]), f"Filled {ident} void"
            assert not ray_hits(pieces[ident], [x,y,10], [x,y,-1])
            probes += 2
    # Both full-size slabs and the lift/pad have uninterrupted usable top faces.
    for ident, half, top in (("floor_4x4",7.99,.5),("landing_guarded",3.49,.5),
                             ("lift_station",1.99,.5),("teleporter_pad_wide",1.99,.5)):
        for i in range(9):
            for j in range(9):
                x,y = -half+2*half*i/8, -half+2*half*j/8
                hits = ray_hits(pieces[ident], [x,y,9], [x,y,-1])
                assert hits and math.isclose(max(p[2] for p in hits),top,abs_tol=1e-7)
                assert not ray_hits(pieces[ident], [x,y,top+.001], [x,y,top+8])
                probes += 2
    for x in (-3.75,3.75):
        assert solid_at(pieces["landing_guarded"],[x,0,1.99])
    assert pieces["lift_station"]["lift"]["offset_m"] == [0,0,.45]
    assert pieces["lift_station"]["lift"]["size_m"] == [4,4,3.5]
    probes += verify_lift_walkups(pieces["lift_station"])
    return probes


def main():
    source = json.loads((ROOT / "source" / "geometry.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    catalog = manifest["forge_pack"]["blocks"]
    base = gen.load_original()
    originals = {p["id"]: p for p in base["pieces"]}
    assert source == gen.build_source(), "Generated source has drifted from the pinned original/transform."
    assert source["units"] == "meters" and source["axes"] == "right_handed_z_up"
    assert source["module_m"] == 4 and source["provenance"]["canonical_json_sha256"] == gen.BASE_SHA256
    assert manifest["version"] == gen.VERSION == "0.2.0" and manifest["type"] == "content"
    assert manifest["forge_pack"]["id"] == "foundry-wide"
    assert [p["id"] for p in source["pieces"]] == [p["id"] for p in catalog] == list(gen.IDS + gen.ADDITIONS)
    assert gen.source_fingerprint(source["pieces"][:18]) == gen.LEGACY_PIECES_SHA256
    hull_count = triangle_count = probe_count = 0
    bounds = {}
    for piece, block in zip(source["pieces"], catalog):
        ident = piece["id"]
        original = originals.get(ident)
        assert piece["origin"] == "bottom_center" and piece["snap_m"] == block["snap_m"] == 0.5
        assert piece["name"] == block["name"] and block["name"].startswith("Wide ")
        assert block["tag"] == "objects\\mjolnir\\forge\\foundry-wide\\" + ident
        assert piece["dimensions_m"] == block["dimensions_m"]
        assert piece["category"] == block["category"] and "light" not in piece and "light" not in block
        distance = piece["render_distance_m"]
        assert isinstance(distance, (int, float)) and not isinstance(distance, bool)
        assert math.isfinite(distance) and 0 < distance <= 1000 and distance == 200
        assert "render_distance_m" not in block, "Native draw distance is source-only metadata."
        if original:
            verify_scaled(piece["collision"], original["collision"], ident)
            assert len(piece["collision"]["hulls"]) == len(original["collision"]["hulls"])
        assert 1 <= len(piece["collision"]["hulls"]) <= 256
        assert len(piece["collision"]["triangles"]) <= 4096
        vertices, triangles = [], []
        for index, hull in enumerate(piece["collision"]["hulls"]):
            volume = checks.verify_hull(hull, f"{ident}/hull/{index}")
            if original:
                old = original["collision"]["hulls"][index]
                verify_scaled(hull, old, f"{ident}/hull/{index}")
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
        if original:
            assert len(piece["visual"]) == len(original["visual"])
        for index, part in enumerate(piece["visual"]):
            if original:
                old = original["visual"][index]
                verify_scaled(part, old, f"{ident}/visual/{index}")
                assert part["material"] == old["material"] and part["bevel_m"] == old["bevel_m"]
            if part.get("surface") == "two_sided":
                assert part["material"] == "portal_green" and len(part["vertices"]) == 4 and len(part["triangles"]) == 2
            else:
                checks.verify_hull(part, f"{ident}/visual/{index}")
            if part["material"] in ("glass", "portal_green"):
                assert len(part["uvs"]) == len(part["vertices"])
                assert all(len(uv) == 2 and all(math.isfinite(v) and 0 <= v <= 1 for v in uv) for uv in part["uvs"])
                assert len({tuple(uv) for uv in part["uvs"]}) == 4
            assert all(lo[k]-1e-6 <= v[k] <= hi[k]+1e-6 for v in part["vertices"] for k in range(3))
        for key in ("lift", "door", "surfaces"):
            assert piece.get(key) == block.get(key)
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
    extension_probes = verify_extensions(pieces)
    print(f"PASS: 18 unchanged legacy + 20 new pieces; {hull_count} closed convex hulls; {triangle_count} collision triangles; {probe_count} legacy + {extension_probes} extension collision probes; origins, UVs, openings, ramps and utility clearance.")


if __name__ == "__main__":
    main()
