"""First-release packaging must not depend on a previous hub installation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pack_local_map import prepare
from owned_map_cook import snapshot_owned_cook, check_generated_meshes


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


if __name__ == "__main__":
    unittest.main()
