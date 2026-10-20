"""Offline upgrade coverage; every game/output path is a temporary directory."""
import json
import contextlib
import io
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import upgrade_ce_map as upgrade


class LocalInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paks = self.root / "game/Paks"
        self.ue4ss = self.root / "game/ue4ss"
        self.staged = self.root / "staged"
        self.loader = self.ue4ss / "Mods/MJOLNIRLevelLoader"
        self.state = self.root / "hub_state.json"
        self.config = self.root / "config.json"
        self.cli = self.root / "mjolnir.exe"
        self.work = self.root / "work"
        self.map = {"conversion": str(self.root / "conversion"), "level": "tst.level.json",
                    "sbsp": "tst.sbsp", "chunk": 969, "landscape": "LTT", "bake_foliage": True}
        self.paths = upgrade.paths("TST", self.map, str(self.work))
        self.patch = patch.multiple(upgrade, PAKS=str(self.paks), UE4SS=str(self.ue4ss),
                                    STAGED=str(self.staged), REPO=str(self.root),
                                    LAUNCHER_STATE=str(self.state), CONFIG=str(self.config))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        env = patch.dict(os.environ, {"MJOLNIR": str(self.cli)})
        env.start()
        self.addCleanup(env.stop)
        self.write(self.cli)
        self.write(self.config, {"TST": self.map})
        self.write(self.loader / "Scripts/main.lua")
        self.write(self.loader / "native/mjolnir_map_registry.dll")
        self.write(self.root / "mods/MJOLNIRLevelLoader/Scripts/main.lua")
        for mode in ("slayer", "ctf"):
            for ext in ("mglo", "layout.json"):
                self.write(self.loader / f"variants/{mode}.{ext}")
        self.write(self.paks / "pakchunk115-Windows.pak", b"stub")
        for ext in ("utoc", "ucas"):
            self.write(self.staged / f"pakchunk983-Windows.{ext}")
        self.runtime = ["pakchunk983-MJOLNIRCETRIAL-Windows", "pakchunk988-MJOLNIRMAT-Windows", "pakchunk994-MJOLNIRSPAWN_P",
                        "pakchunk993-MJOLNIRTELES_P", "pakchunk992-MJOLNIRTELER_P", "pakchunk991-MJOLNIRTELE2_P"]
        self.runtime += [f"pakchunk990-MJOLNIR{s}_P" for s in
                         ("CTFMESH", "FLAG", "STAND", "MOTL", "HPACK", "HPSPOT", "HPMESH", "FLUX")]
        for stem in self.runtime:
            for ext in ("pak", "utoc", "ucas"):
                self.write(self.paks / f"{stem}.{ext}")
        self.write(self.paths["out_level"], {"modes": ["slayer", "ctf"], "health_pack": {"mesh": "health"},
                                            "flux": {"feeds": []}, "foliage": {"file": "foliage.bin"}})
        self.write(Path(self.paths["work"]) / "foliage.bin")
        self.write(Path(self.paths["work"]) / "decals/test.dds")
        self.write(Path(self.paths["bake"]) / "TST.registration.json", {"code": "TST"})
        for folder, stem in (("bake", "pakchunk997-MJOLNIRMAP-TST_P"),
                             ("bake", "pakchunk969-MJOLNIRLAND-Windows"),
                             ("conv", "pakchunk986-MJOLNIRMESH-TST_P"),
                             ("conv", "pakchunk985-MJOLNIRCOOK-TST_P")):
            for ext in ("utoc", "ucas"):
                self.write(Path(self.paths[folder]) / f"{stem}.{ext}", stem.encode())
        # A stale bake registry must never overwrite the installed merged one.
        self.write(Path(self.paths["bake"]) / "pakchunk996-MJOLNIRREG_P.utoc", b"stale")
        self.write(self.paks / "pakchunk996-MJOLNIRREG_P.utoc", b"existing")

    def write(self, path, value=b"fixture"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(value).encode() if isinstance(value, dict) else value)

    def main(self, *flags):
        with patch("sys.argv", ["upgrade_ce_map.py", "TST", "--work", str(self.work), "--stages", "install", *flags]):
            upgrade.main()

    def test_fresh_local_install_merges_registration_after_copying_all_data(self):
        def run(cmd, **kwargs):
            if cmd == ["tasklist"]:
                return "explorer.exe"
            self.assertEqual(cmd, [str(self.cli), "level", "register", "--paks", str(self.paks)])
            data = self.ue4ss / "MJOLNIRMaps/TST"
            self.assertTrue((data / "registration.json").is_file())
            self.assertTrue((data / "foliage.bin").is_file())
            self.assertTrue((data / "decals/test.dds").is_file())
            self.assertEqual((self.paks / "pakchunk969-MJOLNIRLAND-Windows.pak").read_bytes(), b"stub")
            self.assertEqual((self.paks / "pakchunk996-MJOLNIRREG_P.utoc").read_bytes(), b"existing")
            return "2 map(s) registered: BGL, TST"
        with patch.object(upgrade, "run", side_effect=run) as run_mock, patch.object(upgrade, "install_shared") as shared:
            self.main("--local-install")
        shared.assert_called_once()
        self.assertEqual(run_mock.call_count, 2)
        self.assertFalse(self.state.exists())
        for stem in ("pakchunk997-MJOLNIRMAP-TST_P", "pakchunk986-MJOLNIRMESH-TST_P", "pakchunk985-MJOLNIRCOOK-TST_P"):
            for ext in ("utoc", "ucas", "pak"):
                self.assertTrue((self.paks / f"{stem}.{ext}").is_file())

    def test_missing_output_stops_before_shared_or_game_writes(self):
        (Path(self.paths["conv"]) / "pakchunk985-MJOLNIRCOOK-TST_P.ucas").unlink()
        with patch.object(upgrade, "run", return_value=""), patch.object(upgrade, "install_shared") as shared:
            with self.assertRaisesRegex(SystemExit, "local install is incomplete"):
                self.main("--local-install")
        shared.assert_not_called()
        self.assertFalse((self.ue4ss / "MJOLNIRMaps").exists())

    def test_running_game_blocks_shared_install_for_both_routes(self):
        for flag in ("--install", "--local-install"):
            with self.subTest(flag=flag), patch.object(upgrade, "run", return_value="HaloCampaignEvolved.exe"), \
                    patch.object(upgrade, "install_shared") as shared:
                with self.assertRaisesRegex(SystemExit, "close the game"):
                    self.main(flag)
                shared.assert_not_called()

    def test_hub_runtime_is_supported_but_hub_map_cannot_be_overwritten_locally(self):
        stem = self.runtime[0]
        for ext in ("pak", "utoc", "ucas"):
            (self.paks / f"{stem}.{ext}").rename(self.paks / f"pakchunk988-MJOLNIRHUB-mjolnir-ce-runtime-0_P.{ext}")
        state = {"installed": [{"slug": "mjolnir-ce-runtime", "containers": [stem]}]}
        self.write(self.state, state)
        upgrade.local_install_plan("TST", self.map, self.paths)
        state["installed"].append({"slug": "existing-map", "map_code": "TST"})
        self.write(self.state, state)
        with self.assertRaisesRegex(SystemExit, "existing hub map"):
            upgrade.local_install_plan("TST", self.map, self.paths)

    def test_missing_runtime_component_is_reported(self):
        (self.paks / "pakchunk990-MJOLNIRFLAG_P.pak").unlink()
        with self.assertRaisesRegex(SystemExit, "install the CE runtime first"):
            upgrade.local_install_plan("TST", self.map, self.paths)

    def test_default_install_keeps_hub_dispatch(self):
        with patch.object(upgrade, "run", return_value=""), patch.object(upgrade, "install_shared") as shared, \
                patch.object(upgrade, "stage_install") as hub, patch.object(upgrade, "local_install_plan") as local:
            self.main("--install")
        shared.assert_called_once()
        hub.assert_called_once()
        local.assert_not_called()

    def test_swap_forwards_explicit_tree_variant_only_when_configured(self):
        self.write(self.paths["level"], {})
        with patch.object(upgrade, "run", return_value="swapped") as run:
            upgrade.stage_swap("TST", self.map, self.paths)
            self.assertNotIn("--tree-variant", run.call_args.args[0])
            upgrade.stage_swap("TST", dict(self.map, tree_variant="Lrg_A"), self.paths)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--tree-variant") + 1], "Lrg_A")


class ShadowShellTest(unittest.TestCase):
    def test_rerun_uses_current_material_order_cut_and_swap_with_base_level_override(self):
        import shadow_shell
        for explicit_base in (False, True):
            with self.subTest(explicit_base=explicit_base), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                config = {"conversion": str(root / "conversion"), "level": "source.json"}
                if explicit_base:
                    config["base_level"] = str(root / "base_override.json")
                paths = upgrade.paths("TST", config, str(root / "work"))
                for key in ("conv", "work", "land"):
                    Path(paths[key]).mkdir(parents=True, exist_ok=True)
                material = lambda name: {"parent": "M_CE_Environment", "textures": {"Base": name}}
                ground, trim, trunk, rock = map(material, ("ground", "trim", "trunk", "rock"))
                fresh = {"decor": [{"id": "tst_terrain", "materials": [None, ground, trim, trunk, rock]}],
                         "landscape": {"cut": {"slots": [2]}, "pbr": {"keep": True}}}
                stale = {"decor": [{"id": "tst_terrain", "materials": [None, ground, upgrade.HIDDEN, material("teleporter")]}],
                         "landscape": {"cut": {"slots": [3]}}}
                cut = {"slots": [1], "rect": [0, 0, 100, 100]}
                Path(paths["level"]).write_text(json.dumps(fresh), encoding="utf-8")
                Path(paths["out_level"]).write_text(json.dumps(stale), encoding="utf-8")
                (Path(paths["land"]) / "landscape.json").write_text(json.dumps({"cut": cut}), encoding="utf-8")
                (Path(paths["work"]) / "swap.json").write_text(json.dumps({"hide": [trunk, rock]}), encoding="utf-8")
                # Four isolated triangles identify each slot in the resulting shell.
                # Only the new trim survives the current ground cut and scenery swap.
                data, views, accessors, primitives = bytearray(), [], [], []
                for slot in range(4):
                    attrs = {}
                    for name, values, kind, count, fmt in (
                            ("POSITION", [slot * 10, 0, 0, slot * 10 + 1, 0, 0, slot * 10, 0, 1], "VEC3", 3, "9f"),
                            ("NORMAL", [0, 1, 0] * 3, "VEC3", 3, "9f"),
                            ("indices", [0, 1, 2], "SCALAR", 3, "3I")):
                        chunk = struct.pack("<" + fmt, *values)
                        views.append({"buffer": 0, "byteOffset": len(data), "byteLength": len(chunk)})
                        data.extend(chunk)
                        attrs[name] = len(accessors)
                        accessors.append({"bufferView": len(views) - 1, "componentType": 5125 if name == "indices" else 5126,
                                          "count": count, "type": kind})
                    primitives.append({"material": slot, "indices": attrs.pop("indices"), "attributes": attrs})
                scene = {"buffers": [{"uri": "scene.bin", "byteLength": len(data)}], "bufferViews": views,
                         "accessors": accessors, "meshes": [{"primitives": primitives}]}
                (Path(paths["scene"]) / "scene.bin").write_bytes(data)
                (Path(paths["scene"]) / "scene.gltf").write_text(json.dumps(scene), encoding="utf-8")

                def run_shell(cmd):
                    output = io.StringIO()
                    with patch("sys.argv", cmd[1:]), contextlib.redirect_stdout(output):
                        shadow_shell.main()
                    return output.getvalue()

                with patch.object(upgrade, "run", side_effect=run_shell) as run:
                    result = upgrade.shadow_shells({"TST": config}, {"TST": paths})
                out = Path(paths["work"]) / "shadow_shell.json"
                shell = json.loads(out.read_text(encoding="utf-8"))
                self.assertEqual(shell["positions"], [[1000, 0, -20], [1100, 0, -20], [1000, 100, -20]])
                self.assertEqual(result, [f"SM_TST_ShadowShell={out}"])
                source_path = Path(run.call_args.args[0][2])
                self.assertEqual(source_path, Path(paths["work"]) / "shadow_source.json")
                source = json.loads(source_path.read_text(encoding="utf-8"))
                self.assertEqual(source["decor"], fresh["decor"])
                self.assertEqual(source["landscape"], {"cut": cut, "pbr": {"keep": True}})
                self.assertEqual(json.loads(Path(paths["level"]).read_text(encoding="utf-8")), fresh)
                self.assertEqual(json.loads(Path(paths["out_level"]).read_text(encoding="utf-8")), stale)


class HorizonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Ground is 20 x 10 m; the much larger sky must not move its bounds.
        data = struct.pack("<12f", -10, 0, -5, 10, 0, 5, -500, 0, -500, 500, 0, 500)
        (self.root / "scene.bin").write_bytes(data)
        scene = {"buffers": [{"uri": "scene.bin", "byteLength": len(data)}],
                 "bufferViews": [{"buffer": 0, "byteLength": len(data)}],
                 "accessors": [{"bufferView": 0, "byteOffset": offset, "componentType": 5126,
                                "count": 2, "type": "VEC3"} for offset in (0, 24)],
                 "materials": [{"name": "ground"}, {"name": "sky"}],
                 "meshes": [{"primitives": [{"material": i, "attributes": {"POSITION": i}}
                                             for i in range(2)]}]}
        (self.root / "scene.gltf").write_text(json.dumps(scene), encoding="utf-8")
        self.paths = {"scene": str(self.root), "land": str(self.root)}
        self.horizon = {"z": -150, "reach": 10000}
        self.level = {"canvas": {"origin": [100, 200, 300]}}

    def test_default_keeps_ground_color_tiling_and_overlap(self):
        from PIL import Image
        (self.root / "landscape.json").write_text('{"slot":"ground"}', encoding="utf-8")
        image = Image.new("RGB", (2, 1))
        image.putdata([(51, 102, 153), (255, 0, 0)])
        image.save(self.root / "base.png")
        mask = Image.new("L", (2, 1))
        mask.putdata([0, 255])
        mask.save(self.root / "landmask.png")
        material = {"parent": "ground-master", "textures": {"Base": "source-color", "Detail": "detail"},
                    "scalars": {"HasLightmap": 1, "HasBake": 1, "Roughness": 0.7}}
        self.level["decor"] = [{"mesh": "/Game/Test/SM_TST_Terrain.SM_TST_Terrain",
                                "materials": [{}, material]}]
        before = json.dumps(self.level, sort_keys=True)
        result = upgrade.horizon_skirt("TST", {"horizon": self.horizon}, self.paths, self.level)
        expected = []
        for i, (pos, scale, tiles) in enumerate([
                ([-5600, -200, -450], [90, 200, 1], [4.5, 20, 0, 0]),
                ([5400, -200, -450], [90, 200, 1], [4.5, 20, 0, 0]),
                ([-100, -5450, -450], [60, 95, 1], [3, 9.5, 0, 0]),
                ([-100, 5050, -450], [60, 95, 1], [3, 9.5, 0, 0])]):
            expected.append({"id": f"horizon_{i}", "mesh": "/Engine/BasicShapes/Plane.Plane",
                             "pos": pos, "scale": scale, "cast_shadow": False,
                             "materials": [{"parent": "ground-master",
                                            "textures": {"Base": upgrade.WHITE, "Detail": "detail"},
                                            "scalars": {"HasLightmap": 0, "HasBake": 0, "Roughness": 0.7},
                                            "vectors": {"MaterialColor": [0.2, 0.4, 0.6, 1], "BaseXform": tiles}}]})
        self.assertEqual(result, expected)
        self.assertEqual(json.dumps(self.level, sort_keys=True), before)

    def test_override_needs_no_ground_files_preserves_spec_and_has_no_overlap(self):
        material = {"parent": "water-master", "textures": {"DetailWave": "stock-wave"},
                    "scalars": {"WaveAmplitude": 0}, "vectors": {"WaterColor": [0.02, 0.1, 0.17, 1]}}
        self.horizon["material"] = material
        before = json.dumps(self.horizon, sort_keys=True)
        result = upgrade.horizon_skirt("TST", {"horizon": self.horizon}, self.paths, self.level)
        self.assertEqual([i["materials"] for i in result], [[material]] * 4)
        self.assertEqual([i["scale"] for i in result], [[90, 200, 1], [90, 200, 1], [20, 95, 1], [20, 95, 1]])
        # No strip intersects the map; no pair shares an area (translucent corners).
        rects = []
        for item in result:
            x, y = (item["pos"][i] + self.level["canvas"]["origin"][i] for i in range(2))
            w, h = (item["scale"][i] * 100 for i in range(2))
            rects.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        for i, a in enumerate(rects):
            for b in [(-1000, -500, 1000, 500), *rects[i + 1:]]:
                area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
                self.assertEqual(area, 0)
        result[0]["materials"][0]["scalars"]["WaveAmplitude"] = 3
        self.assertEqual(result[1]["materials"][0]["scalars"]["WaveAmplitude"], 0)
        self.assertEqual(json.dumps(self.horizon, sort_keys=True), before)

    def test_invalid_override_fails_before_reading_scene(self):
        for material in (None, "water-master", [], 1):
            with self.subTest(material=material), self.assertRaisesRegex(SystemExit, "horizon.material must be"):
                upgrade.horizon_skirt("TST", {"horizon": {"material": material}}, {}, {})


class FluxSpecTest(unittest.TestCase):
    def test_surface_color_is_opt_in_and_does_not_change_simulation(self):
        river = {"positions": [[0, 0, -18], [100, 0, -18], [0, 100, -18]], "indices": [0, 1, 2]}
        options = {"outlet": False}
        default = upgrade.flux_spec("TST", options, river, {})
        look = {"color_preset": "/Game/Color.Color", "surface_vectors": {"SurfaceScattering0": [0.06, 0.28, 0.34, 0.003]}}
        adjusted = upgrade.flux_spec("TST", dict(options, **look), river, {})
        self.assertEqual(adjusted, dict(default, **look))
        self.assertNotIn("color_preset", default)
        self.assertNotIn("surface_vectors", default)
        self.assertEqual(options, {"outlet": False})

    def test_loader_applies_preset_before_vectors_and_leaves_default_surface_untouched(self):
        try:
            from lupa import LuaRuntime
        except ImportError:
            self.skipTest("optional lupa is required to execute the loader helper offline")
        lua = LuaRuntime()
        source = (Path(__file__).resolve().parents[2] / "mods/MJOLNIRLevelLoader/Scripts/main.lua").read_text(encoding="utf-8")
        # Compile the entire loader as well: this catches Lua's 200-local limit
        # without executing any game API.
        lua.compile(source)
        start = source.index("function Effects.fluxColor(")
        helper = source[start:source.index("--- The sea as", start)]
        lua.execute("""
            Effects = {}; calls = {}; FName = function(name) return name end
            resolveMesh = function(path) calls[#calls + 1] = 'load'; return {path = path} end
            local function material()
                return {values = {}, SetVectorParameterValue = function(self, key, value)
                    calls[#calls + 1] = 'vector'; self.values[key] = value
                end}
            end
            surf = {MaterialInstances = {material(), material()}, ApplyColor = function(self)
                calls[#calls + 1] = 'preset'
                for _, m in ipairs(self.MaterialInstances) do m.values.Tint = {R = 99} end
            end}
        """)
        lua.execute(helper)
        lua.execute("Effects.fluxColor(surf, {}); assert(#calls == 0)")
        lua.execute("""
            Effects.fluxColor(surf, {color_preset = '/Game/Color.Color', surface_vectors = {Tint = {.1, .2, .3, 0}}})
            assert(surf.BaseColorPreset.path == '/Game/Color.Color')
            assert(#calls == 4 and calls[1] == 'load' and calls[2] == 'preset')
            for _, m in ipairs(surf.MaterialInstances) do
                assert(m.values.Tint.R == .1 and m.values.Tint.G == .2 and m.values.Tint.B == .3 and m.values.Tint.A == 0)
            end
        """)

    def test_grid_mode_override_preserves_default_feeds_outlet_and_lifetime(self):
        river = {"positions": [[0, 0, -18], [900, 0, -18], [900, 900, -18], [0, 900, -18]],
                 "indices": [0, 1, 2, 0, 2, 3]}
        config = {"feeds": [{"pos": [400, 400, -18], "mode": 2, "volume": 3}],
                  "outlet": [900, 900, -18], "grid": 300, "level_strength": 1}
        for hold in (False, True):
            with self.subTest(hold=hold):
                options = dict(config, hold=hold)
                default = upgrade.flux_spec("TST", options, river, {})
                explicit_default = upgrade.flux_spec("TST", dict(options, level_mode=1), river, {})
                adjusted = upgrade.flux_spec("TST", dict(options, level_mode=2), river, {})
                self.assertEqual(default, explicit_default)
                self.assertGreater(len(default["sources"]), 3)
                self.assertEqual(len(adjusted["sources"]), len(default["sources"]))
                for before, after in zip(default["sources"], adjusted["sources"]):
                    if "prime" in before:
                        self.assertEqual(before["mode"], 1)
                        self.assertEqual(after, dict(before, mode=2))
                        self.assertEqual(after["prime"], not hold)
                    else:
                        self.assertEqual(before, after)
                expected = dict(default, sources=adjusted["sources"])
                self.assertEqual(adjusted, expected)
                self.assertNotIn("level_mode", options)


class AssembleTest(unittest.TestCase):
    def test_water_materials_do_not_replace_map_options(self):
        for grime_enabled in (True, False):
            with self.subTest(grime_enabled=grime_enabled), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "landscape.json").write_text("{}", encoding="utf-8")
                near = {"parent": "/Game/MJOLNIR/CE/M_CE_Water", "scalars": {"PerpBrightness": 0.4}}
                distant = {"parent": "/Game/MJOLNIR/CE/M_CE_Water", "scalars": {"PerpBrightness": 0.8}}
                source = {"environment": {}, "decor": [{"id": "tst_water",
                          "mesh": "/Game/MJOLNIR/Maps/TST/SM_TST_Water.SM_TST_Water",
                          "materials": [near, distant, upgrade.HIDDEN]}]}
                (root / "source.json").write_text(json.dumps(source), encoding="utf-8")
                paths = {"land": folder, "work": folder, "scene": folder,
                         "level": str(root / "source.json"), "out_level": str(root / "level.json")}
                config = {"indoor": True, "grime": grime_enabled}
                expected_grime = [{"material": "grime", "pos": [1, 2, 3]}]
                with patch.object(upgrade, "ce_lights", return_value=[]), \
                        patch.object(upgrade, "ce_decals", return_value=([], [])), \
                        patch.object(upgrade, "grime_decals", return_value=expected_grime) as grime:
                    upgrade.stage_assemble("TST", config, paths)
                result = json.loads((root / "level.json").read_text(encoding="utf-8"))
                self.assertEqual(result["decor"][0]["materials"], [near, near, upgrade.HIDDEN])
                self.assertEqual(result.get("decals"), expected_grime if grime_enabled else None)
                self.assertEqual(grime.call_count, int(grime_enabled))
                self.assertEqual(config, {"indoor": True, "grime": grime_enabled})


if __name__ == "__main__":
    unittest.main()
