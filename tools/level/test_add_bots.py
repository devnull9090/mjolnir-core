"""A scenario-only bot update must retain a map's saved Fluid Flux pond."""
import argparse
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import add_bots


class WaterPreservationTests(unittest.TestCase):
    level = {"blam": {"single_bsp": 0}, "flux": {"state": {"res": [256, 256]}}}
    water = {"map/flux_state/state.json": b'{"cell":20}',
             "map/flux_state/height.exr": b"saved height pixels\x00\xff",
             "map/flux_state/velocity.exr": b"saved velocity pixels\x00\xfe"}

    def archive(self, members):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        return zipfile.ZipFile(stream)

    def test_missing_metadata_or_state_fails_instead_of_dropping_water(self):
        with self.archive(self.water) as archive:
            with self.assertRaisesRegex(ValueError, "metadata"):
                add_bots.flux_members(archive, {"blam": {}})
        with self.archive({"map/flux_state/height.exr": b"pixels"}) as archive:
            with self.assertRaisesRegex(ValueError, "state.json is missing"):
                add_bots.flux_members(archive, self.level)

    def test_nested_water_path_is_refused(self):
        with self.archive({**self.water, "map/flux_state/sub/height.exr": b"pixels"}) as archive:
            with self.assertRaisesRegex(ValueError, "flat regular files"):
                add_bots.flux_members(archive, self.level)

    def test_dry_maps_remain_supported(self):
        with self.archive({}) as archive:
            self.assertEqual(add_bots.flux_members(archive, {"blam": {}}), [])

    def test_full_repack_preserves_water_and_runtime_level_bytes(self):
        # Exercise the full staging + repack path. Only the external game tools
        # are faked; archive reads, copies and final preservation checks run.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paks = root / "paks"
            paks.mkdir()
            (paks / "pakchunk115-Windows.pak").write_bytes(b"stub")
            stem = "pakchunk997-MJOLNIRMAP-TST_P"
            manifest = {"version": "0.2.0", "name": "Test pond", "map": {"code": "TST"}}
            level_bytes = json.dumps(self.level, indent=3).encode()
            members = {"mjolnir.json": json.dumps(manifest).encode(),
                       "map/level.json": level_bytes,
                       "map/registration.json": b'{"code":"TST","world":"/Game/TST.TST"}',
                       f"content/{stem}.utoc": b"original toc",
                       f"content/{stem}.ucas": b"original scenario", **self.water}
            source = root / "test-pond-0.2.0.mjolnir"
            with zipfile.ZipFile(source, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)

            def run(command, **kwargs):
                if command[1] == "extract":
                    tags = Path(command[command.index("--out") + 1])
                    tags.mkdir()
                    (tags / "world.scenario_structure_bsp").write_bytes(b"bsp")
                elif command[1:3] == ["level", "bake"]:
                    bake = Path(command[command.index("--out-dir") + 1])
                    bake.mkdir()
                    for ext in ("utoc", "ucas"):
                        (bake / f"{stem}.{ext}").write_bytes(b"new bot scenario " + ext.encode())
                    (bake / "TST.bots.json").write_text('{"squads":[]}')
                elif command[1:3] == ["map", "pack"]:
                    stage = Path(command[3])
                    output = Path(command[command.index("--out") + 1])
                    with zipfile.ZipFile(output, "w") as archive:
                        archive.writestr("mjolnir.json", json.dumps(manifest))
                        for path in stage.rglob("*"):
                            if not path.is_file():
                                continue
                            relative = path.relative_to(stage).as_posix()
                            name = {"tst.level.json": "map/level.json",
                                    "TST.registration.json": "map/registration.json",
                                    "TST.bots.json": "map/bots.json"}.get(relative)
                            if name is None:
                                name = ("content/" if path.suffix in (".utoc", ".ucas")
                                        else "map/") + relative
                            archive.writestr(name, path.read_bytes())
                else:
                    Path(command[-1]).write_bytes(b"unchanged BSP package")
                return ""

            args = argparse.Namespace(work=str(root / "work"), out=str(root / "out"),
                paks=str(paks), version="0.3.0-beta.1", version_bump="minor",
                bake_only=False, sign=False, runtime="^1.16.0")
            with patch.object(add_bots, "run", side_effect=run), patch.object(
                add_bots, "packages", return_value=["BSP.uasset", "map-scenario.uasset", "map-scenario.ubulk"]):
                result = add_bots.one(str(source), args, {"count": 15})
            with zipfile.ZipFile(result) as archive:
                self.assertEqual(archive.read("map/level.json"), level_bytes)
                for name, expected in self.water.items():
                    self.assertEqual(archive.read(name), expected)
                self.assertIn("map/bots.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()
