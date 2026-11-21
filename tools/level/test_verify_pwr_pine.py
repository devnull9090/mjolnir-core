import unittest
import numpy as np
from verify_pwr_pine import compare_triangles


class PineParityTests(unittest.TestCase):
    def primitive(self):
        return {'name':'Bark','attrs':{
          'POSITION':np.array([[[0.,0,0],[1.,0,0],[0,1.,0]]]),
          'NORMAL':np.tile([[[0.,0,1.]]],(1,3,1)),
          'TEXCOORD_0':np.array([[[0.,0],[1.,0],[0,1.]]]),
          'TEXCOORD_1':np.array([[[.2,.4],[.3,.5],[.1,.6]]]),
          'TEXCOORD_2':np.array([[[.8,.2],[.3,.7],[.9,.1]]]),
          'COLOR_0':np.array([[[254,255,1,53],[4,8,12,16],[255,0,63,128]]],dtype=np.uint8)}}

    def test_reordered_triangle_corners_pass(self):
        a=self.primitive();b=self.primitive()
        for k in b['attrs']:b['attrs'][k]=np.roll(b['attrs'][k],1,axis=1)
        self.assertEqual(compare_triangles(a,b)['max_absolute_errors']['COLOR_0'],0)

    def test_bgra_swap_rejected(self):
        a=self.primitive();b=self.primitive();b['attrs']['COLOR_0']=b['attrs']['COLOR_0'][...,[2,1,0,3]]
        with self.assertRaises(ValueError):compare_triangles(a,b)

    def test_uv2_mutation_rejected(self):
        a=self.primitive();b=self.primitive();b['attrs']['TEXCOORD_2'][0,0,0]+=.01
        with self.assertRaises(ValueError):compare_triangles(a,b)

    def test_reverse_winding_rejected(self):
        a=self.primitive();b=self.primitive()
        for k in b['attrs']:b['attrs'][k]=b['attrs'][k][:,::-1]
        with self.assertRaises(ValueError):compare_triangles(a,b)

    def test_duplicate_replacement_rejected(self):
        a=self.primitive()
        for k,v in a['attrs'].items():a['attrs'][k]=np.concatenate([v,v.copy()])
        a['attrs']['POSITION'][1,:,2]=1
        b={'name':a['name'],'attrs':{k:np.repeat(v[:1],2,axis=0) for k,v in a['attrs'].items()}}
        with self.assertRaises(ValueError):compare_triangles(a,b)


if __name__=='__main__':unittest.main()
