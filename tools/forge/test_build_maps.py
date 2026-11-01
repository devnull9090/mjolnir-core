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
