import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import scenery_v6 as candidate


class FrozenSelectionTests(unittest.TestCase):
    def document(self, ids):
        return {'instances':[{'id':i,'position':[i+.125,-i,107.123456789],
                              'recipe':'PWR_MaturePine_A','scale':.987654321} for i in ids],
                'selected_count':len(ids),'input_count':len(ids)+3,'graph':'fixture graph',
                'source_sha256':'a'*64,'pcg_output_sha256':'b'*64}

    def test_union_preserves_every_existing_value_and_describes_new_outputs(self):
        old=self.document([4,7]);before=copy.deepcopy(old)
        provenance={'input_receipt_sha256':'c'*64,'output_receipt_sha256':'d'*64}
        with patch.object(candidate,'sha256',return_value='e'*64):
            result=candidate.merge_tree_selection(old,[self.document([100]),self.document([200])],provenance)
        self.assertEqual(old,before)
        self.assertEqual(result['instances'][:2],before['instances'])
        self.assertEqual(result['selected_count'],4)
        self.assertEqual(result['composition']['base_count'],2)
        self.assertEqual(result['composition']['new_count'],2)
        self.assertEqual(result['selected_by_recipe'],{'PWR_MaturePine_A':4})

    def test_duplicate_id_cannot_overwrite_existing_physics(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            candidate.merge_tree_selection(self.document([4]),[self.document([4])],{})


class CandidateGeometryTests(unittest.TestCase):
    def test_density_target_preserves_taper_and_rejects_impossible_budget(self):
        weights=np.array([0.,.01,.1,.5,1.])
        actual=candidate.density_for_target(weights,2.)
        self.assertAlmostEqual(actual.sum(),2.,places=8)
        self.assertEqual(actual[0],0.)
        self.assertTrue(np.all(actual[1:]>=actual[:-1]))
        self.assertLess(actual[1],actual[-1]*.1)
        with self.assertRaises(ValueError):candidate.density_for_target(weights,5)

    def test_small_native_pose_finite_triangles_and_collapse_gate(self):
        points=np.array([[0,0,0],[100,0,0],[0,100,0],[0,0,100]],float)
        faces=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
        row={'id':'test','pos':[70000.,-50000.,10700.],'rot':[0,30,0],'scale':[.35]*3}
        result=candidate.finite_pose_check(points,faces,row)
        self.assertEqual(result['faces'],4)
        self.assertLess(result['maximum_corresponding_vertex_shift_m'],.001)
        row['scale']=[1e-10]*3
        with self.assertRaisesRegex(ValueError,'collapses'):
            candidate.finite_pose_check(points,faces,row)


if __name__=='__main__':unittest.main()
