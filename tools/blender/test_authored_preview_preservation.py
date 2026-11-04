"""Headless regression for TST's authored-face preview preservation guard.

blender --background --factory-startup --python-exit-code 1 --python \
    tools/blender/test_authored_preview_preservation.py
"""
from pathlib import Path
import runpy
import unittest

import bpy

REPO=Path(__file__).resolve().parents[2]
RENDERER=runpy.run_path(str(REPO/'levels/test/tst/render_preview.py'))
snapshot_surfaces=RENDERER['snapshot_authored_surfaces']
assert_surfaces=RENDERER['assert_authored_surfaces']


class AuthoredPreviewPreservation(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene=bpy.context.scene
        self.owned=bpy.data.materials.new('owned finish')
        self.owned['tst_surface_role']='facility_structure'
        self.owned['source_shader_tag']='levels/test/tst/shaders/tst_structure'
        self.stock=bpy.data.materials.new('stock approximation')
        self.part=self.make_quad('authored part',self.owned)
        self.part.data.materials.append(self.stock)
        self.stock_part=self.make_quad('stock part',self.stock)
        self.before=snapshot_surfaces(self.scene)

    def make_quad(self,name,material):
        mesh=bpy.data.meshes.new(name)
        mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[],[(0,1,2,3)])
        mesh.materials.append(material)
        uv=mesh.uv_layers.new(name='UVMap')
        for index,coord in enumerate(((0,0),(1,0),(1,1),(0,1))):
            uv.data[index].uv=coord
        obj=bpy.data.objects.new(name,mesh)
        self.scene.collection.objects.link(obj)
        return obj

    def expect_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Preview changed authored surfaces'):
            assert_surfaces(self.scene,self.before)

    def test_unchanged_authored_faces_pass(self):
        result=assert_surfaces(self.scene,self.before)
        self.assertTrue(result['passed'])
        self.assertEqual(result['checked_faces'],1)
        self.assertEqual(result['changed_faces'],0)

    def test_stock_material_and_uv_styling_is_allowed(self):
        self.stock.diffuse_color=(.1,.5,.9,1)
        self.stock['source_shader_tag']='preview/stock/approximation'
        self.stock_part.data.uv_layers['UVMap'].data[0].uv=(.3,.7)
        self.assertTrue(assert_surfaces(self.scene,self.before)['passed'])

    def test_authored_role_change_is_rejected(self):
        self.owned['tst_surface_role']='armor'
        self.expect_rejected()

    def test_authored_shader_path_change_is_rejected(self):
        self.owned['source_shader_tag']='preview/wrong/shader'
        self.expect_rejected()

    def test_exported_uv_change_is_rejected(self):
        self.part.data.uv_layers['UVMap'].data[0].uv.x=.125
        self.expect_rejected()

    def test_authored_face_replaced_with_stock_is_rejected(self):
        # The actual regression: a later fallback loop remapped the polygon
        # despite the initial authored-material slot guard.
        self.part.data.polygons[0].material_index=1
        self.expect_rejected()


if __name__=='__main__':
    unittest.main(argv=[__file__])
