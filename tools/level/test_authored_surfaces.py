import copy
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from authored_surfaces import apply_library, load_library

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "levels/test/tst/surfaces.json"


class AuthoredSurfacesTest(unittest.TestCase):
    def scene(self, library=LIBRARY):
        surfaces = load_library(library)
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
        self.assertEqual(set(surfaces), set(load_library(LIBRARY)))
        self.assertEqual(slots[-2:], untouched)
        for slot in slots[:-2]:
            self.assertTrue(slot["material"]["parent"].startswith("/Game/MJOLNIR/Maps/TST/SurfaceMaterials/"))
            self.assertNotIn("textures", slot["material"])
        expected = {Path(s[key]).stem for s in surfaces.values()
                    for key in ("albedo", "roughness_map", "normal_map") if key in s}
        self.assertEqual(set(textures), {"Existing"} | {"T_Authored_" + name for name in expected})
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
            for key in ("albedo", "roughness_map", "normal_map"):
                if key in spec:
                    spec[key] = str(LIBRARY.parent / spec[key])
        doc["surfaces"]["armor"]["roughness"] = [-1, .4]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "Invalid PBR range"):
                load_library(path)

    def normal_library(self, root, convention):
        source = dict(load_library(LIBRARY)["armor"])
        source.update(normal_map="shared_normal.png", normal_convention=convention)
        (root / "shared_normal.png").touch()
        surfaces = {}
        for role in ("facility_extra", "facility_extra_recess"):
            surfaces[role] = dict(source, shader="tst_" + role, tag="levels/test/tst/shaders/tst_" + role)
        path = root / "surfaces.json"
        path.write_text(json.dumps({"version": 1, "surfaces": surfaces}))
        return path

    def test_normal_convention_and_linear_compression_survive_shared_role_binding(self):
        for convention in ("opengl", "directx"):
            with self.subTest(convention=convention), tempfile.TemporaryDirectory() as tmp:
                library = self.normal_library(Path(tmp), convention)
                mats, slots, gltf = self.scene(library)
                textures = {}
                surfaces = apply_library(library, "/Game/MJOLNIR/Maps/TST", mats, slots, gltf, textures)
                normal = textures["T_Authored_shared_normal"]
                self.assertFalse(normal["srgb"])
                self.assertTrue(normal["normal_map"])
                self.assertEqual(normal["compression"], "normalmap")
                self.assertEqual(normal["normal_convention"], convention)
                self.assertEqual(normal["flip_green_channel"], convention == "opengl")
                self.assertEqual({s["normal_map_asset"] for s in surfaces.values()},
                                 {"/Game/MJOLNIR/Maps/TST/Textures/T_Authored_shared_normal"})
                # Both exact source tags, on every lightmap page, retain their own masters.
                self.assertEqual(len({slot["material"]["parent"] for slot in slots[:-2]}), 2)

    def test_normal_convention_is_validated_and_opengl_is_the_explicit_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.normal_library(Path(tmp), "wrong")
            with self.assertRaisesRegex(ValueError, "normal_convention"):
                load_library(library)
            doc = json.loads(library.read_text())
            for surface in doc["surfaces"].values():
                surface.pop("normal_convention")
            library.write_text(json.dumps(doc))
            self.assertTrue(all(s["normal_convention"] == "opengl" for s in load_library(library).values()))
            for surface in doc["surfaces"].values():
                surface.pop("normal_map")
                surface["normal_convention"] = "opengl"
            library.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "requires normal_map"):
                load_library(library)

    def test_normal_strength_defaults_validates_and_stays_per_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.normal_library(Path(tmp), "opengl")
            self.assertTrue(all(s["normal_strength"] == 1 for s in load_library(library).values()))
            doc = json.loads(library.read_text())
            roles = list(doc["surfaces"])
            for value in (-.01, 1.01, float("nan"), float("inf"), "0.5", True, None):
                doc["surfaces"][roles[0]]["normal_strength"] = value
                library.write_text(json.dumps(doc))
                with self.subTest(invalid=value), self.assertRaisesRegex(ValueError, "normal_strength"):
                    load_library(library)
            for role, strength in zip(roles, (.45, .6)):
                doc["surfaces"][role]["normal_strength"] = strength
            library.write_text(json.dumps(doc))
            mats, slots, gltf = self.scene(library)
            textures = {}
            surfaces = apply_library(library, "/Game/MJOLNIR/Maps/TST", mats, slots, gltf, textures)
            self.assertEqual([surfaces[role]["normal_strength"] for role in roles], [.45, .6])
            self.assertEqual(sum(bool(t.get("normal_map")) for t in textures.values()), 1)
            for surface in doc["surfaces"].values():
                surface.pop("normal_map")
                surface.pop("normal_convention")
            library.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "normal_strength requires normal_map"):
                load_library(library)


class NativeNormalImportTest(unittest.TestCase):
    def setUp(self):
        # Run the actual import helper without importing/launching Unreal or
        # executing the build script's destructive asset-management top level.
        path = ROOT / "unreal/MJOLNIRMaterials/Scripts/build_ce_level.py"
        tree = ast.parse(path.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "configure_authored_texture")
        unreal = SimpleNamespace(
            TextureCompressionSettings=SimpleNamespace(TC_NORMALMAP="normal", TC_DEFAULT="color", TC_MASKS="masks"),
            TextureMipGenSettings=SimpleNamespace(TMGS_FROM_TEXTURE_GROUP="mips"))
        namespace = {"unreal": unreal}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        self.configure = namespace["configure_authored_texture"]

    def test_reimport_flips_opengl_once_and_clears_flip_for_directx(self):
        properties = {}
        texture = SimpleNamespace(set_editor_property=properties.__setitem__)
        for convention, flip in (("opengl", True), ("directx", False)):
            self.configure(texture, {"srgb": False, "normal_map": True, "compression": "normalmap",
                                     "normal_convention": convention, "flip_green_channel": flip})
            self.assertEqual(properties["compression_settings"], "normal")
            self.assertEqual(properties["flip_green_channel"], flip)
            self.assertFalse(properties["srgb"])
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.configure(texture, {"srgb": False, "normal_map": True, "compression": "normalmap",
                                     "normal_convention": "opengl", "flip_green_channel": False})

    def test_existing_color_and_scalar_import_settings_are_unchanged(self):
        for srgb, compression in ((True, "color"), (False, "masks")):
            properties = {}
            self.configure(SimpleNamespace(set_editor_property=properties.__setitem__), {"srgb": srgb})
            self.assertEqual(properties, {"srgb": srgb, "compression_settings": compression,
                                          "flip_green_channel": False, "never_stream": False,
                                          "mip_gen_settings": "mips"})

    def normal_graph(self, strength):
        """Record the actual native builder's graph without starting Unreal."""
        class Node:
            def __init__(self, kind="asset"):
                self.kind, self.properties = kind, {}
            def set_editor_property(self, key, value):
                self.properties[key] = value
        expressions, connections, outputs = [], [], {}
        def create(material, cls):
            node = Node(cls)
            expressions.append(node)
            return node
        def connect(source, pin, target, target_pin):
            connections.append((source, pin, target, target_pin))
            return True
        def output(source, pin, prop):
            outputs[prop] = (source, pin)
            return True
        unreal = SimpleNamespace(
            load_asset=lambda path: Node(), CustomInput=Node, LinearColor=lambda *args: args,
            MaterialExpressionTextureSample="texture", MaterialExpressionCustom="custom",
            MaterialExpressionConstant="constant", MaterialExpressionConstant3Vector="constant3",
            MaterialSamplerType=SimpleNamespace(SAMPLERTYPE_COLOR="color", SAMPLERTYPE_MASKS="masks", SAMPLERTYPE_NORMAL="normal"),
            CustomMaterialOutputType=SimpleNamespace(CMOT_FLOAT3="float3", CMOT_FLOAT1="float1"),
            MaterialProperty=SimpleNamespace(MP_BASE_COLOR="base", MP_ROUGHNESS="rough", MP_METALLIC="metal", MP_NORMAL="normal"))
        namespace = {"unreal": unreal, "root": "/Game/Test",
            "mel": SimpleNamespace(delete_all_material_expressions=lambda material: None,
                create_material_expression=create, connect_material_expressions=connect,
                connect_material_property=output, recompile_material=lambda material: None),
            "eal": SimpleNamespace(save_loaded_asset=lambda material: None)}
        path = ROOT / "unreal/MJOLNIRMaterials/Scripts/build_ce_level.py"
        tree = ast.parse(path.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_authored_surface")
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        surface = {"albedo_asset": "a", "roughness_map_asset": "r", "normal_map_asset": "n",
                   "soften": .1, "tint": [1,1,1], "roughness": [.3,.6], "metallic": .5}
        if strength is not None:
            surface["normal_strength"] = strength
        namespace["build_authored_surface"]("test", surface)
        return expressions, connections, outputs

    def test_native_normal_strength_graph_blends_then_normalizes_and_keeps_default_direct(self):
        for strength in (None, 1.0, 0.0, .45, .6):
            with self.subTest(strength=strength):
                expressions, connections, outputs = self.normal_graph(strength)
                decoded = next(n for n in expressions if n.properties.get("sampler_type") == "normal")
                result, pin = outputs["normal"]
                if strength in (None, 1.0):
                    self.assertIs(result, decoded)
                    self.assertEqual(pin, "RGB")
                else:
                    self.assertEqual(result.kind, "custom")
                    self.assertEqual(result.properties["code"],
                                     "return normalize(lerp(float3(0.0, 0.0, 1.0), N, Strength));")
                    self.assertIn((decoded, "RGB", result, "N"), connections)
                    value = next(src for src, _, dest, dest_pin in connections if dest is result and dest_pin == "Strength")
                    self.assertEqual(value.properties["r"], strength)
                    self.assertEqual([i.properties["input_name"] for i in result.properties["inputs"]], ["N", "Strength"])


class ExplicitRoleAssignmentTest(unittest.TestCase):
    def setUp(self):
        path = LIBRARY.parent / "architecture_surfaces.py"
        spec = importlib.util.spec_from_file_location("architecture_surfaces_test", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def scene(self, roles, face_indices):
        class Object(dict):
            type = "MESH"
            name = "facility_explicit_test"
        obj = Object()
        obj.data = SimpleNamespace(materials=[{"tst_surface_role": role} for role in roles],
                                   polygons=[SimpleNamespace(material_index=i) for i in face_indices])
        return SimpleNamespace(objects=[obj]), obj

    def test_used_explicit_roles_count_without_remapping_faces(self):
        scene, obj = self.scene(["armor", "facility_extra"], [0, 1, 1])
        with patch.object(self.module, "SURFACES", {"armor": {}, "facility_extra": {}}):
            self.module.assign(scene)
        self.assertTrue(obj["tst_exported_surfaces"])
        self.assertEqual([p.material_index for p in obj.data.polygons], [0, 1, 1])

    def test_unused_slots_and_unknown_roles_do_not_satisfy_assignment(self):
        scene, _ = self.scene(["armor", "facility_extra"], [0])
        with patch.object(self.module, "SURFACES", {"armor": {}, "facility_extra": {}}):
            with self.assertRaisesRegex(RuntimeError, "Unassigned architectural finishes"):
                self.module.assign(scene)
        scene, _ = self.scene(["misspelled_role"], [0])
        with patch.object(self.module, "SURFACES", {"armor": {}}):
            with self.assertRaisesRegex(RuntimeError, "Unknown explicit architectural finish"):
                self.module.assign(scene)


if __name__ == "__main__":
    unittest.main()
