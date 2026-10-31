"""The authored amber lens survives the existing CE-to-native material path."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import ce_material_spec

SOURCE = Path(__file__).resolve().parents[2] / "levels/test/tst"
sys.path.insert(0, str(SOURCE))
from amber_light import build_tag, load_spec


class AmberLightTest(unittest.TestCase):
    def test_derived_shader_keeps_stock_atlas_and_leaves_template_unchanged(self):
        data = {"base map": {"group name": "bitm", "path": "stock\\atlas"}, "flags": 0}
        for channel in ("primary", "secondary", "plasma"):
            data[f"{channel} animation function"] = {"value": 0}
        template = {"Data": data}
        before = copy.deepcopy(template)
        derived = build_tag(template)["Data"]
        self.assertEqual(template, before)
        self.assertEqual(derived["base map"], derived["map"])
        self.assertIsNot(derived["base map"], derived["map"])
        self.assertEqual(derived["flags"], 0)

    def test_atlas_mask_and_amber_vectors_reach_native_material(self):
        authored = load_spec()
        color = authored["color"]
        name = authored["material"].rstrip("!")
        channels = [{"on": color, "off": color, "function": 0, "period": 1, "phase": 0}]
        channels += [{"on": [0,0,0], "off": [0,0,0], "function": 0, "period": 1, "phase": 0}] * 2
        # This is halo2ue's shader_environment summary and parsed tag shape.
        shader = {"shader_class": "senv", "shader_flags": 0, "shader_type": 0,
                  "base_map": "atlas.png", "detail": {},
                  "self_illum": {"map": "atlas.png", "map_scale": 1, "channels": channels},
                  "tag": {"material_color": color}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "textures").mkdir()
            (root / "textures/atlas.png").touch()
            (root / "materials.json").write_text(json.dumps({name: {"shader": shader}}))
            scene = root / "scene.gltf"
            scene.write_text(json.dumps({"materials": [{"name": name,
                "extras": {"halo": {"material": name, "tag_path": authored["tag"]}}}]}))
            output = root / "spec.json"
            with patch.object(sys, "argv", ["ce_material_spec.py", str(root), "test", str(output), str(scene)]):
                ce_material_spec.main()
            entry = json.loads(output.read_text())["materials"][0]
        self.assertEqual(entry["parent"], ce_material_spec.master("M_CE_Environment"))
        self.assertEqual(entry["textures"]["SelfIllumMap"], entry["textures"]["Base"])
        self.assertEqual(entry["scalars"]["HasSelfIllum"], 1)
        self.assertEqual(entry["scalars"]["SelfIllumScale"], 1)
        self.assertEqual(entry["vectors"]["MaterialColor"], color + [1])
        for state in ("SelfOn", "SelfOff"):
            self.assertEqual(entry["vectors"][state + "0"], color + [1])
            for channel in (1, 2):
                self.assertEqual(entry["vectors"][state + str(channel)], [0,0,0,1])


if __name__ == "__main__":
    unittest.main()
