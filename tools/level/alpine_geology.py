"""Opt-in Alpine2 Base RGB codec; original road alpha stays byte-exact."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path,master_sha256):
    path=Path(path);spec=json.loads(path.read_text())
    if spec.get('schema')!='pwr-alpine-geology-v1' or spec.get('coordinates')!='authoring_metres_z_up' or spec.get('row_order')!='+y':
        raise ValueError('Unsupported Alpine geology coordinates/schema')
    if spec.get('master_sha256')!=master_sha256:raise ValueError('Geology belongs to another runtime master')
    source=path.parent/spec['data']
    if digest(source)!=spec['data_sha256']:raise ValueError('Geology data hash mismatch')
    data=np.load(source,allow_pickle=False)
    if data.dtype!=np.float32 or data.shape!=(*spec['dimensions'][::-1],3) or not np.isfinite(data).all() or data.min()<0 or data.max()>1:
        raise ValueError('Geology must contain finite float32 RGB masks in0..1')
    return data,spec


def sample_texture(data,width,height):
    """At pixel centres, flip authored+Y to UE/PNG rows. No gamma conversion."""
    h,w,channels=data.shape
    u=(np.arange(width)+.5)/width*(w-1)
    v=(1-(np.arange(height)+.5)/height)*(h-1)
    i=np.minimum(np.floor(u).astype(int),w-2);j=np.minimum(np.floor(v).astype(int),h-2)
    a=(u-i)[None,:,None];output=np.empty((height,width,channels),dtype=np.uint8)
    # A4096square bake should not allocate several full float64 RGB images
    # while the editor/cook is in memory. Process bounded strips instead.
    for start in range(0,height,128):
        stop=min(height,start+128);rows=j[start:stop];b=(v[start:stop]-rows)[:,None,None]
        result=((1-a)*(1-b)*data[rows[:,None],i[None,:]]+a*(1-b)*data[rows[:,None],i[None,:]+1]
                +(1-a)*b*data[rows[:,None]+1,i[None,:]]+a*b*data[rows[:,None]+1,i[None,:]+1])
        output[start:stop]=np.rint(np.clip(result,0,1)*255).astype(np.uint8)
    return output


def apply_to_bake(folder,document,geology,master_sha256):
    folder=Path(folder);data,spec=load(geology,master_sha256)
    path=folder/document['textures']['Base']
    original=np.asarray(Image.open(path).convert('RGBA')).copy()
    encoded=original.copy();encoded[:,:,:3]=sample_texture(data,original.shape[1],original.shape[0])
    if not np.array_equal(original[:,:,3],encoded[:,:,3]):raise AssertionError('Road alpha changed')
    Image.fromarray(encoded,'RGBA').save(path)
    # Mode2 is explicit. Missing masks or existing mode1 maps retain their
    # previous shader behavior; no new sampler/runtime loader hook is needed.
    alpine=list(document['pbr'].get('alpine',[19000,27000,1800,0]));alpine[3]=2
    document['pbr']['alpine']=alpine
    report={'schema':'pwr-alpine-geology-bake-v1','master_sha256':master_sha256,
            'geology_spec_sha256':digest(geology),'data_sha256':spec['data_sha256'],
            'base_texture_sha256':digest(path),'road_alpha_sha256':hashlib.sha256(original[:,:,3].tobytes()).hexdigest(),
            'road_alpha_unchanged':True,'mode':2,'dimensions':[original.shape[1],original.shape[0]],
            'channels':spec['channels'],
            'texture_encoding':{'rgb':'linear_unorm8','alpha':'original_linear_unorm8',
                                'srgb':False,'compression':'TC_VECTOR_DISPLACEMENTMAP',
                                'base_sampler':'SAMPLERTYPE_LINEAR_COLOR'}}
    (folder/'geology.receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
