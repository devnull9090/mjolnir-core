import copy
import json
from pathlib import Path
import tempfile
import unittest

from authored_surfaces import apply_library, load_library

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "levels/test/tst/surfaces.json"


class AuthoredSurfacesTest(unittest.TestCase):
    def scene(self):
        surfaces = load_library(LIBRARY)
        mats, slots, gltf = [], [], []
        # Multiple lightmap pages must all bind; unrelated stock metal stays stock.
        for tag in [s["tag"] for s in surfaces.values()] + ["levels/b30/shaders/metal panels generic ext"]:
            for page in (0, 1):
                name = tag.replace("/", "_").replace(" ", "_") + f"__lm{page}"
                original = {"parent": "/Game/MJOLNIR/CE/M_CE_Environment", "textures": {"Base": "stock"}}
                mats.append(dict(original, name=name))
                slots.append({"pattern": name + "$", "material": copy.deepcopy(original)})
                gltf.append({"name": name, "extras": {"halo": {"tag_path": tag.replace("/", chr(92))}}})
        return mats, slots, gltf

    def test_exact_shader_binding_owns_masters_and_preserves_other_materials(self):
        mats, slots, gltf = self.scene()
        untouched = copy.deepcopy(slots[-2:])
        textures = {"Existing": {"name": "Existing"}}
        surfaces = apply_library(LIBRARY, "/Game/MJOLNIR/Maps/TST", mats, slots, gltf, textures)
        self.assertEqual(len(surfaces), 8)
        self.assertEqual(slots[-2:], untouched)
        for slot in slots[:-2]:
            self.assertTrue(slot["material"]["parent"].startswith("/Game/MJOLNIR/Maps/TST/SurfaceMaterials/"))
            self.assertNotIn("textures", slot["material"])
        self.assertEqual(len(textures), 5)  # four shared source images plus existing
        self.assertTrue(textures["T_Authored_forerunner_fitted_plate_albedo"]["srgb"])
        self.assertFalse(textures["T_Authored_forerunner_titanium_roughness"]["srgb"])

    def test_missing_geometry_role_is_an_error_not_silent_fallback(self):
        mats, slots, gltf = self.scene()
        with self.assertRaisesRegex(ValueError, "missing exported shader slots"):
            apply_library(LIBRARY, "/Game/MJOLNIR/Maps/TST", mats[2:], slots[2:], gltf[2:], {})

    def test_bad_color_or_range_cannot_reach_the_editor(self):
        doc = json.loads(LIBRARY.read_text())
        # Absolute files let this invalid copy resolve all image sources.
        for spec in doc["surfaces"].values():
            for key in ("albedo", "roughness_map"):
                spec[key] = str(LIBRARY.parent / spec[key])
        doc["surfaces"]["armor"]["roughness"] = [-1, .4]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "Invalid PBR range"):
                load_library(path)


if __name__ == "__main__":
    unittest.main()
