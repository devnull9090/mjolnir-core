"""Export and verify native cooked base meshes before installing their chunk.

Runs the pinned read-only mesh exporter, compares every section's geometry,
UV range, material slot and overall count/bounds, then writes a cook receipt.
Usage: python .../verify_runtime_visuals.py --paks <isolated native audit paks>
"""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess
import numpy as np
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parents[4]
DEFAULT=ROOT/'out/pwr/base-runtime/visuals/manifest.json'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read_mesh(path,mesh_index=0):
    path=Path(path);raw=path.read_bytes()
    if raw[:4]==b'glTF':
        chunks={};offset=12
        while offset<len(raw):
            n,kind=struct.unpack_from('<II',raw,offset);offset+=8;chunks[kind]=raw[offset:offset+n];offset+=n
        doc=json.loads(chunks[0x4e4f534a]);data=chunks[0x004e4942]
    else:
        doc=json.loads(raw);data=(path.parent/doc['buffers'][0]['uri']).read_bytes()
    def acc(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        count={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
        out=np.ndarray((a['count'],count),dtype=dtype,buffer=data,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dtype.itemsize*count),dtype.itemsize)).copy()
        if a.get('normalized'):out=out.astype(float)/np.iinfo(dtype).max
        return out
    output=[]
    for p in doc['meshes'][mesh_index]['primitives']:
        a=p['attributes'];idx=acc(p['indices']).reshape(-1,3)
        used,inverse=np.unique(idx,return_inverse=True)
        output.append({'slot':doc['materials'][p['material']]['name'],'position':acc(a['POSITION'])[used],
                       'normal':acc(a['NORMAL'])[used],'uv':acc(a['TEXCOORD_0'])[used],'triangles':inverse.reshape(-1,3)})
    return output

def canonical(triangles):
    first=np.argmin(triangles,axis=1)
    return np.take_along_axis(triangles,(first[:,None]+np.arange(3))%3,axis=1)


def triangle_difference(source,target):
    keys,inverse=np.unique(np.concatenate([canonical(source),canonical(target)]),axis=0,return_inverse=True)
    counts=np.bincount(inverse[:len(source)],minlength=len(keys))-np.bincount(inverse[len(source):],minlength=len(keys))
    return keys,counts


def nanite_uvs(uv):
    """Exact UE5.5 NaniteEncode.cpp EncodeUVFloat/DecodeUVFloat, m=14."""
    x=np.ascontiguousarray(uv,dtype=np.float32);bits=x.view(np.uint32);ab=bits&0x7fffffff
    lo=ab<0x3f800000;em=np.empty(x.shape,dtype=np.uint32)
    em[lo]=np.floor((np.abs(x[lo])*np.float32(16384)).astype(np.float64)+.5).astype(np.uint32)
    em[~lo]=np.minimum(((ab[~lo]-np.uint32(0x3f000000))+np.uint32(256))>>np.uint32(9),np.uint32(524287))
    result=(np.uint32(0x3f000000)+(em<<np.uint32(9))).view(np.float32)
    result=np.minimum(result*2-1,result)
    return np.where((bits>>31)!=0,-result,result)


def verify_fallback(a,b):
    """Exact oriented triangle/UV multiset after the native float32 weld."""
    si=a['triangles'];ti=b['triangles']
    # MeshDescription stores float32 centimetres. The GLB reader converts those
    # float32 values back to metres; reproduce this conversion before matching.
    original=(a['position'].astype(np.float64)*100).astype(np.float32)*np.float32(.01)
    positions,target_map=np.unique(b['position'],axis=0,return_inverse=True)
    distance,source_map=cKDTree(positions).query(original,workers=-1)
    used=np.unique(si)
    # A two-ULP bound covers UE's welding of nearly coincident f32 positions.
    # This is micrometres at base scale, not a gameplay-geometry tolerance.
    centimetres=np.max(np.abs(a['position'][used]))*100
    weld_bound=max(1e-6,float(np.spacing(np.float32(centimetres)))*2/100)
    point_error=float(distance[used].max(initial=0))
    if point_error>weld_bound:raise ValueError(f'Fallback position/weld error {a["slot"]}: {point_error} > {weld_bound}')
    # UV is part of every vertex key, including seams. Thus local UV swaps,
    # V inversion, orientation changes and duplicate/missing real triangles
    # cannot hide behind equal UV extrema or equal total triangle counts.
    attributes,ids=np.unique(np.concatenate([np.c_[source_map,a['uv']],np.c_[target_map,b['uv']]]),axis=0,return_inverse=True)
    # StaticMeshBuilder::AreVerticesEqual uses MeshBuild.h::UVsEqual:
    # per-coordinate difference <=1/1024, at the same geometric position.
    # Bound whole clusters, preventing transitive chains exceeding that rule.
    uv_bound=1/1024
    parent=np.arange(len(attributes));lower=attributes[:,1:].copy();upper=lower.copy()
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,j in cKDTree(attributes).query_pairs(uv_bound*np.sqrt(2),output_type='ndarray'):
        if attributes[i,0]==attributes[j,0] and np.all(np.abs(attributes[i,1:]-attributes[j,1:])<=uv_bound):
            ri,rj=find(i),find(j)
            if ri!=rj:
                lo=np.minimum(lower[ri],lower[rj]);hi=np.maximum(upper[ri],upper[rj])
                if np.all(hi-lo<=uv_bound):
                    keep,drop=min(ri,rj),max(ri,rj);parent[drop]=keep;lower[keep]=lo;upper[keep]=hi
    roots=np.array([find(i) for i in range(len(parent))]);ids=roots[ids]
    source=ids[:len(source_map)][si];target=ids[len(source_map):][ti]
    keys,delta=triangle_difference(source,target)
    if np.any(delta<0):raise ValueError(f'Fallback added/reoriented/UV-changed triangles {a["slot"]}: {int(-delta[delta<0].sum())}')
    missing=keys[delta>0];removed=int(delta[delta>0].sum())
    if len(missing):
        xyz=positions[attributes[missing,0].astype(np.int64)].astype(np.float64)
        area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)
        if np.any(area!=0):raise ValueError(f'Fallback removed nonzero-area triangles {a["slot"]}: {float(area.max())}')
    if len(si)-len(ti)!=removed:raise ValueError('Fallback triangle accounting mismatch')
    return {'slot':a['slot'],'source_triangles':len(si),'native_triangles':len(ti),'removed_zero_area_triangles':removed,
            'maximum_native_weld_error_m':point_error,'native_weld_bound_m':weld_bound,
            'corner_uv_weld_bound':uv_bound,'maximum_corner_uv_weld':float(np.max(upper-lower)),
            'oriented_triangle_and_corner_uv_multiset_exact_after_native_weld':True}


def triangle_features(part,quantize_uv=False):
    idx=part['triangles'];position=part['position'][idx].astype(np.float64)
    uv=nanite_uvs(part['uv'])[idx] if quantize_uv else part['uv'][idx]
    # Float14's minimum UV step is 2^-14. Scaling it by 100 makes even a
    # one-step UV error much greater than the position-quantization budget.
    return np.concatenate([position,uv.astype(np.float64)*100],axis=2)


def directed_nanite_match(reference,query,bound):
    # Keep all cyclic rotations (never reverse winding). This avoids ambiguous
    # canonical corners on triangles with equal UVs or quantized equal points.
    rotations=np.concatenate([np.roll(reference,k,axis=1).reshape(len(reference),15) for k in range(3)])
    distances,indices=cKDTree(rotations).query(query.reshape(len(query),15),workers=-1)
    if float(distances.max(initial=0))>bound:raise ValueError('Nanite triangle geometry/corner-UV coverage changed')
    match=rotations[indices].reshape(-1,3,5)
    if not np.array_equal(match[:,:,3:],query[:,:,3:]):raise ValueError('Nanite UV differs from exact float14 encoding')
    return float(np.linalg.norm(match[:,:,:3]-query[:,:,:3],axis=2).max(initial=0))


def verify_nanite(classic,native):
    if len(classic['triangles'])!=len(native['triangles']):raise ValueError('Nanite/full fallback triangle count differs')
    a=triangle_features(classic,True);b=triangle_features(native)
    # PositionPrecision=6 is a 1/64-cm lattice. Each coordinate moves at most
    # half a step; three corners plus f32 metre readback give this L2 bound.
    position_bound=3/(128*100)+1e-5
    forward=directed_nanite_match(a,b,position_bound)
    backward=directed_nanite_match(b,a,position_bound)
    return {'slot':classic['slot'],'triangles':len(classic['triangles']),
            'maximum_corner_position_quantization_m':max(forward,backward),
            'position_precision':6,'uv_mantissa_bits':14,'uv_exact_encoder_roundtrip':True,
            'bidirectional_oriented_triangle_coverage':True,
            'limitation':'Nanite coverage is not multiplicity certification; fallback multiset is authoritative'}


def verify(spec,path):
    gltf=Path(spec['gltf']);doc=json.loads(gltf.read_text())
    if sha(gltf)!=spec['gltf_sha256'] or sha(gltf.parent/doc['buffers'][0]['uri'])!=spec['bin_sha256']:
        raise ValueError('Source mesh bytes differ from manifest')
    source=read_mesh(gltf);nanite=read_mesh(path,0);classic=read_mesh(path,1)
    for representation in (nanite,classic):
        if [p['slot'] for p in representation]!=spec['material_keys']:raise ValueError('Cooked material slot order differs: '+spec['name'])
        if len(source)!=len(representation):raise ValueError('Section count changed')
    checks=[];gpu_checks=[]
    for a,b,n in zip(source,classic,nanite):
        checks.append(verify_fallback(a,b));gpu_checks.append(verify_nanite(b,n))
    return {'asset':spec['asset'],'source_triangles':sum(x['source_triangles'] for x in checks),
            'triangles':sum(x['native_triangles'] for x in checks),
            'removed_zero_area_triangles':sum(x['removed_zero_area_triangles'] for x in checks),
            'sections':checks,'nanite_sections':gpu_checks,
            'native_readback':str(path),'native_readback_sha256':sha(path)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=DEFAULT)
    p.add_argument('--paks',type=Path,required=True)
    p.add_argument('--cli',type=Path,default=ROOT/'out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe')
    p.add_argument('--out',type=Path,default=ROOT/'out/pwr/base-runtime/visual-readback')
    p.add_argument('--reuse-exports',action='store_true')
    args=p.parse_args();manifest=json.loads(args.manifest.read_text());args.out.mkdir(parents=True,exist_ok=True)
    checks=[];failures=[]
    for spec in manifest['assets']:
        target=args.out/(spec['name']+'.glb')
        if not args.reuse_exports:
            # CLI matches mounted package paths, not Unreal's /Game alias.
            call=[str(args.cli),'mesh','export','--paks',str(args.paks),'--asset',spec['asset'].removeprefix('/Game/'),'--out',str(target)]
            done=subprocess.run(call,cwd=ROOT,capture_output=True,text=True)
            (args.out/(spec['name']+'.log')).write_text(done.stdout+done.stderr)
            if done.returncode:raise RuntimeError('Native mesh readback failed: '+spec['name'])
        try:
            checks.append(verify(spec,target));print(json.dumps({'verified':spec['name'],'triangles':checks[-1]['triangles']}),flush=True)
        except ValueError as error:
            failures.append({'asset':spec['name'],'error':str(error)});print(json.dumps(failures[-1]),flush=True)
    report={'schema':'pwr-native-base-visual-readback-v1','passed':not failures,'failures':failures,'manifest_sha256':sha(args.manifest),
            'cli':str(args.cli),'cli_sha256':sha(args.cli),'paks':str(args.paks),'checks':checks,
            'total_triangles':sum(c['triangles'] for c in checks),'source_total_triangles':sum(c['source_triangles'] for c in checks),
            'removed_zero_area_triangles':sum(c['removed_zero_area_triangles'] for c in checks),
            'material_proof':'slot names/order; cooked material values are covered by editor import and package ownership receipts',
            'native_physics_proof':False}
    (args.out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':not failures,'assets':len(checks),'triangles':report['total_triangles']}))
    if failures:raise ValueError('Native readback failures: '+str(len(failures)))

if __name__=='__main__':main()
