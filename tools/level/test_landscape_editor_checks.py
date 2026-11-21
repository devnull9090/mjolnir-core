"""Exercise editor preflight/verification without loading Unreal or modifying assets."""
import ast
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock


SOURCE = (Path(__file__).resolve().parents[2] / "unreal/MJOLNIRMaterials/Scripts/build_ce_landscape.py")
# The commandlet intentionally runs at module scope. Compile only its pure/check
# functions so tests exercise the production checks without launching an editor.
NAMES = {"open_scratch_level", "requested_pine_culls", "verify_pine_cull"}
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
checks = {"math": math, "os": os}
exec(compile(ast.Module(body=[node for node in tree.body
                            if isinstance(node, ast.FunctionDef) and node.name in NAMES],
                        type_ignores=[]), str(SOURCE), "exec"), checks)


class PineCullChecks(unittest.TestCase):
    def request(self, cull, declared=True):
        pine = {"instances": 2, "groups": [{"group": 2, "count": 2}]}
        if declared:
            pine["cull_cm"] = cull
        return pine, [{"cull": [100, 200]}, {"cull": cull}]

    def test_default_and_map_requested_culls_are_verified_exactly(self):
        for cull in ([90000, 180000], [160000, 300000]):
            with self.subTest(cull=cull):
                actual, groups = checks["requested_pine_culls"](*self.request(cull))
                self.assertEqual(actual, cull)
                self.assertEqual(groups, {2: cull})
                component = Mock()
                component.get_editor_property.side_effect = cull
                checks["verify_pine_cull"](component, groups[2])
                component.get_editor_property.side_effect = [cull[0], cull[1] - 1]
                with self.assertRaisesRegex(RuntimeError, "requested.*got"):
                    checks["verify_pine_cull"](component, groups[2])

    def test_legacy_receipt_uses_its_actual_group_request(self):
        self.assertEqual(checks["requested_pine_culls"](*self.request([160000, 300000], False)),
                         ([160000, 300000], {2: [160000, 300000]}))

    def test_disagreement_invalid_ranges_and_group_indices_fail_closed(self):
        pine, groups = self.request([160000, 300000])
        groups[1]["cull"] = [90000, 180000]
        with self.assertRaisesRegex(RuntimeError, "differs from request"):
            checks["requested_pine_culls"](pine, groups)
        for invalid in ([1, math.nan], [1, math.inf], [True, 2], [-1, 2],
                        [3, 2], [1.5, 2], [1, 2**31], [], None):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(RuntimeError, "Invalid"):
                checks["requested_pine_culls"](*self.request(invalid))
        for index in (0, 3, True, 1.2):
            pine, groups = self.request([160000, 300000])
            pine["groups"][0]["group"] = index
            with self.subTest(index=index), self.assertRaisesRegex(RuntimeError, "group index"):
                checks["requested_pine_culls"](pine, groups)


class ScratchWorldChecks(unittest.TestCase):
    def test_unregistered_existing_file_is_loaded_and_not_recreated(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "__MJOLNIR_Scratch.umap").write_bytes(b"existing")
            levels, assets = Mock(), Mock()
            assets.does_asset_exist.return_value = False
            checks["open_scratch_level"](levels, assets, folder)
            levels.load_level.assert_called_once_with("/Game/__MJOLNIR_Scratch")
            levels.new_level.assert_not_called()

    def test_registry_existing_world_is_loaded_and_missing_world_created(self):
        with tempfile.TemporaryDirectory() as folder:
            for exists in (False, True):
                levels, assets = Mock(), Mock()
                assets.does_asset_exist.return_value = exists
                checks["open_scratch_level"](levels, assets, folder)
                used = levels.load_level if exists else levels.new_level
                unused = levels.new_level if exists else levels.load_level
                used.assert_called_once_with("/Game/__MJOLNIR_Scratch")
                unused.assert_not_called()

    def test_failed_world_switch_stops_before_generated_assets_are_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            for exists in (False, True):
                levels, assets = Mock(), Mock()
                assets.does_asset_exist.return_value = exists
                levels.load_level.return_value = levels.new_level.return_value = False
                with self.assertRaisesRegex(RuntimeError, "scratch level"):
                    checks["open_scratch_level"](levels, assets, folder)


if __name__ == "__main__":
    unittest.main()
