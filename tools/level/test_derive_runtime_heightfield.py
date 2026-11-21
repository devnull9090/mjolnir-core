import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from build_landscape import heightfield_geometry, encode_master_heights
from derive_runtime_heightfield import derive
from heightfield import load_heightfield, write_heightfield, sha256


class RuntimeHeightfieldTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);source=self.root/"approved";source.mkdir()
        geometry=source/"terrain.geometry.json"
        geometry.write_text(json.dumps({"schema":"pwr-terrain-geometry-v1","sites":[]}))
        y,x=np.mgrid[:128,:128]
        heights=48+x*.125+y*.25+7*np.exp(-((x-41)**2+(y-79)**2)/15)
        self.field=write_heightfield(source/"master.json",heights,[-63.5,-63.5],[1,1],
            {"road":x/127,"shore":y/127},geometry=geometry.name,geometry_sha256=sha256(geometry))
        self.before={p.name:p.read_bytes() for p in source.iterdir()}
        self.output=self.root/"runtime"/"runtime-master.json"

    def test_exact_landscape_grid_transform_and_immutable_source(self):
        report=derive(self.field.path,self.output,components=1)
        field=load_heightfield(self.output)
        self.assertEqual(field.dimensions,(64,64))
        self.assertEqual(field.bounds_m,self.field.bounds_m)
        self.assertEqual(field.metadata["surface_interpolation"],"triangle_nw_se")
        original=heightfield_geometry(self.field,1)
        actual=heightfield_geometry(field,1)
        before,centre,scale,_=encode_master_heights(original["heights_cm"])
        after,new_centre,new_scale,_=encode_master_heights(actual["heights_cm"])
        np.testing.assert_array_equal(before,after)
        np.testing.assert_array_equal(original["origin"],actual["origin"])
        self.assertEqual((centre,scale,original["quad"]),(new_centre,new_scale,actual["quad"]))
        self.assertEqual(self.output.with_suffix(".r16").read_bytes(),before.tobytes())
        self.assertTrue(report["landscape_r16_bit_identical"])
        self.assertEqual(self.before,{p.name:p.read_bytes() for p in self.field.path.parent.iterdir()})
        self.assertEqual(sha256(self.output.parent/field.metadata["geometry"]),self.field.metadata["geometry_sha256"])

    def test_masks_resample_bilinearly_but_ground_uses_actual_triangles(self):
        derive(self.field.path,self.output,components=1)
        field=load_heightfield(self.output)
        lo,hi=field.bounds_m;xx=np.linspace(lo[0],hi[0],64)[None,:];yy=np.linspace(lo[1],hi[1],64)[:,None]
        for name in self.field.masks:
            np.testing.assert_allclose(field.masks[name],self.field.sample_mask(name,xx,yy),atol=3e-8)
        a,b,c,d=(field.heights_m[39,20],field.heights_m[39,21],field.heights_m[40,20],field.heights_m[40,21])
        px=lo[0]+20.25*field.spacing_m[0];py=lo[1]+39.25*field.spacing_m[1]
        expected=a+.25*(b-a)+.25*(c-a)
        self.assertAlmostEqual(float(field.sample(px,py)),expected,places=10)
        self.assertNotAlmostEqual(expected,.5625*a+.1875*b+.1875*c+.0625*d,places=5)

    def test_source_replacement_and_stale_geometry_are_refused(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            derive(self.field.path,self.field.path,components=1)
        geometry=self.field.path.parent/"terrain.geometry.json"
        geometry.write_text(geometry.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"geometry hash"):
            derive(self.field.path,self.output,components=1)
        self.assertFalse(self.output.exists())

    def test_identical_noninteger_grid_copies_hard_masks_exactly(self):
        y,x=np.mgrid[:64,:64]
        binary=(x>25)&(y<41)
        source=write_heightfield(self.field.path.parent/"binary.json",np.full((64,64),48),[-1000,-1000],[2000/63]*2,
            {"protected":binary},geometry="terrain.geometry.json",geometry_sha256=sha256(self.field.path.parent/"terrain.geometry.json"))
        derive(source.path,self.output,components=1)
        actual=load_heightfield(self.output)
        np.testing.assert_array_equal(actual.masks["protected"],binary)
        self.assertTrue(np.isin(actual.masks["protected"],[0,1]).all())


if __name__=="__main__":unittest.main()
