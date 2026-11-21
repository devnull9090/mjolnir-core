"""Constrained-terrain proof on curved roads, shore and shared UE encoding."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from constrain_terrain import biharmonic_blend, protected_mask, constrain, compatibility_collar, limit_boundary_grade
from heightfield import write_heightfield, load_heightfield, sha256
from derive_runtime_heightfield import derive
from build_landscape import heightfield_geometry, encode_master_heights


class ConstrainedTerrainTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);base=self.root/"baseline";base.mkdir()
        y,x=np.mgrid[:64,:64];self.x=x;self.y=y
        cx=np.linspace(5,58,30);cy=22+3*np.sin((cx-5)/53*np.pi)
        line=np.c_[cx,cy,np.full(len(cx),48.)]
        sections=np.stack([line+np.array([0,d,0]) for d in (-18,-12,0,12,18)],axis=1)
        self.geometry={"schema":"pwr-terrain-geometry-v1","roads":[{"id":"curve","centreline_m":line.tolist(),
            "cross_sections_m":sections.tolist(),"grade_limit":.1,"minimum_radius_m":100,"target_min_radius_m":25}],
            "watercourses":[{"id":"river","surface_centreline_m":[[55,63,55],[55,0,55]]}],
            "crossings":[],"sites":[{"id":"base","position_m":[15,48,48]}],"lakes":[]}
        gp=base/"terrain.geometry.json";gp.write_text(json.dumps(self.geometry))
        self.layout=base/"layout.json";self.layout.write_text(json.dumps({"homes_m":{"red":[15,48,48]},
            "captures_m":[[30,48,48]],"warmup_m":[15,50,48],"spawns_m":{"red":[[14,48,48.8]]}}))
        self.masks={"road":(np.abs(y-(22+3*np.sin((x-5)/53*np.pi)))<12),"water":x>=52,
            "shore":np.abs(x-52)<4,"bases":((x-15)**2+(y-48)**2)<16,"flat":((x-15)**2+(y-48)**2)<16}
        encoding={"centre_cm":22400.,"z_scale":100.,"components":1,"size":64,"origin_cm":[0.,-6300.],"quad_cm":100.}
        self.base=write_heightfield(base/"runtime-master.json",np.full((64,64),48.),[0,0],[1,1],self.masks,
            geometry=gp.name,geometry_sha256=sha256(gp),surface_interpolation="triangle_nw_se",landscape_encoding=encoding)
        self.new=write_heightfield(self.root/"gaea"/"source.json",49+.5*np.sin(x/11)*np.cos(y/13),[0,0],[1,1])
        self.output=self.root/"final-v5"/"final-master.json"

    def test_biharmonic_blend_keeps_curved_core_and_distant_new_relief(self):
        x=self.x;y=self.y
        mask=np.abs(y-(22+3*np.sin(x/12)))<2
        new=48+2*np.sin(x/15)*np.cos(y/18)
        result,report=biharmonic_blend(new,np.full_like(new,48),mask,(1,1),blend_m=10,max_correction_grade=2)
        np.testing.assert_array_equal(result[mask],np.full(mask.sum(),48))
        np.testing.assert_array_equal(result[-1],new[-1])
        self.assertGreater(report["solver_iterations"],0)
        self.assertLess(report["solver_max_residual"],1e-5)
        with self.assertRaisesRegex(ValueError,"adds grade"):
            biharmonic_blend(new+100,np.full_like(new,48),mask,(1,1),blend_m=10,max_correction_grade=.75)

    def test_unprotected_old_relief_cannot_reenter_boundary_blend(self):
        mask=np.abs(self.y-25)<3
        old=48+.01*self.x;new=50+.1*np.sin(self.x/10)*np.cos(self.y/10)
        first,_=biharmonic_blend(new,old,mask,(1,1),blend_m=20,max_correction_grade=2)
        changed=old.copy();changed[~mask]+=100*np.sin(self.x[~mask]/7)
        second,_=biharmonic_blend(new,changed,mask,(1,1),blend_m=20,max_correction_grade=2)
        np.testing.assert_array_equal(first,second)

    def test_compatibility_collar_grows_only_measured_failure_and_keeps_twelve_metre_cap(self):
        protected=self.y<25
        new=np.full((64,64),48.);failed=new.copy();failed[25,20]=51
        grown,report=compatibility_collar(self.base,new,protected,failed,protected)
        self.assertTrue(grown[25,20])
        self.assertFalse(grown[25,50])
        self.assertLessEqual(report["actual_max_extension_m"],12)
        self.assertLess(report["added_vertices"],30)
        # A failure far from the original boundary cannot hide itself by
        # becoming a new protected island.
        failed=new.copy();failed[50,20]=100
        far,_=compatibility_collar(self.base,new,protected,failed,protected)
        np.testing.assert_array_equal(far,protected)

    def test_local_grade_projection_preserves_protected_and_far_samples(self):
        source=np.full((64,64),48.);fit=source.copy();fit[26,20]+=2
        protected=self.y<25
        limited,receipt=limit_boundary_grade(fit,source,protected,(1,1),20)
        np.testing.assert_array_equal(limited[protected],fit[protected])
        np.testing.assert_array_equal(limited[50:],fit[50:])
        self.assertLessEqual(receipt["max_correction_grade"],.75)
        self.assertLessEqual(receipt["max_height_adjustment_m"],1)
        self.assertLess(receipt["changed_vertices"],100)
        raw,centre,scale,_=encode_master_heights(limited*100,{"mode":"fixed","centre_cm":22400.,"z_scale":100.})
        decoded=(centre+(raw.astype(float)-32768)*scale/128)/100
        dy,dx=np.gradient(decoded-source)
        self.assertLessEqual(np.hypot(dx,dy)[~protected].max(),.75)

    def test_full_contract_survives_encoding_and_derivation_without_source_writes(self):
        before={p:p.read_bytes() for p in self.base.path.parent.iterdir()}
        report=constrain(self.new.path,self.base.path,self.layout,self.output,blend_m=10)
        candidate=load_heightfield(self.output)
        mask=candidate.masks["protected"]>0
        np.testing.assert_array_equal(candidate.heights_m[mask],self.base.heights_m[mask])
        self.assertGreater(np.max(np.abs(candidate.heights_m[~mask]-48)),.1)
        self.assertEqual(report["full_road_water_support_max_error_m"],0)
        self.assertEqual((self.output.parent/"terrain.geometry.json").read_bytes(),before[self.base.path.parent/"terrain.geometry.json"])
        runtime=self.root/"runtime-v5"/"runtime-master.json"
        derived=derive(candidate.path,runtime,components=1)
        self.assertTrue(derived["preservation"]["protected_runtime_heights_exact"])
        actual=load_heightfield(runtime)
        np.testing.assert_array_equal(actual.heights_m[mask],self.base.heights_m[mask])
        prepared=heightfield_geometry(actual,1)
        raw,centre,scale,_=encode_master_heights(prepared["heights_cm"],actual.metadata["landscape_encoding_policy"])
        self.assertEqual((centre,scale),(22400,100))
        self.assertEqual(raw.tobytes(),runtime.with_suffix(".r16").read_bytes())
        for path,data in before.items():self.assertEqual(path.read_bytes(),data)

    def test_fails_closed_on_overwrite_flight_limit_or_changed_layout(self):
        with self.assertRaisesRegex(ValueError,"isolated"):
            constrain(self.new.path,self.base.path,self.layout,self.base.path)
        with self.assertRaisesRegex(ValueError,"flight envelope"):
            constrain(self.new.path,self.base.path,self.layout,self.output,maximum_terrain_m=40)
        self.assertFalse(self.output.exists())
        constrain(self.new.path,self.base.path,self.layout,self.output,blend_m=10)
        self.layout.write_text(self.layout.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"layout hash"):
            derive(self.output,self.root/"runtime-v5"/"runtime-master.json",components=1)

    def test_support_cells_and_water_are_protected_with_two_cell_collar(self):
        mask,report=protected_mask(self.base,self.geometry,json.loads(self.layout.read_text()))
        self.assertTrue(mask[self.masks["water"]].all())
        self.assertTrue(mask[46:51,13:18].all())
        self.assertEqual(report["collar_cells"],2)
        with self.assertRaisesRegex(ValueError,"two"):
            protected_mask(self.base,self.geometry,json.loads(self.layout.read_text()),collar_cells=1)

    def test_runtime_derivation_rejects_changed_protected_vertex_and_baseline_overwrite(self):
        constrain(self.new.path,self.base.path,self.layout,self.output,blend_m=10)
        with self.assertRaisesRegex(ValueError,"preservation baseline"):
            derive(self.output,self.base.path,components=1)
        field=load_heightfield(self.output)
        values=field.heights_m.astype(np.float32)
        iy,ix=np.argwhere(field.masks["protected"]>.5)[0]
        values[iy,ix]+=.0078125
        raster=self.output.parent/field.metadata["height"]["path"]
        np.save(raster,values)
        meta=field.metadata;meta["height"]["sha256"]=sha256(raster)
        self.output.write_text(json.dumps(meta))
        target=self.root/"runtime-v5"/"runtime-master.json"
        with self.assertRaisesRegex(ValueError,"Protected runtime heights changed"):
            derive(self.output,target,components=1)
        self.assertFalse(target.exists())


if __name__=="__main__":unittest.main()
