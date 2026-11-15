"""Collision occupancy regressions for mirrored/anisotropic native transforms."""
import unittest
from types import SimpleNamespace
import numpy as np
from finish_outcrops_v3 import inside_at_height,filtered_tree_metadata
from outcrops_v3 import World
import pcg_tree_decor

class OccupancyTest(unittest.TestCase):
    def world(self):
        points=np.array([[x,y,z] for x in (-1.,1.) for y in (-1.,1.) for z in (-1.,1.)])
        world=SimpleNamespace(models={'test':{'mesh':'test','points':points}})
        world.transform=lambda model,row:World.transform(world,model,row)
        return world

    def test_native_y_mirror_and_rotation(self):
        world=self.world();row={'mesh':'test','pos':[1000,2000,3000],'rot':[0,90,0],'scale':[3,1,2]}
        queries=np.array([[10,-20,30],[10,-22.9,30],[12,-20,30],[10,-20,32.5]])
        self.assertEqual(inside_at_height(world,[row],queries,0).tolist(),[True,True,False,False])

    def test_trunk_above_rock_is_not_crown_overlap(self):
        world=self.world();row={'mesh':'test','pos':[0,0,0],'rot':[17,-43,11],'scale':[2,1,3]}
        queries=np.array([[0,0,0],[0,0,12],[5,5,0]])
        self.assertEqual(inside_at_height(world,[row],queries,.1).tolist(),[True,False,False])

    def test_filter_updates_adapter_counts_without_new_pcg_claim(self):
        row={'id':1,'kind':'tree','mesh':None,'recipe':'Pine_Optimized','position':[1,2,3],
             'position_cm':[100,-200,300],'scale':1.,'scale_xyz':[1,1,1],'yaw_degrees':45.}
        source={'schema':1,'generator':'Actual UE PCG','graph':'actual_graph','source_sha256':'a'*64,
                'pcg_output_sha256':'b'*64,'input_count':10,'selected_count':2,'instances':[row,dict(row,id=2)]}
        result=dict(source,instances=[row])
        with self.assertRaisesRegex(ValueError,'selection counts'):pcg_tree_decor.convert(result,{})
        filtered_tree_metadata(source,result)
        converted=pcg_tree_decor.convert(result,{},max_trees=4600)
        self.assertEqual(result['selected_count'],1)
        self.assertEqual(result['selected_by_recipe'],{'Pine_Optimized':1})
        self.assertFalse(result['structural_exclusion']['new_pcg_run'])
        self.assertEqual(result['source_sha256'],source['source_sha256'])
        self.assertEqual(len(converted['background_trees']),1)

if __name__=='__main__':unittest.main()
