"""First-release packaging must not depend on a previous hub installation."""
import json
from pathlib import Path
import tempfile
import unittest

from pack_local_map import prepare


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

    def test_auxiliary_path_cannot_escape_map(self):
        self.level["foliage"]["file"] = "../../outside.bin"
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse((self.root / "staging").exists())

    def test_wrong_registration_code_is_rejected(self):
        (self.bake / "TST.registration.json").write_text('{"code":"BGL"}')
        with self.assertRaises(ValueError):
            self.stage()


if __name__ == "__main__":
    unittest.main()
