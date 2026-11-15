import ast
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import alpine_geology

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bind_apron_geology',ROOT/'levels/warfare/pwr/visual_dressing/bind_apron_geology.py')
binding_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(binding_module)


class ApronGeologyTests(unittest.TestCase):
    def test_binding_uses_actual_rectangle_and_is_opt_in(self):
        source={'textures':{},'vectors':{}}
        land={'pbr':{'rect':[-100000,-100000,200000,200000],
              'base':'/Game/MJOLNIR/Landscape/LPW/T_LandBase.T_LandBase',
              'alpine':[19000,27000,1800,2],'mix':[.2,.75,0,.25]}}
        result=binding_module.binding(source,land)
        self.assertEqual(source,{'textures':{},'vectors':{}})
        self.assertEqual(result['vectors']['ApronGeologyRect'],land['pbr']['rect'])
        self.assertEqual(result['vectors']['ApronGeologyBlend'],[0,15000,.72,1])
        land['pbr']['alpine'][3]=1
        with self.assertRaises(ValueError):binding_module.binding(source,land)

    def test_authoring_corners_match_unreal_world_uv_without_gamma(self):
        # Independent asymmetric marker pattern proves both X and Y signs.
        authored=np.array([[[.1,.2,.3],[.4,.5,.6]],[[.7,.8,.9],[.2,.3,.4]]],dtype=np.float32)
        baked=alpine_geology.sample_texture(authored,2,2)
        for x,y in [(-500,500),(500,500),(-500,-500),(500,-500)]:
            ue=np.array([x*100,-y*100])
            uv=(ue-[-100000,-100000])/[200000,200000]
            ix,iy=(uv*2).astype(int)
            tx=(x+1000)/2000;ty=(y+1000)/2000
            expected=(authored[0,0]*(1-tx)+authored[0,1]*tx)*(1-ty)+(authored[1,0]*(1-tx)+authored[1,1]*tx)*ty
            np.testing.assert_array_equal(baked[iy,ix],np.round(expected*255).astype(np.uint8))

    def test_apron_graph_declares_linear_clamped_sampler_and_defaults_disabled(self):
        path=ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'
        tree=ast.parse(path.read_text())
        func=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='build_alpine_apron')
        source=ast.get_source_segment(path.read_text(),func)
        self.assertIn('parameter_name="ApronGeology"',source)
        self.assertIn('SAMPLERTYPE_LINEAR_COLOR',source)
        self.assertIn('SSM_CLAMP_WORLD_GROUP_SETTINGS',source)
        self.assertIn('"ApronGeologyBlend", (0.0, 15000.0, 0.72, 0.0)',source)
        code=next(ast.literal_eval(x.value) for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALPINE_APRON_CODE' for t in x.targets))
        self.assertLess(code.index('snow *= lerp'),code.index('snow = lerp(snow, saturate(edgeGeology.g), seamWeight)'))
        self.assertIn('(W.xy - GeologyRect.xy)',code)


if __name__=='__main__':unittest.main()
