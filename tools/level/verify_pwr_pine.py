"""Audit cooked mature-pine attributes against its immutable GLB, per triangle.

UVs/colors use the classic full-fidelity LOD; Nanite geometry is checked
separately. Native Nanite UV1/2/color decoding is not exposed by the exporter.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from collections import Counter


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(path):
    raw=Path(path).read_bytes();offset=12;doc=None;binary=None
    while offset<len(raw):
        n,k=struct.unpack_from('<II',raw,offset);offset+=8
        data=raw[offset:offset+n];offset+=n
        if k==0x4e4f534a:doc=json.loads(data)
        elif k==0x004e4942:binary=data
    def acc(i):
        a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']]
        dtype={5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];item=np.dtype(dtype).itemsize
        b=np.ndarray((a['count'],width),dtype,buffer=binary,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',width*item),item)).copy()
        if a.get('normalized'):b=b.astype(np.float64)/np.iinfo(dtype).max
        return b
    result=[]
    for mesh in doc['meshes']:
        prims=[]
        for primitive in mesh['primitives']:
            indices=acc(primitive['indices']).reshape(-1).astype(int)
            attrs={key:acc(value)[indices].reshape(-1,3,acc(value).shape[1]) for key,value in primitive['attributes'].items()}
            if 'COLOR_0' in attrs:attrs['COLOR_0']=np.rint(attrs['COLOR_0']*255).astype(np.uint8)
            prims.append({'name':doc['materials'][primitive['material']]['name'],'attrs':attrs})
        result.append({'name':mesh.get('name'),'extras':mesh.get('extras',{}),'primitives':prims})
    return result


def compare_triangles(source,actual,attributes=True):
    a=source['attrs'];b=actual['attrs'];pa=a['POSITION'];pb=b['POSITION']
    if len(pa)!=len(pb):raise ValueError(f'Triangle count changed {len(pa)} -> {len(pb)}')
    if source['name']!=actual['name']:raise ValueError('Material slot order changed')
    channels=['POSITION']+(['TEXCOORD_0','TEXCOORD_1','TEXCOORD_2','COLOR_0','NORMAL'] if attributes else [])
    for key in channels:
        if key not in a or key not in b:raise ValueError('Missing '+key)
    # Centroids identify candidate triangles despite reorder/welding. Compare
    # cyclic rotations only: a winding reversal cannot pass this audit.
    tree=cKDTree(pa.mean(axis=1));maxima={key:0.0 for key in channels};matched=[]
    tolerance={'POSITION':0.00001 if attributes else .0002,'TEXCOORD_0':1e-6,'TEXCOORD_1':1e-6,'TEXCOORD_2':1e-6,'COLOR_0':0,'NORMAL':.0002}
    for start in range(0,len(pb),2048):
        end=min(start+2048,len(pb));dist,ids=tree.query(pb[start:end].mean(axis=1),k=min(16,len(pa)))
        if ids.ndim==1:ids=ids[:,None]
        best=np.full((end-start,),np.inf);bestids=np.zeros(end-start,dtype=int);besterrors={key:np.zeros(end-start) for key in channels}
        for rotation in range(3):
            errors={key:abs(a[key][ids].astype(float)-np.roll(b[key][start:end],rotation,axis=1)[:,None].astype(float)).max(axis=(2,3)) for key in channels}
            rank=sum(errors[key]/max(tolerance[key],.1 if key=='COLOR_0' else 1e-8) for key in channels)
            choices=rank.argmin(axis=1);rows=np.arange(end-start);values=rank[rows,choices];better=values<best
            best[better]=values[better];bestids[better]=ids[rows,choices][better]
            for key in channels:besterrors[key][better]=errors[key][rows,choices][better]
        matched.extend(bestids.tolist())
        for key in channels:maxima[key]=max(maxima[key],float(besterrors[key].max(initial=0)))
    # Check multiplicity too: replacing a missing triangle with a duplicate
    # must fail even when every exported corner matches some source corner.
    # Identical source triangles share a token, avoiding arbitrary KDTree ties.
    records=np.concatenate([a[key].astype('<f8') for key in channels],axis=2)
    tokens=[min(np.roll(row,rotation,axis=0).tobytes() for rotation in range(3)) for row in records]
    if Counter(tokens)!=Counter(tokens[index] for index in matched):
        raise ValueError(source['name']+' triangle multiplicity changed')
    failures={key:value for key,value in maxima.items() if value>tolerance[key]}
    if failures:raise ValueError(f'{source["name"]} parity failed: {failures}')
    return {'slot':source['name'],'triangles':len(pa),'max_absolute_errors':maxima,'winding':'cyclic_only_preserved','matched_source_triangles':len(set(matched))}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--cooked',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    original=load(args.source)[0];meshes=load(args.cooked)
    classic=next(m for m in meshes if m['extras'].get('decodedUvColorComplete'))
    if classic['extras'].get('nativeUvChannelCount')!=3:raise ValueError('Native UV count is not3')
    audits=[compare_triangles(a,b) for a,b in zip(original['primitives'],classic['primitives'],strict=True)]
    nanite=next(m for m in meshes if not m['extras'].get('decodedUvColorComplete'))
    nanite_audits=[compare_triangles(a,b,False) for a,b in zip(original['primitives'],nanite['primitives'],strict=True)]
    positions=np.concatenate([p['attrs']['POSITION'].reshape(-1,3) for p in classic['primitives']])
    source_positions=np.concatenate([p['attrs']['POSITION'].reshape(-1,3) for p in original['primitives']])
    result={'schema':'pwr-cooked-pine-parity-v1','source_sha256':digest(args.source),'cooked_export_sha256':digest(args.cooked),'classic':audits,'nanite_geometry':nanite_audits,'classic_metadata':classic['extras'],'bounds_gltf_m':[positions.min(axis=0).tolist(),positions.max(axis=0).tolist()],'height_m':float(np.ptp(positions[:,1])),'max_bounds_displacement_m':float(max(abs(positions.min(axis=0)-source_positions.min(axis=0)).max(),abs(positions.max(axis=0)-source_positions.max(axis=0)).max())),'nanite_attribute_limitation':'Native exporter exposes Nanite positions/normals/UV0 only; all3 UV channels and exactRGBA audit applies to classic full-fidelity fallback, from same MeshDescription.','passed':True}
    args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
