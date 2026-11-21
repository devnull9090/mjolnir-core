import json
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from prepare_terrain_probe import compiled_seams, seams_for_owners, patch_level, sha256, verify_master_vertices
from heightfield import write_heightfield


class ProbeTests(unittest.TestCase):
    def test_clipped_boundary_requires_proof_and_keeps_interior_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            field=write_heightfield(Path(tmp)/"master.json",np.zeros((3,3)),[0,0],[10,10],
                {"walkable":np.ones((3,3))},surface_interpolation="triangle_nw_se")
            points=np.array([[0,20,.285],[10,10,0]],dtype=float)
            with self.assertRaisesRegex(ValueError,"requires.*proof"):verify_master_vertices(points,field)
            proof={"accuracy_and_mesh_budget_pass":True,"master_manifest_sha256":field.manifest_sha256,
                "requested_errors_m":{"ground":.5,"road":.15,"shore":.25,"flat":.1,"outside_walkable_mask":2.}}
            self.assertEqual(verify_master_vertices(points,field,proof)["approximated_boundary_vertices"],1)
            points[1,2]=.002
            with self.assertRaisesRegex(ValueError,"Interior"):verify_master_vertices(points,field,proof)
            points[1,2]=0;points[0,2]=.501
            with self.assertRaisesRegex(ValueError,"region tolerance"):verify_master_vertices(points,field,proof)
            field.masks["walkable"][:]=0
            with self.assertRaisesRegex(ValueError,"region tolerance"):verify_master_vertices(points,field,proof)

    def test_actual_instance_edges_ignore_shared_edges_with_same_owner(self):
        v = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [10, 10, 0]], dtype=float)
        t = np.array([[0, 1, 2], [1, 3, 2]])
        self.assertEqual(seams_for_owners(v, t, [4, 4]), [])
        seams = seams_for_owners(v, t, [4, 9])
        self.assertEqual(len(seams), 1)
        self.assertEqual(seams[0]["instances"], [4, 9])

    def test_nonmanifold_seam_cannot_be_claimed(self):
        with self.assertRaisesRegex(ValueError, "Nonmanifold"):
            seams_for_owners(np.zeros((4, 3)), np.array([[0, 1, 2], [1, 0, 3], [0, 1, 3]]), [1, 2, 3])

    def test_complete_staged_range_verification_including_trailing_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            field = write_heightfield(p / "master.json", np.zeros((2, 2)), [0, 0], [10, 10], surface_interpolation="triangle_nw_se")
            v = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [10, 10, 0]], dtype=float)
            t = np.array([[0, 1, 2], [1, 3, 2]])
            ordered = p / "ordered.npz"; np.savez(ordered, vertices_m=v, triangles=t)
            # Prefix scenery, two terrain triangles, trailing architecture.
            all_tri = np.concatenate([np.ones((1, 3, 3)), v[t] / 3.048, np.ones((1, 3, 3)) * 2])
            arrays = [b""] * 5
            surfaces, edges, vertices = bytearray(), bytearray(), bytearray()
            for i, tri in enumerate(all_tri):
                e = i * 3
                surfaces.extend(struct.pack("<iiBbh", 0, e, 1, -1, 0))
                for j, point in enumerate(tri):
                    edges.extend(struct.pack("<iiiiii", e+j, e+(j+1)%3, e+(j+1)%3, -1, i, -1))
                    vertices.extend(struct.pack("<fffi", *point, e+j))
            arrays += [surfaces, edges, vertices]
            sizes = [12, 16, 8, 8, 20, 12, 24, 16]
            binary = b"".join(struct.pack("<I", len(a)//size) + a for a, size in zip(arrays, sizes))
            source = p / "source.json"; source.write_text("{}")
            source.with_suffix(".bin").write_bytes(binary)
            output = p / "tag.bin"; output.write_bytes(b"compiled")
            terrain = p / "terrain.json"; terrain.write_text(json.dumps({"triangles": 2, "trailing_architecture_surfaces": 1}))
            receipt = {"schema": "mjolnir-collision-pieces-v1", "tail_linked_in_host": False,
                "delta_wu": [0, 0, 0], "source_manifest": str(source), "source_manifest_sha256": sha256(source),
                "source_binary_sha256": sha256(source.with_suffix('.bin')), "output": str(output), "output_sha256": sha256(output),
                "source_tail_range": [0, 4], "source_surfaces": 4,
                "pieces": [{"source_surface_range": [0, 2], "instance": 7}, {"source_surface_range": [2, 4], "instance": 8}]}
            rp = p / "receipt.json"; rp.write_text(json.dumps(receipt))
            seams, provenance = compiled_seams(rp, ordered, field, terrain)
            self.assertEqual(seams[0]["instances"], [7, 8])
            self.assertEqual(provenance["terrain_source_first"], 1)
            # Same counts but wrong ordering cannot silently invent a seam.
            np.savez(ordered, vertices_m=v, triangles=t[::-1])
            with self.assertRaisesRegex(ValueError, "exact staged collision"):
                compiled_seams(rp, ordered, field, terrain)

    def test_flag_patch_is_idempotent_and_keeps_existing_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); plan = p / "plan.json"; level = p / "level.json"
            plan.write_text(json.dumps({"probes": [{"flag": "terrain_probe_a", "position_m": [1, 2, 3], "yaw": 30}]}))
            level.write_text(json.dumps({"warfare": {"protocol": 20569, "layout_revision": 3},
                "blam": {"cutscene_flags": [{"name": "pwr_red_home", "pos": [1, 2, 3], "yaw": 0}]}}))
            patch_level(plan, level); once = level.read_bytes(); patch_level(plan, level)
            self.assertEqual(once, level.read_bytes())
            flags = json.loads(once)["blam"]["cutscene_flags"]
            self.assertEqual(len(flags), 3)
            self.assertEqual(next(f for f in flags if f["name"] == "terrain_probe_a")["pos"], [100, -200, 300])
            self.assertEqual(flags[-1]["name"], "pwr_red_home")


if __name__ == "__main__":
    unittest.main()
