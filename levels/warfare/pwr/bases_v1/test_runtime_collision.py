"""Meaningful geometry and publication-contract regressions; no game calls."""
from pathlib import Path
import json,struct,tempfile,unittest
from unittest.mock import patch
import numpy as np
import runtime_collision as rc

class GeometryTests(unittest.TestCase):
    def cube(self,lo=(0,0,0),hi=(1,1,1)):
        v,f=rc.box_triangles(lo,hi)
        return {'name':'unit cube','vertices_m':v.tolist(),'triangles':f.tolist()}

    def test_blue_reflection_repairs_only_inward_winding(self):
        row=self.cube();v=np.asarray(row['vertices_m']);v[:,0]*=-1;row['vertices_m']=v.tolist()
        p,proof=rc.normalize_mesh(row)
        self.assertEqual(proof['inward_components_repaired'],1)
        self.assertEqual(proof['closed_components'],1)
        p2,again=rc.normalize_mesh({'name':'already corrected','vertices_m':p.reshape(-1,3).tolist(),
                                  'triangles':np.arange(p.size//3).reshape(-1,3).tolist()})
        self.assertEqual(again['inward_components_repaired'],0)

    def test_open_structural_module_is_rejected(self):
        row=self.cube();row['triangles'].pop()
        with self.assertRaisesRegex(ValueError,'not closed'):rc.normalize_mesh(row)

    def test_small_triangle_inside_vehicle_box_is_detected(self):
        tri=np.array([[[.2,.2,.5],[.8,.2,.5],[.5,.8,.5]]])
        self.assertEqual(rc.triangles_intersect_box(tri,[0,0,0],[1,1,1]).tolist(),[0])
        self.assertEqual(rc.triangles_intersect_box(tri,[2,2,2],[3,3,3]).tolist(),[])

    def test_enclosing_whole_base_hull_fails_parity_supplement(self):
        row=self.cube((-10,-10,-10),(10,10,10));p,_=rc.normalize_mesh(row)
        self.assertEqual(rc.triangles_intersect_box(p,[-1,-1,-1],[1,1,1]).tolist(),[])
        self.assertTrue(rc.contains_point(p,[0,0,0]))
        self.assertFalse(rc.contains_point(p,[12,0,0]))

    def test_floor_sampler_ignores_roof_and_keeps_floor_seams(self):
        row=self.cube((-1,-1,0),(1,1,.2));p,_=rc.normalize_mesh(row)
        roof,_=rc.normalize_mesh(self.cube((-1,-1,4),(1,1,4.2)))
        self.assertAlmostEqual(rc.floor_height(np.concatenate([p,roof]),0,0,1),.2)
        self.assertIsNone(rc.floor_height(p,2,0,1))

    def test_detail_omission_keeps_doors_roofs_and_driveable_ramps(self):
        for name,role in [('facade/gateway/monolithic armor-0','facade'),('ramp/driveable roof access','ramp'),
                          ('roof/large staggered armor plate','roof'),('gallery/cover plinth','gallery')]:
            self.assertIsNone(rc.omission_reason({'name':name,'module_role':role}))
        self.assertIsNotNone(rc.omission_reason({'name':'02_BLUE/facade/trim/gallery continuous glyphs','module_role':'facade'}))
        self.assertIsNotNone(rc.omission_reason({'name':'ramp/segmented traction plate','module_role':'ramp'}))

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.patchers=[patch.object(rc,'TERRAIN',2),patch.object(rc,'BRIDGES',1),patch.object(rc,'REMOVED',6)]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
        p=np.array([[[0,0,0],[1,0,0],[0,1,0]]],dtype=float)
        self.points=np.concatenate([p,p+2,p+4,p+6])
        self.extra=self.root/'extra.json';rc.write(self.extra,{'triangles':self.points.tolist(),'materials':['stone']*4})
        self.contract=self.root/'contract.json';base=self.root/'source.bin';base.write_bytes(b'fixed')
        audit=self.root/'audit.json';rc.write(audit,{'passed':True})
        ref=lambda path:{'path':str(path),'sha256':rc.sha(path)}
        self.c={'schema':rc.SCHEMA,**{k:ref(base) for k in ('source','source_blend','placement_plan','handoff','baseline_extra','ordered')},
           'output_extra':ref(self.extra),'audit':ref(audit),
           'counts':{'terrain':2,'bridges':1,'removed_legacy_base':6,'new_base':1,'trailing_architecture':2,'total_extra':4,'baseline_global':10,'expected_global':5},
           'preserved_terrain':{'triangle_f64_le_sha256':rc.triangle_hash(self.points[:2]),'materials_sha256':rc.canonical(['stone']*2)},
           'preserved_bridges':[{'id':'bridge','new_first_extra_surface':2,'surface_count':1,'triangle_f64_le_sha256':rc.triangle_hash(self.points[2:3])}],
           'replacement_objects':[{'name':'new base','first_extra_surface':3,'surfaces':1,'triangle_f64_le_sha256':rc.triangle_hash(self.points[3:])}]}
        self.save()

    def save(self):
        rc.write(self.contract,self.c)
        self.receipt={'architecture_contract_sha256':rc.sha(self.contract),'file':str(self.extra),'sha256':rc.sha(self.extra),
                      'triangles':2,'trailing_architecture_surfaces':2,'total_extra_surfaces':4}

    def test_exact_replacement_passes(self):rc.verify_contract(self.contract,self.receipt)

    def test_changed_bridge_rejects_even_with_new_output_hash(self):
        extra=rc.read(self.extra);extra['triangles'][2][0][2]+=.1;rc.write(self.extra,extra)
        self.c['output_extra']['sha256']=rc.sha(self.extra);self.save()
        with self.assertRaisesRegex(ValueError,'Protected bridge changed'):rc.verify_contract(self.contract,self.receipt)

    def test_duplicate_or_unaccounted_tail_rejected(self):
        self.c['replacement_objects'][0]['first_extra_surface']=2;self.save()
        with self.assertRaisesRegex(ValueError,'overlap/gap'):rc.verify_contract(self.contract,self.receipt)

    def test_stale_architecture_contract_rejected(self):
        self.c['counts']['expected_global']+=1;rc.write(self.contract,self.c)
        with self.assertRaisesRegex(ValueError,'different architecture contract'):rc.verify_contract(self.contract,self.receipt)

    def compiled_fixture(self, tamper_triangle=False, missing_piece=False):
        plan=self.root/'plan.json';rc.write(plan,{})
        self.c['placement_plan']={'path':str(plan),'sha256':rc.sha(plan)}
        self.c['replacement_objects'][0].update(team='red',module_role='floor')
        self.save();rc.write(self.extra.with_suffix('.receipt.json'),self.receipt)
        points=np.concatenate([self.points[:1],self.points]).astype('<f4')
        if tamper_triangle:points[-1,0,2]+=.125
        surfaces=np.zeros((5,3),dtype='<i4');surfaces[:,1]=np.arange(5)*3
        edges=np.zeros((15,6),dtype='<i4')
        edges[:,0]=np.arange(15);edges[:,1]=np.arange(15)//3*3+(np.arange(15)+1)%3
        edges[:,2]=edges[:,1]
        vertices=np.zeros(15,dtype=np.dtype([('xyz','<f4',3),('edge','<i4')]))
        vertices['xyz']=points.reshape(-1,3)
        arrays=[(0,b'')]*5+[(5,surfaces.tobytes()),(15,edges.tobytes()),(15,vertices.tobytes())]
        source=self.root/'collision_scene.json';rc.write(source,{})
        source.with_suffix('.bin').write_bytes(b''.join(struct.pack('<I',n)+data for n,data in arrays))
        output=self.root/'pwr.sbsp';output.write_bytes(b'compiled tag fixture')
        receipt=self.root/'native-collision-receipt.json'
        rc.write(receipt,{'schema':'mjolnir-collision-pieces-v1','tail_linked_in_host':False,
            'source_surfaces':5,'source_tail_range':[1,5],
            'source_manifest':str(source),'source_manifest_sha256':rc.sha(source),
            'source_binary_sha256':rc.sha(source.with_suffix('.bin')),
            'output':str(output),'output_sha256':rc.sha(output),
            'pieces':[{'instance':1,'source_surface_range':[1,4 if missing_piece else 5]}]})
        return receipt

    def test_compiled_triangle_readback_and_piece_coverage(self):
        receipt=self.compiled_fixture()
        with patch.object(rc,'audit_architecture',return_value={'passed':True}):
            proof=rc.verify_compiled(self.contract,receipt,self.root/'proof.json')
        self.assertEqual(proof['verified_extra_triangles'],4)
        self.assertTrue(proof['compiled_boundaries_verified'])
        self.assertEqual(proof['extra_collision_instances'],[1])

    def test_rehashed_native_triangle_mutation_rejects(self):
        receipt=self.compiled_fixture(tamper_triangle=True)
        with self.assertRaisesRegex(ValueError,'preserve every prepared'):
            rc.verify_compiled(self.contract,receipt,self.root/'proof.json')

    def test_missing_compiled_base_piece_rejects(self):
        receipt=self.compiled_fixture(missing_piece=True)
        with self.assertRaisesRegex(ValueError,'do not cover'):
            rc.verify_compiled(self.contract,receipt,self.root/'proof.json')

if __name__=='__main__':unittest.main()
