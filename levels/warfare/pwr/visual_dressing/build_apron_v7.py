"""Refine the existing exterior mesh against its unchanged native Gaea field.

CPU only. Conforming shared-edge splits retain all 4032 original seam vertices
and never change the playable field or the solved harmonic collar. Error
receipts measure physical metres at triangle centres and edge midpoints.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools/level'))
from heightfield import sha256
import build_apron_v3 as join

BASE = ROOT / 'out/pwr/visual-v5/apron-v4'
MASTER = ROOT / 'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
SOURCE = ROOT / 'levels/warfare/pwr/terrain/gaea-apron-v4/source.json'
OUT = ROOT / 'out/pwr/visual-v7/apron-cliffs/apron'


def errors(vertices, triangles, sample):
    result = np.zeros(len(triangles))
    for start in range(0, len(triangles), 100000):
        q = vertices[triangles[start:start+100000]]
        worst = np.zeros(len(q))
        for p in (q.mean(1), (q[:, 0]+q[:, 1])/2, (q[:, 1]+q[:, 2])/2, (q[:, 2]+q[:, 0])/2):
            worst = np.maximum(worst, abs(sample(p[:, 0], p[:, 1])-p[:, 2]))
        result[start:start+len(q)] = worst
    return result


def split(vertices, triangles, selected, sample, seam_vertices=4032):
    """Conforming red/green split; an edge midpoint is shared by all neighbours."""
    raw = triangles[:, [[0, 1], [1, 2], [2, 0]]]
    edges, inverse = np.unique(np.sort(raw.reshape(-1, 2), axis=1), axis=0, return_inverse=True)
    inverse = inverse.reshape(-1, 3)
    chosen = np.zeros(len(edges), dtype=bool)
    chosen[inverse[selected].ravel()] = True
    chosen[np.all(edges < seam_vertices, axis=1)] = False
    mid_ids = np.full(len(edges), -1, dtype=np.int64)
    xy = vertices[edges[chosen], :2].mean(1)
    mid_ids[chosen] = np.arange(len(xy))+len(vertices)
    added = np.c_[xy, sample(xy[:, 0], xy[:, 1])]
    mids = mid_ids[inverse]
    code = np.sum((mids >= 0)*[1, 2, 4], axis=1)
    pieces = []
    # Templates use vertices a,b,c and midpoints d(ab),e(bc),f(ca).
    templates = {0: [(0,1,2)], 1: [(0,3,2),(3,1,2)],
        2: [(0,1,4),(0,4,2)], 4: [(0,1,5),(5,1,2)],
        3: [(3,1,4),(0,3,4),(0,4,2)],
        5: [(0,3,5),(3,1,2),(3,2,5)],
        6: [(5,4,2),(0,1,4),(0,4,5)],
        7: [(0,3,5),(3,1,4),(5,4,2),(3,4,5)]}
    all_ids = np.c_[triangles, mids]
    for key, pattern in templates.items():
        rows = all_ids[code == key]
        for tri in pattern:
            pieces.append(rows[:, tri])
    return np.concatenate([vertices, added]), np.concatenate(pieces).astype(np.uint32)


def summary(err, vertices, triangles):
    centers = vertices[triangles].mean(1)
    i = int(np.argmax(err))
    return {'sampled_triangles': len(err), 'samples_per_triangle': 4,
        'error_m': dict(zip(['p50','p90','p95','p99','max'], np.percentile(err,[50,90,95,99,100]).tolist())),
        'worst_triangle_center_m': centers[i].tolist()}


def write_mesh(out, vertices, triangles, seam_normals):
    q = vertices[triangles]
    cross = np.cross(q[:,1]-q[:,0], q[:,2]-q[:,0])
    if np.any(cross[:,2] <= 0): raise ValueError('Degenerate or reversed exterior triangle')
    normals = np.zeros_like(vertices)
    for k in range(3): np.add.at(normals, triangles[:,k], cross)
    normals /= np.linalg.norm(normals, axis=1)[:,None]
    normals[:len(seam_normals)] = seam_normals
    edges = np.sort(triangles[:,[[0,1],[1,2],[2,0]]].reshape(-1,2), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    if np.any(counts > 2): raise ValueError('Non-manifold exterior edge')
    boundary = unique[counts == 1]
    inner = boundary[np.all(np.max(abs(vertices[boundary,:2]),axis=2) == 1000,axis=1)]
    outer = boundary[np.all(np.max(abs(vertices[boundary,:2]),axis=2) == 4000,axis=1)]
    if len(inner) != 4032 or len(inner)+len(outer) != len(boundary):
        raise ValueError('Split introduced a crack or changed the exact inner seam')
    if np.any(np.max(abs(q[:,:,:2].mean(1)),axis=1)<1000): raise ValueError('Enters playable square')
    np.savez_compressed(out/'apron.source.npz', vertices_m=vertices, triangles=triangles, normals=normals)
    arrays = [vertices[:,[0,2,1]]*[1,1,-1], normals[:,[0,2,1]]*[1,1,-1], vertices[:,:2]/25]
    arrays = [a.astype('<f4') for a in arrays]+[triangles.astype('<u4')]
    views=[]; offset=0
    for a in arrays:
        views.append({'buffer':0,'byteOffset':offset,'byteLength':a.nbytes});offset+=a.nbytes
    (out/'apron.bin').write_bytes(b''.join(a.tobytes() for a in arrays))
    doc={'asset':{'version':'2.0','generator':'PWR conforming native-field refinement v7'},
        'buffers':[{'uri':'apron.bin','byteLength':offset}],'bufferViews':views,
        'accessors':[{'bufferView':i,'componentType':5126,'count':len(vertices),'type':kind}
                     for i,kind in enumerate(('VEC3','VEC3','VEC2'))]+
                    [{'bufferView':3,'componentType':5125,'count':triangles.size,'type':'SCALAR'}],
        'materials':[{'name':'PWR_Distant_Granite'}],
        'meshes':[{'name':'PWR_Distant_Apron_V7','primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3,'material':0}]}],
        'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    doc['accessors'][0].update(min=arrays[0].min(0).tolist(),max=arrays[0].max(0).tolist())
    (out/'apron.gltf').write_text(json.dumps(doc,indent=2)+'\n')
    return len(outer), float(np.max(np.linalg.norm(vertices[unique[:,0],:2]-vertices[unique[:,1],:2],axis=1)))


def build(out=OUT, max_triangles=1800000, rounds=4, near_error=.5, far_error=1.):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    sampler, joined=join.sampler(MASTER,SOURCE,BASE)
    old=np.load(BASE/'apron.source.npz');vertices=old['vertices_m'].copy();triangles=old['triangles'].copy()
    original_seam=vertices[:4032].copy();iterations=[]
    before=errors(vertices,triangles,sampler);initial=summary(before,vertices,triangles)
    err=before
    for step in range(rounds):
        radius=np.max(abs(vertices[triangles,:2].mean(1)),axis=1)
        target=np.where(radius<2500,near_error,far_error)
        selected=np.flatnonzero(err>target)
        limit=max(0,(max_triangles-len(triangles))//6)
        if len(selected)>limit:
            selected=selected[np.argsort((err/target)[selected])[-limit:]] if limit else np.array([],dtype=int)
        if not len(selected):break
        vertices,triangles=split(vertices,triangles,selected,sampler)
        if len(triangles)>max_triangles:raise ValueError('Refinement exceeded explicit render triangle budget')
        err=errors(vertices,triangles,sampler)
        iterations.append({'iteration':step+1,'selected_triangles':len(selected),'triangles':len(triangles),**summary(err,vertices,triangles)})
        print(json.dumps(iterations[-1]),flush=True)
    if not np.array_equal(vertices[:4032],original_seam):raise ValueError('Seam changed')
    outer,maxedge=write_mesh(out,vertices,triangles,old['normals'][:4032])
    after=summary(err,vertices,triangles)
    receipt={'schema':'pwr-apron-v7','runtime_master_sha256':sha256(MASTER),'source_gaea_sha256':sha256(SOURCE),
        'baseline_npz_sha256':sha256(BASE/'apron.source.npz'),'join_receipt_sha256':sha256(BASE/'join.receipt.json'),
        'method':'Shared-edge conforming subdivision; elevations sample unchanged native Gaea/harmonic collar',
        'source_stretch':False,'height_amplification':False,'no_native_collision':True,'no_playable_height_edits':True,
        'vertices':len(vertices),'triangles':len(triangles),'maximum_render_triangles':max_triangles,
        'exact_inner_seam_vertices':4032,'max_seam_error_m':0.,'outer_boundary_edges':outer,
        'maximum_horizontal_edge_m':maxedge,'bounds_m':[vertices.min(0).tolist(),vertices.max(0).tolist()],
        'sampled_error_target_m':{'near':near_error,'far':far_error},'before':initial,'after':after,'iterations':iterations,
        'gltf_sha256':sha256(out/'apron.gltf'),'bin_sha256':sha256(out/'apron.bin'),
        'status':'CPU geometry candidate; actual view/native roundtrip/FPS pending; sampled error is not a continuous bound'}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--max-triangles',type=int,default=1800000);p.add_argument('--rounds',type=int,default=4)
    a=p.parse_args();r=build(a.out,a.max_triangles,a.rounds);print(json.dumps(r['after']))
