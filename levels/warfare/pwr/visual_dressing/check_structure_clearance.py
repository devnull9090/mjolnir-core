# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "shapely>=2,<3"]
# ///
"""List decor rocks whose collision hull reaches into a bridge or culvert deck.

    python levels/warfare/pwr/visual_dressing/check_structure_clearance.py LEVEL HULLS [--json OUT]

LEVEL is a PWR level.json; HULLS the outcrop hull folder (one <mesh leaf>.json
of local-centimetre points per stock rock, from outcrops_v3.py's inputs).
Every road whose `structure` is bridge or culvert in the terrain geometry is a
swept deck (world_geometry.bridge_parts): its corridor runs to the outermost
cross-section offsets (the shoulders, +-18 m), and a rock intrudes when any hull
point inside that corridor comes within SURFACE_MARGIN of the driving surface or
rises above it (by up to CEILING metres). A rock wholly below that, the river bank
under a span or a toe inside the 2 m slab, is out of sight and out of the way. A rock is matched to its hull by mesh leaf name; rows with no
hull are listed as unchecked. Pure reading: changes nothing.
"""
from pathlib import Path
import argparse, json, math, sys

import numpy as np
import shapely
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
import b30_collision  # noqa: E402

GEOMETRY = ROOT / "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json"
SURFACE_MARGIN = 0.25  # metres below the driving surface a hull point already shows through it
CEILING = 12.0    # metres above the surface a hull point still counts (vehicles, walls)


def decks(geometry):
    out = []
    for road in geometry["roads"]:
        if road.get("structure") not in ("bridge", "culvert"):
            continue
        sections = road["cross_sections_m"]
        offsets = road["cross_section_offsets_m"]
        left, right, mid = 0, len(offsets) - 1, offsets.index(0)
        ring = [tuple(s[left][:2]) for s in sections] + [tuple(s[right][:2]) for s in reversed(sections)]
        centre = np.array([s[mid] for s in sections])
        out.append({"id": road["id"], "structure": road["structure"], "corridor": Polygon(ring), "centre": centre})
    return out


def intrusion(spans, pts):
    """(deck, hull points reaching it, highest above its surface) for the first
    deck `pts` (native metres, N x 3) reach into, or None. outcrops_v3.py's
    validator rejects a placement for which this is not None."""
    for deck in spans:
        if not deck["corridor"].buffer(30).contains(shapely.Point(pts[:, :2].mean(axis=0))):
            continue
        inside = shapely.contains_xy(deck["corridor"], pts[:, 0], pts[:, 1])
        if not inside.any():
            continue
        gap = np.hypot(*(deck["centre"][:, None, :2] - pts[inside][None, :, :2]).transpose(2, 0, 1))
        near = deck["centre"][np.argmin(gap, axis=0)]
        above = pts[inside][:, 2] - near[:, 2]
        reach = (above > -SURFACE_MARGIN) & (above < CEILING)
        if reach.any():
            return deck, int(reach.sum()), float(above[reach].max())
    return None


def hull_points(hulls, row):
    leaf = row["mesh"].rsplit("/", 1)[-1].split(".")[0]
    path = hulls / f"{leaf}.json"
    if not path.is_file():
        return None
    local = np.array(json.loads(path.read_text())["points"]) / 100.0
    native = local * np.array(row.get("scale", [1, 1, 1])) @ b30_collision.rotator_matrix(*row.get("rot", [0, 0, 0])) \
        + np.array(row["pos"]) / 100.0
    return native * np.array([1, -1, 1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("level", type=Path)
    parser.add_argument("hulls", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    level = json.loads(args.level.read_text(encoding="utf-8"))
    spans = decks(json.loads(GEOMETRY.read_text(encoding="utf-8")))
    hits, unchecked = [], []
    for row in level.get("decor", []):
        mesh = row.get("mesh", "")
        if "/Rock" not in mesh and "Rock_" not in mesh:
            continue
        pts = hull_points(args.hulls, row)
        if pts is None:
            unchecked.append(row["id"])
            continue
        found = intrusion(spans, pts)
        if found:
            deck, count, highest = found
            hits.append({"id": row["id"], "deck": deck["id"], "structure": deck["structure"],
                         "points_in_deck": count, "highest_above_surface_m": round(highest, 2),
                         "pos_m": [round(v / 100, 1) for v in row["pos"]]})
    for h in hits:
        print(f"{h['id']}: {h['points_in_deck']} hull points in {h['deck']} ({h['structure']}), up to {h['highest_above_surface_m']} m above its surface, at {h['pos_m']}")
    print(f"{len(hits)} rock(s) intrude on {len(spans)} deck(s); {len(unchecked)} rock row(s) without a hull to check")
    if args.json:
        args.json.write_text(json.dumps({"intruding": hits, "unchecked": unchecked}, indent=1) + "\n")


if __name__ == "__main__":
    main()
