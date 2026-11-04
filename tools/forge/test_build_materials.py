"""Portable cook-receipt and namespacing regressions; no Unreal or game needed."""
import json
import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import build_materials as materials
from build_pack import MATERIALS, surface_materials


class SurfaceBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack, self.textures = self.root / "pack", self.root / "textures"
        self.pack.mkdir(); self.textures.mkdir()
        (self.pack / "catalog.json").write_text(json.dumps({"forge_pack": {"id": "test-pack"}}))
        profiles = json.loads(materials.PROFILES.read_text())
        for texture in profiles["textures"]:
            (self.textures / texture["source"]).write_bytes(b"DDS " + bytes(124))

    def prepare(self):
        return materials.prepare(self.pack, self.textures, 967)

    def receipt(self):
        spec, _ = self.prepare()
        content = spec.parent / "content"
        content.mkdir(exist_ok=True)
        files = {}
        for suffix in (".utoc", ".ucas", ".pak"):
            file = content / ("pakchunk967-MJOLNIRFORGEMAT-test-pack_P" + suffix)
            file.write_bytes(b"cooked" + suffix.encode())
            files[file.name] = materials.sha(file)
        receipt = {"schema_version": 1, "slug": "test-pack", "chunk": 967,
                   "spec_sha256": materials.sha(spec), "profiles_sha256": materials.sha(materials.PROFILES),
                   "files": files}
        path = spec.parent / "receipt.json"
        path.write_text(json.dumps(receipt))
        return path, receipt

    def test_self_contained_spec_records_original_stages_and_inputs(self):
        path, spec = self.prepare()
        self.assertEqual(spec["root"], "/Game/MJOLNIR/Forge/test-pack")
        self.assertEqual(spec["profiles_sha256"], materials.sha(materials.PROFILES))
        self.assertEqual(spec["provenance"]["teleporter_green"]["source_shader_tag"],
                         r"levels\test\tutorial\shaders\example_tutorial_teleporter")
        portal = spec["profiles"]["teleporter_green"]
        self.assertEqual(portal["scalars"]["StageCount"], 4)
        self.assertEqual(portal["vectors"]["StageColorFunctions"], [4, 2, 4, 0])
        self.assertEqual(portal["vectors"]["StageAlphaFunctions"], [10, 10, 2, 0])
        self.assertEqual(portal["vectors"]["Stage0UAnim"], [6, 4, 0, -1])
        self.assertFalse(any("Fog" in key for group in ("scalars", "vectors") for key in portal[group]))
        self.assertNotIn("/Game/CE/TST", path.read_text())
        for item in spec["textures"]:
            self.assertEqual(item["sha256"], materials.sha(item["file"]))

    def test_invalid_inputs_are_rejected_before_cook(self):
        for chunk in (True, 899, 1000, 967.5):
            with self.assertRaises(ValueError):
                materials.prepare(self.pack, self.textures, chunk)
        for slug in ("../escape", "a", "Upper", "valid/escape"):
            (self.pack / "catalog.json").write_text(json.dumps({"forge_pack": {"id": slug}}))
            with self.assertRaises(ValueError):
                self.prepare()
        (self.pack / "catalog.json").write_text(json.dumps({"forge_pack": {"id": "test-pack"}}))
        next(self.textures.iterdir()).write_bytes(b"not a DDS")
        with self.assertRaisesRegex(ValueError, "DDS"):
            self.prepare()

    def test_complete_receipt_then_corrupt_payload(self):
        self.receipt()
        files = materials.verified_content(self.pack, "test-pack")
        self.assertEqual(len(files), 3)
        next(f for f in files if f.suffix == ".ucas").write_bytes(b"different cook")
        with self.assertRaisesRegex(ValueError, "missing/changed"):
            materials.verified_content(self.pack, "test-pack")

    def test_stale_spec_profile_other_pack_and_shader_chunk_fail_closed(self):
        path, receipt = self.receipt()
        for mutation in ({"slug": "other-pack"}, {"profiles_sha256": "0"*64},
                         {"spec_sha256": "0"*64}, {"chunk": 968}, {"schema_version": 2}):
            path.write_text(json.dumps({**receipt, **mutation}))
            with self.assertRaises(ValueError):
                materials.verified_content(self.pack, "test-pack")

    def test_missing_misnamed_or_traversing_container_is_rejected(self):
        path, receipt = self.receipt()
        for replacement in ({}, {"../escape.utoc": "0"*64},
                            {k.replace("967", "968"): v for k, v in receipt["files"].items()},
                            {k: v for k, v in receipt["files"].items() if not k.endswith(".pak")}):
            path.write_text(json.dumps({**receipt, "files": replacement}))
            with self.assertRaises(ValueError):
                materials.verified_content(self.pack, "test-pack")

    def test_old_materials_are_unchanged_and_new_slots_are_namespaced(self):
        for block in ({}, {"surfaces": None}, {"surfaces": []}):
            self.assertEqual(surface_materials("foundry", block), MATERIALS)
        selected = surface_materials("test-pack", {"surfaces": [{"slot": 7, "profile": "glass_cyan"}]})
        self.assertEqual(selected[:7], MATERIALS)
        self.assertEqual(selected[7], ("glass", "/Game/MJOLNIR/Forge/test-pack/Materials/M_ForgeGlassCyan"))
        self.assertEqual(selected[8], ("portal_green", "/Game/MJOLNIR/Forge/test-pack/Materials/M_ForgePortalGreen"))
        for surface in ({"slot": 8, "profile": "glass_cyan"}, {"slot": True, "profile": "glass_cyan"},
                        {"slot": 7, "profile": "custom"}, {"slot": 7, "profile": "glass_cyan", "path": "/Game/TST"}):
            with self.assertRaises(ValueError):
                surface_materials("test-pack", {"surfaces": [surface]})

    def test_ce_graph_defaults_are_opt_in_and_portal_defaults_are_real_assets(self):
        # Compile the actual graph helper with a tiny Unreal expression shim.
        # This exercises first-frame defaults, independent of runtime MID work.
        path = materials.ROOT / "unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        graph = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Graph")
        graph.body = [n for n in graph.body if isinstance(n, ast.FunctionDef)
                      and n.name in ("__init__", "scalar", "vector", "texture")]
        namespace = {"unreal": SimpleNamespace(
            MaterialExpressionScalarParameter="scalar", MaterialExpressionVectorParameter="vector",
            MaterialExpressionTextureSampleParameter2D="texture",
            MaterialSamplerType=SimpleNamespace(SAMPLERTYPE_LINEAR_COLOR="linear"),
            LinearColor=lambda *rgba: rgba), "link": lambda *args: None}
        exec(compile(ast.Module(body=[graph], type_ignores=[]), str(path), "exec"), namespace)
        graph_type = namespace["Graph"]
        graph_type.node = lambda _, kind, **props: (kind, props)
        stock = graph_type("material")
        self.assertEqual(stock.scalar("StageCount", 1)[1]["default_value"], 1)
        self.assertEqual(stock.texture("Map0", "white", "uv")[1]["texture"], "white")
        profile = json.loads(materials.PROFILES.read_text())["profiles"]["teleporter_green"]
        profile["textures"] = {name: object() for name in profile["textures"]}
        forge = graph_type("material", profile)
        self.assertEqual(forge.scalar("StageCount", 1)[1]["default_value"], 4)
        self.assertEqual(forge.vector("Stage0UAnim")[1]["default_value"], (6, 4, 0, -1))
        self.assertIs(forge.texture("Map0", "white", "uv")[1]["texture"], profile["textures"]["Map0"])
        self.assertEqual(forge.scalar("Unspecified", 17)[1]["default_value"], 17)


if __name__ == "__main__":
    unittest.main()
