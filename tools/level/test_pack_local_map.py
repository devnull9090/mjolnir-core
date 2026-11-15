"""First-release packaging must not depend on a previous hub installation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pack_local_map import prepare
from owned_map_cook import snapshot_owned_cook, check_generated_meshes, input_files, flux_bed_requires_mesh


class LocalPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conv = self.root / "conversion"
        self.work = self.root / "upgrade"
        self.map = self.work / "TST"
        self.bake = self.map / "bake"
        self.conv.mkdir()
        self.bake.mkdir(parents=True)
        self.config = {"conversion": str(self.conv), "chunk": 969}
        self.level = {"foliage": {"file": "foliage.bin"},
                      "flux": {"state": {"res": [16, 16], "cell": 20}}}
        (self.map / "foliage.bin").write_bytes(b"foliage")
        (self.map / "flux_state").mkdir()
        (self.map / "flux_state/state.json").write_text("{}")
        (self.map / "flux_state/pixels.bin").write_bytes(b"water")
        (self.bake / "TST.registration.json").write_text('{"code":"TST"}')
        for folder, stem in [
            (self.conv, "pakchunk985-MJOLNIRCOOK-TST_P"),
            (self.conv, "pakchunk986-MJOLNIRMESH-TST_P"),
            (self.bake, "pakchunk997-MJOLNIRMAP-TST_P"),
            (self.bake, "pakchunk969-MJOLNIRLAND-Windows"),
        ]:
            for ext in ("utoc", "ucas"):
                (folder / f"{stem}.{ext}").write_bytes(b"fixture")

    def stage(self):
        (self.map / "level.json").write_text(json.dumps(self.level))
        return prepare("TST", self.config, self.work, self.root / "staging")

    def test_new_map_includes_upgraded_world_and_auxiliary_files(self):
        stage = self.stage()
        self.assertTrue((stage / "pakchunk969-MJOLNIRLAND-TST_P.utoc").is_file())
        self.assertEqual((stage / "flux_state/pixels.bin").read_bytes(), b"water")
        self.assertEqual((stage / "foliage.bin").read_bytes(), b"foliage")
        self.assertFalse(any("MJOLNIRREG" in p.name for p in stage.iterdir()))

    def test_rejects_authoring_solver_or_missing_named_state_in_release(self):
        for entry in ({"id":"river","playback":"simulate"}, {"id":"river","playback":"baked"}):
            self.level["flux"]={"domains":[entry]}
            with self.assertRaisesRegex(ValueError,"requires baked states"):
                self.stage()
            self.assertFalse((self.root/"staging").exists())

    def test_incomplete_container_pair_fails_before_staging(self):
        (self.conv / "pakchunk985-MJOLNIRCOOK-TST_P.ucas").unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.assertFalse((self.root / "staging").exists())

    def test_authored_shader_library_keeps_cook_chunk(self):
        (self.conv / "materials.spec.json").write_text(json.dumps({
            "chunk": 48621, "authored_surfaces": {"armor": {}}}))
        # A stale legacy container must never mask the missing correct cook.
        with self.assertRaises(FileNotFoundError):
            self.stage()
        for ext in ("utoc", "ucas"):
            (self.conv / f"pakchunk48621-MJOLNIRCOOK-TST_P.{ext}").write_bytes(b"shaders")
        stage = self.stage()
        self.assertEqual((stage / "pakchunk48621-MJOLNIRCOOK-TST_P.ucas").read_bytes(), b"shaders")
        self.assertFalse((stage / "pakchunk985-MJOLNIRCOOK-TST_P.ucas").exists())

    def test_native_material_clones_are_required_and_packaged(self):
        self.config["native_rock_materials"] = True
        with self.assertRaises(FileNotFoundError):
            self.stage()
        for ext in ("utoc", "ucas"):
            (self.bake / f"pakchunk970-MJOLNIRROCK-TST_P.{ext}").write_bytes(b"native layers")
        stage = self.stage()
        self.assertEqual((stage / "pakchunk970-MJOLNIRROCK-TST_P.ucas").read_bytes(), b"native layers")

    def test_auxiliary_path_cannot_escape_map(self):
        self.level["foliage"]["file"] = "../../outside.bin"
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse((self.root / "staging").exists())

    def test_wrong_registration_code_is_rejected(self):
        (self.bake / "TST.registration.json").write_text('{"code":"BGL"}')
        with self.assertRaises(ValueError):
            self.stage()

    def owned_fixture(self):
        self.config["map_mesh_chunk"] = True
        (self.conv / "materials.spec.json").write_text(json.dumps({
            "chunk": 968, "authored_surfaces": {"armor": {}}}))
        (self.map / "cliff_mesh.json").write_text('{"fresh":true}')
        self.staged = self.root / "cooked"
        self.staged.mkdir()
        for ext in ("utoc", "ucas"):
            (self.conv / f"pakchunk968-MJOLNIRCOOK-TST_P.{ext}").write_bytes(b"stale")
            (self.staged / f"pakchunk968-Windows.{ext}").write_bytes(b"fresh")
            (self.staged / f"pakchunk969-Windows.{ext}").write_bytes(b"fixture")

    def snapshot(self):
        with patch('owned_map_cook.check_generated_meshes', return_value={'cliff': 'fixture'}):
            return snapshot_owned_cook("TST", self.config, self.map, self.staged, 'fake-cli')

    def test_legacy_distribution_name_uses_actual_editor_chunk(self):
        self.owned_fixture()
        (self.conv / 'materials.spec.json').write_text(json.dumps({
            'chunk': 43579, 'authored_surfaces': {}}))
        for ext in ('utoc', 'ucas'):
            (self.staged / f'pakchunk43579-Windows.{ext}').write_bytes(b'actual editor cook')
        with patch('owned_map_cook.check_generated_meshes', return_value={'cliff': 'fixture'}) as check:
            result = snapshot_owned_cook('TST', self.config, self.map, self.staged, 'fake-cli')
        self.assertEqual(check.call_args.args[4], 43579)
        self.assertEqual(result.name, 'pakchunk985-MJOLNIRCOOK-TST_P')
        self.assertEqual(Path(str(result) + '.ucas').read_bytes(), b'actual editor cook')
        stage = self.stage()
        self.assertEqual((stage / 'pakchunk985-MJOLNIRCOOK-TST_P.ucas').read_bytes(), b'actual editor cook')

    def test_owned_mesh_requires_later_cook_and_uses_it(self):
        self.owned_fixture()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.assertFalse((self.root / "staging").exists())
        self.snapshot()
        stage = self.stage()
        self.assertEqual((stage / "pakchunk968-MJOLNIRCOOK-TST_P.ucas").read_bytes(), b"fresh")

    def test_owned_cook_rejects_changed_generated_geometry(self):
        self.owned_fixture()
        self.snapshot()
        (self.map / "cliff_mesh.json").write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, "stale"):
            self.stage()
        self.assertFalse((self.root / "staging").exists())

    def test_landscape_terrain_can_own_shadow_mesh_without_cliff_copy(self):
        self.owned_fixture()
        self.config['tess'] = False
        (self.map / 'cliff_mesh.json').unlink()
        (self.map / 'shadow_shell.json').write_text('{"fresh":true}')
        self.snapshot()
        self.assertTrue(self.stage().is_dir())
        (self.map / 'shadow_shell.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.stage()

    def test_owned_cook_rejects_tampered_container(self):
        self.owned_fixture()
        cook = self.snapshot()
        Path(str(cook) + '.ucas').write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.stage()
        self.assertFalse((self.root / "staging").exists())

    def test_owned_cook_rejects_different_landscape_cook(self):
        self.owned_fixture()
        self.snapshot()
        (self.bake / 'pakchunk969-MJOLNIRLAND-Windows.ucas').write_bytes(b'other cook')
        with self.assertRaisesRegex(ValueError, 'Landscape bake does not match'):
            self.stage()
        self.assertFalse((self.root / 'staging').exists())

    def test_mismatched_duplicate_cliffs_are_rejected(self):
        self.owned_fixture()
        for stem in ('global',):
            for ext in ('utoc', 'ucas'):
                (self.staged / f'{stem}.{ext}').write_bytes(b'fixture')
        def export(command, **kwargs):
            out = Path(command[-1])
            out.write_bytes(b'old' if out.parent.name == '968' else b'new')
            return type('Result', (), {'returncode': 0, 'stderr': ''})()
        with patch('owned_map_cook.subprocess.run', side_effect=export):
            with self.assertRaisesRegex(ValueError, 'different generated meshes'):
                check_generated_meshes('TST', self.config, self.map, self.staged, 968, 'fake-cli')

    def test_baked_heightfield_bed_retains_provenance_without_cooked_mesh(self):
        self.owned_fixture()
        self.config['flux'] = {'heightfield': 'runtime.json', 'playback': 'baked',
                               'domains': [{'id': 'upper'}, {'id': 'lower', 'playback': 'baked'}]}
        (self.map / 'flux_bed.json').write_text('{"exact_ground":true}')
        for ext in ('utoc', 'ucas'):
            (self.staged / f'global.{ext}').write_bytes(b'fixture')
        exported = []
        def export(command, **kwargs):
            exported.append(command[command.index('--asset') + 1])
            Path(command[-1]).write_bytes(b'same cooked mesh')
            return type('Result', (), {'returncode': 0, 'stderr': ''})()
        with patch('owned_map_cook.subprocess.run', side_effect=export):
            snapshot_owned_cook('TST', self.config, self.map, self.staged, 'fake-cli')
        self.assertEqual(exported, ['SM_TST_CliffTess'] * 2)
        self.assertIn('flux_bed', input_files('TST', self.config, self.map))
        self.assertIn('flux_bed', json.loads((self.map / 'owned-cook.json').read_text())['inputs'])
        self.assertTrue(self.stage().is_dir())
        (self.map / 'flux_bed.json').write_text('{"changed_ground":true}')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.stage()

    def test_simulated_mixed_or_legacy_flux_still_requires_mesh(self):
        self.owned_fixture()
        (self.map / 'flux_bed.json').write_text('{}')
        for ext in ('utoc', 'ucas'):
            (self.staged / f'global.{ext}').write_bytes(b'fixture')
        cases = [
            {'heightfield': 'runtime.json', 'playback': 'simulate'},
            {'heightfield': 'runtime.json', 'playback': 'baked',
             'domains': [{'playback': 'baked'}, {'playback': 'simulate'}]},
            {'bed': True, 'playback': 'baked'},
            {},
        ]
        def export(command, **kwargs):
            if command[command.index('--asset') + 1].endswith('FluxBed'):
                return type('Result', (), {'returncode': 1, 'stderr': 'missing fixture bed'})()
            Path(command[-1]).write_bytes(b'same cooked mesh')
            return type('Result', (), {'returncode': 0, 'stderr': ''})()
        for flux in cases:
            self.config['flux'] = flux
            with self.subTest(flux=flux):
                self.assertTrue(flux_bed_requires_mesh(self.config))
                with patch('owned_map_cook.subprocess.run', side_effect=export):
                    with self.assertRaisesRegex(ValueError, 'Cannot verify SM_TST_FluxBed'):
                        check_generated_meshes('TST', self.config, self.map, self.staged, 968, 'fake-cli')

    def test_playback_change_cannot_reuse_cook_without_bed(self):
        self.owned_fixture()
        self.config['flux'] = {'heightfield': 'runtime.json', 'playback': 'baked'}
        (self.map / 'flux_bed.json').write_text('{}')
        self.snapshot()
        self.config['flux']['playback'] = 'simulate'
        with self.assertRaisesRegex(ValueError, 'required Flux capture mesh'):
            self.stage()


if __name__ == "__main__":
    unittest.main()
