"""Keep a new Forge map's source, pack inputs and player archive consistent."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_maps import MAPS, check_level, check_pack_view, unchanged, verify_archive


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
            self.assertTrue(all(abs(v[0]) < 80 and abs(v[1]) < 80 for v in vertices))
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
            self.assertEqual(road["clear_width_m"], 8)
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
                for lateral in (-3.8, -1.6, 0, 1.6, 3.8):
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
                for lateral in (-3.8, 0, 3.8):
                    point = [p + side * t + lateral * r for p, t, r in zip(position, tangent, right)]
                    self.assertAlmostEqual(surface(current[1] + following[1], point), position[2], places=5)
                if current[2] and following[2]:
                    for lateral in (-4.2, 4.2):
                        point = [p + side * t + lateral * r for p, t, r in zip(position, tangent, right)]
                        self.assertAlmostEqual(surface(current[1] + following[1], point), position[2] + 1, places=5)

        # Pit and spur use real deck collision at3m; the floor at0 cannot hide
        # a broken join. The unguarded T-junction has solid walls elsewhere.
        all_tris = [t for _, tris, _ in loop for t in tris]
        for record in [layout["spur"]] + [{"object_index": i, "id": "straight_24"}
                                         for i in layout["pad_object_indices"]]:
            all_tris.extend(triangles(objects[record["object_index"]], geometry[record["id"]]))
        foundry = json.loads((repo / "forge-packs/foundry/source/geometry.json").read_text())
        half = next(p for p in foundry["pieces"] if p["id"] == "wall_half")
        for item in objects:
            if item["tag"].endswith("\\foundry\\wall_half"):
                all_tris.extend(triangles(item, half))
        for seam in (15.6, 39.6):
            for offset in (-.01, .01):
                for y in (-3.8, 0, 3.8):
                    self.assertAlmostEqual(surface(all_tris, (seam + offset, y)), 3)
        for y in (-11.9, -10, -6, -4.41, 4.41, 6, 10, 11.9):
            self.assertGreaterEqual(surface(all_tris, (39.75, y)), 4.5 - 1e-7)
        for y in range(-12, 13):
            self.assertGreaterEqual(surface(all_tris, (48.25, y)), 4.5 - 1e-7)
        self.assertEqual(len(level["blam"]["vehicles"]), 2)
        for vehicle in level["blam"]["vehicles"]:
            p = vehicle["pos"]
            self.assertEqual(vehicle["type"], "warthog")
            self.assertAlmostEqual(surface(all_tris, (p[0] / 100, -p[1] / 100)), 3)
            self.assertEqual(p[2], 380)
        self.assertTrue(all(s["pos"][2] == 335 for s in level["blam"]["player_starts"]))

    def test_crossline_perimeter_is_solid_to_nine_metres_and_leaves_routes_open(self):
        repo = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("forge_map_generator", repo / "forge-maps/generate.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        level = generator.arena()
        geometry = json.loads((repo / "forge-packs/foundry/source/geometry.json").read_text())
        wall = next(p for p in geometry["pieces"] if p["id"] == "wall")
        self.assertEqual(len(wall["collision"]["hulls"]), 1, "perimeter uses solid walls, not apertures")
        vertices = wall["collision"]["hulls"][0]["vertices"]
        hull_bounds = [(min(v[a] for v in vertices), max(v[a] for v in vertices)) for a in range(3)]
        self.assertEqual(set(map(tuple, vertices)),
                         {(x, y, z) for x in hull_bounds[0] for y in hull_bounds[1] for z in hull_bounds[2]},
                         "the wall's convex collision is a solid box, so its transformed bounds are exact")
        boxes = []
        for item in level["blam"]["objects"]:
            if item["tag"] != generator.ref("wall"):
                continue
            px, py, pz = item["pos"][0] / 100, -item["pos"][1] / 100, item["pos"][2] / 100
            if abs(px) != 11.75 and abs(py) != 19.75:
                continue
            yaw = math.radians(-item["rot"][1])
            points = [(px + x * math.cos(yaw) - y * math.sin(yaw),
                       py + x * math.sin(yaw) + y * math.cos(yaw), pz + z)
                      for x, y, z in vertices]
            boxes.append(tuple((min(p[a] for p in points), max(p[a] for p in points)) for a in range(3)))
        self.assertEqual(len(boxes), 96, "32 full wall panels in each of three courses")
        self.assertEqual(len(level["blam"]["objects"]), 204)
        eps = 1e-7
        # Prove continuous coverage of every side and vertical band using
        # transformed collision hulls, not just the authored panel centres.
        for axis, plane, span in [(0, -11.75, 20), (0, 11.75, 20),
                                  (1, -19.75, 12), (1, 19.75, 12)]:
            side = [b for b in boxes if b[axis][0] - eps <= plane <= b[axis][1] + eps]
            heights = sorted({0.0, 9.0} | {h for b in side for h in b[2]})
            self.assertEqual(heights[0], 0)
            self.assertEqual(heights[-1], 9)
            for bottom, top in zip(heights, heights[1:]):
                z = (bottom + top) / 2
                intervals = sorted(b[1 - axis] for b in side if b[2][0] <= z <= b[2][1])
                covered = -span
                for start, end in intervals:
                    self.assertLessEqual(start, covered + eps, "gap in perimeter collision")
                    covered = max(covered, end)
                self.assertGreaterEqual(covered, span - eps)
            self.assertGreaterEqual(heights[-1] - 4.5, 4.5, "normal jumps from decks remain enclosed")
        # Corner seams overlap rather than merely meeting at a floating-point
        # edge. Each course contains both perpendicular walls at each corner.
        for x in (-11.75, 11.75):
            for y in (-19.75, 19.75):
                for z in (1.5, 4.5, 7.5):
                    corner = [b for b in boxes if all(b[a][0] + eps < p < b[a][1] - eps
                                                     for a, p in enumerate((x, y, z)))]
                    self.assertEqual(len(corner), 2, "sealed overlapping corner")
        for item in level["blam"]["objects"]:
            if item["tag"] not in (generator.SPAWN, generator.TELE + "2way"):
                continue
            p = (item["pos"][0] / 100, -item["pos"][1] / 100, item["pos"][2] / 100)
            self.assertLess(abs(p[0]) + 1.25, 11.5, "spawn/portal clear of side wall")
            self.assertLess(abs(p[1]) + 1.25, 19.5, "spawn/portal clear of end wall")
        self.assertEqual(len([o for o in generator.blank()["blam"]["objects"]
                              if o["group"] == "crates"]), 0, "blank construction canvas stays blank")

    def test_crossline_team_spawns_match_red_and_blue_bases(self):
        path = Path(__file__).resolve().parents[2] / "forge-maps/generate.py"
        spec = importlib.util.spec_from_file_location("forge_map_generator", path)
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        level = generator.arena()
        spawns = [o for o in level["blam"]["objects"] if o["tag"] == generator.SPAWN]
        self.assertEqual(len(spawns), 8)
        # Scenario enum 0 is defender (red); 1 is attacker (blue), matching
        # the existing CE converter. Authored Y is reflected into Unreal Y.
        for team, unreal_y, light in [("defender", 1600, "light_pylon_red"),
                                      ("attacker", -1600, "light_pylon_blue")]:
            team_spawns = [s for s in spawns if s["set"]["multiplayer data.owner team"] == team]
            self.assertEqual(len(team_spawns), 4)
            self.assertTrue(all(s["pos"][1] * unreal_y > 0 for s in team_spawns))
            lamps = [o for o in level["blam"]["objects"] if o["tag"] == generator.ref(light)]
            self.assertEqual(len(lamps), 2)
            self.assertTrue(all(o["pos"][1] * unreal_y > 0 for o in lamps))

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
