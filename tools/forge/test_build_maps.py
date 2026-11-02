"""Keep a new Forge map's source, pack inputs and player archive consistent."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
import zipfile
from functools import lru_cache

from build_maps import MAPS, check_level, check_pack_view, unchanged, verify_archive


@lru_cache(maxsize=1)
def crossline_fixture():
    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("forge_map_generator", repo / "forge-maps/generate.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    level, layout = generator.arena_layout()
    geometry = {rf"objects\mjolnir\forge\{slug}\{p['id']}": p
        for slug in ("foundry", "foundry-wide")
        for p in json.loads((repo / f"forge-packs/{slug}/source/geometry.json").read_text())["pieces"]}
    return repo, generator, level, layout, geometry


def point(item, local, lift=0):
    angle = math.radians(-item["rot"][1])
    c, s = math.cos(angle), math.sin(angle)
    return (item["pos"][0] / 100 + local[0]*c - local[1]*s,
            -item["pos"][1] / 100 + local[0]*s + local[1]*c,
            item["pos"][2] / 100 + local[2] + lift)


def collision_world(level, geometry, doors=()):
    # Native canvas generation separately verifies this slab's real collision.
    vertices = [(-48, -80, 0), (48, -80, 0), (48, 80, 0), (-48, 80, 0)]
    world = [(-1, [(-48, 48), (-80, 80), (0, 0)],
              [(vertices[0], vertices[1], vertices[2]), (vertices[0], vertices[2], vertices[3])])]
    raised = {d["panel_index"]: d["travel_m"] for d in doors}
    for i, item in enumerate(level["blam"]["objects"]):
        if item["tag"] not in geometry:
            continue
        body = geometry[item["tag"]]["collision"]
        vertices = [point(item, v, raised.get(i, 0)) for v in body["vertices"]]
        bounds = [(min(v[a] for v in vertices), max(v[a] for v in vertices)) for a in range(3)]
        world.append((i, bounds, [tuple(vertices[j] for j in t) for t in body["triangles"]]))
    return world


def ray(world, start, end, only=None):
    def sub(a, b): return tuple(x-y for x, y in zip(a, b))
    def dot(a, b): return sum(x*y for x, y in zip(a, b))
    def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    direction, hits = sub(end, start), []
    for index, bounds, triangles in world:
        if only is not None and index not in only:
            continue
        if any(max(start[a], end[a]) < lo-1e-7 or min(start[a], end[a]) > hi+1e-7
               for a, (lo, hi) in enumerate(bounds)):
            continue
        for a, b, c in triangles:
            e1, e2 = sub(b, a), sub(c, a)
            h = cross(direction, e2)
            determinant = dot(e1, h)
            if abs(determinant) < 1e-10:
                continue
            inverse, s = 1 / determinant, sub(start, a)
            u, q = inverse * dot(s, h), cross(s, e1)
            v, t = inverse * dot(direction, q), inverse * dot(e2, q)
            if min(u, v, t) >= -1e-7 and u+v <= 1.0000001 and t <= 1.0000001:
                hits.append(t)
    return hits


def samples(points, spacing=.5):
    for start, end in zip(points, points[1:]):
        length = math.dist(start[:2], end[:2])
        tangent = [(end[a]-start[a])/length for a in range(2)]
        count = max(1, math.ceil(length / spacing))
        for i in range(count+1):
            yield [a+(b-a)*i/count for a, b in zip(start, end)], tangent


class ForgeMapBuildTests(unittest.TestCase):
    def test_roadworks_driving_loop_has_flush_collision_and_guarded_seams(self):
        repo = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("roadworks_generator", repo / "forge-maps/generate_roadworks.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        level, layout = generator.circuit()
        self.assertEqual(level, json.loads((repo / "forge-maps/roadworks/roadworks_circuit.level.json").read_text()))
        source = json.loads((repo / "forge-packs/roadworks/source/geometry.json").read_text())
        geometry = {p["id"]: p for p in source["pieces"]}
        objects = level["blam"]["objects"]
        self.assertEqual(MAPS["roadworks"]["dimensions"], [320, 320, 1])
        self.assertEqual(MAPS["roadworks"]["version"], "0.2.0")
        self.assertEqual(level["blam"]["forge_packs"][1]["version"], "0.2.0")
        self.assertAlmostEqual(layout["lap_plan_length_m"], 731.327412287)
        world = level["blam"]["world_bounds"][0]
        self.assertEqual(world["min"], [-192 / 3.048, -192 / 3.048, -8 / 3.048])
        self.assertEqual(world["max"], [192 / 3.048, 192 / 3.048, 64 / 3.048])

        def transform(item, point, direction=False):
            yaw = math.radians(-item["rot"][1])
            p = [point[0] * math.cos(yaw) - point[1] * math.sin(yaw),
                 point[0] * math.sin(yaw) + point[1] * math.cos(yaw), point[2]]
            if not direction:
                p = [p[0] + item["pos"][0] / 100, p[1] - item["pos"][1] / 100,
                     p[2] + item["pos"][2] / 100]
            return p

        def triangles(item, piece):
            vertices = [transform(item, v) for v in piece["collision"]["vertices"]]
            self.assertTrue(all(abs(v[0]) < 160 and abs(v[1]) < 160 and 0 < v[2] < 64 for v in vertices))
            return [tuple(vertices[i] for i in t) for t in piece["collision"]["triangles"]]

        def surface(tris, point):
            # Independent vertical ray against authored collision triangles.
            # Highest hit catches intrusive rails as well as missing pavement.
            hits = []
            x, y = point[:2]
            for a, b, c in tris:
                d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(d) < 1e-10:
                    continue
                u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
                v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
                w = 1 - u - v
                if min(u, v, w) >= -1e-8:
                    hits.append(u * a[2] + v * b[2] + w * c[2])
            self.assertTrue(hits, f"missing road collision at {point}")
            return max(hits)

        loop = []
        for record in layout["loop"]:
            item, piece = objects[record["object_index"]], geometry[record["id"]]
            self.assertTrue(item["tag"].endswith("\\" + piece["id"]))
            road = piece["road"]
            self.assertEqual(road["clear_width_m"], 16)
            ends = list(reversed(road["connectors"])) if record["reverse"] else road["connectors"]
            transformed = []
            for connector in ends:
                tangent = transform(item, connector["forward"], True)
                if record["reverse"]:
                    tangent = [-v for v in tangent]
                transformed.append((transform(item, connector["position_m"]), tangent,
                                    [transform(item, p) for p in connector["edge_points_m"]]))
            tris = triangles(item, piece)
            # Sample every actual road cross-section, plus each span midpoint,
            # across nearly the full clear lane, including both ramp transitions.
            sections = road["sections"]
            samples = sections + [{"center_m": [(a + b) / 2 for a, b in zip(s["center_m"], t["center_m"])],
                                    "right": [(a + b) / 2 for a, b in zip(s["right"], t["right"])]}
                                   for s, t in zip(sections, sections[1:])]
            for section in samples:
                for lateral in (-7.8, -5.625, -2.375, 0, 2.375, 5.625, 7.8):
                    local = [v + lateral * r for v, r in zip(section["center_m"], section["right"])]
                    world = transform(item, local)
                    self.assertAlmostEqual(surface(tris, world), world[2], places=6)
            loop.append((transformed, tris, road["guardrail_height_m"]))
        self.assertEqual(sum(r["reverse"] for r in layout["loop"]), 1, "descent exercises reversed connectors")
        for current, following in zip(loop, loop[1:] + loop[:1]):
            end, start = current[0][1], following[0][0]
            self.assertLess(math.dist(end[0], start[0]), 1e-5, "closed loop has no position/elevation gap")
            self.assertLess(math.dist(end[1], start[1]), 1e-5, "connector tangents agree")
            self.assertLess(max(min(math.dist(e, p) for p in start[2]) for e in end[2]), 1e-5,
                            "entire deck edges meet, including reversed ramps")
            position, tangent = end[:2]
            right = [tangent[1], -tangent[0], 0]
            for side in (-.005, .005):
                for lateral in (-7.8, 0, 7.8):
                    point = [p + side * t + lateral * r for p, t, r in zip(position, tangent, right)]
                    self.assertAlmostEqual(surface(current[1] + following[1], point), position[2], places=5)
                if current[2] and following[2]:
                    for lateral in (-8.4, 8.4):
                        point = [p + side * t + lateral * r for p, t, r in zip(position, tangent, right)]
                        self.assertAlmostEqual(surface(current[1] + following[1], point), position[2] + 1.5, places=5)

        # Pit and spur use real deck collision at3m; the floor at0 cannot hide
        # a broken join. The unguarded T-junction has solid walls elsewhere.
        all_tris = [t for _, tris, _ in loop for t in tris]
        for record in [layout["spur"]] + [{"object_index": i, "id": "straight_48"}
                                         for i in layout["pad_object_indices"]]:
            all_tris.extend(triangles(objects[record["object_index"]], geometry[record["id"]]))
        foundry = json.loads((repo / "forge-packs/foundry/source/geometry.json").read_text())
        half = next(p for p in foundry["pieces"] if p["id"] == "wall_half")
        for item in objects:
            if item["tag"].endswith("\\foundry\\wall_half"):
                all_tris.extend(triangles(item, half))
        for seam in (31.2, 79.2):
            for offset in (-.01, .01):
                for y in (-7.8, 0, 7.8):
                    self.assertAlmostEqual(surface(all_tris, (seam + offset, y)), 3)
        for y in (-23.9, -20, -12, -8.81, 8.81, 12, 20, 23.9):
            self.assertGreaterEqual(surface(all_tris, (79.45, y)), 4.5 - 1e-7)
        for x in (31.2, 79.2):
            for y in (-8.8, 8.8):
                self.assertGreaterEqual(surface(all_tris, (x, y)), 4.5 - 1e-7, "closed pit-junction corner")
        for y in range(-24, 25):
            self.assertGreaterEqual(surface(all_tris, (96.25, y)), 4.5 - 1e-7)
        # Full-size stock visual footprints,6.13x3.25m, in two lanes at Â±4m.
        # Check each rectangle's four corners over real collision, including
        # curved facets and ramp transitions. This is static clearance only;
        # live steering/passing and suspension contact still need playtesting.
        for record in layout["loop"]:
            item, piece = objects[record["object_index"]], geometry[record["id"]]
            sections = piece["road"]["sections"]
            for a, b in zip(sections, sections[1:]):
                center = [(x + y) / 2 for x, y in zip(a["center_m"], b["center_m"])]
                tangent = [b["center_m"][i] - a["center_m"][i] for i in range(2)]
                length = math.hypot(*tangent)
                tangent = [v / length for v in tangent]
                right = [tangent[1], -tangent[0]]
                for lane in (-4, 4):
                    for fore in (-6.13 / 2, 6.13 / 2):
                        for side in (-3.25 / 2, 3.25 / 2):
                            p = [center[i] + fore * tangent[i] + (lane + side) * right[i] for i in range(2)]
                            world_point = transform(item, [*p, center[2]])
                            self.assertLess(abs(surface(all_tris, world_point) - world_point[2]), .4,
                                            "vehicle corner supported by pavement, not a raised barrier")
        self.assertEqual(len(level["blam"]["vehicles"]), 3)
        for vehicle in level["blam"]["vehicles"]:
            p = vehicle["pos"]
            self.assertEqual(vehicle["type"], "warthog")
            self.assertAlmostEqual(surface(all_tris, (p[0] / 100, -p[1] / 100)), 3)
            self.assertEqual(p[2], 380)
            yaw = math.radians(-vehicle["yaw"])
            forward, right = (math.cos(yaw), math.sin(yaw)), (math.sin(yaw), -math.cos(yaw))
            for fore in (-6.13 / 2, 6.13 / 2):
                for side in (-3.25 / 2, 3.25 / 2):
                    corner = (p[0] / 100 + fore * forward[0] + side * right[0],
                              -p[1] / 100 + fore * forward[1] + side * right[1])
                    self.assertAlmostEqual(surface(all_tris, corner), 3, msg="whole staged vehicle fits flat pavement")
        west_cars = sorted(level["blam"]["vehicles"][1:], key=lambda v: v["pos"][0])
        left, right = [v["pos"][0] / 100 for v in west_cars]
        self.assertEqual(right - left, 8)
        self.assertEqual((west_cars[0]["yaw"] - west_cars[1]["yaw"]) % 360, 180)
        self.assertEqual(right - left - 3.25, 4.75, "clear gap between two full-size Warthogs")
        self.assertEqual(left - 3.25 / 2 - (-96), 2.375, "left guard clearance")
        self.assertEqual(-80 - (right + 3.25 / 2), 2.375, "right guard clearance")
        self.assertTrue(all(s["pos"][2] == 335 for s in level["blam"]["player_starts"]))
        pit_car = level["blam"]["vehicles"][0]["pos"]
        first_player = level["blam"]["player_starts"][0]["pos"]
        self.assertAlmostEqual(math.dist(pit_car[:2], first_player[:2]) / 100, 3.8,
                               msg="the adjacent Spartan remains close to a full-size vehicle")
        bar = next(d for d in level["decor"] if d["id"] == "scale_2m")
        self.assertEqual(bar["scale"], [.08, 2, .012], "scale reference stays two metres")
        ticks = sorted(d["pos"][1] for d in level["decor"] if d["id"].startswith("scale_tick_"))
        self.assertEqual([b - a for a, b in zip(ticks, ticks[1:])], [100, 100])

    def test_crossline_showcase_preserves_palette_prefix_and_other_maps(self):
        repo, generator, level, layout, _ = crossline_fixture()
        self.assertEqual(level, json.loads((repo / "forge-maps/crossline/crossline.level.json").read_text()))
        self.assertEqual(layout, json.loads((repo / "forge-maps/crossline/crossline.layout.json").read_text()))
        self.assertEqual(generator.blank(), json.loads((repo / "forge-maps/blank/forge_canvas.level.json").read_text()))
        self.assertEqual(MAPS["blank"]["dimensions"], [64, 64, 1])
        self.assertEqual(MAPS["roadworks"]["dimensions"], [320, 320, 1])
        self.assertEqual(MAPS["roadworks"]["version"], "0.2.0")
        self.assertEqual(MAPS["crossline"]["dimensions"], [96, 160, 1])
        self.assertEqual(MAPS["crossline"]["version"], "0.3.0")
        self.assertTrue(MAPS["crossline"]["vehicles"])
        dependencies = level["blam"]["forge_packs"]
        self.assertEqual([(p["slug"], p["version"], len(p["blocks"])) for p in dependencies],
                         [("foundry", "0.2.0", 24), ("foundry-wide", "0.2.0", 38)])
        original = json.loads((repo / "forge-packs/foundry/catalog.json").read_text())["forge_pack"]["blocks"]
        self.assertEqual(dependencies[0]["blocks"], [{"id": b["id"], "tag": b["tag"]} for b in original])
        prefix = ["block_1x1", "block_1x2", "floor_1x1", "floor_1x2", "floor_2x2", "bridge_straight",
                  "bridge_corner", "ramp", "ramp_shallow", "wall", "wall_half", "wall_corner", "doorway",
                  "window", "railing", "column", "cover", "stairs"]
        self.assertEqual([b["id"] for b in dependencies[1]["blocks"][:18]], prefix)
        placed = {o["tag"].split("\\")[-1] for o in level["blam"]["objects"] if "\\foundry-wide\\" in o["tag"]}
        self.assertTrue(set(generator.SHOWCASE_IDS) <= placed)
        count = sum(len(level["blam"].get(k, [])) for k in ("objects", "weapons", "equipment", "vehicles"))
        self.assertEqual(layout["authored_object_count"], count)
        self.assertLessEqual(count, 500, "at least151 native slots stay available for user edits")
        spawns = [o for o in level["blam"]["objects"] if o["tag"] == generator.SPAWN]
        self.assertEqual(len(spawns), 8)
        for sign, team in [(-1, "defender"), (1, "attacker")]:
            own = [s for s in spawns if s["set"]["multiplayer data.owner team"] == team]
            self.assertEqual(len(own), 4)
            self.assertTrue(all(-s["pos"][1] * sign > 0 for s in own))
        self.assertEqual([o["tag"] for o in level["blam"]["forge_objects"]],
                         [generator.SPAWN, generator.TELE+"sender", generator.TELE+"receiver", generator.TELE+"2way"])

    def test_crossline_long_wall_perimeter_and_query_volume(self):
        _, _, level, layout, geometry = crossline_fixture()
        world = collision_world(level, geometry)
        boxes = [bounds for index, bounds, _ in world if index in layout["perimeter"]]
        self.assertEqual(len(boxes), 96)
        for _, bounds, _ in world:
            self.assertGreaterEqual(bounds[0][0], -48-1e-6); self.assertLessEqual(bounds[0][1], 48+1e-6)
            self.assertGreaterEqual(bounds[1][0], -80-1e-6); self.assertLessEqual(bounds[1][1], 80+1e-6)
            self.assertGreaterEqual(bounds[2][0], 0); self.assertLessEqual(bounds[2][1], 9)
        for axis, plane, span in [(0, -47.5, 80), (0, 47.5, 80), (1, -79.5, 48), (1, 79.5, 48)]:
            for z in (1.5, 4.5, 7.5):
                intervals = sorted(b[1-axis] for b in boxes if b[axis][0] <= plane <= b[axis][1] and b[2][0] <= z <= b[2][1])
                end = -span
                for low, high in intervals:
                    self.assertLessEqual(low, end+1e-6, "gap in perimeter")
                    end = max(end, high)
                self.assertGreaterEqual(end, span-1e-6)
        for x in (-47.5, 47.5):
            for y in (-79.5, 79.5):
                for z in (1.5, 4.5, 7.5):
                    self.assertEqual(sum(all(lo < p < hi for p, (lo, hi) in zip((x, y, z), b)) for b in boxes), 2)
        bounds = level["blam"]["world_bounds"][0]
        self.assertEqual(bounds, {"bsp": 8, "min": [-96/3.048, -96/3.048, -8/3.048],
                                  "max": [96/3.048, 96/3.048, 64/3.048]})

    def test_crossline_preflight_rejects_previous_canvas_and_pack(self):
        repo, _, level, _, _ = crossline_fixture()
        packs = [json.loads((repo / f"forge-packs/{p['slug']}/catalog.json").read_text())
                 for p in level["blam"]["forge_packs"]]
        bounds = level["blam"]["world_bounds"][0]
        collision = {"bsp_index": 0, "world_bounds_wu": {k: bounds[k] for k in ("min", "max")},
                     "slab_m": {"width": 96, "depth": 160, "thickness": 1, "top_z": 0}}
        check_level(level, MAPS["crossline"], packs, collision)
        old = copy.deepcopy(collision)
        old["slab_m"].update(width=48, depth=80)
        with self.assertRaisesRegex(ValueError, "collision dimensions"):
            check_level(level, MAPS["crossline"], packs, old)
        old = copy.deepcopy(packs)
        old[1]["version"] = "0.1.0"
        with self.assertRaisesRegex(ValueError, "palette differs"):
            check_level(level, MAPS["crossline"], old, collision)
        old = copy.deepcopy(packs)
        old[1]["forge_pack"]["blocks"][0:2] = reversed(old[1]["forge_pack"]["blocks"][0:2])
        with self.assertRaisesRegex(ValueError, "palette differs"):
            check_level(level, MAPS["crossline"], old, collision)

    def test_crossline_walk_routes_have_support_and_standing_clearance(self):
        _, _, level, layout, geometry = crossline_fixture()
        world = collision_world(level, geometry, layout["doors"])
        radius, height = .5334, 1.9812
        for route in layout["routes"]:
            if route["kind"] != "walk":
                continue
            offset = route["width_m"]/2-radius-.05
            for centre, forward in samples(route["points_m"]):
                for lane in (-offset, 0, offset):
                    p = [centre[0]+lane*forward[1], centre[1]-lane*forward[0], centre[2]]
                    support = ray(world, (p[0], p[1], p[2]+.1), (p[0], p[1], p[2]-.1))
                    self.assertTrue(support, f"{route['name']}: missing surface at {p}")
                    self.assertAlmostEqual(min(support), .5, places=5, msg=f"wrong route elevation at {p}")
                    for angle in range(0, 360, 90):
                        x, y = p[0]+radius*math.cos(math.radians(angle)), p[1]+radius*math.sin(math.radians(angle))
                        self.assertFalse(ray(world, (x, y, p[2]+radius+.03), (x, y, p[2]+height)),
                                         f"{route['name']}: standing body obstructed at {p}")
                    # Check horizontal capsule sections too: a low plinth
                    # or railing bar can lie between the vertical probes.
                    for z in (.15, .35, 1.0, 1.8):
                        cap = max(radius-z, z-(height-radius), 0)
                        r = math.sqrt(radius*radius-cap*cap)
                        for dx, dy in ((r, 0), (0, r)):
                            self.assertFalse(ray(world, (p[0]-dx,p[1]-dy,p[2]+z),
                                                 (p[0]+dx,p[1]+dy,p[2]+z)),
                                             f"{route['name']}: capsule side obstructed at {p}")

    def test_crossline_vehicles_fit_routes_and_open_vehicle_gate(self):
        _, _, level, layout, geometry = crossline_fixture()
        world = collision_world(level, geometry, layout["doors"])
        for route in layout["routes"]:
            if not route["kind"].startswith("vehicle"):
                continue
            for p, forward in samples(route["points_m"], 1):
                for fore in (-6.13/2, 0, 6.13/2):
                    for side in (-3.25/2, 0, 3.25/2):
                        x = p[0]+fore*forward[0]+side*forward[1]
                        y = p[1]+fore*forward[1]-side*forward[0]
                        self.assertTrue(ray(world, (x, y, .1), (x, y, -.1)), f"missing vehicle support at {(x,y)}")
                        self.assertFalse(ray(world, (x, y, .05), (x, y, 2.43+.2)), f"vehicle clearance blocked at {(x,y)}")
        self.assertEqual(len(level["blam"]["vehicles"]), 2)
        for vehicle in level["blam"]["vehicles"]:
            self.assertEqual(vehicle["type"], "warthog")
            self.assertEqual(vehicle["pos"][0], 0)
            self.assertEqual(abs(vehicle["pos"][1]), 6400)

    def test_crossline_door_motion_bypasses_glass_and_lift_clearance(self):
        _, _, level, layout, geometry = crossline_fixture()
        world, opened = collision_world(level, geometry), collision_world(level, geometry, layout["doors"])
        for door in layout["doors"]:
            frame = level["blam"]["objects"][door["frame_index"]]
            panel = level["blam"]["objects"][door["panel_index"]]
            self.assertAlmostEqual((frame["pos"][1]-panel["pos"][1])/100, -.75)
            for x in (-door["opening_m"][0]/2+.1, 0, door["opening_m"][0]/2-.1):
                for z in (.1, 1.98, door["opening_m"][1]-.1):
                    start, end = point(frame, (x, -2, z)), point(frame, (x, 2, z))
                    self.assertFalse(ray(world, start, end, {door["frame_index"]}), "frame opening blocked")
                    self.assertTrue(ray(world, start, end, {door["panel_index"]}), "closed panel does not close opening")
                    self.assertFalse(ray(opened, start, end), "open door still obstructs passage")
            # Move the whole actual panel through its authored travel. Its
            # solid body must not intersect another placed hull or header.
            body = geometry[panel["tag"]]["collision"]["vertices"]
            centre = [sum(v[a] for v in body)/len(body) for a in range(3)]
            for v in body:
                # The back of the moving panel is intentionally flush with
                # the frame's front face. Test penetration slightly inside its
                # volume, not shared boundary contact at the lintel/pillars.
                inside = [c+(x-c)*.999 for x, c in zip(v, centre)]
                start, end = point(panel, inside), point(panel, inside, door["travel_m"])
                others = {index for index, _, _ in world if index not in (-1, door["panel_index"])}
                self.assertFalse(ray(world, start, end, others), "door sweep hits another piece")
            self.assertLess(max(point(panel, v, door["travel_m"])[2] for v in body), 64,
                            "open door remains inside the authored query volume")
            for p, _ in samples(door["bypass_m"]):
                for dx in (-.5334, 0, .5334):
                    self.assertFalse(ray(world, (p[0]+dx, p[1], .03), (p[0]+dx, p[1], 1.9812)), "closed-door bypass obstructed")
        for feature in layout["showcase"]:
            if feature["id"] not in ("glass_wall", "window_glazed"):
                continue
            item = level["blam"]["objects"][feature["object_index"]]
            self.assertTrue(ray(world, point(item, (0,-2,1.75)), point(item, (0,2,1.75)), {feature["object_index"]}),
                            "glazed panels must retain solid collision")
        for lift in layout["lifts"]:
            launch, landing = lift["launch_m"], lift["landing_m"]
            for dx, dy in ((0,0),(-.5334,0),(.5334,0),(0,-.5334),(0,.5334)):
                x, y = launch[0]+dx, launch[1]+dy
                self.assertTrue(ray(world, (x,y,.6),(x,y,.4)))
                self.assertFalse(ray(world, (x,y,.51),(x,y,lift["clear_top_m"])), "lift has an overhead obstruction")
                x, y, z = landing[0]+dx, landing[1]+dy, landing[2]
                self.assertTrue(ray(world, (x,y,z+.1),(x,y,z-.1)))
                self.assertFalse(ray(world, (x,y,z+.01),(x,y,z+1.9812)), "lift landing obstructed")

    def test_crossline_lift_has_walkable_ground_approaches(self):
        _, _, level, layout, geometry = crossline_fixture()
        world = collision_world(level, geometry)
        radius, height = .5334, 1.9812
        for lift in layout["lifts"]:
            cx, cy, _ = lift["launch_m"]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for lane in (-1.4, 0, 1.4):
                    for step in range(19):
                        distance = 4.5-step*.25
                        z = min(.5, max(0, (4-distance)*.25))
                        x, y = cx+dx*distance-dy*lane, cy+dy*distance+dx*lane
                        support = ray(world, (x,y,z+.08), (x,y,z-.08))
                        self.assertTrue(support, f"lift approach step/gap at {(x,y,z)}")
                        self.assertAlmostEqual(min(support), .5, places=5)
                        for ox, oy in ((0,0),(-radius,0),(radius,0),(0,-radius),(0,radius)):
                            self.assertFalse(ray(world, (x+ox,y+oy,z+radius+.03),
                                                 (x+ox,y+oy,z+height)),
                                             "lift approach has no standing clearance")
                        # Include the lower capsule, where the old vertical
                        # 0.5 m deck edge blocked normal ground entry.
                        for dz in (.15, .35, 1.0, 1.8):
                            cap = max(radius-dz, dz-(height-radius), 0)
                            r = math.sqrt(radius*radius-cap*cap)
                            for ox, oy in ((r,0),(0,r)):
                                self.assertFalse(ray(world, (x-ox,y-oy,z+dz),
                                                     (x+ox,y+oy,z+dz)),
                                                 "lift approach blocks the player capsule")

    def test_crossline_spawns_and_teleporters_have_safe_footprints_and_exit_paths(self):
        _, generator, level, layout, geometry = crossline_fixture()
        world = collision_world(level, geometry)
        teleports = {t["object_index"]: t for t in layout["teleporters"]}
        for i, marker in enumerate(level["blam"]["objects"]):
            if marker["tag"] not in (generator.SPAWN, generator.TELE+"2way"):
                continue
            receiver = teleports.get(i)
            x, y = marker["pos"][0]/100, -marker["pos"][1]/100
            ground = receiver["support_z_m"] if receiver else 4.5
            top = ground+1.9812+(.61 if receiver else 0)
            for angle in range(0, 360, 45):
                px, py = x+.5334*math.cos(math.radians(angle)), y+.5334*math.sin(math.radians(angle))
                support = ray(world, (px,py,ground+.1),(px,py,ground-.1))
                self.assertTrue(support)
                self.assertAlmostEqual(min(support), .5, places=5)
                self.assertFalse(ray(world, (px,py,ground+.01),(px,py,top)), "spawn or receiver sweep blocked")
            if receiver:
                self.assertEqual(marker["set"]["multiplayer data.teleporter channel"], "alpha")
                for distance in (0, 1, 2, 2.6, 3.5):
                    py = y+receiver["exit_direction"][1]*distance
                    for px in (x-.5334, x, x+.5334):
                        self.assertFalse(ray(world, (px,py,4.55),(px,py,top)), "teleporter cannot leave rearm radius")
        self.assertEqual(len(teleports), 2)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = MAPS["blank"]
        block = {"id": "floor", "tag": r"objects\mjolnir\forge\foundry\floor"}
        self.pack = {"type": "content", "version": "0.2.0", "forge_pack": {
            "id": "foundry", "blocks": [block]}}
        self.bounds = {"min": [-64 / 3.048, -64 / 3.048, -8 / 3.048],
                       "max": [64 / 3.048, 64 / 3.048, 64 / 3.048]}
        self.level = {"canvas": {"scenario": "B40", "origin": [0, 0, 0]},
                      "multiplayer": True, "modes": ["forge", "slayer"], "kill_floor": -600,
                      "blam": {"map_variant": True, "active_bsps": [8], "single_bsp": 8,
                               "world_bounds": [{"bsp": 8, **self.bounds}],
                               "forge_packs": [{"slug": "foundry", "version": "0.2.0", "blocks": [block]}]}}
        self.collision = {"bsp_index": 0, "world_bounds_wu": self.bounds,
                          "slab_m": {"width": 64, "depth": 64, "thickness": 1, "top_z": 0}}

    def test_preflight_rejects_stale_palette_or_wrong_canvas(self):
        check_level(self.level, self.spec, self.pack, self.collision)
        cases = []
        old = copy.deepcopy(self.level)
        old["blam"]["forge_packs"][0]["version"] = "0.1.0"
        cases.append((old, self.collision))
        missing = copy.deepcopy(self.level)
        missing["blam"]["forge_packs"][0]["blocks"] = []
        cases.append((missing, self.collision))
        clipped = copy.deepcopy(self.level)
        clipped["blam"]["world_bounds"][0]["max"][2] = 1
        cases.append((clipped, self.collision))
        wrong_floor = copy.deepcopy(self.collision)
        wrong_floor["slab_m"]["width"] = 24
        cases.append((self.level, wrong_floor))
        for level, collision in cases:
            with self.assertRaises(ValueError):
                check_level(level, self.spec, self.pack, collision)

    def test_multiple_pack_dependencies_require_exact_palette_and_archive_pins(self):
        road = {"type": "content", "version": "0.1.0", "forge_pack": {"id": "roadworks", "blocks": [
            {"id": "straight_24", "tag": r"objects\mjolnir\forge\roadworks\straight_24"}]}}
        self.level["blam"]["forge_packs"].append({"slug": "roadworks", "version": "0.1.0",
                                                "blocks": road["forge_pack"]["blocks"]})
        check_level(self.level, self.spec, [self.pack, road], self.collision)
        with self.assertRaisesRegex(ValueError, "Missing built Forge pack: roadworks"):
            check_level(self.level, self.spec, [self.pack], self.collision)
        stale = copy.deepcopy(road)
        stale["version"] = "0.0.9"
        with self.assertRaisesRegex(ValueError, "palette differs"):
            check_level(self.level, self.spec, [self.pack, stale], self.collision)
        with self.assertRaisesRegex(ValueError, "unique"):
            check_level(self.level, self.spec, [self.pack, road, road], self.collision)
        with self.assertRaisesRegex(ValueError, "pin"):
            verify_archive(self.archive(), self.spec, self.level, "0.1.0", "^1.17.0", False)
        def pin(members):
            members["mjolnir.json"]["deps"].append({"slug": "roadworks", "range": "=0.1.0"})
        verify_archive(self.archive(pin), self.spec, self.level, "0.1.0", "^1.17.0", False)

    def test_vehicle_listing_must_match_authored_placements_and_archive(self):
        self.level["blam"]["vehicles"] = [{"type": "warthog", "pos": [0, 0, 380], "yaw": 90}]
        with self.assertRaisesRegex(ValueError, "vehicle metadata"):
            check_level(self.level, self.spec, self.pack, self.collision)
        spec = {**self.spec, "vehicles": True}
        check_level(self.level, spec, self.pack, self.collision)
        with self.assertRaisesRegex(ValueError, "vehicle flag"):
            verify_archive(self.archive(), spec, self.level, "0.1.0", "^1.17.0", False)
        archive = self.archive(lambda members: members["mjolnir.json"]["map"].update({"vehicles": True}))
        verify_archive(archive, spec, self.level, "0.1.0", "^1.17.0", False)

    def test_pack_view_must_match_built_bytes_and_stay_unchanged(self):
        manifest = self.root / "pack/mjolnir.json"
        content = manifest.parent / "content"
        content.mkdir(parents=True)
        manifest.write_text(json.dumps(self.pack))
        view = self.root / "paks"
        view.mkdir()
        for extension in ("utoc", "ucas"):
            name = f"pakchunk987-FORGE-foundry-floor_P.{extension}"
            (content / name).write_bytes(b"new pack data")
            (view / name).write_bytes(b"old pack data")
        with self.assertRaisesRegex(ValueError, "different Foundry"):
            check_pack_view(view, manifest)
        for source in content.iterdir():
            (view / source.name).write_bytes(source.read_bytes())
        _, fingerprints = check_pack_view(view, manifest)
        unchanged(fingerprints)
        next(view.iterdir()).write_bytes(b"changed during bake")
        with self.assertRaisesRegex(ValueError, "changed while baking"):
            unchanged(fingerprints)

    def archive(self, change=None):
        manifest = {"type": "map", "version": "0.1.0", "map": {"code": "FBK", "modes": ["forge", "slayer"]},
                    "deps": [{"slug": "mjolnir-ce-runtime", "range": "^1.17.0"},
                             {"slug": "foundry", "range": "=0.2.0"}]}
        members = {"mjolnir.json": manifest, "map/level.json": self.level,
                   "map/registration.json": {"code": "FBK", "from": "B40", "world": "/Game/Levels/Halo1/Solo/FBK/FBK.FBK"},
                   "content/pakchunk997-MJOLNIRMAP-FBK_P.utoc": b"table",
                   "content/pakchunk997-MJOLNIRMAP-FBK_P.ucas": b"scenario, BSP, world"}
        if change:
            change(members)
        archive = self.root / "test.mjolnir"
        with zipfile.ZipFile(archive, "w") as z:
            for name, value in members.items():
                z.writestr(name, value if isinstance(value, bytes) else json.dumps(value))
        return archive

    def test_archive_preserves_level_and_requires_exact_pack_dependency(self):
        archive = self.archive()
        result = verify_archive(archive, self.spec, self.level, "0.1.0", "^1.17.0", False)
        self.assertEqual(result["deps"][1], {"slug": "foundry", "range": "=0.2.0"})
        self.assertEqual(len(result["sha256"]), 64)
        def unpin(members):
            members["mjolnir.json"]["deps"][1]["range"] = "^0.2.0"
        with self.assertRaisesRegex(ValueError, "pin"):
            verify_archive(self.archive(unpin), self.spec, self.level, "0.1.0", "^1.17.0", False)

    def test_archive_cannot_ship_a_private_layout_or_shared_registration(self):
        for name in ("map/FBK.mvar", "content/pakchunk996-MJOLNIRREG_P.ucas"):
            archive = self.archive(lambda members: members.update({name: b"unexpected"}))
            with self.assertRaisesRegex(ValueError, "private Forge save"):
                verify_archive(archive, self.spec, self.level, "0.1.0", "^1.17.0", False)


if __name__ == "__main__":
    unittest.main()
