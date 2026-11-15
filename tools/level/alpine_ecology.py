"""Static, terrain-derived PWR ecology; no noise or height/collision mutation.

RGBA = moisture, canopy litter, exposed colluvium, road runoff weathering.
The channels come from drainage/curvature and the actual selected tree roots.
They are colour/material weights, never simulation or native water volumes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from heightfield import load_heightfield


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smooth(a, b, value):
    t = np.clip((value-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def drainage(z, spacing):
    """Deterministic D8 contributing area; strict downhill avoids cycles."""
    h, w = z.shape
    best = np.zeros_like(z)
    downstream = np.full(z.shape, -1, dtype=np.int64)
    indices = np.arange(z.size).reshape(z.shape)
    for dy, dx in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
        src = (slice(max(0,-dy),min(h,h-dy)), slice(max(0,-dx),min(w,w-dx)))
        dst = (slice(max(0,dy),min(h,h+dy)), slice(max(0,dx),min(w,w+dx)))
        fall = (z[src]-z[dst])/(spacing*np.hypot(dx,dy))
        chosen = fall > best[src]+1e-8
        best[src][chosen] = fall[chosen]
        downstream[src][chosen] = indices[dst][chosen]
    area = np.ones(z.size, dtype=float)*spacing**2
    down = downstream.ravel()
    for i in np.argsort(z.ravel(), kind='stable')[::-1]:
        if down[i] >= 0:
            area[down[i]] += area[i]
    return area.reshape(z.shape)


def derive(field, roots):
    z = field.heights_m
    dx, dy = field.spacing_m
    if not np.isclose(dx, dy):
        raise ValueError('Ecology requires square runtime cells')
    zero = np.zeros_like(z)
    z4 = gaussian_filter(z, 4/dx)
    z24 = gaussian_filter(z, 24/dx)
    gy, gx = np.gradient(z4, dy, dx)
    slope = np.hypot(gx, gy)
    concavity = smooth(.15, 3.5, z24-z4)
    convexity = smooth(.3, 4.0, z4-z24)
    flow = gaussian_filter(smooth(5.0, 10.0, np.log1p(drainage(z4, dx))), 11/dx)
    shore = field.masks.get('shore', zero)
    road = field.masks.get('road', zero)
    water = field.masks.get('water', zero)
    bases = field.masks.get('bases', zero)
    # Splat selected roots, then integrate canopy influence at two real scales.
    # Saplings get less area. Trunks do not become opaque circular dirt stamps.
    density = np.zeros_like(z)
    for row in roots:
        x, y = row['position'][:2]
        ix = int(round((x-field.origin_m[0])/dx))
        iy = int(round((y-field.origin_m[1])/dy))
        if not (0 <= iy < z.shape[0] and 0 <= ix < z.shape[1]):
            raise ValueError('Tree root lies outside the ecology field')
        weight = .2 if 'sapling' in row.get('recipe','').lower() else 1.
        density[iy,ix] += weight
    local = gaussian_filter(density, 9/dx)*2*np.pi*(9/dx)**2
    stands = gaussian_filter(density, 32/dx)*2*np.pi*(32/dx)**2
    litter = (.30*smooth(.15,1.8,local)+.70*smooth(1.2,5.5,stands))*smooth(.5,3.5,stands)
    moisture = np.clip(.16+.48*flow+.28*concavity+.18*smooth(1,5,stands)+.25*shore, 0, 1)
    # Eroded convex slopes and colluvial runnels make distinct soil/scree
    # openings. High rock/snow remains controlled by the separate geology map.
    exposure = smooth(.045,.32,slope)*np.maximum(.65*convexity, .72*flow*(1-concavity*.5))
    exposure = gaussian_filter(exposure, 3/dx)
    available = 1-smooth(.05,.65,np.maximum.reduce([road,water,bases]))
    litter *= available
    exposure *= available*(1-.55*litter)
    weathering = np.clip(.15+.6*flow+.25*concavity,0,1)*(1-smooth(.2,.8,water))
    data = np.stack([moisture,litter,exposure,weathering],-1).astype(np.float32)
    return data


def generate(master, trees, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    field = load_heightfield(master)
    selection = json.loads(Path(trees).read_text())
    roots = selection['instances']
    if len(roots) != selection['selected_count']:
        raise ValueError('Tree selection count mismatch')
    data = derive(field, roots)
    np.save(out/'ecology.rgba.npy', data)
    Image.fromarray(np.rint(data[::-1]*255).astype(np.uint8)).save(out/'ecology.png')
    report = {'schema':'pwr-alpine-ecology-v1','coordinates':'authoring_metres_z_up','row_order':'+y',
              'master_sha256':field.manifest_sha256,'trees_sha256':digest(trees),'tree_count':len(roots),
              'dimensions':list(field.dimensions),'origin_m':list(field.origin_m),'spacing_m':list(field.spacing_m),
              'data':'ecology.rgba.npy','data_sha256':digest(out/'ecology.rgba.npy'),
              'channels':['moisture','canopy_litter','colluvium','road_weathering'],
              'mean':data.mean((0,1)).tolist(),'generator_sha256':digest(__file__),
              'height_changes':False,'random_noise':False,'status':'offline material candidate; live review pending'}
    (out/'ecology.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def load(path, master_sha256):
    path = Path(path); spec = json.loads(path.read_text())
    if (spec.get('schema') != 'pwr-alpine-ecology-v1' or spec.get('coordinates') != 'authoring_metres_z_up'
            or spec.get('row_order') != '+y' or spec.get('master_sha256') != master_sha256):
        raise ValueError('Ecology schema/coordinate/runtime provenance mismatch')
    source = path.parent/spec['data']
    if digest(source) != spec['data_sha256']:
        raise ValueError('Ecology data hash mismatch')
    data = np.load(source,allow_pickle=False)
    if (data.dtype != np.float32 or data.shape != (*spec['dimensions'][::-1],4)
            or not np.isfinite(data).all() or data.min()<0 or data.max()>1):
        raise ValueError('Ecology must be finite float32 RGBA in 0..1')
    return data, spec


def apply_to_bake(folder, document, manifest, master_sha256):
    from alpine_geology import sample_texture
    folder = Path(folder)
    data, spec = load(manifest,master_sha256)
    base = folder/document['textures']['Base']
    before = digest(base)
    original = np.asarray(Image.open(base).convert('RGBA'))
    # Reuse the exact pixel-centre +Y-to-UE codec; it handles any channel count.
    rgba = sample_texture(data,original.shape[1],original.shape[0])
    Image.fromarray(rgba).save(folder/'ecology.png')
    document['textures']['Ecology'] = 'ecology.png'
    package = document['pbr']['base'].rsplit('/',1)[0]
    document['pbr']['ecology'] = {'texture':package+'/T_LandEcology.T_LandEcology'}
    document.setdefault('texture_encoding',{})['Ecology'] = {
        'srgb':False,'compression':'vector_displacement','channels':spec['channels']}
    if before != digest(base):
        raise AssertionError('Ecology modified Base')
    receipt = {'schema':'pwr-alpine-ecology-bake-v1','master_sha256':master_sha256,
               'ecology_spec_sha256':digest(manifest),'texture_sha256':digest(folder/'ecology.png'),
               'base_sha256_before':before,'base_sha256_after':digest(base),
               'road_alpha_sha256':hashlib.sha256(original[...,3].tobytes()).hexdigest(),
               'texture_encoding':{'srgb':False,'compression':'TC_VECTOR_DISPLACEMENTMAP'},
               'dimensions':[original.shape[1],original.shape[0]]}
    (folder/'ecology.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master',type=Path,required=True)
    parser.add_argument('--trees',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.master,args.trees,args.out),indent=2))
