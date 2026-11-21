"""Construct and verify .10's flush court finishes against Saturday .9's collision."""

import copy
import json
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from base_approach_paths import PLAN
from base_approach_surfaces import MASTER, WIT, material_polygons, support_planes, drape
from base_approach_witnesses import sha
from base_site_finish import FINISH, BASE9, SLOTS, footprint, write_footprints
from heightfield import load_heightfield
from package_base_approaches import package, read_glb, recipe as paving
from verify_base_approaches import HeightProbe


def material_profile():
    level = json.loads((BASE9 / "map-input/pwr.level.json").read_text())
    native = next(d for d in level["decor"] if d["id"] == "pwr_distant_apron")[
        "materials"
    ][0]["textures"]
    # Match the mean linear colour of the stock decoded scans to the baked
    # terrace border. The same projection provides grain at high/mid detail.
    root = "/Game/MJOLNIR/World/PWR/Surfaces/M_CE_PWRRock"

    def rubble(stock, tint, scale, roughness, strength):
        return {
            "parent": root + ".M_CE_PWRRock",
            "textures": {"RockD": native[stock + "D"], "RockN": native[stock + "N"]},
            "vectors": {
                "RockTint": [*tint, 1],
                "RockParams": [scale, roughness, strength, 0],
            },
        }

    return [
        rubble("Rock", [0.97, 1.12, 1.28], 156, 0.88, 0.48),
        rubble("Soil", [0.82, 0.88, 0.95], 188, 0.86, 0.60),
        paving(0),
        paving(1),
        paving(3),
    ]


def near_halfplane(poly, coeff):
    """Portion of an XY polygon where the linear height difference is positive."""
    from shapely.geometry import LineString
    from shapely.ops import split

    x0, y0, x1, y1 = poly.bounds
    corners = np.array([[x0, y0], [x0, y1], [x1, y0], [x1, y1]])
    h = corners @ coeff[:2] + coeff[2]
    if h.min() >= 0:
        return poly
    if h.max() <= 0:
        return Polygon()
    n = coeff[:2]
    mid = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    base = mid - n * (mid @ n + coeff[2]) / (n @ n)
    along = (
        np.array([-n[1], n[0]])
        / np.linalg.norm(n)
        * (2 * np.linalg.norm([x1 - x0, y1 - y0]) + 2)
    )
    parts = split(poly, LineString([base - along, base + along]))
    return unary_union(
        [
            sub
            for sub in parts.geoms
            if np.array(sub.representative_point().coords[0]) @ n + coeff[2] > 0
        ]
    )


def visible_planes(base, field):
    # The legacy spur rises diagonally across the court ramp. Split their XY
    # overlap at the intersection of their sloped planes, selecting the true
    # upper surface point-by-point before producing the new render surface.
    patches = support_planes(base, field)
    tree = shapely.STRtree([p for _, p, _ in patches])
    visible = []
    for i, (_, poly, plane) in enumerate(patches):
        hidden = []
        for j in tree.query(poly, predicate="intersects"):
            if j == i:
                continue
            _, other, higher = patches[j]
            difference = higher - plane
            if np.max(abs(difference)) < 1e-7:
                continue
            overlap = poly.intersection(other)
            if overlap.area < 1e-7:
                continue
            cut = near_halfplane(overlap, difference)
            if cut.area > 1e-8:
                hidden.append(cut)
        front = poly.difference(unary_union(hidden)) if hidden else poly
        if front.area > 1e-8:
            visible.append((patches[i][0], front, plane))
    return visible


def geometry():
    field = load_heightfield(MASTER)
    plan = json.loads(PLAN.read_text())
    write_footprints()
    surfaces = {}
    art = json.loads((BASE9 / "receipt.json").read_text())
    old = json.loads((WIT / "source.json").read_text())
    members = art["world_packages"]["preserved"]
    if members.get(old["native_source_member"]) != old["shipped_bsp_sha256"]:
        raise ValueError(
            "The previous map's compiled collision differs from the decoded witness"
        )
    for base in plan["bases"]:
        team = base["id"]
        shapes, _, _ = footprint(base, plan)
        planes = visible_planes(base, field)
        groups = {
            key: np.asarray(drape(poly, planes, field)) for key, poly in shapes.items()
        }
        for k, g in groups.items():
            if not len(g):
                raise ValueError("No geometry for " + team + "/" + k)
            # Slivers below float32 position precision would give undefined normals.
            cm = g.astype("<f4")
            good = (
                np.linalg.norm(
                    np.cross(cm[:, 1] - cm[:, 0], cm[:, 2] - cm[:, 0]), axis=1
                )
                > 1e-7
            )
            groups[k] = g[good]
        np.savez_compressed(FINISH / (team + "-surfaces.npz"), **groups)
        surfaces[team] = shapes
    return surfaces


def checks(actors, shapes):
    plan = json.loads(PLAN.read_text())
    faces = np.load(WIT / "base-collision-triangles.npy").astype(float)
    results = {}
    for model, base in zip(actors, plan["bases"]):
        team = base["id"]
        cx, cy = base["terrace_center_m"][:2]
        local = np.all(faces.max(1)[:, :2] > [cx - 110, cy - 120], axis=1) & np.all(
            faces.min(1)[:, :2] < [cx + 110, cy + 100], axis=1
        )
        probe = HeightProbe(faces[local])
        art = model["mesh"].rsplit(".", 1)[1]
        pts, _, ind, doc = read_glb(FINISH / "native" / (art + ".glb"))
        world = (pts * model["scale"] + model["pos"]) * np.array([0.01, -0.01, 0.01])
        tri = world[ind]
        center = tri.mean(1)
        # Ignore projected fragments smaller than a few square millimetres.
        triangle_areas = (
            np.abs(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2]) * 0.5
        )
        central = center[triangle_areas > 5e-6]
        values = central[:, 2] - probe.floors(central[:, :2], central[:, 2] + 0.075)
        if (
            not np.isfinite(values).all()
            or values.min() < -0.021
            or values.max() > 0.06
        ):
            ids = np.where((values < -0.021) | (values > 0.06) | ~np.isfinite(values))[
                0
            ]
            raise ValueError(
                (
                    team,
                    "site-to-native contact",
                    len(ids),
                    [(central[i].tolist(), values[i]) for i in ids[:10]],
                )
            )
        d = {
            "team": team,
            "center": np.array([cx, cy]),
            "rear_pad": next(
                Polygon(f["geometry"]["coordinates"][0])
                for f in json.loads((WIT.parent / "gate-routes.geojson").read_text())[
                    "features"
                ]
                if f["properties"]["site"] == team
                and f["properties"]["role"] == "rear_pad"
            ),
        }
        previous = unary_union(list(material_polygons(d).values()))
        visible = unary_union(list(shapes[team].values()))
        overlap = previous.intersection(visible).area
        if overlap > 0.001:
            raise ValueError((team, "overlap with .9 main driving lane", overlap))
        court = Polygon(base["court_outer_polygon_m"])
        driven = shapes[team]["ServiceSoil"]
        link_coverage = None
        if team != "green":
            row = next(
                s
                for s in plan["surfaces"]
                if s["id"] == team + "_original_road_court_link"
            )
            link = Polygon([p[:2] for p in row["top_polygon_m"]])
            link_coverage = driven.intersection(link).area / link.area
            if link_coverage < 0.999:
                raise ValueError((team, "old lip exposed", link_coverage))
        results[team] = {
            "native_triangles": len(ind),
            "contact_samples": len(values),
            "native_face_to_collision_m": [float(values.min()), float(values.max())],
            "surface_area_m2": {k: round(v.area, 2) for k, v in shapes[team].items()},
            "legacy_court_top_new_coverage_m2": round(
                court.intersection(visible).area, 2
            ),
            "legacy_court_footprint_m2": round(court.area, 2),
            "upper_terrain_overlap_with_952_m2": overlap,
            "service_link_original_top_replaced_fraction": link_coverage,
        }
    return {
        "passed": True,
        "native_parent": sha(BASE9 / "receipt.json"),
        "unchanged_bsp_sha256": json.loads((WIT / "source.json").read_text())[
            "shipped_bsp_sha256"
        ],
        "render_only": True,
        "sites": results,
    }


def main():
    shapes = geometry()
    profiles = material_profile()
    result = package(
        source=FINISH,
        stem="pakchunk951-MJOLNIRPWRSITEFINISH-PWR_P",
        mesh_prefix="SM_PWR_SiteFinish_",
        actor_prefix="pwr_site_finish_",
        slots=SLOTS,
        binding_keys=("floor", "dark_floor", "alloy", "dark", "trim"),
        make_recipe=lambda i: copy.deepcopy(profiles[i]),
        retired=(),
        schema="pwr-native-site-finishes-v1",
    )
    result["validation"] = checks(result["decor"], shapes)
    (FINISH / "native/package.receipt.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result["validation"], indent=2))


if __name__ == "__main__":
    main()
