import unittest
from surface_policy import SurfacePolicy


def document(policy="NONE", points=None):
    return {"schema_version":1,"coordinates":"blender_world_metres_z_up",
            "triangles":[{"policy":policy,"vertices":points or [[0,10,2],[4,10,2],[0,14,2]]}]}


class SurfacePolicyTests(unittest.TestCase):
    def test_world_units_y_flip_and_height_tolerance(self):
        mask=SurfacePolicy(document())
        self.assertFalse(mask.allows(100,-1100,200,"ground"))
        self.assertFalse(mask.allows(100,-1100,204,"ground"))
        self.assertTrue(mask.allows(100,-1100,210,"ground"))
        self.assertTrue(mask.allows(100,1100,200,"ground"))
        self.assertTrue(mask.allows(350,-1350,200,"ground"))  # outside triangle, inside AABB

    def test_permissions_and_overlap(self):
        mask=SurfacePolicy(document("CLIFF"))
        self.assertFalse(mask.allows(100,-1100,200,"ground"))
        self.assertTrue(mask.allows(100,-1100,200,"cliff"))
        doc=document("BOTH")
        doc["triangles"] += document("NONE")["triangles"]
        self.assertFalse(SurfacePolicy(doc).allows(100,-1100,200,"cliff"))

    def test_vertical_faces_and_negative_cells(self):
        mask=SurfacePolicy(document("GROUND",[[-5,-3,0],[-5,2,0],[-5,-3,5]]))
        self.assertFalse(mask.allows(-500,200,100,"cliff"))
        self.assertTrue(mask.allows(-500,200,100,"ground"))

    def test_invalid_input_is_not_silently_ignored(self):
        with self.assertRaises(ValueError): SurfacePolicy(document("TYPO"))
        with self.assertRaises(ValueError): SurfacePolicy(document(points=[[0,0,float("nan")],[1,0,0],[0,1,0]]))


if __name__=="__main__": unittest.main()
