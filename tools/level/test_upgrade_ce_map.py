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


class AuthoredMaterialOverridesTest(unittest.TestCase):
    def fixture(self, root):
        source = "/Game/Maps/Test/T_Floor.T_Floor"
        material = "/HaloMaterialLibrary/Metal/MI_Floor.MI_Floor"
        level = {"decor": [
            {"id": "architecture", "materials": ["/Game/Keep.Keep", {
                "parent": "/Game/MJOLNIR/CE/M_CE_Environment.M_CE_Environment",
                "textures": {"Base": source}, "scalars": {"HasLightmap": 1}}]},
            {"id": "other", "materials": [{"textures": {"Base": source}}]}]}
        document = {"schema": "mjolnir-authored-material-overrides-v1", "overrides": [
            {"decor_id": "architecture", "source_base": source, "material": material}]}
        path = root / "materials.json"
        path.write_text(json.dumps(document))
        return level, {"authored_material_overrides": str(path)}, document, path

    def test_replaces_complete_material_without_touching_other_decor(self):
        with tempfile.TemporaryDirectory() as temp:
            level, config, document, _ = self.fixture(Path(temp))
            original = json.loads(json.dumps(level))
            upgrade.mark_structures(level)
            self.assertEqual(upgrade.apply_authored_material_overrides(level, config), 1)
            self.assertEqual(level["decor"][0]["materials"][1], document["overrides"][0]["material"])
            self.assertEqual(level["decor"][0]["materials"][0], original["decor"][0]["materials"][0])
            self.assertEqual(level["decor"][1], original["decor"][1])
            self.assertEqual(upgrade.apply_authored_material_overrides(level, {}), 0)

    def test_missing_or_ambiguous_source_fails_before_any_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            level, config, document, path = self.fixture(Path(temp))
            original = json.loads(json.dumps(level))
            second = dict(document["overrides"][0], source_base="/Game/Missing.Missing")
            document["overrides"].append(second)
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "found 0"):
                upgrade.apply_authored_material_overrides(level, config)
            self.assertEqual(level, original)
            document["overrides"].pop()
            path.write_text(json.dumps(document))
            level["decor"][0]["materials"].append(level["decor"][0]["materials"][1])
            with self.assertRaisesRegex(ValueError, "found 2"):
                upgrade.apply_authored_material_overrides(level, config)

    def test_native_instance_parameters_create_mid_without_ce_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            level, config, document, path = self.fixture(Path(temp))
            rule = document["overrides"][0]
            rule["scalars"] = {"Base Emissive Strength": 4096, "Offset": -0.25}
            rule["vectors"] = {"Color Tint 1": [0.2, 0.6, 1.0, 700], "RGB": [1, 0.5, 0]}
            path.write_text(json.dumps(document))
            self.assertEqual(upgrade.apply_authored_material_overrides(level, config), 1)
            self.assertEqual(level["decor"][0]["materials"][1], {
                "parent": rule["material"], "scalars": rule["scalars"], "vectors": rule["vectors"]})

    def test_invalid_native_parameters_fail_before_any_mutation(self):
        invalid = [
            ("scalars", []), ("scalars", None), ("scalars", {"": 1}),
            ("scalars", {"Intensity": True}), ("scalars", {"Intensity": "8"}),
            ("scalars", {"Intensity": float("nan")}),
            ("scalars", {"Intensity": float("inf")}), ("scalars", {"Intensity": 1e100}),
            ("scalars", {"Intensity": 10 ** 400}),
            ("vectors", {"Tint": [1, 2]}), ("vectors", {"Tint": [1, 2, 3, 4, 5]}),
            ("vectors", {"Tint": [1, 2, float("-inf"), 1]}),
            ("vectors", {"Tint": [1, False, 0]}), ("vectors", {"Tint": "cyan"}),
        ]
        with tempfile.TemporaryDirectory() as temp:
            for kind, value in invalid:
                with self.subTest(kind=kind, value=value):
                    level, config, document, path = self.fixture(Path(temp))
                    original = json.loads(json.dumps(level))
                    # The first valid rule must not mutate its slot before the
                    # second rule's invalid parameter is discovered.
                    second = dict(document["overrides"][0], decor_id="other")
                    second[kind] = value
                    document["overrides"].append(second)
                    path.write_text(json.dumps(document))
                    with self.assertRaises(ValueError):
                        upgrade.apply_authored_material_overrides(level, config)
                    self.assertEqual(level, original)


class PCGOnlyFoliageTest(unittest.TestCase):
    def test_exact_pcg_transforms_bypass_legacy_scatter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.json"
            source.write_text(json.dumps({"file": "source.bin", "groups": [
                {"mesh": "/Game/Test.Test", "rule": "short grass", "exact": True}]}))
            payload = struct.pack("<fffBBbbBBB", 1, 2, 3, 0, 100, 0, 0, 0, 0, 0)
            (root / "source.bin").write_bytes(b"MJF3" + struct.pack("<III", 3, 1, 1) + payload)
            exact = struct.pack("<10f", 1.125, 2.5, 3.75, 0, 0, 0, 1, 1, 1, 1)
            (root / "source.bin.xf1").write_bytes(exact)
            with patch.object(upgrade, "run") as run:
                upgrade.stage_foliage("PWR", {"pcg_foliage_only": True, "pcg_foliage": str(source)},
                                     {"foliage": str(root / "output")})
                run.assert_not_called()
            self.assertEqual((root / "output/foliage.bin.xf1").read_bytes(), exact)
            self.assertTrue(json.loads((root / "output/foliage.json").read_text())["groups"][0]["pcg"])


class RuntimeDecorTest(unittest.TestCase):
    def test_distant_scenery_is_explicit_and_invalid_list_does_not_partially_append(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "decor.json"
            level = {"decor": [{"id": "playable"}]}
            apron = {"id": "distant_apron", "mesh": "/Game/Maps/PWR/Apron.Apron", "pos": [0, 0, 0]}
            document = {"schema": "mjolnir-runtime-decor-v1", "render_only": True, "decor": [apron]}
            source.write_text(json.dumps(document))
            self.assertEqual(upgrade.append_runtime_decor(level, {"runtime_decor": str(source)}), 1)
            self.assertEqual(level["decor"][-1], apron)
            original = json.loads(json.dumps(level))
            document["decor"] = [dict(apron, id="new_apron"), dict(apron, id="playable")]
            source.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                upgrade.append_runtime_decor(level, {"runtime_decor": str(source)})
            self.assertEqual(level, original)
            document["render_only"] = False
            source.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "render-only"):
                upgrade.append_runtime_decor(level, {"runtime_decor": str(source)})


class AuthoredTerrainCollisionTest(unittest.TestCase):
    def fixture(self,root):
        import numpy as np
        from heightfield import sha256,write_heightfield
        field=write_heightfield(root/"master.json",np.zeros((2,2)),(0,0),(1,1))
        own=root/"map.sbsp";own.write_bytes(b"verified native BSP")
        binary=root/"collision_scene.bin";binary.write_bytes(b"compiled source")
        scene=root/"collision_scene.json";scene.write_text(json.dumps({"bin":binary.name,"counts":{"surfaces":3}}))
        authored=root/"terrain-extra.json";authored.write_text("current terrain triangles")
        (root/"b30_collision.json").write_text(json.dumps({"authored_sources":[{"path":str(authored),
            "sha256":sha256(authored),"master_manifest_sha256":field.manifest_sha256}]}))
        receipt={"schema":"mjolnir-collision-pieces-v1","output":str(own),"output_sha256":sha256(own),
                 "source_manifest":str(scene),"source_manifest_sha256":sha256(scene),
                 "source_binary_sha256":sha256(binary),"source_surfaces":3}
        receipt_path=root/"native-collision-receipt.json";receipt_path.write_text(json.dumps(receipt))
        config={"authored_collision":str(authored),"heightfield":str(field.path),"sbsp":own.name}
        return config,{"work":str(root),"conv":str(root/"converted")},receipt_path

    def test_authored_bake_requires_matching_compiled_output_and_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,paths,receipt_path=self.fixture(root)
            self.assertEqual(upgrade.bake_sbsp(config,paths),str(root/"map.sbsp"))
            for name in ("map.sbsp","collision_scene.json","collision_scene.bin","terrain-extra.json","master.heights.npy"):
                target=root/name;original=target.read_bytes()
                with self.subTest(changed=name):
                    target.write_bytes(original+b"changed")
                    with self.assertRaises(ValueError):upgrade.bake_sbsp(config,paths)
                    target.write_bytes(original)
            receipt=json.loads(receipt_path.read_text());receipt["output"]=str(root/"other.sbsp")
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,"path mismatch"):upgrade.bake_sbsp(config,paths)

    def test_authored_bake_never_falls_back_to_converted_core(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,paths,receipt_path=self.fixture(root)
            (root/"converted").mkdir();(root/"converted/map.sbsp").write_bytes(b"empty membership core")
            receipt_path.unlink()
            with self.assertRaisesRegex(ValueError,"core fallback is forbidden"):upgrade.bake_sbsp(config,paths)
            (root/"map.sbsp").unlink()
            self.assertEqual(upgrade.bake_sbsp({"sbsp":"map.sbsp"},paths),str(root/"converted/map.sbsp"))

    def test_bad_collision_does_not_delete_previous_bake(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,paths,receipt_path=self.fixture(root)
            bake=root/"bake";bake.mkdir();saved=bake/"previous.utoc";saved.write_bytes(b"previous complete bake")
            paths["bake"]=str(bake);receipt_path.unlink()
            with patch.object(upgrade,"run") as run:
                with self.assertRaisesRegex(ValueError,"core fallback is forbidden"):
                    upgrade.stage_bake("PWR",config,paths)
                run.assert_not_called()
            self.assertEqual(saved.read_bytes(),b"previous complete bake")

    def test_matching_terrain_appends_after_scenery_and_stale_source_fails(self):
        from heightfield import sha256
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);manifest=root/"master.json";manifest.write_text("fixture")
            original={"triangles":[[[0,0,0],[1,0,0],[0,1,0]]],"materials":["wood"],"objects":1}
            source={"schema":"pwr-native-terrain-extra-v1","coordinates":"ce_world_units_z_up",
                    "master_manifest":str(manifest),"master_manifest_sha256":sha256(manifest),"accuracy_pass":True,
                    "triangles":[[[0,0,2],[1,0,2],[0,1,2]]],"materials":["stone"],"objects":2}
            extra=root/"extra.json";extra.write_text(json.dumps(original));terrain=root/"terrain.json";terrain.write_text(json.dumps(source))
            self.assertEqual(upgrade.append_authored_collision(str(extra),str(terrain)),1)
            merged=json.loads(extra.read_text());self.assertEqual(merged["objects"],3)
            self.assertEqual(merged["materials"],["wood","stone"])
            manifest.write_text("changed")
            before=extra.read_bytes()
            with self.assertRaisesRegex(ValueError,"stale"):
                upgrade.append_authored_collision(str(extra),str(terrain))
            self.assertEqual(extra.read_bytes(),before)


class CollisionHullCacheTest(unittest.TestCase):
    def paths(self, root):
        return {key: str(root) for key in ("work", "foliage", "scene", "conv")}

    def test_default_omits_override_and_explicit_cache_is_forwarded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for setting in ({}, {"collision_hulls": str(root)}):
                with self.subTest(setting=setting), patch.object(upgrade, "run", return_value="fixture") as run, contextlib.redirect_stdout(io.StringIO()):
                    upgrade.stage_collision("PWR", {"sbsp": "pwr.sbsp", **setting}, self.paths(root))
                    command = run.call_args_list[0].args[0]
                    if setting:
                        self.assertEqual(command[-2:], ["--hulls", str(root.resolve())])
                    else:
                        self.assertNotIn("--hulls", command)

    def test_missing_non_directory_and_invalid_cache_stop_before_compile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / "not-directory.json"
            file.write_text("{}")
            for value in ("", None, 12, str(file), str(root / "missing")):
                with self.subTest(value=value), patch.object(upgrade, "run") as run:
                    with self.assertRaisesRegex(ValueError, "collision_hulls"):
                        upgrade.stage_collision("PWR", {"sbsp": "pwr.sbsp", "collision_hulls": value}, self.paths(root))
                    run.assert_not_called()


class LandscapeSpacingTest(unittest.TestCase):
    def test_large_map_forwards_centimetre_spacing_with_component_count(self):
        config = {"shaders": ["ground"], "landscape": "LPW", "components": 16, "quad": 200}
        with patch.object(upgrade, "run", return_value="") as run:
            upgrade.stage_land("PWR", config, {"scene": "scene", "land": "land"})
        argv = run.call_args.args[0]
        spacing = float(argv[argv.index("--quad") + 1])
        components = int(argv[argv.index("--components") + 1])
        self.assertEqual(components * 63 * spacing, 201600,
                         "The 2 km recipe must not silently build a 1 km landscape")

    def test_existing_map_keeps_landscape_default_spacing(self):
        with patch.object(upgrade, "run", return_value="") as run:
            upgrade.stage_land("TST", {"shaders": ["ground"], "landscape": "LTT"},
                               {"scene": "scene", "land": "land"})
        self.assertNotIn("--quad", run.call_args.args[0])

    def test_invalid_spacing_fails_before_launch(self):
        for value in (0, -200, float("inf"), float("nan")):
            with self.subTest(value=value), patch.object(upgrade, "run") as run:
                with self.assertRaisesRegex(ValueError, "spacing"):
                    upgrade.stage_land("PWR", {"shaders": ["ground"], "landscape": "LPW", "quad": value},
                                       {"scene": "scene", "land": "land"})
                run.assert_not_called()


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
        installed = {}

        def run(cmd, **kwargs):
            if cmd == ["tasklist"]:
                return "explorer.exe"
            if cmd[1:3] == ["dev", "install"]:
                self.assertEqual(cmd[-2:], ["--paks", str(self.paks)])
                installed[cmd[cmd.index("--name") + 1]] = Path(cmd[3]).name
                return "installed"
            self.assertEqual(cmd, [str(self.cli), "level", "register", "--paks", str(self.paks)])
            data = self.ue4ss / "MJOLNIRMaps/TST"
            self.assertTrue((data / "registration.json").is_file())
            self.assertTrue((data / "foliage.bin").is_file())
            self.assertTrue((data / "decals/test.dds").is_file())
            self.assertEqual((self.paks / "pakchunk996-MJOLNIRREG_P.utoc").read_bytes(), b"existing")
            self.assertEqual(len(installed), 4, "every container is in before the registration")
            return "2 map(s) registered: BGL, TST"
        with patch.object(upgrade, "run", side_effect=run) as run_mock, patch.object(upgrade, "install_shared") as shared:
            self.main("--local-install")
        shared.assert_called_once()
        self.assertEqual(run_mock.call_count, 6)
        self.assertFalse(self.state.exists())
        # Every container goes in as a local build named for the map, above
        # any hub copy; none is copied in under its own name.
        self.assertEqual(installed, {
            "MJOLNIRMAP-TST": "pakchunk997-MJOLNIRMAP-TST_P",
            "MJOLNIRMESH-TST": "pakchunk986-MJOLNIRMESH-TST_P",
            "MJOLNIRCOOK-TST": "pakchunk985-MJOLNIRCOOK-TST_P",
            "MJOLNIRLAND-TST": "pakchunk969-MJOLNIRLAND-Windows",
        })
        for stem in ("pakchunk997-MJOLNIRMAP-TST_P", "pakchunk969-MJOLNIRLAND-Windows"):
            self.assertFalse((self.paks / f"{stem}.utoc").exists())

    def test_authored_local_install_keeps_shader_library_number(self):
        conv = Path(self.paths["conv"])
        self.write(conv / "materials.spec.json", {"chunk": 48621, "authored_surfaces": {"armor": {}}})
        for ext in ("utoc", "ucas"):
            self.write(conv / f"pakchunk48621-MJOLNIRCOOK-TST_P.{ext}")
        _, _, containers = upgrade.local_install_plan("TST", self.map, self.paths, shared=False)
        sources = [Path(base).name for base, _ in containers]
        self.assertIn("pakchunk48621-MJOLNIRCOOK-TST_P", sources)
        self.assertNotIn("pakchunk985-MJOLNIRCOOK-TST_P", sources)

    def test_extra_map_container_is_required_before_any_install(self):
        stem = self.root / "extra/pakchunk963-MJOLNIRAPRON-TST_P"
        self.map["extra_containers"] = [str(stem)]
        self.write(str(stem) + ".utoc", b"toc")
        with self.assertRaisesRegex(SystemExit, "local install is incomplete"):
            upgrade.local_install_plan("TST", self.map, self.paths, shared=False)
        self.assertFalse((self.paks / (stem.name + ".utoc")).exists())
        self.write(str(stem) + ".ucas", b"payload")
        plan = upgrade.local_install_plan("TST", self.map, self.paths, shared=False)
        with patch.object(upgrade, "run", return_value="installed") as run:
            upgrade.install_local("TST", plan)
        # It goes in as a local build named for itself, like the map's own.
        names = {c.args[0][c.args[0].index("--name") + 1]: Path(c.args[0][3]).name for c in run.call_args_list}
        self.assertEqual(names.get("MJOLNIRAPRON-TST"), stem.name)

    def test_beta_local_install_keeps_published_runtime_unchanged(self):
        self.map["environment"] = {"light_scale": 8192, "sun": {"atmosphere_sun": True},
                                   "skylight": {"physical": True}, "post": {}}
        self.write(self.config, {"TST": self.map})
        for ext in ("utoc", "ucas"):
            (self.staged / f"pakchunk983-Windows.{ext}").unlink()
        with patch.object(upgrade, "run", return_value=""), patch.object(upgrade, "install_shared") as shared:
            self.main("--local-install", "--release-beta")
        shared.assert_not_called()
        self.assertTrue((self.ue4ss / "MJOLNIRMaps/TST/level.json").exists())

    def test_local_install_preserves_baked_water_and_rejects_missing_state(self):
        level_path = Path(self.paths["out_level"])
        level = json.loads(level_path.read_text())
        level["flux"]["state"] = {"resolution": [192, 160]}
        self.write(level_path, level)
        with self.assertRaisesRegex(SystemExit, "local install is incomplete"):
            upgrade.local_install_plan("TST", self.map, self.paths)
        water = Path(self.paths["work"]) / "flux_state"
        self.write(water / "state.json", {})
        self.write(water / "height.exr", b"height")
        self.write(water / "velocity.exr", b"velocity")
        with patch.object(upgrade, "run", return_value="installed"):
            upgrade.install_local("TST", upgrade.local_install_plan("TST", self.map, self.paths))
        dest = self.ue4ss / "MJOLNIRMaps/TST/flux_state"
        self.assertEqual((dest / "height.exr").read_bytes(), b"height")
        self.assertEqual((dest / "velocity.exr").read_bytes(), b"velocity")

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
        # The launcher's names since load order went by suffix.
        for ext in ("pak", "utoc", "ucas"):
            (self.paks / f"pakchunk988-MJOLNIRHUB-mjolnir-ce-runtime-0_P.{ext}").rename(
                self.paks / f"pakchunk983-MJOLNIRHUB-mjolnir-ce-runtime-0_1000_P.{ext}")
        upgrade.local_install_plan("TST", self.map, self.paths)
        # Another container's index never stands in for it.
        for ext in ("pak", "utoc", "ucas"):
            (self.paks / f"pakchunk983-MJOLNIRHUB-mjolnir-ce-runtime-0_1000_P.{ext}").rename(
                self.paks / f"pakchunk10010-MJOLNIRHUB-mjolnir-ce-runtime-10_1040_P.{ext}")
        with self.assertRaisesRegex(SystemExit, "install the CE runtime first"):
            upgrade.local_install_plan("TST", self.map, self.paths)
        for ext in ("pak", "utoc", "ucas"):
            (self.paks / f"pakchunk10010-MJOLNIRHUB-mjolnir-ce-runtime-10_1040_P.{ext}").rename(
                self.paks / f"pakchunk988-MJOLNIRHUB-mjolnir-ce-runtime-0_P.{ext}")
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

    def hub_install(self, m):
        for stem in ("bake/pakchunk997-MJOLNIRMAP-TST_P", "bake/pakchunk969-MJOLNIRLAND-Windows"):
            for ext in ("utoc", "ucas"):
                self.write(self.work / "TST" / f"{stem}.{ext}")
        self.write(self.paths["out_level"], {})
        self.write(Path(self.paths["work"]) / "foliage.bin")
        (self.ue4ss / "MJOLNIRMaps/TST").mkdir(parents=True, exist_ok=True)
        with patch.object(upgrade, "run", return_value="installed") as run, \
                patch.object(upgrade, "require_game_closed"), patch.object(upgrade, "require_hub_map"):
            upgrade.stage_install("TST", m, self.paths)
        return [c.args[0][c.args[0].index("--name") + 1] for c in run.call_args_list]

    def test_hub_install_adds_conversion_containers_only_when_asked(self):
        self.assertEqual(self.hub_install(self.map), ["MJOLNIRMAP-TST", "MJOLNIRLAND-TST"])
        conv = Path(self.map["conversion"])
        for stem in ("pakchunk986-MJOLNIRMESH-TST_P", "pakchunk985-MJOLNIRCOOK-TST_P"):
            for ext in ("utoc", "ucas"):
                self.write(conv / f"{stem}.{ext}")
        self.assertEqual(self.hub_install(dict(self.map, conversion_containers=True)),
                         ["MJOLNIRMAP-TST", "MJOLNIRLAND-TST", "MJOLNIRMESH-TST", "MJOLNIRCOOK-TST"])
        (conv / "pakchunk985-MJOLNIRCOOK-TST_P.ucas").unlink()
        with self.assertRaisesRegex(SystemExit, "install is incomplete"):
            self.hub_install(dict(self.map, conversion_containers=True))

    def test_swap_forwards_explicit_tree_variant_only_when_configured(self):
        self.write(self.paths["level"], {})
        with patch.object(upgrade, "run", return_value="swapped") as run:
            upgrade.stage_swap("TST", self.map, self.paths)
            self.assertNotIn("--tree-variant", run.call_args.args[0])
            upgrade.stage_swap("TST", dict(self.map, tree_variant="Lrg_A"), self.paths)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--tree-variant") + 1], "Lrg_A")

    def test_measured_tree_recipes_reach_both_pcg_and_scenery(self):
        self.write(self.paths["level"], {})
        recipes = Path(self.paths["work"]) / "measured-recipes.json"
        trees = recipes.with_name("trees.json")
        self.write(recipes, {})
        self.write(trees, {})
        config = dict(self.map, tree_recipes=str(recipes), pcg_trees=str(trees))
        with patch.object(upgrade, "run", return_value="swapped") as run:
            upgrade.stage_swap("TST", config, self.paths)
            commands = [call.args[0] for call in run.call_args_list]
            adapter = next(cmd for cmd in commands if cmd[1].endswith("pcg_tree_decor.py"))
            scenery = next(cmd for cmd in commands if cmd[1].endswith("scenery_swap.py"))
            self.assertEqual(adapter[3], str(recipes.resolve()))
            self.assertEqual(scenery[5], str(recipes.resolve()))
        recipes.unlink()
        with patch.object(upgrade, "run") as run:
            with self.assertRaisesRegex(FileNotFoundError, "Measured tree recipes"):
                upgrade.stage_swap("TST", config, self.paths)
            run.assert_not_called()


class SharedInstallTest(unittest.TestCase):
    def test_trial_and_water_masters_go_in_as_local_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "staged"
            staged.mkdir()
            for stem in ("pakchunk983-Windows", "pakchunk982-Windows"):
                (staged / f"{stem}.utoc").write_bytes(b"x")
            repo = Path(tmp) / "repo"
            ue4ss = Path(tmp) / "ue4ss"
            (repo / "mods/MJOLNIRLevelLoader/Scripts").mkdir(parents=True)
            (repo / "mods/MJOLNIRLevelLoader/Scripts/main.lua").write_text("--")
            (repo / "mods/MJOLNIRLevelLoader/Scripts/flux_runtime.lua").write_text("--")
            (ue4ss / "Mods/MJOLNIRLevelLoader/Scripts").mkdir(parents=True)
            with patch.multiple(upgrade, STAGED=str(staged), PAKS="P", REPO=str(repo), UE4SS=str(ue4ss)), \
                    patch.dict(os.environ, {"MJOLNIR": "cli"}), \
                    patch.object(upgrade, "run", return_value="installed") as run:
                upgrade.install_shared()
            calls = [c.args[0] for c in run.call_args_list]
            self.assertEqual(calls, [
                ["cli", "dev", "install", str(staged / "pakchunk983-Windows"), "--name", "MJOLNIRCETRIAL", "--paks", "P"],
                ["cli", "dev", "install", str(staged / "pakchunk982-Windows"), "--name", "MJOLNIRWATER", "--paks", "P"],
            ])


class GeneratedMeshTest(unittest.TestCase):
    def test_original_maps_use_package_ids_distinct_from_shared_runtime(self):
        for suffix in ("CliffTess", "River", "FluxBed", "ShadowShell"):
            name = f"SM_TST_{suffix}"
            owned = upgrade.generated_mesh("TST", {"map_mesh_chunk": True}, suffix)
            shared = upgrade.generated_mesh("TST", {}, suffix)
            self.assertEqual(owned, f"/Game/MJOLNIR/Maps/TST/Generated/{name}.{name}")
            self.assertEqual(shared, f"/Game/MJOLNIR/CETrial/{name}.{name}")
            self.assertNotEqual(owned, shared)


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
                if explicit_base:
                    trim = {"parent": "/Game/MJOLNIR/Maps/TST/SurfaceMaterials/M_Authored_armor.M_Authored_armor"}
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
    def test_tst_keeps_only_one_permanent_water_modifier(self):
        config = json.loads((Path(__file__).with_name("ce_upgrade_maps.json")).read_text())["TST"]["flux"]
        river = {"positions": [[3200, 1900, -18], [4100, 1900, -18], [4100, 2800, -18], [3200, 2800, -18]],
                 "indices": [0, 1, 2, 0, 2, 3]}
        spec = upgrade.flux_spec("TST", config, river, {})
        permanent = [s for s in spec["sources"] if not s.get("prime")]
        self.assertEqual(len(permanent), 1)
        self.assertEqual(permanent[0]["pos"], [3600, 2300, -18])
        self.assertEqual(permanent[0]["mode"], 2)
        self.assertGreater(len(spec["sources"]), 3)

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


class ReleaseEnvironmentTest(unittest.TestCase):
    def test_beta_preserves_physical_sky_intensity_for_published_loader(self):
        source = json.loads(Path(upgrade.CONFIG).read_text(encoding="utf-8"))["TST"]
        expected = source["environment"]["skylight"]["intensity"]
        # Exercise the real CLI/config path without invoking editor or game.
        for scale in (8192, 4096):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as folder:
                source["environment"]["light_scale"] = scale
                config = Path(folder) / "config.json"
                config.write_text(json.dumps({"TST": source}), encoding="utf-8")
                with patch.object(upgrade, "CONFIG", str(config)), \
                        patch.object(upgrade, "stage_assemble") as assemble, \
                        patch("sys.argv", ["upgrade_ce_map.py", "TST", "--release-beta",
                                           "--stages", "assemble", "--work", folder]):
                    upgrade.main()
                result = assemble.call_args.args[1]
                env = result["environment"]
                self.assertAlmostEqual(env["skylight"]["intensity"] * scale, expected)
                self.assertNotIn("physical", env["skylight"])
                self.assertFalse(env["atmosphere"])
                self.assertEqual(env["sun"]["source_angle"], source["environment"]["sun"]["source_angle"])
                self.assertEqual(json.loads(config.read_text()), {"TST": source})


if __name__ == "__main__":
    unittest.main()
