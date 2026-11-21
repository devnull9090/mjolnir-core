import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from heightfield import load_heightfield,write_heightfield,sha256
from adaptive_heightfield import build,Rtin,topology,align_leaf_diagonals,audit

class ReaderTests(unittest.TestCase):
    def test_unreal_triangle_diagonal_preserves_bilinear_masks(self):
        with tempfile.TemporaryDirectory() as temp:
            z=np.array([[0,0],[0,8]],dtype=float)
            f=write_heightfield(Path(temp)/"runtime.json",z,(0,0),(2,2),{"road":z/8},surface_interpolation="triangle_nw_se")
            self.assertEqual(float(f.sample(1,1)),0)
            self.assertEqual(float(f.sample(1.5,1.5)),4)
            self.assertEqual(float(f.sample_mask("road",1,1)),.25)

    def test_eight_bit_concept_is_not_silently_treated_as_sixteen_bit_height(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);Image.fromarray(np.array([[0,255],[128,64]],dtype=np.uint8)).save(root/"concept.png")
            doc={"schema":"pwr-heightfield-v1","coordinates":"authoring_metres_z_up",
                 "origin_m":[0,0],"spacing_m":[1,1],"dimensions":[2,2],"row_order":"+y",
                 "height":{"path":"concept.png","encoding":"uint16_png","offset_m":0,"scale_m":400/65535,"sha256":sha256(root/"concept.png")}}
            (root/"master.json").write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"8-bit image"):load_heightfield(root/"master.json")

    def test_raw_height_calibration_axis_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=np.array([[.3,.4],[.1,.2]],dtype="<f4")
            (root/"gaea.r32").write_bytes(raw.tobytes())
            manifest={"schema":"pwr-heightfield-v1","coordinates":"authoring_metres_z_up",
                "origin_m":[-1000,-1000],"spacing_m":[2000,2000],"dimensions":[2,2],"row_order":"-y",
                "height":{"path":"gaea.r32","encoding":"float32_raw_le","offset_m":10,"scale_m":400,"sha256":sha256(root/"gaea.r32")}}
            path=root/"terrain.json";path.write_text(json.dumps(manifest))
            field=load_heightfield(path)
            self.assertAlmostEqual(float(field.sample(-1000,-1000)),50,places=5)
            self.assertAlmostEqual(float(field.sample(1000,1000)),170,places=5)
            self.assertAlmostEqual(float(field.sample(0,0)),110,places=5)
            with self.assertRaises(ValueError):field.sample(1001,0)
            (root/"gaea.r32").write_bytes(raw.tobytes()+b"x")
            with self.assertRaisesRegex(ValueError,"SHA-256"):load_heightfield(path)

    def test_master_roundtrip_mask_and_explicit_scale(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"master.json";a=np.arange(20).reshape(4,5)/2
            f=write_heightfield(path,a,(-4,-6),(2,4),{"road":np.eye(4,5)})
            np.testing.assert_allclose(f.heights_m,a)
            self.assertEqual(f.bounds_m,((-4.,-6.),(4.,6.)))
            self.assertAlmostEqual(float(f.sample_mask("road",-4,-6)),1)
            d=json.loads(path.read_text());del d["height"]["scale_m"];path.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"explicit"):load_heightfield(path)

class AdaptiveTests(unittest.TestCase):
    def test_full_resolution_triangle_diagonal_matches_runtime_surface(self):
        with tempfile.TemporaryDirectory() as temp:
            z=np.array([[0,0],[0,8]],dtype=float)
            f=write_heightfield(Path(temp)/"runtime.json",z,(0,0),(1,1),surface_interpolation="triangle_nw_se")
            v=np.array([[0,0,0],[1,0,0],[0,1,0],[1,1,8]],dtype=float)
            t=np.array([[0,1,3],[0,3,2]])
            self.assertEqual(audit(f,v,t,(1,1),np.ones((2,2)))["regions"]["all"]["max_abs_m"],4)
            v,t=align_leaf_diagonals(v,t)
            self.assertEqual(audit(f,v,t,(1,1),np.ones((2,2)))["regions"]["all"]["max_abs_m"],0)

    def test_padded_non_power_grid_preserves_sharp_sample_locations(self):
        y,x=np.mgrid[:32,:32];z=np.zeros((32,32));z[10:22,15]=20
        with tempfile.TemporaryDirectory() as temp:
            f=write_heightfield(Path(temp)/"ridge.json",z,(-31,-31),(2,2),surface_interpolation="triangle_nw_se")
            v,t,r=build(f,terrain_budget=2400,reserve_surfaces=8000)
            self.assertLess(r["measurement"]["regions"]["all"]["max_abs_m"],.01)
            self.assertTrue(r["accuracy_and_mesh_budget_pass"])

    def test_non_power_of_two_source_preserves_extent_and_grid_coverage(self):
        y,x=np.mgrid[:29,:37];z=20+x*.125+y*.25
        with tempfile.TemporaryDirectory() as temp:
            f=write_heightfield(Path(temp)/"rect.json",z,(-100,-80),(3,5))
            v,t,r=build(f,terrain_budget=100,reserve_surfaces=8000)
            np.testing.assert_allclose(v[:,:2].min(axis=0),[-100,-80])
            np.testing.assert_allclose(v[:,:2].max(axis=0),[8,60])
            self.assertEqual(r["measurement"]["regions"]["all"]["samples"],29*37+28*36)
            self.assertTrue(r["accuracy_and_mesh_budget_pass"])

    def test_plane_stays_two_triangles_and_exact(self):
        y,x=np.mgrid[:33,:33];z=12+.25*x-.125*y
        with tempfile.TemporaryDirectory() as temp:
            f=write_heightfield(Path(temp)/"plane.json",z,(0,0),(4,4),{"flat":np.ones(z.shape)})
            v,t,r=build(f,terrain_budget=100,reserve_surfaces=8000)
            self.assertEqual(len(t),2)
            self.assertLess(r["measurement"]["regions"]["flat"]["max_abs_m"],1e-9)
            self.assertTrue(r["accuracy_and_mesh_budget_pass"])
            self.assertFalse(r["runtime_ready"])

    def test_curved_road_and_shore_are_measured_and_conforming(self):
        y,x=np.mgrid[-256:256:129j,-256:256:129j]
        road_dist=np.abs(x-65*np.sin(y/120))
        road=(road_dist<16).astype(float)
        blend=np.clip((road_dist-14)/46,0,1)
        blend=blend*blend*(3-2*blend)
        lake=np.hypot((x+100)/75,(y-90)/55)
        shore=(np.abs(lake-1)<.18).astype(float)
        z=40+13*np.sin(x/110)*np.cos(y/130)
        z=z*blend+(35+y*.025)*(1-blend)
        z-=9*np.exp(-((x+100)/75)**2-((y-90)/55)**2)
        with tempfile.TemporaryDirectory() as temp:
            f=write_heightfield(Path(temp)/"curved.json",z,(-256,-256),(4,4),{"road":road,"shore":shore})
            v,t,r=build(f,terrain_budget=12000,reserve_surfaces=8000,ground_error=.5,road_error=.15,shore_error=.25)
            self.assertLessEqual(len(t),12000)
            self.assertEqual(r["topology"]["interior_boundary_edges"],0)
            self.assertEqual(r["topology"]["nonmanifold_edges"],0)
            self.assertLess(r["measurement"]["regions"]["road"]["max_abs_m"],.15)
            self.assertLess(r["measurement"]["regions"]["shore"]["max_abs_m"],.25)
            self.assertTrue(r["accuracy_and_mesh_budget_pass"])
            self.assertGreater(r["measurement"]["regions"]["all"]["samples"],129*129)

    def test_small_budget_reports_failure_instead_of_claiming_precision(self):
        y,x=np.mgrid[:65,:65];z=20+3*np.sin(x*1.3)*np.cos(y*.7)
        with tempfile.TemporaryDirectory() as temp:
            f=write_heightfield(Path(temp)/"rough.json",z,(0,0),(2,2),{"road":np.ones(z.shape)})
            _,t,r=build(f,terrain_budget=50,reserve_surfaces=8000)
            self.assertLessEqual(len(t),50)
            self.assertFalse(r["accuracy_and_mesh_budget_pass"])
            self.assertGreater(r["measurement"]["regions"]["road"]["max_abs_m"],.15)

if __name__=="__main__":unittest.main()
