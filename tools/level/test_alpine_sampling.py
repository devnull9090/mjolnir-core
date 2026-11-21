import unittest
import ast
from pathlib import Path
import numpy as np
from alpine_sampling import turn, stochastic, bilinear


class StochasticSamplingTests(unittest.TestCase):
    def test_rotated_normal_is_in_original_frame(self):
        gradient=np.array([[.2,.7]]*4);rotations=np.arange(4)
        np.testing.assert_allclose(turn(turn(gradient,rotations),(4-rotations)%4),gradient)

    def test_triangle_and_square_boundaries_are_continuous(self):
        image=np.random.default_rng(8).random((32,32,3))
        for point,direction in [([.3,.7],[1,1]),([1,.37],[1,0]),([.37,1],[0,1]),([1,1],[1,1])]:
            uv=np.array(point)+np.array(direction)*np.array([[-1e-8],[1e-8]])
            actual=stochastic(image,uv)
            self.assertLess(np.max(np.abs(actual[0]-actual[1])),1e-5)

    def test_removes_source_period_not_only_colour_tuning(self):
        image=np.random.default_rng(5).random((32,32,3))
        points=np.random.default_rng(6).uniform(-10,10,(400,2))
        periodic=np.mean(abs(bilinear(image,points)-bilinear(image,points+[1,0])))
        randomized=np.mean(abs(stochastic(image,points)-stochastic(image,points+[1,0])))
        self.assertLess(periodic,1e-12)
        self.assertGreater(randomized,.1)

    def test_constant_map_stays_constant(self):
        points=np.random.default_rng(9).uniform(-100,100,(100,2))
        np.testing.assert_allclose(stochastic(np.ones((2,2,3))*.42,points),.42)

    def test_biased_far_normal_does_not_become_rotated_tile_lighting(self):
        points=np.random.default_rng(9).uniform(-100,100,(100,2))
        image=np.empty((4,4,3));image[:]=[.52468385,.49312938,0]
        np.testing.assert_allclose(stochastic(image,points,normal=True)[...,:2],0,atol=1e-14)
        image=np.random.default_rng(11).random((32,32,3))
        np.testing.assert_allclose(stochastic(image,points,normal=True,footprint=.5)[...,:2],0)
        self.assertGreater(np.std(stochastic(image,points,normal=True,footprint=.01)[...,:2]),.05)

    def test_apron_and_playable_share_sampler_and_chroma_balance(self):
        path=Path(__file__).resolve().parents[2]/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'
        tree=ast.parse(path.read_text())
        codes={target.id:ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
               for target in node.targets if isinstance(target,ast.Name) and target.id in ('LAND_PBR_CODE','ALPINE_APRON_CODE')}
        land,apron=codes['LAND_PBR_CODE'],codes['ALPINE_APRON_CODE']
        def helper(code):return code[code.index('struct LPStochastic'):code.index('\n};',code.index('struct LPStochastic'))+3]
        self.assertEqual(helper(land),helper(apron))
        for code in (land,apron):
            self.assertIn('meanLuma/max(meanGrass,1e-3),.65',code)
            self.assertIn('float3(.78,.92,.82)',code)
            self.assertIn('float3(1.02,1.08,.94)',code)
        mean=np.array([.37077046,.27321412,.17264567]);luma=mean@[.2126,.7152,.0722]
        balanced=mean*(.35+.65*luma/mean)
        self.assertAlmostEqual(float(balanced@[.2126,.7152,.0722]),luma,places=7)
        self.assertLess(balanced[0]/balanced[2],1.35)


if __name__=='__main__':unittest.main()
