"""split_apron: every triangle lands in exactly one sector, sectors are even,
and a sector's glTF holds the apron's own vertices unchanged."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

import split_apron


def ring(segments=360, rings=4):
    """A flat annulus in glTF's X/Z plane (Y up), like the apron."""
    a = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    r = np.linspace(3000, 4000, rings)
    pos = np.array([[ri * np.cos(t), 100.0 + ri / 100, ri * np.sin(t)] for ri in r for t in a], np.float32)
    tris = []
    for j in range(rings - 1):
        for i in range(segments):
            p, q = j * segments + i, j * segments + (i + 1) % segments
            tris += [[p, q, p + segments], [q, q + segments, p + segments]]
    attrs = {"POSITION": pos, "NORMAL": np.tile([0, 1, 0], (len(pos), 1)).astype(np.float32),
             "TEXCOORD_0": pos[:, [0, 2]] / 8000}
    return attrs, np.array(tris, np.uint32)


GLTF = {"asset": {"version": "2.0", "generator": "test"}, "meshes": [{"name": "m", "primitives": [
    {"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
    "materials": [{"name": "PWR_Distant_Granite"}], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}


class SplitApron(unittest.TestCase):
    def test_every_triangle_once_and_even(self):
        attrs, tris = ring()
        which, cuts = split_apron.sector_of(attrs, tris, 12)
        counts = np.bincount(which, minlength=12)
        self.assertEqual(counts.sum(), len(tris))
        self.assertEqual(len(counts), 12)
        self.assertLessEqual(counts.max() - counts.min(), 12)

    def test_sector_round_trip(self):
        attrs, tris = ring()
        which, _ = split_apron.sector_of(attrs, tris, 6)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.gltf"
            part = tris[which == 2]
            split_apron.write_sector(GLTF, attrs, part, path)
            (Path(tmp) / "apron.gltf").write_text(path.read_text())
            (Path(tmp) / "apron.bin").write_bytes((Path(tmp) / "s.bin").read_bytes())
            gltf = json.loads(path.read_text())
            gltf["buffers"][0]["uri"] = "apron.bin"
            (Path(tmp) / "apron.gltf").write_text(json.dumps(gltf))
            _, back, back_tris = split_apron.load(Path(tmp))
            # Same triangles, same corner positions, in the same order.
            self.assertTrue(np.array_equal(back["POSITION"][back_tris], attrs["POSITION"][part]))
            self.assertTrue(np.array_equal(back["TEXCOORD_0"][back_tris], attrs["TEXCOORD_0"][part]))


if __name__ == "__main__":
    unittest.main()
