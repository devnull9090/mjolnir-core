# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0,<3", "scipy==1.17.0", "pillow>=11,<13", "pyamg>=5,<6"]
# ///
"""Fit physical roads, terraces and drainage into the immutable Gaea terrain.

Run with uv run levels/warfare/pwr/terrain/finalize_terrain.py. No app calls.
All coordinates remain authoring metres Z-up; output rows increase in Y.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import distance_transform_edt, gaussian_filter
from scipy.optimize import LinearConstraint, minimize
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import Heightfield, load_heightfield, write_heightfield, sha256


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def arclength(xy):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]


def line_samples(a, b, spacing=2.0):
    n = max(1, int(np.ceil(np.linalg.norm(b - a) / spacing)))
    return np.linspace(a, b, n + 1)[1:]


def rounded_road(points, radius=35.0, spacing=2.0):
    """Tangent circular fillets; preserve exact named endpoints, trace controls.

    Interior controls define intersecting tangents, not mandatory road vertices.
    The circle replaces each sharp corner while preserving its approach lines.
    """
    p = np.asarray(points, dtype=float)
    out = [p[0]]
    radii = []
    for i in range(1, len(p) - 1):
        u, v = p[i] - p[i - 1], p[i + 1] - p[i]
        a, b = np.linalg.norm(u), np.linalg.norm(v)
        u, v = u / a, v / b
        angle = math.acos(float(np.clip(u @ v, -1, 1)))
        if angle < 1e-4:
            out.extend(line_samples(np.asarray(out[-1]), p[i], spacing))
            continue
        distance = min(radius * math.tan(angle / 2), a * .45, b * .45)
        actual_radius = distance / math.tan(angle / 2)
        radii.append(actual_radius)
        start, end = p[i] - u * distance, p[i] + v * distance
        sign = 1 if u[0] * v[1] - u[1] * v[0] > 0 else -1
        centre = start + np.array([-u[1], u[0]]) * actual_radius * sign
        out.extend(line_samples(np.asarray(out[-1]), start, spacing))
        theta = math.atan2(start[1] - centre[1], start[0] - centre[0])
        n = max(2, int(math.ceil(actual_radius * angle / spacing)))
        angles = theta + sign * np.linspace(0, angle, n + 1)[1:]
        out.extend(centre + actual_radius * np.c_[np.cos(angles), np.sin(angles)])
        out[-1] = end
    out.extend(line_samples(np.asarray(out[-1]), p[-1], spacing))
    xy = np.asarray(out)
    keep = np.r_[True, np.linalg.norm(np.diff(xy, axis=0), axis=1) > 1e-7]
    return xy[keep], min(radii, default=1e12)


def water_curve(points, spacing=2.0):
    points = np.asarray(points, dtype=float)
    s = arclength(points)
    curve = CubicSpline(s, points, bc_type="natural")
    # Include control stations exactly, particularly the braid's parent junction.
    t = np.unique(np.r_[np.linspace(0, s[-1], int(s[-1] / spacing) + 1), s])
    return curve(t)


def inside_polygon(x, y, polygon):
    result = np.zeros(np.broadcast_shapes(np.shape(x), np.shape(y)), dtype=bool)
    p = np.asarray(polygon)
    for a, b in zip(p, np.roll(p, -1, axis=0)):
        if abs(b[1] - a[1]) < 1e-12:
            continue
        result ^= ((a[1] > y) != (b[1] > y)) & (x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0])
    return result


def nearest_line(points, line):
    """Exact projection onto segments beside nearest dense (<=2 m) samples."""
    _, nearest = cKDTree(line[:, :2]).query(points)
    best = np.full(len(points), np.inf)
    index = np.zeros(len(points), dtype=int)
    fraction = np.zeros(len(points))
    for delta in (-2, -1, 0, 1):
        i = np.clip(nearest + delta, 0, len(line) - 2)
        a, b = line[i, :2], line[i + 1, :2]
        ab = b - a
        t = np.clip(np.sum((points - a) * ab, axis=1) / np.maximum(np.sum(ab * ab, axis=1), 1e-12), 0, 1)
        distance = np.linalg.norm(points - a - ab * t[:, None], axis=1)
        take = distance < best
        best[take], index[take], fraction[take] = distance[take], i[take], t[take]
    return best, index, fraction


def local_raster(x, y, line, reach):
    low = np.min(line[:, :2], axis=0) - reach
    high = np.max(line[:, :2], axis=0) + reach
    ix = np.flatnonzero((x >= low[0]) & (x <= high[0]))
    iy = np.flatnonzero((y >= low[1]) & (y <= high[1]))
    region = np.s_[iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1]
    gx, gy = np.meshgrid(x[ix], y[iy])
    shape = gx.shape
    distance, i, t = nearest_line(np.c_[gx.ravel(), gy.ravel()], line)
    z = line[i, 2] * (1 - t) + line[i + 1, 2] * t
    return region, distance.reshape(shape), z.reshape(shape)


def fit_roads(plan, field):
    nodes = plan["nodes"]
    ids = {n["id"]: i for i, n in enumerate(nodes)}
    xy = np.asarray([n["position_m"] for n in nodes])
    target = field.sample(xy[:, 0], xy[:, 1])
    weights = np.ones(len(nodes))
    for site in plan["sites"]:
        if site["role"] in ("permanent_base", "dominant_northern_citadel"):
            index = ids[site["access_node"]]
            xx, yy = site["position_m"]
            offsets = np.array([(dx, dy) for dx in (-35, 0, 35) for dy in (-35, 0, 35)])
            target[index] = np.median(field.sample(xx + offsets[:, 0], yy + offsets[:, 1]))
            weights[index] = 8
    roads, rows, limits = [], [], []
    def constrain(a, b, limit):
        if a == b:
            return
        row = np.zeros(len(nodes)); row[ids[b]] = 1; row[ids[a]] = -1
        rows.append(row); limits.append(limit)
    curves = {r["id"]: rounded_road(r["control_points_m"]) for r in plan["roads"]}
    for source in plan["roads"]:
        curve, radius = curves[source["id"]]
        stations = arclength(curve)
        grade = min(source["max_grade"], .06 if "apron" in source["id"] else .10)
        buffer = min(35.0, stations[-1] * .2)
        road = {**source, "xy": curve, "stations": stations, "minimum_radius_m": radius,
                "grade_limit": grade, "junction_flat_m": buffer}
        assigned = np.full(len(curve), -1, dtype=int)
        assigned[stations <= buffer] = ids[source["from"]]
        assigned[stations >= stations[-1] - buffer] = ids[source["to"]]
        # Adjacent arms of the same junction can overlap at carriageway width
        # long before their centreline endpoints meet. Give that whole merge
        # the shared node's plane, rather than averaging two incompatible Zs.
        for other in plan["roads"]:
            if other["id"] == source["id"]:
                continue
            close = cKDTree(curves[other["id"]][0]).query(curve)[0] < 46
            for end in ("from", "to"):
                node = source[end]
                if node not in (other["from"], other["to"]):
                    continue
                ordered = close if end == "from" else close[::-1]
                count = next((i for i, value in enumerate(ordered) if not value), len(ordered))
                if count:
                    if end == "from":
                        assigned[stations <= stations[count - 1] + 8] = ids[node]
                    else:
                        assigned[stations >= stations[-count] - 8] = ids[node]
        if not source.get("structure"):
            for site in plan["sites"]:
                if site.get("footprint_m"):
                    polygon = np.asarray(site["footprint_m"])
                    boundary = np.concatenate([np.r_[a[None], line_samples(a, b)]
                                               for a, b in zip(polygon, np.roll(polygon, -1, axis=0))])
                    distance = cKDTree(boundary).query(curve)[0]
                    touched = inside_polygon(curve[:, 0], curve[:, 1], polygon) | (distance < 78)
                else:
                    touched = np.linalg.norm(curve - site["position_m"], axis=1) < max(site["size_m"]) / 2 + 50
                if touched.any():
                    lo, hi = stations[touched].min() - 10, stations[touched].max() + 10
                    assigned[(stations >= lo) & (stations <= hi)] = ids[site["access_node"]]
        assigned[0], assigned[-1] = ids[source["from"]], ids[source["to"]]
        anchors = []
        start = None
        for i in range(len(assigned) + 1):
            value = assigned[i] if i < len(assigned) else -1
            if start is not None and (value != assigned[start] or i == len(assigned)):
                anchors.append((float(stations[start]), float(stations[i - 1]), nodes[assigned[start]]["id"]))
                start = None
            if value >= 0 and start is None:
                start = i
        road["anchors"] = anchors
        roads.append(road)
        for a, b in zip(anchors, anchors[1:]):
            length = b[0] - a[1]
            # The inside lane travels less distance around a bend than its
            # centreline. Limit the entire 24 m carriageway, not just its centre.
            lane_factor = max(.25, 1 - source["width_m"] / (2 * radius))
            constrain(a[2], b[2], 0 if length < 3 or source.get("structure") or "apron" in source["id"]
                      else grade * length / 1.5 * .78 * lane_factor)
    matrix, limits = np.asarray(rows), np.asarray(limits)
    # Bridge equality rows and the citadel apron equality share the same solver.
    equality = limits == 0
    independent = []
    for row in matrix[equality]:
        if np.linalg.matrix_rank(np.asarray(independent + [row])) > len(independent):
            independent.append(row)
    constraints = [LinearConstraint(matrix[~equality], -limits[~equality], limits[~equality])]
    if independent:
        constraints.append(LinearConstraint(np.asarray(independent), 0, 0))
    def objective(z):
        return np.sum(weights * (z - target) ** 2)
    solved = minimize(objective, target, jac=lambda z: 2 * weights * (z - target),
                      constraints=constraints, method="SLSQP", options={"maxiter": 1000, "ftol": 1e-8})
    if not solved.success or np.max(np.abs(matrix @ solved.x) - limits) > 1e-5:
        raise ValueError(f"Road grade fit failed: {solved.message}")
    for road in roads:
        stations = road["stations"]
        z = np.full(len(stations), np.nan)
        for a, b, node in road["anchors"]:
            z[(stations >= a) & (stations <= b)] = solved.x[ids[node]]
        for a, b in zip(road["anchors"], road["anchors"][1:]):
            select = (stations > a[1]) & (stations < b[0])
            start, end = solved.x[ids[a[2]]], solved.x[ids[b[2]]]
            z[select] = start + (end - start) * smooth((stations[select] - a[1]) / (b[0] - a[1]))
        if not np.isfinite(z).all():
            raise ValueError(f"Unassigned elevation on {road['id']}")
        road["line"] = np.c_[road["xy"], z]
    return roads, {node["id"]: float(z) for node, z in zip(nodes, solved.x)}


def make_water(plan, lake_level, roads):
    rivers = []
    for river in plan["watercourses"]:
        xy = water_curve(river["control_points_m"])
        stations = arclength(xy); t = stations / stations[-1]
        profile = np.asarray(river["relative_water_profile"])
        normalized = np.interp(t, profile[:, 0], profile[:, 1]) / profile[0, 1]
        crossings = [c for c in plan["crossings"] if c["watercourse"] == river["id"]]
        controls = []
        for crossing in crossings:
            deck = next(r for r in roads if r["id"] == crossing["road"])["line"][0, 2]
            station = int(np.argmin(np.linalg.norm(xy - crossing["position_m"], axis=1)))
            controls.append((t[station], deck - (16 if crossing["type"] == "culvert" else 20)))
        if river.get("source"):
            parent = next(r for r in rivers if r["id"] == river["source"]["watercourse"])
            point = np.asarray([river["source"]["position_m"]])
            _, i, u = nearest_line(point, parent["line"])
            head = float(parent["line"][i[0], 2] * (1 - u[0]) + parent["line"][i[0] + 1, 2] * u[0])
            anchors = [(0, head), *controls, (1, lake_level)]
            for i in range(len(anchors) - 2, -1, -1):
                anchors[i] = (anchors[i][0], max(anchors[i][1], anchors[i + 1][1] + .1))
            anchors[0] = (0, head)
            levels = np.interp(t, *np.asarray(anchors).T)
            falls = []
        else:
            anchors = [(0, max(150.0, controls[0][1] + 35)), *controls, (1, lake_level)]
            for i in range(len(anchors) - 2, -1, -1):
                anchors[i] = (anchors[i][0], max(anchors[i][1], anchors[i + 1][1] + 2))
            # Each reach descends gently, then spends 35% of its drop in a
            # short cascade. Endpoints remain exactly tied to bridge clearances.
            levels = np.interp(t, *np.asarray(anchors).T)
            falls = []
            for a, b in zip(anchors, anchors[1:]):
                select = (t >= a[0]) & (t <= b[0])
                q = (t[select] - a[0]) / (b[0] - a[0])
                progress = .65 * q + .35 * smooth((q - .56) / .12)
                levels[select] = a[1] + (b[1] - a[1]) * progress
                station = a[0] + .62 * (b[0] - a[0])
                j = int(np.argmin(np.abs(t - station)))
                falls.append({"position_m": xy[j].tolist(), "drop_m": (a[1] - b[1]) * .35,
                              "reach_length_m": .12 * (b[0] - a[0]) * stations[-1]})
        rivers.append({**river, "line": np.c_[xy, levels], "stations": stations, "cascades": falls})
    return rivers


def validate_geometry(field, geometry):
    """Audit the actual exported samples; no inference about native collision."""
    roads, waters, crossings, foundations = [], [], [], []
    for road in geometry["roads"]:
        line = np.asarray(road["centreline_m"])
        sections = np.asarray(road["cross_sections_m"])
        grades = []
        for lane in (1, 2, 3):
            distance = np.linalg.norm(np.diff(sections[:, lane, :2], axis=0), axis=1)
            grades.append(float(np.max(np.abs(np.diff(sections[:, lane, 2])) / np.maximum(distance, 1e-9))))
        error = 0.0 if road.get("structure") else float(np.max(np.abs(field.sample(line[:, 0], line[:, 1]) - line[:, 2])))
        if max(grades) > road["grade_limit"] + .001:
            raise ValueError(f"Road lane grade exceeds limit: {road['id']} {max(grades):.6f}")
        if error > .05:
            raise ValueError(f"Road floats above or cuts into terrain: {road['id']} {error:.6f}m")
        if road["minimum_radius_m"] + 1e-5 < road["target_min_radius_m"]:
            raise ValueError(f"Road turning radius too tight: {road['id']}")
        roads.append({"id": road["id"], "lane_max_grade": max(grades), "alignment_max_error_m": error})
    for river in geometry["watercourses"]:
        line = np.asarray(river["surface_centreline_m"])
        depth = line[:, 2] - field.sample(line[:, 0], line[:, 1])
        if np.max(np.diff(line[:, 2])) > 1e-6 or np.min(depth) < 1.0:
            raise ValueError(f"Blocked or uphill watercourse: {river['id']}")
        if abs(line[-1, 2] - 55) > 1e-6:
            raise ValueError(f"River/lake outlet discontinuity: {river['id']}")
        junction_error = 0.0
        if river.get("source"):
            parent = next(r for r in geometry["watercourses"] if r["id"] == river["source"]["watercourse"])
            parent_line = np.asarray(parent["surface_centreline_m"])
            _, index, fraction = nearest_line(line[:1, :2], parent_line)
            parent_z = parent_line[index[0], 2] * (1 - fraction[0]) + parent_line[index[0] + 1, 2] * fraction[0]
            junction_error = float(abs(line[0, 2] - parent_z))
            if junction_error > 1e-5:
                raise ValueError("Tributary water level does not match its parent")
        waters.append({"id": river["id"], "min_depth_m": float(depth.min()),
                       "max_depth_m": float(depth.max()), "source_z_m": float(line[0, 2]),
                       "outlet_z_m": float(line[-1, 2]), "parent_junction_error_m": junction_error})
    for crossing in geometry["crossings"]:
        road = next(r for r in geometry["roads"] if r["id"] == crossing["road"])
        river = next(r for r in geometry["watercourses"] if r["id"] == crossing["watercourse"])
        water = np.asarray(river["surface_centreline_m"])
        _, index, fraction = nearest_line(np.asarray([crossing["position_m"]]), water)
        z = water[index[0], 2] * (1 - fraction[0]) + water[index[0] + 1, 2] * fraction[0]
        freeboard = float(road["centreline_m"][0][2] - z)
        if freeboard < crossing["minimum_freeboard_m"]:
            raise ValueError(f"Insufficient crossing clearance: {crossing['id']}")
        crossings.append({"id": crossing["id"], "water_z_m": float(z), "freeboard_m": freeboard})
    for site in geometry["sites"]:
        x, y, z = site["position_m"]
        error = abs(float(field.sample(x, y)) - z)
        if error > .02:
            raise ValueError(f"Foundation centre does not match terrace: {site['id']}")
        foundations.append({"id": site["id"], "height_m": z, "centre_error_m": error})
    return {"roads": roads, "watercourses": waters, "crossings": crossings, "foundations": foundations,
            "max_lane_grade": max(r["lane_max_grade"] for r in roads),
            "max_road_alignment_error_m": max(r["alignment_max_error_m"] for r in roads)}


def finalize(source, plan_path, output):
    field = load_heightfield(source)
    plan_bytes = Path(plan_path).read_bytes(); plan = json.loads(plan_bytes)
    w, h = field.dimensions
    x = np.linspace(field.bounds_m[0][0], field.bounds_m[1][0], w)
    y = np.linspace(field.bounds_m[0][1], field.bounds_m[1][1], h)
    gx, gy = np.meshgrid(x, y)
    spacing = field.spacing_m
    # Gaea preserves the outer mountain formations. Its image-derived lowland
    # levels were too high over the lake, so grade a broad connected valley
    # floor before fitting narrow transport corridors. This prevents road mesas.
    network = np.concatenate([rounded_road(r["control_points_m"])[0] for r in plan["roads"]] +
                             [water_curve(r["control_points_m"]) for r in plan["watercourses"]])
    distance = cKDTree(network).query(np.c_[gx.ravel(), gy.ravel()])[0].reshape(gx.shape)
    corridor = 1 - smooth((distance - 110) / 180)
    lowland = 1 - smooth((field.heights_m - 190) / 95)
    valley_floor = 55 + .047 * (gy + 1000)
    rolling = 3 * np.sin(gx / 95) * np.cos(gy / 125)
    gentle = valley_floor + .14 * (gaussian_filter(field.heights_m, 5) - valley_floor) + rolling
    basis = field.heights_m * (1 - corridor * lowland) + gentle * corridor * lowland
    terrain = basis.copy()
    masks = {k: np.zeros_like(terrain) for k in ("road", "water", "shore", "bases", "flat", "forest", "walkable")}
    basis_field = Heightfield(basis, field.origin_m, field.spacing_m, {}, field.metadata, field.manifest_sha256, field.path)
    roads, node_z = fit_roads(plan, basis_field)
    rivers = make_water(plan, 55.0, roads)
    sites = []
    # Terraces are local irregular footprints; the surrounding eroded ridges remain.
    for site in plan["sites"]:
        cx, cy = site["position_m"]
        if site.get("footprint_m"):
            inside = inside_polygon(gx, gy, site["footprint_m"])
        else:
            inside = (gx - cx) ** 2 + (gy - cy) ** 2 <= (max(site["size_m"]) / 2) ** 2
        outside = distance_transform_edt(~inside, sampling=spacing[::-1])
        z = node_z[site["access_node"]]
        # Warmup and capture B use their parent terrace's exact height.
        blend = 1 - smooth(outside / (55 if site.get("footprint_m") else 28))
        terrain = terrain * (1 - blend) + z * blend
        masks["bases"] = np.maximum(masks["bases"], inside)
        masks["flat"] = np.maximum(masks["flat"], inside)
        sites.append({**site, "position_m": [cx, cy, z], "terrace_z_m": z,
                      "blend_width_m": 55 if site.get("footprint_m") else 28})
    # Road earthworks first, waterways last: a bridge never becomes an earthen dam.
    weight_sum, target_sum, influence = (np.zeros_like(terrain) for _ in range(3))
    for road in roads:
        if road.get("structure"):
            continue
        region, distance, z = local_raster(x, y, road["line"], 100)
        carriage = road["width_m"] / 2
        core = carriage + road["shoulder_m"] + 4  # Grid/interpolation safety outside 24 m carriageway.
        weight = 1 - smooth((distance - core) / 70)
        active = distance <= core + 70
        # Strong nearest-carriageway priority prevents wide shoulders shifting another road.
        weighted = np.where(active, weight / (1e-5 + np.maximum(distance - core, 0) ** 2), 0)
        weight_sum[region] += weighted
        target_sum[region] += weighted * z
        influence[region] = np.maximum(influence[region], weight)
        masks["road"][region] = np.maximum(masks["road"][region], 1 - smooth((distance - carriage) / 12))
    road_target = target_sum / np.maximum(weight_sum, 1e-12)
    terrain = terrain * (1 - influence) + road_target * influence
    # Re-lock building interiors. Road endpoints are on their shared exact plane.
    for site in sites:
        cx, cy, z = site["position_m"]
        inside = (inside_polygon(gx, gy, site["footprint_m"]) if site.get("footprint_m") else
                  (gx - cx) ** 2 + (gy - cy) ** 2 <= (max(site["size_m"]) / 2) ** 2)
        terrain[inside] = z
    lakes = []
    for lake in plan["lakes"]:
        inside = inside_polygon(gx, gy, lake["polygon_m"])
        din = distance_transform_edt(inside, sampling=spacing[::-1])
        dout = distance_transform_edt(~inside, sampling=spacing[::-1])
        floor = 55.0 - 7.0 * smooth(din / 28)
        outside_target = 55.0 + .06 * dout + 1.5 * np.sin(gx / 70) * smooth(dout / 35)
        blend = 1 - smooth(dout / 180)
        terrain = terrain * (1 - blend) + np.where(inside, floor, outside_target) * blend
        wet = inside.copy()
        island_rows = []
        for island in lake.get("islands", []):
            land = inside_polygon(gx, gy, island["polygon_m"])
            di = distance_transform_edt(land, sampling=spacing[::-1])
            do = distance_transform_edt(~land, sampling=spacing[::-1])
            island_z = 56.0 + 7 * smooth(di / 35) + .8 * np.sin(gx / 22) * smooth(di / 20)
            b = 1 - smooth(do / 22)
            terrain = terrain * (1 - b) + island_z * b
            wet &= ~land
            island_rows.append({**island, "minimum_land_z_m": float(terrain[land].min())})
        masks["water"] = np.maximum(masks["water"], wet)
        masks["shore"] = np.maximum(masks["shore"], 1 - smooth(np.where(inside, din, dout) / 35))
        lakes.append({**lake, "water_z_m": 55.0, "floor_z_m": 48.0, "islands": island_rows})
    # Channels inherit continuous downstream water levels; parent/braid levels coincide.
    for river in rivers:
        region, distance, water = local_raster(x, y, river["line"], 90)
        half = river["channel_width_m"] / 2
        depth = river["target_water_depth_m"]
        bank = 1 - smooth((distance - half) / 55)
        bed = water - depth * (1 - smooth((distance - half * .65) / (half * .35)))
        bank_target = water + .15 * np.maximum(distance - half, 0)
        target = np.where(distance <= half, bed, bank_target)
        previous = terrain[region].copy()
        shaped = previous * (1 - bank) + target * bank
        existing_water = masks["water"][region] >= .5
        # A tributary's bank must not dam its parent channel or raise a lake bed.
        shaped = np.where(existing_water, np.minimum(previous, shaped), shaped)
        terrain[region] = shaped
        masks["water"][region] = np.maximum(masks["water"][region], distance <= half)
        masks["shore"][region] = np.maximum(masks["shore"][region], 1 - smooth(np.abs(distance - half) / 28))
    # Shore blending must not dig the vehicle carriageway down toward the river.
    # Restore road profiles outside wet channels, then keep dry foundations flat.
    water_distance = distance_transform_edt(masks["water"] < .5, sampling=spacing[::-1])
    dry_influence = influence * smooth(water_distance / 12)
    terrain = terrain * (1 - dry_influence) + road_target * dry_influence
    for site in sites:
        cx, cy, z = site["position_m"]
        inside = (inside_polygon(gx, gy, site["footprint_m"]) if site.get("footprint_m") else
                  (gx - cx) ** 2 + (gy - cy) ** 2 <= (max(site["size_m"]) / 2) ** 2)
        outside = distance_transform_edt(~inside, sampling=spacing[::-1])
        blend = (1 - smooth(outside / (55 if site.get("footprint_m") else 28))) * smooth(water_distance / 12)
        terrain = terrain * (1 - blend) + z * blend
    # Save the physical field before geometry sampling. Every reported placement
    # below uses these exact float32 samples, matching later collision/PCG inputs.
    terrain = terrain.astype(np.float32)
    final = Heightfield(terrain, field.origin_m, spacing, masks, {}, "", Path(output))
    dy, dx = np.gradient(terrain.astype(float), *spacing[::-1])
    slope = np.hypot(dx, dy)
    masks["walkable"] = (slope <= .35) & (masks["water"] < .5)
    water_distance = distance_transform_edt(masks["water"] < .5, sampling=spacing[::-1])
    road_distance = distance_transform_edt(masks["road"] < .1, sampling=spacing[::-1])
    base_distance = distance_transform_edt(masks["bases"] < .5, sampling=spacing[::-1])
    masks["forest"] = np.clip((.65 - slope) / .45, 0, 1) * smooth((water_distance - 18) / 35) * smooth((road_distance - 12) / 20) * smooth(base_distance / 24)
    road_rows, road_checks = [], []
    for road in roads:
        line = road["line"]
        tangents = np.gradient(line[:, :2], axis=0)
        tangents /= np.linalg.norm(tangents, axis=1)[:, None]
        normals = np.c_[-tangents[:, 1], tangents[:, 0]]
        offsets = [-18, -12, 0, 12, 18]
        sections = []
        for point, normal in zip(line, normals):
            positions = point[:2] + np.asarray(offsets)[:, None] * normal
            z = final.sample(positions[:, 0], positions[:, 1])
            if road.get("structure"):
                z = np.full_like(z, point[2])
            sections.append(np.c_[positions, z].tolist())
        heights = final.sample(line[:, 0], line[:, 1])
        designed_grade = np.max(np.abs(np.diff(line[:, 2]) / np.diff(road["stations"])))
        sampled_grade = np.max(np.abs(np.diff(heights) / np.diff(road["stations"])))
        error = np.max(np.abs(heights - line[:, 2]))
        row = {k: v for k, v in road.items() if k not in ("xy", "stations", "line")}
        row.update(centreline_m=line.tolist(), cross_section_offsets_m=offsets, cross_sections_m=sections)
        road_rows.append(row)
        road_checks.append({"id": road["id"], "length_m": float(road["stations"][-1]),
                            "min_radius_m": road["minimum_radius_m"], "grade_limit": road["grade_limit"],
                            "design_max_grade": float(designed_grade), "terrain_max_grade": float(sampled_grade),
                            "max_terrain_alignment_error_m": float(error), "structure": road.get("structure")})
    river_rows = [{**{k: v for k, v in river.items() if k not in ("line", "stations")},
                   "surface_centreline_m": river["line"].tolist()} for river in rivers]
    geometry = {"schema": "pwr-terrain-geometry-v1", "coordinates": "authoring_metres_z_up",
                "nodes": [{**n, "position_m": [*n["position_m"], node_z[n["id"]]]} for n in plan["nodes"]],
                "roads": road_rows, "watercourses": river_rows, "lakes": lakes, "sites": sites,
                "crossings": plan["crossings"]}
    validation = validate_geometry(final, geometry)
    root = Path(output).parent
    root.mkdir(parents=True, exist_ok=True)
    geometry_path = root / "terrain.geometry.json"
    geometry_path.write_text(json.dumps(geometry, indent=1) + "\n")
    final = write_heightfield(output, terrain, field.origin_m, spacing, masks,
                             source_manifest_sha256=field.manifest_sha256,
                             source_height_sha256=field.metadata["height"]["sha256"],
                             site_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                             generator="finalize_terrain.py v1", geometry=geometry_path.name,
                             geometry_sha256=sha256(geometry_path), water_level_m=55.0)
    report = {"schema": "pwr-terrain-finalization-v1", "master_sha256": final.manifest_sha256,
              "height_sha256": final.metadata["height"]["sha256"], "roads": road_checks,
              "terrain_range_m": [float(terrain.min()), float(terrain.max())],
              "modified_fraction_over_1m": float(np.mean(np.abs(terrain - field.heights_m) > 1)),
              "water_downhill": all(np.all(np.diff(r["line"][:, 2]) <= 1e-7) for r in rivers),
              "validation": validation,
              "earthworks": {"lake_level_m": 55, "lake_floor_m": 48, "lake_shore_blend_m": 180,
                             "nearshore_target_grade": .06, "lowland_floor_grade_north_south": .047,
                             "mountain_preservation": "Gaea slopes above285m remain outside lowland compression"},
              "maximum_adjacent_height_jump_m": float(max(np.max(np.abs(np.diff(terrain, axis=0))),
                                                            np.max(np.abs(np.diff(terrain, axis=1))))),
              "native_collision_parity": "pending adaptive collision report and live checks"}
    (root / "finalization.receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"master": str(output), "geometry": str(geometry_path), "roads": len(roads),
                      "range_m": report["terrain_range_m"], "modified_fraction": report["modified_fraction_over_1m"],
                      "worst_terrain_road_error_m": max(r["max_terrain_alignment_error_m"] for r in road_checks if not r["structure"]),
                      "worst_terrain_road_grade": max(r["terrain_max_grade"] for r in road_checks if not r["structure"])}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--plan", type=Path, default=HERE / "site-plan-v3.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--preserve-runtime",type=Path,help="Constrain new relief to this immutable tested runtime master")
    parser.add_argument("--preserve-layout",type=Path,default=HERE.parent/"native-contract-v3/layout.json")
    parser.add_argument("--resume-rejected",type=Path,help="Hash-verified rejected fit NPZ; applies the bounded local derivative correction")
    parser.add_argument("--blend-m",type=float,default=180.0)
    parser.add_argument("--max-correction-grade",type=float,default=.75)
    parser.add_argument("--maximum-terrain-m",type=float,default=400.0)
    args = parser.parse_args()
    if args.preserve_runtime:
        if not args.source:parser.error("Constrained terrain requires an explicit new --source")
        from constrain_terrain import constrain
        output=args.out or HERE/"final-v5/final-master.json"
        report=constrain(args.source,args.preserve_runtime,args.preserve_layout,output,args.blend_m,
                         args.max_correction_grade,args.maximum_terrain_m,args.resume_rejected)
        print(json.dumps({"master":str(output),"master_sha256":report["master_manifest_sha256"],
                          "protected_error_m":report["protected_max_abs_error_m"],"blend":report["blend"]}))
    else:
        if args.out is None:parser.error("Legacy terrain generation requires explicit --out; frozen v3 is never overwritten by default")
        finalize(args.source or HERE/"gaea-v2/source.json", args.plan, args.out)


if __name__ == "__main__":
    main()
