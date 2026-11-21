"""Prepare the offline PWR base assembly; never launch Blender or a game.

The output supplies metre-space mesh surfaces and placement matrices. It leaves
the shared terrain, native layout, old collision and all build defaults intact.
Run: python levels/warfare/pwr/bases_v1/world_placement.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
sys.path.insert(0, str(ROOT / "levels/warfare/pwr"))
from heightfield import load_heightfield
from world_placements import placements


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(point, polygon):
    """Boundary-inclusive convex polygon test, either winding."""
    point = np.asarray(point)
    p = np.asarray(polygon)
    d = np.roll(p, -1, axis=0) - p
    cross = d[:, 0] * (point[1] - p[:, 1]) - d[:, 1] * (point[0] - p[:, 0])
    return bool(np.all(cross >= -1e-8) or np.all(cross <= 1e-8))


def surface(name, xy, z, center, thickness=.16, role="court"):
    """A small closed polygon prism with fan-triangulated top/bottom faces.

    Polygons supplied here are convex. Values are absolute world metres in the
    output, so consumers need no additional base transform for these meshes.
    """
    xy = np.asarray(xy, dtype=float)
    z = np.broadcast_to(np.asarray(z, dtype=float), (len(xy),))
    area = np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - xy[:, 1] * np.roll(xy[:, 0], -1))
    if area < 0:
        xy, z = xy[::-1], z[::-1]
    top = np.column_stack((xy[:, 0] + center[0], xy[:, 1] + center[1], z))
    bottom = top - np.array([0., 0., thickness])
    n = len(xy)
    faces = [[0, i, i + 1] for i in range(1, n - 1)]
    faces += [[n, n + i + 1, n + i] for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        faces += [[i, n + i, n + j], [i, n + j, j]]
    return {"id": name, "role": role, "vertices_m": np.vstack((top, bottom)).tolist(),
            "triangles": faces, "top_polygon_m": top.tolist(),
            "native_collision_installed": False, "material_role": "court_alloy"}


def ribbon(name, a, b, width, za, zb, center, role="road_link"):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    if np.linalg.norm(d) < .01:
        raise ValueError("Degenerate ribbon")
    n = np.array([-d[1], d[0]]) / np.linalg.norm(d) * width / 2
    return surface(name, [a - n, b - n, b + n, a + n], [za, zb, zb, za], center, .12, role)


def road_at_y(road, y):
    points = np.asarray(road["centreline_m"])
    hits = []
    for a, b in zip(points[:-1], points[1:]):
        if min(a[1], b[1]) <= y <= max(a[1], b[1]) and a[1] != b[1]:
            hits.append(a + (y - a[1]) / (b[1] - a[1]) * (b - a))
    if not hits:
        raise ValueError(f"{road['id']}: no road at Y={y}")
    return hits[0]


def make_plan():
    sources = {
        "heightfield": ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json",
        "geometry": ROOT / "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json",
        "layout": ROOT / "levels/warfare/pwr/native-contract-v3/layout.json",
        "vehicle_spawn_policy": ROOT / "levels/warfare/pwr/vehicle-spawn-policy-v1.json",
        "base_geometry_validation": ROOT / "out/pwr/base-art/geometry-validation.json",
        "trees": ROOT / "out/pwr/visual-v6/scenery/trees/trees.selected.json",
    }
    before = {k: digest(v) for k, v in sources.items()}
    field = load_heightfield(sources["heightfield"])
    geometry = json.loads(sources["geometry"].read_text())
    layout = json.loads(sources["layout"].read_text())
    art = json.loads(sources["base_geometry_validation"].read_text())
    policy = json.loads(sources["vehicle_spawn_policy"].read_text())
    trees = json.loads(sources["trees"].read_text())["instances"]
    tree_xy = np.asarray([t["position"][:2] for t in trees])
    if not art["passed"]:
        raise ValueError("Evaluated base-art geometry must pass first")
    roads = {r["id"]: r for r in geometry["roads"]}
    sites = {s["id"]: s for s in geometry["sites"]}
    gameplay = placements(layout, geometry, field)
    # Keep the existing separately sealed Tank/Banshee origin correction.
    counts = {}
    vehicles = []
    overrides = {p["name"]: p for p in policy["vehicles"]}
    for vehicle in gameplay["vehicles"]:
        team = ("red", "blue")[vehicle["team"]]
        kind = "tank" if "scorpion" in vehicle["tag"] else "banshee" if "banshee" in vehicle["tag"] else "hog"
        key = (team, kind)
        index = counts.get(key, 0)
        counts[key] = index + 1
        name = f"pwr_{kind}_{team}_{index}"
        v = {**vehicle, "id": name, "source": "world_placements.py"}
        if name in overrides:
            x, y, z = overrides[name]["new_pos_cm"]
            v["position_m"] = [x / 100, -y / 100, z / 100]
            v["source"] = "vehicle-spawn-policy-v1.json"
            v["support_floor_m"] = overrides[name]["support_floor_m"]
        else:
            v["support_floor_m"] = vehicle["position_m"][2] - 1
        vehicles.append(v)

    plan = {
        "schema": "pwr-offline-base-world-placement-v1",
        "coordinates": "authoring_metres_z_up",
        "scope": "Offline Blender assembly and numeric preparation only; no native export, collision update, cook, install or game test.",
        "sources": {k: {"path": str(v), "sha256": before[k]} for k, v in sources.items()},
        "base_blend": str(ROOT / "levels/warfare/pwr/bases_v1/forerunner_bases.blend"),
        "remove_old_base_architecture": True,
        "retain_old_podium": False,
        "coordinate_conversion": {"unreal_cm": "[100*x,-100*y,100*z]", "blam_world_units": "metres / 3.048"},
        "gameplay_preserved": {"layout": layout, "vehicles": vehicles, "pickups": gameplay["pickups"],
                               "note": "Coordinates are copied, never moved to the new building. Native gameplay is not modified by this plan."},
        "bases": [], "surfaces": [], "road_visual_trim_polygons_m": [], "validation": {},
    }
    failures = []
    for team, site_id, presentation in [("red", "red_home", [0, 0, 0]),
                                         ("blue", "blue_home", [135, 0, 0]),
                                         ("green", "citadel_plateau", [0, 150, 0])]:
        site = sites[site_id]
        center = np.asarray(site["position_m"], float)
        support_lift = .5075 if team == "green" else .35
        floor_z = float(center[2] + support_lift)
        translation = [float(center[0]), float(center[1]), floor_z - .2]
        delta = np.asarray(translation) - np.asarray(presentation)
        matrix = np.eye(4)
        matrix[:3, 3] = delta
        rear = 30.5 if team == "green" else 29.
        outer = np.array([[-62, -70], [62, -70], [74, -58], [74, 58],
                          [62, 70], [-62, 70], [-74, 58], [-74, -58]], float)
        inner = np.array([[-40, -31], [40, -31], [40, -15], [40, 15],
                          [40, rear], [-40, rear], [-40, 15], [-40, -15]], float)
        base = {"id": team, "site_id": site_id, "collection_prefix": {"red": "01_RED", "blue": "02_BLUE", "green": "03_GREEN"}[team],
                "source_presentation_origin_m": presentation, "normalize_then_translate_m": translation,
                "presentation_world_to_map_matrix": matrix.tolist(), "yaw_degrees": 0,
                "additional_mirror": False, "mirror_note": "Blue already contains the reviewed X reflection; do not reflect it again.",
                "terrace_center_m": center.tolist(), "floor_world_z_m": floor_z,
                "roof_world_z_m": translation[2] + art["datums_m"]["roof_deck_z"],
                "court_hole_local_bounds_m": {"min": [-40, -31], "max": [40, rear]},
                "court_outer_polygon_m": (outer + center[:2]).tolist(),
                "tree_clearance": {}, "surface_ids": [], "connections": [], "samples": [],
                "route_notes": ["Main front/rear and side-front thresholds fill only the external approach; no new floor covers the authored interior seams.",
                                "A 6.5 m ramp pavement leaves the reviewed edge armor intact; turning and articulated vehicle motion remain untested."]}
        def add(item):
            base["surface_ids"].append(item["id"])
            plan["surfaces"].append(item)
        for i in range(8):
            j = (i + 1) % 8
            add(surface(f"{team}_court_{i:02}", [outer[i], outer[j], inner[j], inner[i]], floor_z, center))
        # Close exposed terrain slivers inside the courtyard cutout with a
        # recessed foundation bed. Its top remains below the deepest measured
        # authored floor joint; it must never become an overlay on that floor.
        recess_local_top = .10
        recess_world_top = translation[2] + recess_local_top
        recess_world_bottom = float(center[2] - .25)
        recess = surface(f"{team}_recessed_foundation_bed",
                         [[-40,-31],[40,-31],[40,rear],[-40,rear]],
                         recess_world_top, center, recess_world_top-recess_world_bottom,
                         "recessed_foundation_bed")
        recess["material_role"] = "court_recess"
        add(recess)
        floor_check = "green_main_route_floor_and_cover" if team == "green" else "main_route_floor_and_cover"
        source_minimum_floor = art["checks"][floor_check]["floor_height_range_m"][0]
        recess_check = {"surface_id":recess["id"],"top_local_z_m":recess_local_top,
                        "top_world_z_m":recess_world_top,"bottom_world_z_m":recess_world_bottom,
                        "source_minimum_sampled_floor_local_z_m":source_minimum_floor,
                        "clearance_below_sampled_floor_m":source_minimum_floor-recess_local_top,
                        "clearance_below_ramp_threshold_m":.148-recess_local_top,
                        "passed":bool(recess_local_top < source_minimum_floor and recess_local_top < .148 and recess_world_bottom < recess_world_top)}
        base["recessed_foundation_validation"] = recess_check
        if not recess_check["passed"]:
            failures.append(f"{team}: foundation bed reaches authored floor or ramp")
        # The reviewed side-approach tile joints have no continuous backing:
        # their seam rays reach the original footplate at local Z .07. These
        # separate assembly slabs complete support beneath those joints while
        # leaving every sealed art mesh and its .20 m tile faces unchanged.
        base["gallery_joint_backing"] = []
        for sign in (-1, 1):
            x0, x1 = sorted((sign*29*.65, sign*37*.65))
            y0, y1 = -37*.65, -25.04*.65
            backing = surface(f"{team}_gallery_joint_backing_{sign}",
                              [[x0,y0],[x1,y0],[x1,y1],[x0,y1]],
                              translation[2]+.135, center, .135-.08,
                              "gallery_joint_backing")
            backing["material_role"] = "court_recess"
            add(backing)
            base["gallery_joint_backing"].append({"surface_id":backing["id"],
                "local_bounds_m":{"min":[x0,y0,.08],"max":[x1,y1,.135]},
                "clearance_below_authored_tile_faces_m":.2-.135,
                "scope":"Separate offline assembly support beneath the side-gallery tile joints; sealed art meshes remain unchanged."})
        # Open, low transitions around the sides and rear. The front edge keeps
        # two ground-level Banshee parking bays instead of raising their support.
        expanded = outer.copy()
        expanded[:, 0] += np.sign(expanded[:, 0]) * 6
        expanded[:, 1] += np.sign(expanded[:, 1]) * 6
        for i in range(1, 8):
            j = (i + 1) % 8
            xy = [outer[i], outer[j], expanded[j], expanded[i]]
            endz = field.sample(*(expanded[[j, i]] + center[:2]).T).tolist()
            add(surface(f"{team}_court_edge_{i:02}", xy, [floor_z, floor_z, *endz], center, .12, "court_to_terrain"))
        for x0, x1 in [(-62, -36), (-12, 12), (36, 62)]:
            xy = [[x0, -70], [x1, -70], [x1, -76], [x0, -76]]
            ground = float(field.sample(center[0] + (x0+x1)/2, center[1] - 76))
            add(surface(f"{team}_south_transition_{x0}", xy, [floor_z, floor_z, ground, ground], center, .12, "court_to_terrain"))
        # Authored thresholds end at raw Y -37/36, scaled by .65. The
        # supplied new strips stop at these edges and do not span the building.
        add(surface(f"{team}_main_front_threshold", [[-8,-31],[8,-31],[8,-24.05],[-8,-24.05]], floor_z, center, .12, "tunnel_threshold"))
        add(surface(f"{team}_main_rear_threshold", [[-4.5,23.4],[4.5,23.4],[4.5,rear],[-4.5,rear]], floor_z, center, .12, "tunnel_threshold"))
        for sign in (-1, 1):
            x = sign * 21.45
            # The authored angular apron already supports the gallery before
            # its rectangular doorway floor. Meet its diagonal leading edge;
            # do not lay a new rectangle over its detailed recessed paving.
            def apron_front_y(local_x):
                return -29.25 + (abs(local_x)-17.55) * (5.2/14.95)
            add(surface(f"{team}_side_front_threshold_{sign}",
                        [[x-2.6,-31],[x+2.6,-31],[x+2.6,apron_front_y(x+2.6)],[x-2.6,apron_front_y(x-2.6)]],
                        floor_z, center, .12, "gallery_threshold"))
            x = sign * 32.5
            endpoint_local_z = .148
            endz = translation[2] + endpoint_local_z
            add(surface(f"{team}_roof_ramp_threshold_{sign}", [[x-3.25,-31],[x+3.25,-31],[x+3.25,-27.3],[x-3.25,-27.3]], [floor_z,floor_z,endz,endz], center, .12, "roof_ramp_threshold"))
            measured = next(r for r in art["checks"]["roof_ramps"] if r["bottom_surface"]["point_m"][0] * sign > 0)
            gap = abs(measured["bottom_surface"]["point_m"][2] - endpoint_local_z)
            base["connections"].append({"kind": "roof_ramp", "side": sign, "width_m": 6.5,
                                         "threshold_endpoint_world_m": [center[0]+x,center[1]-27.3,endz],
                                         "measured_ramp_surface_world_m": [center[0]+x,center[1]+measured["bottom_surface"]["point_m"][1],translation[2]+measured["bottom_surface"]["point_m"][2]],
                                         "gap_m": gap, "passed": gap <= .1})
            if gap > .1:
                failures.append(f"{team} ramp {sign}: threshold gap")
        # Clip only road presentation inside this courtyard. Never rewrite
        # terrain.geometry.json, its centreline elevations, or the heightfield.
        plan["road_visual_trim_polygons_m"].append({"id": f"{team}_court_road_cut", "polygon_m": base["court_outer_polygon_m"],
                                                    "operation": "subtract from rendered road mesh/decal only", "native_geometry_changed": False})
        if team in ("red", "blue"):
            road = roads[f"{team}_apron"]
            start = road_at_y(road, center[1]-85)
            end = road_at_y(road, center[1]-70)
            add(ribbon(f"{team}_original_road_court_link", start[:2]-center[:2], end[:2]-center[:2], 16.,
                       float(field.sample(*start[:2]))+.01, floor_z, center))
            base["connections"].append({"kind": "original_road", "road_id": road["id"], "start_world_m": start.tolist(),
                                         "end_world_m": [*end[:2],floor_z], "width_m": 16.,
                                         "note": "New visual link follows the original diagonal to the open court; existing road terminus under the building is trimmed."})
        else:
            start = np.asarray(layout["captures_m"][1])
            knee = np.array([0., center[1]-76])
            knee_z = float(field.sample(*knee))+.01
            add(ribbon("green_capture_court_processional_link", start[:2]-center[:2], knee-center[:2], 24., start[2], knee_z, center))
            add(ribbon("green_processional_court_transition", knee-center[:2], [0,-70], 24., knee_z, floor_z, center))
            base["connections"].append({"kind": "capture_road", "road_id": "citadel_apron", "capture_index": 1,
                                         "start_world_m": start.tolist(), "end_world_m": [0.,center[1]-70,floor_z], "width_m": 24.,
                                         "note": "Runs north across the existing flat terrace from unchanged capture B; no gameplay capture relocation."})
        # Bound terrain support and exclusions on a reproducible 2m grid.
        xx, yy = np.meshgrid(np.arange(-42,42.1,2), np.arange(-100,100.1,2))
        zz = field.sample(center[0]+xx,center[1]+yy)
        mask = field.sample_mask("bases",center[0]+xx,center[1]+yy)
        base["terrain_audit"] = {"sample_count": int(zz.size), "height_min_m": float(zz.min()), "height_max_m": float(zz.max()),
                                 "base_exclusion_min": float(mask.min()), "max_delta_from_terrace_m": float(np.max(np.abs(zz-center[2])))}
        if np.ptp(zz) > .01 or mask.min() < .99:
            failures.append(f"{team}: expected prepared terrace changed")
        for name,x,y in [("main_front",0,-24.05),("main_rear",0,23.4),("left_ramp",-32.5,-27.3),("right_ramp",32.5,-27.3),
                         ("spawn_forecourt",0,-50),("rear_court",0,60)]:
            base["samples"].append({"id":name,"xy_m":[center[0]+x,center[1]+y],"terrain_z_m":float(field.sample(center[0]+x,center[1]+y)),"proposed_floor_z_m":floor_z})
        bounds = art["scene_geometry"][team]["bounds_m"]
        lo = center[:2] + np.asarray(bounds["min"][:2]); hi = center[:2] + np.asarray(bounds["max"][:2])
        distances = np.linalg.norm(np.maximum(np.maximum(lo-tree_xy,tree_xy-hi),0),axis=1)
        nearest = int(distances.argmin())
        base["tree_clearance"] = {"population": len(trees),"minimum_distance_to_base_bounds_m":float(distances[nearest]),
                                  "nearest_xy_m":tree_xy[nearest].tolist(),"vegetation_regenerated":False}
        for corner in [lo,[lo[0],hi[1]],hi,[hi[0],lo[1]]]:
            if not inside(corner,site["footprint_m"]):
                failures.append(f"{team}: base extends outside protected terrace")
        base["bounds_world_m"] = {"min": (np.asarray(bounds["min"])+translation).tolist(), "max": (np.asarray(bounds["max"])+translation).tolist()}
        base["outer_court_replaces_old_podium"] = True
        plan["bases"].append(base)

    # Court tops must still provide the frozen support beneath player spawns,
    # warmup and non-aircraft parking origins. Banshees keep terrain support.
    support_checks = []
    for base in plan["bases"]:
        team = base["id"]
        if team == "green":
            continue
        probes = [(f"{team}_spawn_{i}", p[:2], p[2]-.8) for i,p in enumerate(layout["spawns_m"][team])]
        probes += [(v["id"],v["position_m"][:2],v["support_floor_m"]) for v in vehicles if v["team"] == (0 if team == "red" else 1)]
        if team == "red":
            probes.append(("warmup",layout["warmup_m"][:2],layout["warmup_m"][2]))
        for name,xy,expected in probes:
            in_court = inside(xy,base["court_outer_polygon_m"])
            support = base["floor_world_z_m"] if in_court else float(field.sample(*xy))
            error = abs(support-expected)
            check = {"id":name,"xy_m":list(xy),"expected_z_m":expected,"proposed_z_m":support,"error_m":error,"passed":error <= .01}
            support_checks.append(check)
            if error > .01:
                failures.append(f"{name}: support changed")
    mesh_checks = []
    for item in plan["surfaces"]:
        vertices = np.asarray(item["vertices_m"])
        triangles = np.asarray(item["triangles"])
        area = .5*np.linalg.norm(np.cross(vertices[triangles[:,1]]-vertices[triangles[:,0]],
                                         vertices[triangles[:,2]]-vertices[triangles[:,0]]),axis=1)
        edges = {}
        for triangle in triangles:
            for a,b in zip(triangle,np.roll(triangle,-1)):
                edge = tuple(sorted((int(a),int(b))))
                edges[edge] = edges.get(edge,0)+1
        polygon = np.asarray(item["top_polygon_m"])[:,:2]
        d = np.roll(polygon,-1,axis=0)-polygon
        dn = np.roll(d,-1,axis=0)
        cross = d[:,0]*dn[:,1]-d[:,1]*dn[:,0]
        passed = bool(area.min()>1e-8 and all(n==2 for n in edges.values()) and cross.min()>=-1e-8)
        mesh_checks.append({"id":item["id"],"minimum_triangle_area_m2":float(area.min()),
                            "closed_edges":all(n==2 for n in edges.values()),"convex_top":bool(cross.min()>=-1e-8),"passed":passed})
        if not passed:
            failures.append(f"{item['id']}: invalid prepared surface")
    after = {k:digest(v) for k,v in sources.items()}
    if before != after:
        failures.append("A source changed during preparation")
    plan["validation"] = {"passed":not failures,"failures":failures,"native_support_checks":support_checks,"surface_mesh_checks":mesh_checks,
                          "sources_unchanged":before==after,"surface_count":len(plan["surfaces"]),
                          "scope":"Numeric source-space placement, support-height and ramp endpoint checks. These do not certify imported mesh clearance, collision cooking, vehicle handling or game performance.",
                          "required_next_checks":["Inspect assembled Blender scene and threshold mesh overlaps.",
                                                  "When runtime integration is authorized, replace old structural collision and validate new tunnel collision separately.",
                                                  "Retain the sealed vehicle Z correction and layout; never use prepare_runtime to overwrite the frozen expansion."]}
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=ROOT/"out/pwr/base-integration/placement-plan.json")
    args = parser.parse_args()
    plan = make_plan()
    if not plan["validation"]["passed"]:
        raise SystemExit(json.dumps(plan["validation"],indent=2))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"path":str(args.out),"schema":plan["schema"],"passed":True,
                      "bases":len(plan["bases"]),"surfaces":len(plan["surfaces"]),
                      "support_checks":len(plan["validation"]["native_support_checks"])},indent=2))


if __name__ == "__main__":
    main()
