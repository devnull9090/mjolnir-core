"""Drive and contact probes against decoded .8 Havok and readback .9 mesh faces."""

import json
import sys
import numpy as np
import shapely
from shapely.geometry import LineString
from shapely.strtree import STRtree

from base_approach_paths import ROOT, OUT, PLAN, emit_designs
from base_approach_surfaces import WIT, MASTER, LIFT

sys.path.insert(0, str(ROOT / "levels/warfare/pwr"))
from package_base_paving import read_glb
from heightfield import load_heightfield


class HeightProbe:
    """All vertical ray hits from a broadphase index of real native triangles."""

    def __init__(self, faces):
        normal = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
        keep = np.abs(normal[:, 2]) > 1e-7
        self.faces = faces[keep]
        n = normal[keep]
        self.plane = np.column_stack(
            (-n[:, :2] / n[:, 2, None], np.sum(n * self.faces[:, 0], axis=1) / n[:, 2])
        )
        self.tree = STRtree(shapely.polygons(self.faces[:, :, :2]))

    def hits(self, xy):
        inds = self.tree.query(shapely.points(xy), predicate="intersects")
        i, j = inds
        z = np.sum(xy[i] * self.plane[j, :2], axis=1) + self.plane[j, 2]
        return i, z

    def floors(self, xy, ceiling):
        i, z = self.hits(xy)
        take = z <= ceiling[i]
        floors = np.full(len(xy), -np.inf)
        np.maximum.at(floors, i[take], z[take])
        return floors

    def ceilings(self, xy, floor):
        i, z = self.hits(xy)
        take = z > floor[i] + 0.15
        ceilings = np.full(len(xy), np.inf)
        np.minimum.at(ceilings, i[take], z[take])
        return ceilings


def sampled_route(d, base):
    x, y = d["center"]
    coords = [*d["front"].coords, (x, y + 23.4), *d["rear"].coords]
    line = LineString(coords)
    distance = np.linspace(0, line.length, int(line.length / 0.5) + 1)
    mid = shapely.get_coordinates(shapely.line_interpolate_point(line, distance))
    tangent = np.gradient(mid, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    side = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    return line, mid, tangent, side, distance


def sweep_bodies(faces, probe, center, tangent, side, floor):
    """Check oriented full-length bodies; include vertical faces missed by floor rays."""
    from runtime_collision import triangles_intersect_box

    points = [
        center + tangent * longitudinal + side * lateral
        for longitudinal, lateral in ((-3.5, 0), (3.5, 0), (0, -1.75), (0, 1.75))
    ]
    level = np.array([probe.floors(p, np.full(len(p), floor + 0.14)) for p in points])
    if not np.isfinite(level).all():
        raise ValueError("A chassis corner has no cooked floor")
    pitch = (level[1] - level[0]) / 7.0
    roll = (level[3] - level[2]) / 3.5
    ground = level.mean(axis=0)
    # 7 x 3.5 m chassis with 18 cm underbody clearance. Pitch and roll follow
    # the actual front/rear and side supports on the short court transitions.
    lo = np.array([-3.5, -1.75, 0.18])
    hi = np.array([3.5, 1.75, 4.5])
    index = STRtree(shapely.envelope(shapely.polygons(faces[:, :, :2])))
    for i, origin in enumerate(center):
        query = shapely.box(*(origin - 4.1), *(origin + 4.1))
        test = faces[index.query(query)]
        diff = test[:, :, :2] - origin
        u = diff @ tangent[i]
        v = diff @ side[i]
        w = test[:, :, 2] - ground[i] - pitch[i] * u - roll[i] * v
        body_space = np.stack([u, v, w], axis=2)
        hit = triangles_intersect_box(body_space, lo, hi)
        if len(hit):
            raise ValueError(
                ("Chassis intersects native structure", origin, test[hit[0]])
            )
    return len(center)


def validate(actors):
    source = json.loads((WIT / "source.json").read_text())
    allfaces = np.load(WIT / "base-collision-triangles.npy")
    plan = json.loads(PLAN.read_text())
    sites = {b["id"]: b for b in plan["bases"]}
    field = load_heightfield(MASTER)
    sitesqa = {}
    for d, actor in zip(emit_designs(), actors):
        team = d["team"]
        base = sites[team]
        x, y = d["center"]
        floor = base["floor_world_z_m"]
        local = np.all(
            allfaces.max(1)[:, :2] > d["center"] - [180, 195], axis=1
        ) & np.all(allfaces.min(1)[:, :2] < d["center"] + [180, 140], axis=1)
        all_local = allfaces[local].astype(float)
        probe = HeightProbe(all_local)
        leaf = actor["mesh"].rsplit(".", 1)[1]
        pos, _, t, _ = read_glb(OUT / "native" / (leaf + ".glb"))
        world = (pos * actor["scale"] + actor["pos"]) * np.array([0.01, -0.01, 0.01])
        tri = world[t]
        delta = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = np.abs(delta[:, 2])
        top = tri[
            (area > 1e-7)
            & (area / np.maximum(1e-8, np.linalg.norm(delta, axis=1)) > 0.95)
        ]
        centers = top.mean(1)
        supports = probe.floors(centers[:, :2], centers[:, 2] + 0.09)
        dif = centers[:, 2] - supports
        # Higher than nearby road fascia, no unsupported/punched-through
        # floor allowed. A few mm of legacy visual-vs-BSP sampling difference
        # is normal where the triangle-sized native terrain collision is coarser.
        if not np.isfinite(dif).all() or dif.min() < -0.035 or dif.max() > 0.075:
            ids = np.where((dif < -0.035) | (dif > 0.075) | ~np.isfinite(dif))[0]
            raise ValueError(
                (
                    team,
                    "panel contact",
                    len(ids),
                    [(centers[k].tolist(), dif[k]) for k in ids[:8]],
                )
            )
        vertical = tri[(area / np.maximum(1e-8, np.linalg.norm(delta, axis=1)) < 0.30)]
        if len(vertical) != 12:
            raise ValueError((team, "unexpected under-deck face count", len(vertical)))
        skirt = vertical.reshape(-1, 3)
        ground = field.sample(skirt[:, 0], skirt[:, 1])
        toe = skirt[:, 2] - ground
        if toe.min() > -0.02 or skirt[:, 2].max() > floor - 0.145:
            raise ValueError((team, "under-deck anchoring error"))
        line, mid, tangent, side, dist = sampled_route(d, base)
        lanes = np.vstack(
            [mid + side * offset for offset in (-1.75, -0.8, 0, 0.8, 1.75)]
        )
        floors = probe.floors(lanes, np.full(len(lanes), floor + 0.14))
        heights = probe.ceilings(lanes, floors) - floors
        if not np.isfinite(floors).all() or heights.min() < 4.5:
            q = np.where(~np.isfinite(floors) | (heights < 4.5))[0]
            raise ValueError(
                (
                    team,
                    "Warthog route",
                    len(q),
                    [(lanes[k].tolist(), floors[k], heights[k]) for k in q[:8]],
                )
            )
        # Slope metric is measured over a vehicle wheelbase. Short floor joints
        # at the original threshold are also bounded separately by floor-step.
        h = floors.reshape(5, -1)
        grade = float(np.max(abs(h[:, 8:] - h[:, :-8]) / (dist[8:] - dist[:-8])))
        adjacent = float(np.max(abs(np.diff(h, axis=1))))
        if grade > 0.135 or adjacent > 0.16:
            raise ValueError((team, "drive discontinuity", grade, adjacent))
        parking = [v for v in plan["gameplay_preserved"]["vehicles"] if team in v["id"]]
        clearance = {
            v["id"]: round(line.distance(shapely.Point(v["position_m"][:2])), 2)
            for v in parking
        }
        if clearance and min(clearance.values()) < 9.5:
            raise ValueError((team, "parked vehicle clearance", clearance))
        # At the start of the unloader head the full native pad supports a
        # conservative complete eight-metre turning disk around the center.
        pad = d["rear_pad"]
        probe_xy = np.array(
            [
                [x + u, y + 102 + v]
                for u in np.arange(-8, 8.1, 1)
                for v in np.arange(-8, 8.1, 1)
                if u * u + v * v <= 64
            ]
        )
        if not all(pad.covers(shapely.Point(q)) for q in probe_xy):
            raise ValueError("The rear deck does not contain the receiving turn")
        pad_z = probe.floors(probe_xy, np.full(len(probe_xy), floor + 0.15))
        if not np.isfinite(pad_z).all() or np.ptp(pad_z) > 0.05:
            raise ValueError("Unloading area lacks flat support")
        report = {
            "native_surface_triangles_checked": int(len(top)),
            "native_fascia_triangles_checked": len(vertical),
            "panel_to_native_floor_min_max_m": [float(dif.min()), float(dif.max())],
            "panel_nominal_lift_m": LIFT,
            "fascia_foot_depth_m": float(-toe.min()),
            "native_vehicle_width_m": 3.5,
            "native_vehicle_height_m": 4.5,
            "route_length_m": line.length,
            "native_lane_probes": len(lanes),
            "min_overhead_clearance_m": float(heights.min()),
            "max_grade_over_4m": grade,
            "max_half_metre_step_m": adjacent,
            "vehicle_to_route_centres_m": clearance,
            "rear_head_native_floor_range_m": [float(pad_z.min()), float(pad_z.max())],
            "rear_tested_turn_disk_radius_m": 8.0,
        }
        sitesqa[team] = report
    return {
        "passed": True,
        "mode": "Direct shipped Havok + static native mesh readback, five wheel/body stripes; no live vehicle input",
        "bsp_sha256": source["shipped_bsp_sha256"],
        "collision_readback_triangles": source["decoded_base_faces"],
        "sites": sitesqa,
    }


if __name__ == "__main__":
    faces = np.load(WIT / "base-collision-triangles.npy").astype(float)
    bases = {b["id"]: b for b in json.loads(PLAN.read_text())["bases"]}
    checks = {}
    for d in emit_designs():
        team = d["team"]
        base = bases[team]
        _, center, tangent, side, _ = sampled_route(d, base)
        local = np.all(faces.max(1)[:, :2] > d["center"] - [180, 195], axis=1) & np.all(
            faces.min(1)[:, :2] < d["center"] + [180, 140], axis=1
        )
        native = faces[local]
        checks[team] = sweep_bodies(
            native, HeightProbe(native), center, tangent, side, base["floor_world_z_m"]
        )
    result = {
        "passed": True,
        "native_bsp_sha256": json.loads((WIT / "source.json").read_text())[
            "shipped_bsp_sha256"
        ],
        "envelope_length_width_height_m": [7.0, 3.5, 4.5],
        "underbody_clearance_m": 0.18,
        "chassis_poses_over_native_triangles": checks,
        "sampling_interval_m": 0.5,
    }
    (OUT / "native/body-sweep.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result)
