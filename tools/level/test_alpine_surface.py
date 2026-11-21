import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import alpine_surface
import upgrade_ce_map


class RoadSurfaceTests(unittest.TestCase):
    def road(self, points):
        return {'centreline_m':[[x,y,0] for x,y in points]}

    def test_exact_distance_orientation_and_junction_fade(self):
        graph={'roads':[self.road([(-100,0),(0,0),(100,0)]),self.road([(0,0),(0,100)])]}
        value=alpine_surface.road_field(graph,np.array([[40,3],[40,-5],[0,0],[0,4],[8,0],[20,0]]))
        np.testing.assert_allclose(value[:2,:2],[[1,0],[1,0]])
        np.testing.assert_allclose(value[:2,2],[3,-5])
        np.testing.assert_allclose(value[2:5,3],0)
        self.assertEqual(value[5,3],1)

    def test_distance_continuity_at_curve_segment_joint(self):
        graph={'roads':[self.road([(-50,-10),(0,0),(50,10)])]}
        value=alpine_surface.road_field(graph,np.array([[-.0001,5],[.0001,5]]))
        self.assertLess(abs(value[0,2]-value[1,2]),.0001)
        np.testing.assert_allclose(value[0,:2],value[1,:2])

    def test_base_bytes_unchanged_and_y_axis_correct(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            base=np.arange(64,dtype=np.uint8).reshape(4,4,4)
            Image.fromarray(base).save(root/'base.png')
            before=(root/'base.png').read_bytes()
            geometry=root/'geometry.json'
            geometry.write_text(json.dumps({'roads':[self.road([(-100,0),(100,0)])]}))
            doc={'textures':{'Base':'base.png'},'pbr':{'rect':[-200,-200,400,400],'base':'/Game/Test/T_LandBase.T_LandBase'}}
            receipt=alpine_surface.apply_to_bake(root,doc,geometry)
            self.assertEqual(before,(root/'base.png').read_bytes())
            self.assertEqual(receipt['base_alpha_sha256'],hashlib.sha256(base[...,3].tobytes()).hexdigest())
            image=np.asarray(Image.open(root/'surface-detail.png'))
            self.assertGreater(image[0,0,2],image[-1,0,2]) # top PNG = positive authored Y
            self.assertEqual(doc['pbr']['surface_detail']['range_cm'],1600)

    def test_invalid_graph_fails(self):
        with self.assertRaises(ValueError):alpine_surface.road_field({'roads':[]},[[0,0]])
        with self.assertRaises(ValueError):alpine_surface.road_field({'roads':[self.road([(0,0),(float('nan'),0)])]},[[0,0]])

    def test_upgrade_opt_in_and_other_map_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'master.json').write_text('{}');(root/'roads.json').write_text('{}')
            config={'shaders':['ground'],'landscape':'LPW','heightfield':'master.json','surface_detail':'roads.json'}
            with patch.object(upgrade_ce_map,'REPO',str(root)),patch.object(upgrade_ce_map,'run',return_value='') as run:
                upgrade_ce_map.stage_land('PWR',config,{'scene':'scene','land':'land'})
            argv=run.call_args.args[0]
            self.assertEqual(Path(argv[argv.index('--surface-detail')+1]),root/'roads.json')
            config['landscape']='LBG'
            with patch.object(upgrade_ce_map,'REPO',str(root)),patch.object(upgrade_ce_map,'run') as run:
                with self.assertRaisesRegex(ValueError,'LPW'):upgrade_ce_map.stage_land('PWR',config,{'scene':'scene','land':'land'})
                run.assert_not_called()


if __name__=='__main__':unittest.main()
