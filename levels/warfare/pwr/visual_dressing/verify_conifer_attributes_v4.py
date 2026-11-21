"""Verify native indexed UV/color masks survive the complete tree assembly."""
from collections import Counter
from pathlib import Path
import hashlib,json,struct
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    raw=Path(path).read_bytes();n=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+n]);binary=raw[28+n:]
    def accessor(index):
        a=doc['accessors'][index];view=doc['bufferViews'][a['bufferView']]
        dt=np.dtype({5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']])
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        values=np.ndarray((a['count'],width),dtype=dt,buffer=binary,
            offset=view.get('byteOffset',0)+a.get('byteOffset',0),strides=(view.get('byteStride',dt.itemsize*width),dt.itemsize)).copy()
        if a.get('normalized'):values=values.astype(float)/np.iinfo(dt).max
        return values
    return doc,accessor


def signature(accessor,primitive,channels,deduplicate=False):
    attrs=primitive['attributes'];indices=accessor(primitive['indices']).reshape(-1,3)
    duplicate=0
    if deduplicate:
        seen=set();kept=[]
        for row in indices:
            key=tuple(sorted(row))
            if key in seen:duplicate+=1;continue
            seen.add(key);kept.append(row)
        indices=np.asarray(kept)
    indices=indices.ravel()
    uv=np.c_[tuple(accessor(attrs['TEXCOORD_'+str(c)]) for c in range(channels))]
    color=np.rint(accessor(attrs['COLOR_0'])*255).astype(int)
    rows=np.c_[np.rint(uv[indices]*1e6).astype(np.int64),color[indices]]
    return Counter(map(tuple,rows.tolist())),duplicate


def main():
    source=json.loads((OUT/'source.json').read_text());recipe=source['recipe']
    use=Counter(p['mesh'] for p in recipe['parts']);use[recipe['leaf_mesh']]+=len(recipe['leaves'])
    expected={name:Counter() for name in ('MI_Pine_Tree_Mat','MI_Branch_Mat')};duplicates=0
    for entry in source['assets']:
        doc,accessor=read(entry['glb']);mesh=doc['meshes'][entry['selected_lod']]
        proof=mesh['extras']
        if not proof['decodedUvColorComplete']:raise ValueError('Incomplete native source')
        for p in mesh['primitives']:
            name=doc['materials'][p['material']]['name'];channels=3 if name=='MI_Pine_Tree_Mat' else 1
            attrs=p['attributes'];position=doc['accessors'][attrs['POSITION']];color=doc['accessors'][attrs['COLOR_0']]
            if not(color['componentType']==5121 and color['type']=='VEC4' and color.get('normalized') is True
                and color['count']==position['count']==proof['nativeColorVertexCount']):raise ValueError('Native RGBA accessor mismatch')
            sig,removed=signature(accessor,p,channels,True);duplicates+=removed*use[entry['mesh']]
            expected[name].update({key:count*use[entry['mesh']] for key,count in sig.items()})
    doc,accessor=read(OUT/'mature-pine-a.glb')
    if len(doc['meshes'])!=1 or {m['name'] for m in doc['materials']}!=set(expected):
        raise ValueError('Unexpected tree geometry/materials')
    actual={name:Counter() for name in expected};normals={}
    for p in doc['meshes'][0]['primitives']:
        name=doc['materials'][p['material']]['name'];channels=3 if name=='MI_Pine_Tree_Mat' else 1
        sig,_=signature(accessor,p,channels);actual[name].update(sig)
        attrs=p['attributes'];xyz=accessor(attrs['POSITION']);normal=accessor(attrs['NORMAL']);i=accessor(p['indices']).reshape(-1,3)
        n=np.cross(xyz[i[:,1]]-xyz[i[:,0]],xyz[i[:,2]]-xyz[i[:,0]]);length=np.linalg.norm(n,axis=1);valid=length>1e-10
        dot=(n[valid]/length[valid,None]*normal[i[valid]].mean(1)).sum(1)
        normals[name]={'median_face_vertex_normal_dot':float(np.median(dot)),'opposed_fraction':float((dot<0).mean())}
        if np.median(dot)<.3:raise ValueError('Native normal/winding disagreement remains')
    for name in expected:
        if actual[name]!=expected[name]:
            raise ValueError(f'{name}: indexed UV/RGBA signatures changed: missing{sum((expected[name]-actual[name]).values())}, extra{sum((actual[name]-expected[name]).values())}')
    report={'schema':'pwr-conifer-assembled-attributes-v1','source_sha256':digest(OUT/'source.json'),
        'assembled_glb_sha256':digest(OUT/'mature-pine-a.glb'),'exporter_sha256':source['exporter_sha256'],
        'native_sources':len(source['assets']),'indexed_rgba_original_bytes_exact':True,
        'indexed_uv_tolerance':1e-6,'native_uv_channels':{'bark':3,'needles':1},
        'duplicate_source_triangles_removed':duplicates,'normals':normals,
        'source_primitive_signature_corners':{k:sum(v.values()) for k,v in expected.items()},
        'materials':[m['name'] for m in doc['materials']]}
    (OUT/'native-attributes.receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
