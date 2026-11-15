import unittest
import numpy as np
from audit_flux_state import sample


class FluxTextureCoordinatesTest(unittest.TestCase):
    def test_texel_centres_and_reflected_y(self):
        state={"centre":[0,0,1000],"res":[2,2],"cell":100}
        values=np.array([[11,12],[21,22]],dtype=float)
        result,valid=sample(values,state,[[-.5,.5],[.5,.5],[-.5,-.5],[.5,-.5],[0,0]])
        np.testing.assert_allclose(result,[11,12,21,22,16.5])
        self.assertTrue(valid.all())
        _,valid=sample(values,state,[[1,0],[0,1]])
        self.assertFalse(valid.any())


if __name__=="__main__":unittest.main()
