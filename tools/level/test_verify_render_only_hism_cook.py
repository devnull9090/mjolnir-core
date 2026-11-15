import copy
import math
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np
import verify_render_only_hism_cook as v


class CookedExteriorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.bin=root/'foliage.bin'
        # Nonuniform scale and rotation make transposition/order errors observable.
        values=(120001.25,-150000.5,35555.25,0,0,math.sin(.37),math.cos(.37),1.25,.8,1.1)
        Path(str(self.bin)+'.xf1').write_bytes(struct.pack('<10f',*values))
        self.doc={'instances':[{'mesh':'/Game/Cliff.Cliff'}],'cull_cm':[400000,550000]}
        self.spec={'bin':str(self.bin),'groups':[{'mesh':'/Game/Cliff.Cliff'},{'mesh':'/Game/Pine.Pine'}],
            'render_only_hism':{'sha256':'a'*64,'instances':1,'groups':[{'group':1,'count':1}]},
            'pine_hism':{'instances':3,'groups':[{'group':2,'count':3}]}}
        self.mic='/Game/MJOLNIR/Landscape/LPW/MI_PWR_ExteriorCliffs_'+('a'*12)
        self.cliff={'export':0,'name':'MJFol_1_1_0','class':'HierarchicalInstancedStaticMeshComponent',
            'properties':{'bEvaluateWorldPositionOffset':'false','bCanEverAffectNavigation':'false',
                'BodyInstance.CollisionEnabled':'0 (zeroed)','BodyInstance.CollisionProfileName':'NoCollision',
                'InstanceStartCullDistance':'400000','InstanceEndCullDistance':'550000','NumBuiltInstances':'1',
                'AttachParent':'export 2','RelativeLocation':'0 (zeroed)'},
            'references':{'StaticMesh':{'package':'/Game/Cliff'},'OverrideMaterials[0]':{'package':self.mic}},
            'matrices':v.matrices(str(self.bin)+'.xf1').tolist()}
        self.pine={'export':1,'name':'MJFol_2_1_0','class':'HierarchicalInstancedStaticMeshComponent',
            'properties':{'NumBuiltInstances':'3'},'references':{'StaticMesh':{'package':'/Game/Pine'}}}
        self.parent={'export':2,'name':'Root','class':'SceneComponent','properties':{'RelativeRotation':'0 (zeroed)'}}
        self.data={'exports':[self.cliff,self.pine,self.parent]}

    def test_native_matrices_and_owners(self):
        result=v.verify_components(self.data,self.spec,self.doc)
        self.assertEqual((result['exterior_instances'],result['pine_instances']),(1,3))
        self.assertEqual(result['maximum_position_error_cm'],0)
        matrix=np.asarray(self.cliff['matrices'][0]);qz=math.sin(.37);qw=math.cos(.37)
        self.assertAlmostEqual(matrix[0,1],2*qz*qw*1.25,places=6)
        self.assertAlmostEqual(matrix[1,0],-2*qz*qw*.8,places=6)

    def test_transform_and_component_parent_drift_rejected(self):
        self.cliff['matrices'][0][3][0]+=.02
        with self.assertRaisesRegex(ValueError,'transform drift'):v.verify_components(self.data,self.spec,self.doc)
        self.cliff['matrices'][0][3][0]-=.02
        self.parent['properties']['RelativeScale3D']='1,1,2'
        with self.assertRaisesRegex(ValueError,'Nonidentity'):v.verify_components(self.data,self.spec,self.doc)

    def test_instance_reordering_supported_but_scale_drift_rejected(self):
        one=np.asarray(self.cliff['matrices'][0]);two=one.copy();two[3,0]+=100
        self.assertEqual(v.compare_matrices([two.tolist(),one.tolist()],np.array([one,two])),(0,0))
        expected=np.array([one,two])
        two[0,0]+=.001
        with self.assertRaisesRegex(ValueError,'transform drift'):v.compare_matrices([one,two],expected)

    def test_collision_navigation_wpo_fail_closed(self):
        for key,value in [('BodyInstance.CollisionEnabled','1'),('bCanEverAffectNavigation','true'),('bEvaluateWorldPositionOffset',None)]:
            bad=copy.deepcopy(self.data)
            if value is None:bad['exports'][0]['properties'].pop(key)
            else:bad['exports'][0]['properties'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.verify_components(bad,self.spec,self.doc)

    def test_duplicate_pine_or_exterior_actor_rejected(self):
        for source in (self.pine,self.cliff):
            bad=copy.deepcopy(self.data);duplicate=copy.deepcopy(source)
            duplicate.update(name='DuplicateActor',export=4,**{'class':'StaticMeshComponent'})
            bad['exports'].append(duplicate)
            with self.subTest(source=source['name']),self.assertRaisesRegex(ValueError,'Duplicate'):v.verify_components(bad,self.spec,self.doc)

    def test_material_requires_global_native_textures(self):
        binding={'parent':'/Game/M_CE_PWRRock.M_CE_PWRRock','textures':{'RockD':'/Game/RockD.RockD'},'vectors':{'RockParams':[650,.85,.75,0]}}
        row={'class':'MaterialInstanceConstant','references':{'Parent':{'package':'/Game/M_CE_PWRRock'},
            'TextureParameterValues[0].ParameterValue':{'package':'/Game/RockD'}},'properties':{
            'TextureParameterValues[0].ParameterInfo.Name':'RockD','TextureParameterValues[0].ParameterInfo.Association':'2',
            'VectorParameterValues[0].ParameterInfo.Name':'RockParams','VectorParameterValues[0].ParameterInfo.Association':'2',
            'VectorParameterValues[0].ParameterValue':'650,0.85,0.75,0'}}
        self.assertEqual(v.verify_material({'exports':[row]},binding)['parent'],'/Game/M_CE_PWRRock')
        row['properties']['TextureParameterValues[0].ParameterInfo.Association']='0 (zeroed)'
        with self.assertRaisesRegex(ValueError,'layered'):v.verify_material({'exports':[row]},binding)

    def test_shared_stock_mesh_requires_exact_preexisting_actor(self):
        self.spec['decor']=[{'id':'original','mesh':'/Game/Cliff.Cliff','loc':[100,200,300],
                            'rot':[0,90,0],'scale':[.2,.2,.2]}]
        actor={'export':4,'name':'StaticMeshComponent0','outer':'MJDecor_original','class':'StaticMeshComponent',
               'references':{'StaticMesh':{'package':'/Game/Cliff'}},'properties':{
                   'RelativeLocation':'100,200,300','RelativeRotation':'0,90,0','RelativeScale3D':'.2,.2,.2'}}
        self.data['exports'].append(actor)
        self.assertEqual(v.verify_components(self.data,self.spec,self.doc)['preserved_shared_mesh_scenery'],1)
        actor['properties']['RelativeLocation']='100,200,301'
        with self.assertRaisesRegex(ValueError,'transform changed'):v.verify_components(self.data,self.spec,self.doc)
        actor['properties']['RelativeLocation']='100,200,300'
        self.data['exports'].append(copy.deepcopy(actor))
        with self.assertRaisesRegex(ValueError,'Duplicate'):v.verify_components(self.data,self.spec,self.doc)

    def test_exterior_pines_separate_from_original_owners(self):
        Path(str(self.bin)+'.xf3').write_bytes(Path(str(self.bin)+'.xf1').read_bytes())
        self.spec['groups'].append({'mesh':'/Game/Pine.Pine'})
        self.spec['render_only_pines']={'instances':1,'groups':[{'group':3,'count':1}],
            'expected_material_slots':{'/Game/Pine.Pine':['Bark','Needle']}}
        exterior=copy.deepcopy(self.cliff);exterior.update(name='MJFol_3_1_0',export=4)
        exterior['references']={'StaticMesh':{'package':'/Game/Pine'}}
        self.data['exports'].append(exterior);pine_doc={'cull_cm':[400000,550000]}
        result=v.verify_components(self.data,self.spec,self.doc,pine_doc=pine_doc)
        self.assertEqual((result['pine_instances'],result['exterior_pine_instances']),(3,1))
        with self.assertRaisesRegex(ValueError,'manifest'):v.verify_components(self.data,self.spec,self.doc)
        exterior['properties']['OverrideMaterials[0]']='import 1'
        with self.assertRaisesRegex(ValueError,'overridden'):v.verify_components(self.data,self.spec,self.doc,pine_doc=pine_doc)


if __name__=='__main__':unittest.main()
