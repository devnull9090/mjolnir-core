"""Tests for ce_material_spec.py's choice of master.

    python -m unittest discover -s tools/level -p "test_*.py"
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_material_spec  # noqa: E402


def chicago(flags, blend, base_map="shield.png"):
    # halo2ue writes double_sided true for every transparent shader, so it is
    # set on both kinds here: the choice must follow the shader's own flag.
    return {"alpha_mode": "BLEND", "double_sided": True,
            "shader": {"shader_class": "schi", "shader_flags": flags,
                       "framebuffer_blend_function": blend, "base_map": base_map,
                       "chicago_stages": [{"map": base_map}] if base_map else []}}


class TransparentMasterTest(unittest.TestCase):
    def spec(self, shaders):
        """Run the spec over one staging whose glTF has a material per shader;
        the parents by material name."""
        with tempfile.TemporaryDirectory() as staging:
            os.makedirs(os.path.join(staging, "textures"))
            open(os.path.join(staging, "textures", "shield.png"), "wb").close()
            with open(os.path.join(staging, "materials.json"), "w", encoding="utf-8") as f:
                json.dump(shaders, f)
            scene = os.path.join(staging, "scene.gltf")
            with open(scene, "w", encoding="utf-8") as f:
                json.dump({"materials": [{"name": k, "extras": {"halo": {"material": k}}} for k in shaders]}, f)
            dest = os.path.join(staging, "spec.json")
            argv = sys.argv
            sys.argv = ["ce_material_spec.py", staging, "test", dest, scene]
            try:
                ce_material_spec.main()
            finally:
                sys.argv = argv
            with open(dest, encoding="utf-8") as f:
                spec = json.load(f)
        return {m["name"]: m["parent"] for m in spec["materials"]}

    def test_two_sided_flag_picks_two_sided_master(self):
        parents = self.spec({
            "generator_shield": chicago(4, 3),       # c_field_generator: two-sided, add
            "arrow": chicago(0, 3),                  # one-sided, add
            "decal_alpha": chicago(2, 0),            # decal bit only, alpha blend
            "glass_mul": chicago(4 | 2, 1),          # two-sided, multiply
            "white_light": chicago(4, 0, base_map=None),  # no bitmap: zero-tint add
        })
        m = ce_material_spec.master
        self.assertEqual(parents["generator_shield"], m("M_CE_TransparentAddTwoSided"))
        self.assertEqual(parents["arrow"], m("M_CE_TransparentAdd"))
        self.assertEqual(parents["decal_alpha"], m("M_CE_TransparentAlpha"))
        self.assertEqual(parents["glass_mul"], m("M_CE_TransparentMulTwoSided"))
        self.assertEqual(parents["white_light"], m("M_CE_TransparentAddTwoSided"))


if __name__ == "__main__":
    unittest.main()
