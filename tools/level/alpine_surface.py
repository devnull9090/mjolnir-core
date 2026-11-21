"""Bake a linear road-direction/distance field without changing terrain masks.

RG encodes the unit tangent, B signed lateral distance over +/-16 metres,
A confidence (zero near graph junctions and off the 24 metre carriageway).
The field is presentation only. All geometry remains the canonical road graph.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


def road_segments(geometry):
    starts, ends, joins = [], [], []
    for road in geometry['roads']:
        points = np.asarray(road['centreline_m'], dtype=float)[:, :2]
        if not np.isfinite(points).all():
            raise ValueError('Road coordinates must be finite')
        joins.extend([points[0], points[-1]])
        for a, b in zip(points[:-1], points[1:]):
            distance = np.linalg.norm(b-a)
            if distance < 1e-8:
                continue
            # Bounded segments make nearest midpoint queries conservative.
            p = np.linspace(a, b, max(2, int(np.ceil(distance/4))+1))
            starts.extend(p[:-1]); ends.extend(p[1:])
    if not starts:
        raise ValueError('Road graph is empty')
    return np.asarray(starts), np.asarray(ends), np.unique(joins, axis=0)


def road_field(geometry, xy):
    """Exact segment projection, with explicit junction fading. Authoring m."""
    a, b, joins = road_segments(geometry)
    delta = b-a
    length = np.linalg.norm(delta, axis=1)
    tree = cKDTree((a+b)/2)
    xy = np.asarray(xy, dtype=float)
    shape = xy.shape[:-1]
    points = xy.reshape(-1, 2)
    output = np.empty((len(points), 4), dtype=np.float64)
    join_tree = cKDTree(joins)
    for first in range(0, len(points), 32768):
        p = points[first:first+32768]
        _, index = tree.query(p, k=min(16, len(a)))
        if index.ndim == 1: index = index[:, None]
        v = p[:, None, :]-a[index]
        t = np.clip((v*delta[index]).sum(-1)/length[index]**2, 0, 1)
        offset = v-t[..., None]*delta[index]
        choice = (offset**2).sum(-1).argmin(1)
        best = index[np.arange(len(p)), choice]
        offset = offset[np.arange(len(p)), choice]
        tangent = delta[best]/length[best, None]
        lateral = tangent[:, 0]*offset[:, 1]-tangent[:, 1]*offset[:, 0]
        distance = np.linalg.norm(offset, axis=1)
        junction_distance = join_tree.query(p)[0]
        confidence = np.clip((junction_distance-8)/12, 0, 1)
        confidence = confidence**2*(3-2*confidence)
        confidence *= np.clip((14-distance)/2, 0, 1)
        output[first:first+len(p)] = np.column_stack((tangent, lateral, confidence))
    return output.reshape(*shape, 4)


def apply_to_bake(folder, document, geometry_path):
    folder = Path(folder)
    geometry_path = Path(geometry_path)
    geometry = json.loads(geometry_path.read_text())
    base_path = folder/document['textures']['Base']
    before = hashlib.sha256(base_path.read_bytes()).hexdigest()
    base = np.asarray(Image.open(base_path))
    n, width = base.shape[:2]
    rect = document['pbr']['rect']
    # PNG rows increase in UE +Y, opposite authoring +Y.
    x = (rect[0]+(np.arange(width)+.5)*rect[2]/width)/100
    y = -(rect[1]+(np.arange(n)+.5)*rect[3]/n)/100
    xx, yy = np.meshgrid(x, y)
    field = road_field(geometry, np.stack((xx, yy), -1))
    packed = np.empty_like(field)
    # Tangent is reflected to UE XY as well.
    packed[..., :2] = field[..., :2]*[.5, -.5]+.5
    packed[..., 2] = field[..., 2]/32+.5
    packed[..., 3] = field[..., 3]
    rgba = np.rint(np.clip(packed, 0, 1)*255).astype(np.uint8)
    Image.fromarray(rgba).save(folder/'surface-detail.png')
    document['textures']['SurfaceData'] = 'surface-detail.png'
    root = document['pbr']['base'].rsplit('/', 1)[0]
    document['pbr']['surface_detail'] = {'texture':root+'/T_LandSurfaceData.T_LandSurfaceData', 'range_cm':1600}
    document.setdefault('texture_encoding', {})['SurfaceData'] = {
        'srgb':False, 'compression':'vector_displacement', 'channels':'RG UE tangent; B signed distance +/-16m; A junction confidence'}
    after = hashlib.sha256(base_path.read_bytes()).hexdigest()
    if before != after: raise AssertionError('Road detail modified Base')
    receipt = {'schema':'pwr-alpine-surface-v1', 'geometry_sha256':hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
               'base_sha256_before':before, 'base_sha256_after':after,
               'base_alpha_sha256':hashlib.sha256(base[..., 3].tobytes()).hexdigest(),
               'road_texture_sha256':hashlib.sha256((folder/'surface-detail.png').read_bytes()).hexdigest(),
               'size':[width,n], 'distance_quantization_max_m':16/255,
               'junction_fade_m':[8,20], 'shader_geometry_effect':'none'}
    (folder/'surface-detail.receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt
