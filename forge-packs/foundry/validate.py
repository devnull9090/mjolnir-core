"""Check useful authoring invariants on Foundry sources; no Blender required."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def verify_hull(hull, label):
    vertices, triangles = hull["vertices"], hull["triangles"]
    assert vertices and triangles, label
    assert all(len(v) == 3 and all(math.isfinite(n) for n in v) for v in vertices), label
    directed, undirected, volume = Counter(), Counter(), 0.0
    for triangle in triangles:
        assert len(triangle) == 3 and len(set(triangle)) == 3, label
        assert all(isinstance(i, int) and 0 <= i < len(vertices) for i in triangle), label
        a, b, c = [vertices[i] for i in triangle]
        normal = cross(sub(b, a), sub(c, a))
        assert dot(normal, normal) > 1e-14, f"Degenerate triangle: {label}"
        volume += dot(a, cross(b, c)) / 6
        for i, j in zip(triangle, triangle[1:] + triangle[:1]):
            directed[i, j] += 1
            undirected[tuple(sorted((i, j)))] += 1
    assert all(count == 2 for count in undirected.values()), f"Open/nonmanifold hull: {label}"
    assert all(directed[j, i] == count for (i, j), count in directed.items()), f"Winding mismatch: {label}"
    assert volume > 1e-9, f"Inward/zero-volume hull: {label}"
    # Each collision hull must be convex so runtime conversion can use it as-is.
    for triangle in triangles:
        a, b, c = [vertices[i] for i in triangle]
        normal = cross(sub(b, a), sub(c, a))
        assert all(dot(normal, sub(v, a)) <= 1e-6 for v in vertices), f"Non-convex hull: {label}"
    return volume


def inside_hull(point, hull):
    for triangle in hull["triangles"]:
        a, b, c = [hull["vertices"][i] for i in triangle]
        if dot(cross(sub(b, a), sub(c, a)), sub(point, a)) > 1e-8:
            return False
    return True


def main():
    source = json.loads((ROOT / "source" / "geometry.json").read_text())
    catalog = json.loads((ROOT / "catalog.json").read_text())["forge_pack"]["blocks"]
    assert source["units"] == "meters" and source["axes"] == "right_handed_z_up"
    assert len(source["pieces"]) == len(catalog) == 24
    assert len({p["id"] for p in source["pieces"]}) == 24
    hull_count, triangle_count, bounds = 0, 0, {}
    for piece, block in zip(source["pieces"], catalog):
        ident = piece["id"]
        assert block["id"] == ident and block["dimensions_m"] == piece["dimensions_m"]
        assert block["tag"] == "objects\\mjolnir\\forge\\foundry\\" + ident
        assert block.get("light") == piece.get("light"), f"Light metadata mismatch: {ident}"
        if light := piece.get("light"):
            assert len(light["offset_m"]) == len(light["color_rgb"]) == 3
            assert all(math.isfinite(v) and abs(v) <= 100 for v in light["offset_m"])
            assert all(math.isfinite(v) and 0 <= v <= 1 for v in light["color_rgb"])
            assert 0 < light["intensity_cd"] <= 10000 and 0 < light["radius_m"] <= 100
        vertices = piece["collision"]["vertices"]
        minimum = [min(v[axis] for v in vertices) for axis in range(3)]
        maximum = [max(v[axis] for v in vertices) for axis in range(3)]
        assert all(abs(maximum[i]-minimum[i]-piece["dimensions_m"][i]) < 1e-6 for i in range(3)), ident
        assert minimum[2] == 0 and all(abs(minimum[i]+maximum[i]) < 1e-6 for i in (0,1)), ident
        for index, hull in enumerate(piece["collision"]["hulls"]):
            verify_hull(hull, f"{ident}/{index}")
            hull_count += 1
            triangle_count += len(hull["triangles"])
        for index, component in enumerate(piece["visual"]):
            verify_hull(component, f"{ident}/visual/{index}")
            assert all(minimum[i]-1e-6 <= p[i] <= maximum[i]+1e-6 for p in component["vertices"] for i in range(3)), f"Visual exceeds snap bounds: {ident}"
        bounds[ident] = (minimum, maximum)
    by_id = {p["id"]: p for p in source["pieces"]}
    for ident, point in [("doorway", [0,0,1.5]), ("window", [0,0,1.75]), ("bridge_corner", [1,1,0.25]),
                         ("portal_frame", [0,0,1.5]), ("light_pylon", [0.4,0,1.5])]:
        assert not any(inside_hull(point, h) for h in by_id[ident]["collision"]["hulls"]), f"Blocked opening: {ident}"
    # Paired floors and stacked blocks must meet exactly on the 0.5 m grid.
    assert bounds["floor_1x1"][1][0] == -bounds["floor_1x1"][0][0] == 1
    assert bounds["block_1x1"][1][2] == 2
    for ident, run in [("ramp",4), ("ramp_shallow",8)]:
        hull = by_id[ident]["collision"]["hulls"][0]
        assert inside_hull([0,run/2,2], hull)
        assert inside_hull([0,0,1], hull)
        assert not inside_hull([0,0,1.01], hull)
    # A receiver centred above the pad has >0.7 m lateral safety clearance
    # around the approximately 0.53 m radius player, and 3 m headroom.
    for x in (-0.75, 0, 0.75):
        for y in (-0.5, 0, 0.5):
            for z in (0.55, 1.5, 3.2):
                assert not any(inside_hull([x,y,z], h) for h in by_id["portal_frame"]["collision"]["hulls"])
    assert bounds["teleporter_pad"][1][2] == bounds["floor_1x1"][1][2] == 0.5
    print(f"PASS: {len(catalog)} pieces; {hull_count} closed convex collision hulls; {triangle_count} outward triangles; exact bounds, origins, apertures and ramp seams")


if __name__ == "__main__":
    main()
