"""Continuous Gaea relief outside the frozen PWR boundary; no game or native edits."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rings():
    result = [(1000., 1), (1004., 1), (1016., 2), (1040., 4), (1080., 8)]
    radius = result[-1][0]
    while radius < 4000:
        # Bound radial *and* tangential/diagonal edges, including square corners.
        tangent = (radius + 50) / 1000 * (2000 / 1008) * 8
        step = min(50., (95. - tangent) / math.sqrt(2), 4000 - radius)
        radius += step
        result.append((radius, 8))
    return result


def build(master, source, out, elevation_gain=2.45, blend_m=500., height_sampler=None, method_metadata=None, ring_specs=None):
    master, source, out = Path(master).resolve(), Path(source).resolve(), Path(out).resolve()
    field, gaea = load_heightfield(master), load_heightfield(source)
    if field.dimensions != (1009, 1009) or not np.allclose(field.bounds_m, [[-1000., -1000.], [1000., 1000.]]):
        raise ValueError("Requires the reviewed 2 km runtime field")
    if out in (master.parent, source.parent) or not 1 <= elevation_gain <= 3 or not 250 <= blend_m <= 700:
        raise ValueError("Isolated output and bounded relief scales required")
    out.mkdir(parents=True, exist_ok=True)
    axis = np.linspace(-1000., 1000., 1009)
    boundary = np.vstack([np.c_[axis[:-1], np.full(1008, -1000)],
                          np.c_[np.full(1008, 1000), axis[:-1]],
                          np.c_[axis[:0:-1], np.full(1008, 1000)],
                          np.c_[np.full(1008, -1000), axis[:0:-1]]])
    h = field.heights_m
    boundary_heights = np.concatenate([h[0, :-1], h[:-1, -1], h[-1, :0:-1], h[:0:-1, 0]])
    positions, rows = [], []
    specs = ring_specs or rings()
    for radius, skip in specs:
        edge = boundary[::skip]
        xy = edge * (radius / 1000)
        displacement = xy - edge
        distance = np.linalg.norm(displacement, axis=1)
        direction = displacement / np.maximum(distance[:, None], 1e-12)
        edge_z = field.sample(edge[:, 0], edge[:, 1])
        inner = edge - direction * 8
        gradient = (edge_z - field.sample(inner[:, 0], inner[:, 1])) / 8
        tangent = edge_z + gradient * 90 * (1 - np.exp(-distance / 90))
        # One continuous real Gaea field stretched horizontally 4x. No periodic
        # reflection, synthesized mounds, or min/max union of mountain primitives.
        sample_xy = xy / 4
        eroded = 70 + (gaea.sample(sample_xy[:, 0], sample_xy[:, 1]) - 70) * elevation_gain
        u = np.clip((distance - 16) / blend_m, 0, 1)
        weight = u**3 * (10 - 15*u + 6*u*u)
        height = tangent * (1 - weight) + eroded * weight
        if height_sampler is not None:
            height = height_sampler(xy[:, 0], xy[:, 1])
        if radius == 1000:
            height = boundary_heights
        rows.append((sum(len(x) for x in positions), len(xy)))
        positions.append(np.c_[xy, height])
    vertices = np.concatenate(positions)
    faces = []
    for (a, n), (b, m) in zip(rows[:-1], rows[1:]):
        assert n % m == 0
        ratio = n // m
        for j in range(m):
            for k in range(ratio):
                faces.append([a+(j*ratio+k)%n, b+j, a+(j*ratio+k+1)%n])
            faces.append([a+((j+1)*ratio)%n, b+j, b+(j+1)%m])
    triangles = np.array(faces, dtype=np.uint32)
    t = vertices[triangles]
    cross = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
    flip = cross[:, 2] < 0
    triangles[flip] = triangles[flip][:, [0, 2, 1]]
    t = vertices[triangles]
    cross = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
    normals = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(normals, triangles[:, k], cross)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    # Match the inner edge's lighting normal to the same real rendered field.
    x, y = boundary.T
    dx = (field.sample(np.minimum(x+1, 1000), y)-field.sample(np.maximum(x-1, -1000), y)) / (np.minimum(x+1, 1000)-np.maximum(x-1, -1000))
    dy = (field.sample(x, np.minimum(y+1, 1000))-field.sample(x, np.maximum(y-1, -1000))) / (np.minimum(y+1, 1000)-np.maximum(y-1, -1000))
    seam_normals = np.c_[-dx, -dy, np.ones(len(x))]
    normals[:len(x)] = seam_normals / np.linalg.norm(seam_normals, axis=1)[:, None]
    edges = np.concatenate([np.linalg.norm(t[:, i, :2]-t[:, j, :2], axis=1) for i, j in ((0, 1), (1, 2), (2, 0))])
    max_edge = float(edges.max())
    seam_error = float(np.max(abs(vertices[:4032, 2]-boundary_heights)))
    if max_edge > 100 or seam_error != 0 or np.any(cross[:, 2] <= 0) or not np.isfinite(vertices).all():
        raise ValueError(f"Apron validation failed: edge={max_edge}, seam={seam_error}")
    if np.max(abs(t[:, :, :2].mean(axis=1)), axis=1).min() < 1000:
        raise ValueError("Apron enters frozen gameplay terrain")
    np.savez_compressed(out / 'apron.source.npz', vertices_m=vertices, triangles=triangles, normals=normals)
    data = [np.c_[vertices[:, 0], vertices[:, 2], -vertices[:, 1]].astype('<f4'),
            np.c_[normals[:, 0], normals[:, 2], -normals[:, 1]].astype('<f4'),
            (vertices[:, :2]/25).astype('<f4'), triangles.astype('<u4')]
    views, offset = [], 0
    for array in data:
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': array.nbytes})
        offset += array.nbytes
    (out/'apron.bin').write_bytes(b''.join(array.tobytes() for array in data))
    doc = {'asset': {'version': '2.0', 'generator': 'PWR continuous Gaea apron v2'},
           'buffers': [{'uri': 'apron.bin', 'byteLength': offset}], 'bufferViews': views,
           'accessors': [{'bufferView': i, 'componentType': 5126, 'count': len(vertices), 'type': kind}
                         for i, kind in enumerate(('VEC3', 'VEC3', 'VEC2'))] +
                        [{'bufferView': 3, 'componentType': 5125, 'count': triangles.size, 'type': 'SCALAR'}],
           'materials': [{'name': 'PWR_Distant_Granite'}],
           'meshes': [{'name': 'PWR_Distant_Apron_V2', 'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2}, 'indices': 3, 'material': 0}]}],
           'nodes': [{'mesh': 0}], 'scenes': [{'nodes': [0]}], 'scene': 0}
    doc['accessors'][0].update(min=data[0].min(0).tolist(), max=data[0].max(0).tolist())
    (out/'apron.gltf').write_text(json.dumps(doc, indent=2)+'\n')
    receipt = {'schema': 'pwr-apron-v2', 'runtime_master_sha256': field.manifest_sha256,
               'source_gaea_sha256': gaea.manifest_sha256, 'source_gaea_height_sha256': gaea.metadata['height']['sha256'],
               'source_mapping': 'continuous xy/4; no reflection; z=70+(source-70)*gain',
               'elevation_gain': elevation_gain, 'blend_m': blend_m,
               'vertices': len(vertices), 'triangles': len(triangles), 'bounds_m': [vertices.min(0).tolist(), vertices.max(0).tolist()],
               'maximum_horizontal_edge_m': max_edge, 'exact_inner_seam_vertices': 4032,
               'max_seam_error_m': seam_error, 'no_native_collision': True, 'no_playable_height_edits': True,
               'radial_rings': specs, 'gltf_sha256': sha(out/'apron.gltf'), 'bin_sha256': sha(out/'apron.bin'),
               'status': 'isolated geometry candidate; Blender preview and native package/live review required'}
    if method_metadata is not None:
        receipt.update(method_metadata)
    (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k: receipt[k] for k in ('vertices', 'triangles', 'bounds_m', 'maximum_horizontal_edge_m', 'max_seam_error_m')}))
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--master', type=Path, default=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    p.add_argument('--source', type=Path, default=ROOT/'levels/warfare/pwr/terrain/gaea-v5c/source.json')
    p.add_argument('--out', type=Path, default=ROOT/'out/pwr/visual-v5/apron-v2')
    a = p.parse_args()
    build(a.master, a.source, a.out)
