import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from landscape_lod_policy import apply_policy, digest, generate, validate_policy


class LandscapeLodPolicyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "heights.r16").write_bytes(bytes(10))
        self.spec = {"size": 316, "components": 5, "sections": 1, "quads": 63,
                     "location": [0, 0, 0], "scale": [100, 100, 100], "heights": "heights.r16"}
        (self.root / "landscape.json").write_text(json.dumps(self.spec))
        # Authoring Y is negative here because Unreal's local Y is positive.
        self.paving = self.root / "paving.json"
        self.paving.write_text(json.dumps({"features": [{"geometry": {"type": "Polygon", "coordinates":
            [[[130, -130], [140, -130], [140, -140], [130, -140], [130, -130]]]}}]}))
        self.policy = generate(self.root, self.paving, self.root / "policy.json")

    def test_axis_mapping_complete_guard_and_measured_clearance(self):
        self.assertEqual(self.policy["core_section_bases"], [[126, 126]])
        self.assertEqual(len(self.policy["forced_section_bases"]), 9)
        self.assertEqual(self.policy["minimum_paving_to_morph_boundary_m"], 67)
        self.assertEqual(self.policy["uncovered_paving_area_m2"], 0)
        self.assertEqual(len(validate_policy(self.policy, self.spec, self.root)), 9)

    def test_hash_grid_and_incomplete_guard_fail_closed(self):
        for mutate in (lambda p: p.update(heights_sha256="0" * 64),
                       lambda p: p["grid"].update(size=317),
                       lambda p: p["forced_section_bases"].pop(),
                       lambda p: p.update(minimum_paving_to_morph_boundary_m=62.99)):
            policy = copy.deepcopy(self.policy)
            mutate(policy)
            with self.assertRaises(ValueError):
                validate_policy(policy, self.spec, self.root)
        self.paving.write_text("changed footprint")
        with self.assertRaisesRegex(ValueError, "source changed"):
            validate_policy(self.policy, self.spec, self.root)

    def components(self):
        result = []
        for i in range(5):
            for j in range(5):
                component = Mock()
                values = {"section_base_x": i * 63, "section_base_y": j * 63, "forced_lod": -1}
                component.get_editor_property.side_effect = lambda key, values=values: values[key]
                component.set_forced_lod.side_effect = lambda value, values=values: values.update(forced_lod=value)
                result.append(component)
        return result

    def test_exact_property_readback_and_missing_component_rejection(self):
        landscape = Mock()
        rows = self.components()
        landscape.get_components_by_class.return_value = rows
        report = apply_policy(landscape, object, self.policy, self.spec, self.root)
        self.assertEqual((report["forced_components"], report["automatic_components"]), (9, 16))
        rows[6].set_forced_lod.side_effect = lambda value: None
        rows[6].get_editor_property.side_effect = lambda key: {"section_base_x": 63, "section_base_y": 63, "forced_lod": -1}[key]
        with self.assertRaisesRegex(RuntimeError, "read back"):
            apply_policy(landscape, object, self.policy, self.spec, self.root)
        landscape.get_components_by_class.return_value = self.components()[:-1]
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            apply_policy(landscape, object, self.policy, self.spec, self.root)


if __name__ == "__main__":
    unittest.main()
