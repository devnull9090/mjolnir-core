"""Offline direct-heightfield coverage; no Unreal, apps or installed map writes."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import build_landscape as land
import upgrade_ce_map as upgrade
from heightfield import load_heightfield


class MasterLandscapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def field(self, heights, *, spacing=(1, 1), row_order="+y"):
        heights = np.asarray(heights, dtype=np.float32)
        source = self.root / "master.npy"
        np.save(source, heights)
        meta = {"schema": "pwr-heightfield-v1", "coordinates": "authoring_metres_z_up",
                "origin_m": [10, 20], "spacing_m": list(spacing), "dimensions": list(heights.shape[::-1]),
                "row_order": row_order, "height": {"path": source.name, "encoding": "float32_npy",
                "offset_m": 0, "scale_m": 1, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
        manifest = self.root / "master.json"
        manifest.write_text(json.dumps(meta))
        return load_heightfield(manifest)

    def scene(self):
        # Flat CE proxy: it must not erase the master's 200 m relief.
        arrays = [np.array([[10, 0, -83], [73, 0, -83], [73, 0, -20], [10, 0, -20]], dtype="<f4"),
                  np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype="<f4"),
                  np.array([0, 1, 2, 0, 2, 3], dtype="<u2")]
        views, accessors, data = [], [], b""
        for array, typ in zip(arrays, ("VEC3", "VEC2", "SCALAR")):
            views.append({"buffer": 0, "byteOffset": len(data), "byteLength": array.nbytes})
            accessors.append({"bufferView": len(views) - 1, "componentType": 5126 if array.dtype.kind == "f" else 5123,
                              "count": len(array), "type": typ})
            data += array.tobytes()
        (self.root / "scene.bin").write_bytes(data)
        gltf = {"buffers": [{"uri": "scene.bin", "byteLength": len(data)}], "bufferViews": views,
                "accessors": accessors, "materials": [{"name": "ground"}], "meshes": [{"primitives": [
                {"material": 0, "attributes": {"POSITION": 0, "TEXCOORD_0": 1, "TEXCOORD_1": 1}, "indices": 2}]}]}
        (self.root / "scene.gltf").write_text(json.dumps(gltf))
        (self.root / "materials.json").write_text(json.dumps({"textures": [], "slots": [
            {"pattern": "ground", "material": {"textures": {}, "vectors": {}, "scalars": {}}}]}))

    def run_builder(self, *extra):
        self.scene()
        out = self.root / "land"
        argv = ["build_landscape.py", str(self.root / "scene.gltf"), str(self.root / "materials.json"),
                str(out), "--shader", "ground", "--components", "1", "--texture", "16", *extra]
        with patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()):
            land.main()
        spec = json.loads((out / "landscape.json").read_text())
        raw = np.fromfile(out / "heights.r16", dtype="<u2").reshape(spec["size"], spec["size"])
        heights = spec["location"][2] + (raw.astype(float) - 32768) * spec["scale"][2] / 128
        return spec, heights, np.fromfile(out / "holes.r8", dtype="u1")

    def test_authoring_y_flip_offset_and_exact_extent(self):
        values = np.arange(64 * 64, dtype=np.float32).reshape(64, 64) / 64
        field = self.field(values)
        geometry = land.heightfield_geometry(field, 1, offset=(123, 456, 789))
        np.testing.assert_allclose(geometry["origin"], [1123, -7844])
        np.testing.assert_allclose(geometry["heights_cm"], values[::-1] * 100 + 789)
        self.assertEqual(geometry["quad"], 100)
        flipped = self.field(values[::-1], row_order="-y")
        np.testing.assert_array_equal(land.heightfield_geometry(flipped, 1)["heights_cm"], values[::-1] * 100)

    def test_explicit_spacing_cannot_crop_or_stretch_master(self):
        field = self.field(np.zeros((64, 64)))
        for spacing in (99, 101, float("nan")):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                land.heightfield_geometry(field, 1, spacing)
        with self.assertRaisesRegex(ValueError, "square"):
            land.heightfield_geometry(self.field(np.zeros((64, 64)), spacing=(1, 2)))

    def test_tall_relief_encodes_without_clipping(self):
        values = np.array([[-91000.123, -2000.456], [20000.789, 120000.123]])
        raw, centre, scale, report = land.encode_master_heights(values)
        self.assertGreater(scale, 100)
        decoded = centre + (raw.astype(float) - 32768) * scale / 128
        self.assertLessEqual(np.max(np.abs(decoded - values)), scale / 256 + 1e-7)
        self.assertEqual(report["clipped_samples"], 0)
        with self.assertRaisesRegex(ValueError, "finite"):
            land.encode_master_heights(np.array([[np.nan]]))

    def test_fixed_encoding_retains_shared_heights_despite_new_range(self):
        fixed={"mode":"fixed","centre_cm":22400.,"z_scale":100.}
        common=10759.375
        first=land.encode_master_heights(np.array([[4800.,common,39950.]]),fixed)
        second=land.encode_master_heights(np.array([[5500.,common,25000.]]),fixed)
        self.assertEqual(first[0][0,1],second[0][0,1])
        self.assertEqual(first[1:3],second[1:3])
        self.assertEqual(second[3]["mode"],"fixed")
        with self.assertRaisesRegex(ValueError,"clip"):
            land.encode_master_heights(np.array([[60000.]]),fixed)
        for invalid in ({"mode":"auto"},{"mode":"fixed","centre_cm":False,"z_scale":100},
                        {"mode":"fixed","centre_cm":0,"z_scale":float("nan")},
                        {"mode":"fixed","centre_cm":0,"z_scale":0}):
            with self.assertRaises(ValueError):land.encode_master_heights(np.array([[0.]]),invalid)

    def test_fixed_policy_reaches_cli_and_rejects_shifted_grid(self):
        field=self.field(np.full((64,64),48.0))
        meta=json.loads(field.path.read_text())
        meta["landscape_encoding_policy"]={"mode":"fixed","centre_cm":22400.,"z_scale":100.,
            "components":1,"size":64,"quad_cm":100.,"origin_cm":[1000.,-8300.]}
        field.path.write_text(json.dumps(meta));field=load_heightfield(field.path)
        spec,heights,_=self.run_builder("--heightfield",str(field.path))
        self.assertEqual(spec["location"][2],22400.)
        np.testing.assert_array_equal(heights,np.full((64,64),4800.))
        for kwargs in ({"components":2},{"lift":1},{"offset":(0,1,0)}):
            with self.assertRaisesRegex(ValueError,"Fixed Landscape"):
                land.heightfield_geometry(field,**kwargs)

    def test_source_error_detects_detail_lost_between_landscape_vertices(self):
        values = np.zeros((127, 127), dtype=np.float32)
        values[1, 1] = 30
        field = self.field(values, spacing=(0.5, 0.5))
        geometry = land.heightfield_geometry(field, 1)
        raw, centre, scale, _ = land.encode_master_heights(geometry["heights_cm"])
        report = land.master_sampling_report(field, raw, centre, scale)
        self.assertEqual(report["bilinear_max_abs_m"], 30)
        self.assertEqual(report["sample_count"], 127 * 127)

    def test_direct_cli_retains_detail_instead_of_cutting_or_settling_to_mesh(self):
        values = np.zeros((64, 64), dtype=np.float32)
        values[18:27, 31:36] = 200  # Steep features previously became mesh holes.
        field = self.field(values)
        spec, heights, holes = self.run_builder("--heightfield", str(field.path))
        np.testing.assert_allclose(heights, values[::-1] * 100, atol=0.4)
        self.assertEqual(int(holes.sum()), 0)
        self.assertEqual(spec["lift"], 0)
        receipt = spec["heightfield"]
        self.assertEqual(receipt["coarse_mesh_comparison"]["max_abs_m"], 200)
        self.assertEqual(receipt["manifest_sha256"], field.manifest_sha256)
        self.assertEqual(receipt["source_grid_error"]["sample_count"], 64 * 64)
        self.assertIn("unmeasured", receipt["native_collision_parity"])

    def test_existing_mesh_cli_keeps_eight_centimetre_lift(self):
        spec, heights, _ = self.run_builder()
        self.assertEqual(spec["lift"], 8)
        self.assertEqual(spec["scale"], [100, 100, 100])
        np.testing.assert_allclose(heights, 8, atol=0.4)
        self.assertNotIn("heightfield", spec)

    def test_upgrade_config_forwards_master_without_old_default_spacing(self):
        field = self.field(np.zeros((64, 64)))
        config = {"shaders": ["ground"], "landscape": "LPW", "components": 1,
                  "heightfield": field.path.name, "landscape_lift": 0}
        with patch.object(upgrade, "REPO", str(self.root)), patch.object(upgrade, "run", return_value="") as run:
            upgrade.stage_land("PWR", config, {"scene": "scene", "land": "land"})
        argv = run.call_args.args[0]
        self.assertEqual(Path(argv[argv.index("--heightfield") + 1]), field.path)
        self.assertEqual(argv[argv.index("--lift") + 1], "0")
        self.assertNotIn("--quad", argv)

    def test_upgrade_missing_master_stops_before_process_launch(self):
        config = {"shaders": ["ground"], "landscape": "LPW", "heightfield": "missing.master.json"}
        with patch.object(upgrade, "REPO", str(self.root)), patch.object(upgrade, "run") as run:
            with self.assertRaisesRegex(FileNotFoundError, "heightfield"):
                upgrade.stage_land("PWR", config, {"scene": "scene", "land": "land"})
            run.assert_not_called()

    def test_geology_cli_opts_in_without_changing_height_or_road_alpha(self):
        field=self.field(np.full((64,64),48.0))
        data=self.root/'geology.npy';np.save(data,np.full((64,64,3),.25,dtype=np.float32))
        manifest=self.root/'geology.json'
        manifest.write_text(json.dumps({'schema':'pwr-alpine-geology-v1',
            'coordinates':'authoring_metres_z_up','row_order':'+y','master_sha256':field.manifest_sha256,
            'dimensions':[64,64],'data':data.name,'data_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
            'channels':['exposed_rock','retained_snow','meadow_soil']}))
        spec,heights,_=self.run_builder('--heightfield',str(field.path),'--name','LPW','--geology',str(manifest))
        self.assertEqual(spec['pbr']['alpine'][3],2)
        np.testing.assert_allclose(heights,4800,atol=.4)
        proof=json.loads((self.root/'land/geology.receipt.json').read_text())
        self.assertTrue(proof['road_alpha_unchanged'])
        self.assertEqual(proof['master_sha256'],field.manifest_sha256)


if __name__ == "__main__":
    unittest.main()
