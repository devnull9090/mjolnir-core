"""Complete conifers must collide at the indexed bark, never the shared crown buffer."""
import json
import contextlib
import io
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest import mock

import numpy as np
import b30_collision as collision


def write_shared_sections(path, bark_name="MI_SaplingTrunk", index_type=5123):
    # glTF Y-up metres: four square trunk rings, plus a much wider crown.
    trunk = [(x, y, z) for y in (0, 1, 2, 3) for x, z in ((-.2, -.2), (.2, -.2), (.2, .2), (-.2, .2))]
    crown = [(10 + i/100, 1.5, 10) for i in range(200)]
    positions = trunk + crown
    vertex_bytes = b"".join(struct.pack("<3f", *p) for p in positions)
    code = {5121: "B", 5123: "H", 5125: "I"}[index_type]
    bark_indices = b"".join(struct.pack("<"+code, i) for i in range(len(trunk)))
    leaf_indices = b"".join(struct.pack("<"+code, i) for i in range(len(trunk), len(positions)))
    data = vertex_bytes + bark_indices + leaf_indices
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(data)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(vertex_bytes)},
                           {"buffer": 0, "byteOffset": len(vertex_bytes), "byteLength": len(bark_indices)},
                           {"buffer": 0, "byteOffset": len(vertex_bytes)+len(bark_indices), "byteLength": len(leaf_indices)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3"},
                         {"bufferView": 1, "componentType": index_type, "count": len(trunk), "type": "SCALAR"},
                         {"bufferView": 2, "componentType": index_type, "count": len(crown), "type": "SCALAR"}],
           "materials": [{"name": bark_name}, {"name": "Needles"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0},
                                       {"attributes": {"POSITION": 0}, "indices": 2, "material": 1}]}]}
    metadata = json.dumps(doc).encode()
    metadata += b" " * (-len(metadata) % 4)
    data += b"\0" * (-len(data) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28+len(metadata)+len(data))
                     + struct.pack("<I4s", len(metadata), b"JSON") + metadata
                     + struct.pack("<I4s", len(data), b"BIN\0") + data)


class PineCollisionTests(unittest.TestCase):
    def test_indexed_bark_excludes_crown_in_shared_position_buffer(self):
        for index_type in (5121, 5123, 5125):
            with self.subTest(index_type=index_type), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"sections.glb"
                write_shared_sections(path, index_type=index_type)
                bark = collision.glb_positions(path, ["MI_SaplingTrunk"])
                self.assertEqual(len(bark), 16)
                np.testing.assert_allclose(bark.min(0), [-20, -20, 0], atol=1e-5)
                np.testing.assert_allclose(bark.max(0), [20, 20, 300], atol=1e-5)
                self.assertGreater(collision.glb_positions(path)[:, 0].max(), 1000)

    def test_missing_verified_bark_material_refuses_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"sections.glb"
            write_shared_sections(path, bark_name="Unknown")
            with self.assertRaisesRegex(ValueError, "refuse crown"):
                collision.glb_positions(path, ["MI_SaplingTrunk"])

    def test_complete_pines_are_solid_but_foliage_is_not(self):
        for mesh in (collision.PINE_OPTIMIZED, collision.PINE_SAPLING,collision.PWR_MATURE_PINE):
            self.assertEqual(collision.material_for(mesh), "tough_organic_wood")
            self.assertEqual(collision.material_for(mesh+"."+mesh.rsplit("/", 1)[-1]), "tough_organic_wood")
        self.assertIsNone(collision.material_for("/Game/Env/Tree/Pine/Needles"))

    def test_custom_complete_tree_requires_measured_trunk_cache_not_crown_export(self):
        with tempfile.TemporaryDirectory() as folder:
            leaf=collision.PWR_MATURE_PINE.rsplit('/',1)[-1]
            path=Path(folder)/(leaf+'_bark_v1.json')
            with mock.patch.object(collision.subprocess,'run') as export:
                with self.assertRaisesRegex(ValueError,'trunk-only'):
                    collision.hull_of(collision.PWR_MATURE_PINE,folder)
                record={'mesh':collision.PWR_MATURE_PINE,'points':[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
                        'faces':[[0,2,1],[0,1,3],[0,3,2],[1,2,3]]}
                path.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'trunk-only'):
                    collision.hull_of(collision.PWR_MATURE_PINE,folder)
                record.update(collision_scope='trunk_only',source_geometry_sha256='c'*64,
                              bark_material_slots=['MI_Pine_Tree_Mat'],
                              source_trunk_mesh='/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Trunk',
                              source_trunk_geometry_sha256='e'*64,source_trunk_lod=1,measured_trunk_bounds_cm=[[0,0,0],[1,1,1]])
                path.write_text(json.dumps(record))
                points,faces=collision.hull_of(collision.PWR_MATURE_PINE,folder)
                self.assertEqual(faces,record['faces'])
                self.assertEqual(points.tolist(),record['points'])
                with self.assertRaisesRegex(ValueError,'does not match'):
                    collision.hull_of(collision.PWR_MATURE_PINE,folder,expected_geometry_sha256='d'*64)
                for mutation,message in (({'points':[[0,0,0],[9,0,0],[0,1,0],[0,0,1]]},'bounds'),
                        ({'faces':record['faces'][:-1]},'faces'),
                        ({'faces':[f[::-1] for f in record['faces']]},'inward'),
                        ({'points':[[0,0,0],[1,0,0],[0,float('nan'),0],[0,0,1]]},'finite')):
                    path.write_text(json.dumps(dict(record,**mutation)))
                    with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,message):
                        collision.hull_of(collision.PWR_MATURE_PINE,folder)
                export.assert_not_called()

    def test_hulls_use_bark_only_and_distinct_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = root/"fixture.glb"
            write_shared_sections(fixture)
            leaf = collision.PINE_OPTIMIZED.rsplit("/", 1)[-1]
            # A stale whole-mesh cache must never be reused for bark.
            (root/(leaf+".json")).write_text(json.dumps({"points": [[9999, 9999, 9999]], "faces": []}))
            def export(args, **kwargs):
                shutil.copyfile(fixture, args[args.index("--out")+1])
            with mock.patch.object(collision.subprocess, "run", side_effect=export) as run:
                points, faces = collision.hull_of(collision.PINE_OPTIMIZED, folder)
                self.assertTrue(faces)
                self.assertLessEqual(abs(points[:, :2]).max(), 20.0001)
                self.assertTrue((root/(leaf+"_bark_v1.json")).exists())
                cached_points, cached_faces = collision.hull_of(collision.PINE_OPTIMIZED, folder)
                self.assertEqual(run.call_count, 1)
                np.testing.assert_allclose(points, cached_points, atol=.005)
                self.assertEqual(faces, cached_faces)

    def test_swapped_complete_pine_reaches_blam_at_render_transform(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = root/"fixture.glb"
            write_shared_sections(fixture)
            (root/"level.json").write_text("{}")
            (root/"swap.json").write_text(json.dumps({"decor": [{"id": "pcg_tree_7_part_0",
                "mesh": collision.PINE_OPTIMIZED, "pos": [1000, 2000, 3000],
                "rot": [0, 90, 0], "scale": [2, 2, 2]}]}))
            def export(args, **kwargs):
                shutil.copyfile(fixture, args[args.index("--out")+1])
            argv = ["b30_collision.py", str(root/"level.json"), str(root/"unused.bin"),
                    str(root/"swap.json"), str(root/"collision.json"), "--hulls", folder, "--only", "swap"]
            with mock.patch.object(collision.sys, "argv", argv), \
                    mock.patch.object(collision.subprocess, "run", side_effect=export), \
                    contextlib.redirect_stdout(io.StringIO()):
                collision.main()
            result = json.loads((root/"collision.json").read_text())
            self.assertTrue(result["triangles"])
            self.assertEqual(set(result["materials"]), {"tough_organic_wood"})
            points = np.array(result["triangles"]).reshape(-1, 3)
            np.testing.assert_allclose(points.min(0), np.array([960, -2040, 3000])/collision.WU, atol=.0001)
            np.testing.assert_allclose(points.max(0), np.array([1040, -1960, 3600])/collision.WU, atol=.0001)


if __name__ == "__main__":
    unittest.main()
