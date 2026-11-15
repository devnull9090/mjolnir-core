import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from export_terrain_collision import architecture_parts, export
from heightfield import write_heightfield


class ArchitecturePartsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.field=SimpleNamespace(metadata={'geometry_sha256':'g',
            'preservation':{'layout_sha256':'l','baseline_manifest_sha256':'b'}})
        self.arch={'coordinates':'ce_world_units_z_up','geometry_sha256':'g','objects':1,
            'triangles':[[[0,0,0],[1,0,0],[0,1,0]]],'materials':['hard_metal_thick']}
        self.detail={'schema':'pwr-base-details-collision-v1','coordinates':'ce_world_units_z_up',
            'provenance':{'geometry_sha256':'g','layout_sha256':'l','master_manifest_sha256':'b'},
            'objects':1,'triangles':[[[0,0,1],[1,0,1],[0,1,1]]],'materials':['hard_metal_thick']}
        self.ap=self.root/'arch.json';self.dp=self.root/'detail.json'
        self.ap.write_text(json.dumps(self.arch));self.dp.write_text(json.dumps(self.detail))

    def test_order_and_duplicate_rejection(self):
        parts=architecture_parts(self.field,self.ap,[self.dp])
        self.assertEqual([p[1]['role'] for p in parts],['frozen_architecture','base_details'])
        self.assertEqual(parts[1][0]['triangles'],self.detail['triangles'])
        with self.assertRaisesRegex(ValueError,'twice'):architecture_parts(self.field,self.ap,[self.dp,self.dp])

    def test_changed_support_contract_and_wrong_transform_rejected(self):
        for key in ('geometry_sha256','layout_sha256','master_manifest_sha256'):
            bad=copy.deepcopy(self.detail);bad['provenance'][key]='changed';self.dp.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):architecture_parts(self.field,self.ap,[self.dp])
        with self.assertRaisesRegex(ValueError,'first'):architecture_parts(self.field,None,[self.dp])

    def test_malformed_triangles_and_materials_rejected(self):
        for triangles,materials in (([[[0,0,0]]],['x']), (self.detail['triangles'],[])):
            bad=copy.deepcopy(self.detail);bad.update(triangles=triangles,materials=materials)
            self.dp.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):architecture_parts(self.field,self.ap,[self.dp])

    def test_export_receipt_keeps_terrain_order_and_complete_architecture_tail(self):
        field=write_heightfield(self.root/'runtime.json',np.zeros((2,2)),[0,0],[1,1],
            geometry_sha256='g',preservation=self.field.metadata['preservation'])
        mesh=self.root/'mesh';mesh.mkdir()
        np.savez_compressed(mesh/'collision-surface.npz',vertices_m=[[0,0,0],[1,0,0],[0,1,0],[1,1,0]],
            triangles=[[0,1,2],[1,3,2]])
        (mesh/'collision-report.json').write_text(json.dumps({'master_manifest_sha256':field.manifest_sha256,
            'accuracy_and_mesh_budget_pass':True}))
        target=self.root/'extra.json';receipt=export(field.path,mesh,target,self.ap,[self.dp])
        self.assertEqual(receipt['triangles'],2)
        self.assertEqual(receipt['trailing_architecture_surfaces'],2)
        self.assertEqual(receipt['total_extra_surfaces'],4)
        self.assertEqual([p['first_extra_surface'] for p in receipt['architecture_sources']],[2,3])
        data=json.loads(target.read_text())
        self.assertEqual(data['triangles'][-2:],[*self.arch['triangles'],*self.detail['triangles']])
        self.assertEqual(len(np.load(target.with_suffix('.ordered.npz'))['triangles']),2)


if __name__=='__main__':unittest.main()
