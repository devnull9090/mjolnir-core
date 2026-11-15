import unittest
import numpy as np
import build_apron_v7 as a


class ConformingRefinementTest(unittest.TestCase):
    def test_curved_patch_splits_shared_edge_without_crack(self):
        sample=lambda x,y: x*x+y*y
        v=np.array([[0.,0.,0.],[1.,0.,1.],[1.,1.,2.],[0.,1.,1.]])
        t=np.array([[0,1,2],[0,2,3]])
        original=v.copy();before=a.errors(v,t,sample).max()
        v,t=a.split(v,t,[0],sample,seam_vertices=0)
        self.assertTrue(np.array_equal(v[:4],original));self.assertEqual(len(t),6)
        edges=np.sort(t[:,[[0,1],[1,2],[2,0]]].reshape(-1,2),axis=1)
        edges,count=np.unique(edges,axis=0,return_counts=True)
        self.assertTrue(np.all(count<=2))
        for edge in edges[count==1]:
            p=v[edge,:2]
            self.assertTrue(any(np.all(p[:,k]==bound) for k in (0,1) for bound in (0,1)))
        self.assertLess(a.errors(v,t,sample).max(),before)

    def test_locked_seam_edges_never_gain_a_midpoint(self):
        sample=lambda x,y: x*x+y*y
        v=np.array([[0.,0.,0.],[1.,0.,1.],[0.,1.,1.]])
        refined,t=a.split(v,np.array([[0,1,2]]),[0],sample,seam_vertices=2)
        self.assertTrue(np.array_equal(refined[:2],v[:2]))
        self.assertFalse(np.any(np.all(refined[:,:2]==[.5,0],axis=1)))
        self.assertEqual(len(t),3)


if __name__=='__main__':unittest.main()
