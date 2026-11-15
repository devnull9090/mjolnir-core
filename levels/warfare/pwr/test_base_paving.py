# /// script
# dependencies = ["numpy", "shapely>=2.1,<3"]
# ///
"""Run with `uv run levels/warfare/pwr/test_base_paving.py`."""
from pathlib import Path
import unittest
import numpy as np
from shapely.geometry import Polygon, box
import base_paving
from heightfield import Heightfield


class TerrainPavingTests(unittest.TestCase):
    def field(self):
        # A deliberately folded quad: bilinear or unsplit corner draping
        # would float/cut through its diagonal by metres, rather than 1.5cm.
        return Heightfield(np.array([[0.,8.],[4.,2.]]),(0.,0.),(2.,2.),{},
                           {'surface_interpolation':'triangle_nw_se'},'fixture',Path('fixture'))

    def test_clipped_hollow_motif_matches_whole_terrain_faces(self):
        shape=box(.1,.1,1.9,1.9).difference(box(.7,.6,1.2,1.4))
        field=self.field();v,t,error=base_paving.drape(shape,field)
        self.assertLess(error,1e-10)
        for weights in ([.2,.3,.5],[.7,.1,.2],[.05,.9,.05]):
            points=np.einsum('tvc,v->tc',v[t],weights)
            np.testing.assert_allclose(points[:,2]-field.sample(points[:,0],points[:,1]),.015,atol=1e-10)
        self.assertTrue(np.all(np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]])[:,2]>0))
        area=sum(Polygon(v[face,:2]).area for face in t)
        self.assertAlmostEqual(area,shape.area,places=10)

    def test_projection_rejects_raised_or_wrong_surface(self):
        field=self.field()
        for lift in (0,.020001,-.01):
            with self.assertRaises(ValueError):base_paving.drape(box(.1,.1,.4,.4),field,lift)
        field.metadata['surface_interpolation']='bilinear'
        with self.assertRaisesRegex(ValueError,'topology'):
            base_paving.drape(box(.1,.1,.4,.4),field)


if __name__=='__main__':unittest.main()
