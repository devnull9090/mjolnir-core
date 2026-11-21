"""Build measured trunk-only collision for the reviewed native mature pine.

CPU-only. Never exports game assets, opens Blender, or touches an install.
Five measured convex bands enclose the original Trunk LOD1,
including source triangle intersections at band boundaries. Crown geometry is
used only to verify the final assembled asset contains that same trunk.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

import numpy as np
import trimesh
from scipy.spatial import ConvexHull, HalfspaceIntersection, cKDTree

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
from b30_collision import validate_mature_trunk_cache, hull_of, PWR_MATURE_PINE

TRUNK='/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Trunk'
BARK='MI_Pine_Tree_Mat'
SCALE=28/217.199


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_mesh(path,lod,material):
    raw=Path(path).read_bytes()
    if raw[:4]!=b'glTF':raise ValueError('Expected GLB')
    length=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+length]);binary=raw[28+length:]
    def accessor(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
        columns={'SCALAR':1,'VEC3':3}[a['type']]
        return np.ndarray((a['count'],columns),dtype=dtype,buffer=binary,
            offset=v.get('byteOffset',0)+a.get('byteOffset',0),
            strides=(v.get('byteStride',dtype.itemsize*columns),dtype.itemsize)).copy()
    points=[];faces=[]
    for primitive in doc['meshes'][lod]['primitives']:
        if doc['materials'][primitive['material']]['name']!=material:continue
        p=accessor(primitive['attributes']['POSITION']).astype(np.float64)
        f=accessor(primitive['indices']).reshape(-1,3).astype(np.int64)
        if f.min()<0 or f.max()>=len(p):raise ValueError('Invalid source index')
        used=np.unique(f);remap=np.full(len(p),-1);remap[used]=np.arange(len(used))
        faces.extend((remap[f]+len(points)).tolist());points.extend(p[used].tolist())
    if not points:raise ValueError('Expected indexed bark primitive')
    # Both exporter and Blender assembly publish identity object transforms.
    # Refuse a future hidden transform rather than applying a guessed frame.
    for node in doc.get('nodes',[]):
        if node.get('mesh')==lod and any(k in node for k in ('matrix','translation','rotation','scale')):
            raise ValueError('Nonidentity GLB node transform requires an explicit source contract')
    return np.asarray(points)[:,[0,2,1]]*100,np.asarray(faces),doc


def clipped_points(points,faces,lo,hi):
    """All vertices of source triangles clipped to the closed height band."""
    result=[p for p in points if lo<=p[2]<=hi]
    edges=np.unique(np.sort(np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1),axis=0)
    a,b=points[edges[:,0]],points[edges[:,1]]
    for height in (lo,hi):
        crossing=(np.minimum(a[:,2],b[:,2])<height)&(np.maximum(a[:,2],b[:,2])>height)
        aa,bb=a[crossing],b[crossing]
        t=(height-aa[:,2])/(bb[:,2]-aa[:,2])
        result.extend(aa+(bb-aa)*t[:,None])
    return np.unique(np.asarray(result),axis=0)


def bounded_band(source,budget):
    """Greedily clip measured support planes; never discard source vertices.

    Axis bounds start the enclosure. Each added original convex-hull plane
    removes its most excessive corner. This avoids the large false walls
    produced by a single affine taper across the flared root collar.
    """
    dense=ConvexHull(source);planes=[];centre=source.mean(0);last=None
    for axis in range(3):
        for sign,extreme in ((1,source[:,axis].max()),(-1,source[:,axis].min())):
            plane=np.zeros(4);plane[axis]=sign;plane[3]=-sign*extreme;planes.append(plane)
    for _ in range(100):
        p=HalfspaceIntersection(np.asarray(planes),centre).intersections;hull=ConvexHull(p)
        if len(hull.simplices)>budget:break
        excess=p@dense.equations[:,:3].T+dense.equations[:,3]
        point,plane=np.unravel_index(np.argmax(excess),excess.shape)
        last=(p,hull)
        if excess[point,plane]<.001:break
        planes.append(dense.equations[plane])
    if last is None:raise ValueError('Trunk face budget cannot contain a box')
    p,hull=last;used=np.unique(hull.simplices);remap=np.full(len(p),-1);remap[used]=np.arange(len(used))
    triangles=[]
    for f,equation in zip(hull.simplices,hull.equations):
        if np.dot(np.cross(p[f[1]]-p[f[0]],p[f[2]]-p[f[0]]),equation[:3])<0:f=f[[0,2,1]]
        triangles.append(remap[f].tolist())
    return p[used],triangles


def audit_band(points,faces,source):
    triangles=points[np.asarray(faces)]
    n=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    areas=np.linalg.norm(n,axis=1)/2;n/=np.linalg.norm(n,axis=1)[:,None]
    offsets=-np.einsum('ij,ij->i',n,triangles[:,0])
    deficit=float(np.max(source@n.T+offsets))
    dense=ConvexHull(source)
    overreach=float(np.max(points@dense.equations[:,:3].T+dense.equations[:,3]))
    centre=points.mean(0)
    volume=float(np.einsum('ij,ij->i',triangles[:,0]-centre,np.cross(triangles[:,1]-centre,triangles[:,2]-centre)).sum()/6)
    return {'vertices':len(points),'triangles':len(faces),'maximum_source_plane_deficit_cm':max(0,deficit),
        'maximum_vertex_distance_beyond_source_convex_planes_cm':max(0,overreach),
        'minimum_triangle_area_cm2':float(areas.min()),'signed_volume_cm3':volume}


def audit_surface_samples(points,faces,source_mesh):
    """Exact nearest-source-triangle distances at a finite stated sample set.

    This is not a Hausdorff bound between every point of the two surfaces.
    Horizontal band caps are internal, so only side-face interiors are used.
    All hull vertices remain included in the explicit measurement.
    """
    t=points[np.asarray(faces)]
    n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    t=t[np.abs(n[:,2])<.99999]
    samples=np.unique(np.concatenate((points,t.mean(1),(t[:,0]+t[:,1])/2,
        (t[:,1]+t[:,2])/2,(t[:,2]+t[:,0])/2)),axis=0)
    distances=[]
    for start in range(0,len(samples),20):
        distances.extend(trimesh.proximity.closest_point_naive(source_mesh,samples[start:start+20])[1].tolist())
    distances=np.asarray(distances);index=int(np.argmax(distances))
    return {'method':'all hull vertices plus side-face centroids and edge midpoints; exact nearest original triangle',
        'samples':len(samples),'maximum_sampled_surface_gap_cm':float(distances[index]),
        'p95_sampled_surface_gap_cm':float(np.quantile(distances,.95)),
        'worst_sample_cm':samples[index].tolist(),'continuous_surface_error_bound':False}


def build(source_path,assembled_path,output,receipt_path):
    source=json.loads(source_path.read_text())
    parts=[p for p in source['recipe']['parts'] if p['mesh']==TRUNK]
    entry=next(a for a in source['assets'] if a['mesh']==TRUNK)
    if len(parts)!=1 or parts[0]['off']!=[0,0,0] or source['source_height_m']!=217.199:
        raise ValueError('Changed trunk recipe transform')
    if entry['selected_lod']!=1 or sha(entry['glb'])!=entry['sha256']:
        raise ValueError('Changed selected original trunk or unsealed export')
    original,faces,_=read_mesh(entry['glb'],1,BARK);original*=SCALE
    original_mesh=trimesh.Trimesh(vertices=original,faces=faces,process=False)
    assembled,_,doc=read_mesh(assembled_path,0,BARK)
    if len(doc['meshes'])!=1:raise ValueError('Unexpected assembled mesh count')
    distances=cKDTree(assembled).query(original)[0]
    if distances.max()>.002:raise ValueError('Assembled asset does not preserve the measured trunk')
    bounds=np.stack((original.min(0),original.max(0)))
    # Original authoring pivot is the approved planting datum. The first
    # band is the intentionally buried root flare; budget the visible stem
    # separately to avoid a large convex bridge from roots into the crown.
    boundaries=[bounds[0,2],0.,100.,500.,1600.,bounds[1,2]]
    budgets=[20,40,32,44,44]
    points=[];triangles=[];audits=[]
    for lo,hi,budget in zip(boundaries[:-1],boundaries[1:],budgets):
        clipped=clipped_points(original,faces,lo,hi)
        p,f=bounded_band(clipped,budget)
        # Preserve six decimal centimetres; audit these serialized values.
        p=np.round(p,6);audit=audit_band(p,f,clipped)
        if audit['maximum_source_plane_deficit_cm']>.001:raise ValueError('Serialized trunk hull misses source by >0.01mm')
        if audit['signed_volume_cm3']<=0 or audit['minimum_triangle_area_cm2']<.001:raise ValueError('Invalid serialized trunk hull')
        surface=audit_surface_samples(p,f,original_mesh)
        if surface['maximum_sampled_surface_gap_cm']>(91 if hi<=0 else 32):
            raise ValueError('Trunk enclosure exceeds reviewed buried-root/visible-stem sample error')
        audit['actual_surface_samples']=surface
        audit['relative_to_planting_datum']='buried_root_flare' if hi<=0 else 'above_ground_stem'
        audit.update(height_range_cm=[float(lo),float(hi)],clipped_source_points=len(clipped));audits.append(audit)
        triangles.extend([[i+len(points) for i in face] for face in f]);points.extend(p.tolist())
    if len(triangles)>180:raise ValueError('Exceeded 180 triangle trunk budget')
    cache={'mesh':PWR_MATURE_PINE,'collision_scope':'trunk_only','bark_material_slots':[BARK],
        'source_geometry_sha256':sha(assembled_path),'source_trunk_mesh':TRUNK,
        'source_trunk_geometry_sha256':sha(entry['glb']),'source_trunk_lod':1,
        'measured_trunk_bounds_cm':bounds.tolist(),'points':points,'faces':triangles}
    validate_mature_trunk_cache(cache)
    if output.exists() or receipt_path.exists():raise ValueError('Refuse to overwrite a cache or receipt')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(cache,separators=(',',':'))+'\n')
    loaded_p,loaded_f=hull_of(PWR_MATURE_PINE,str(output.parent),expected_geometry_sha256=sha(assembled_path))
    if not np.array_equal(loaded_p,np.asarray(points)) or loaded_f!=triangles:raise ValueError('b30 cache readback differs')
    report={'schema':'pwr-mature-pine-trunk-collision-v1','installed':False,'cache':str(output.resolve()),'cache_sha256':sha(output),
        'source_index_sha256':sha(source_path),'source_glb':str(Path(entry['glb']).resolve()),'source_glb_sha256':sha(entry['glb']),
        'assembled_glb':str(assembled_path.resolve()),'assembled_glb_sha256':sha(assembled_path),'scale':SCALE,
        'planting_root_z_cm':0,'planting_policy':'Original authoring pivot rests on PCG ground; min_z is bounds metadata only.',
        'source_lod':1,'indexed_source_vertices':len(original),'indexed_source_triangles':len(faces),
        'assembled_trunk_nearest_vertex_max_cm':float(distances.max()),'measured_trunk_bounds_cm':bounds.tolist(),
        'total_triangles':len(triangles),'bands':audits,'closed_outward_positive_volume':True,'b30_readback_exact':True,
        'scope':'Approximate conservative fit of original classic Trunk LOD1 only; all crown branches and needles excluded. Convex bands fill bark concavities. Buried flare is deliberately coarser; slope-dependent exposed roots still require live contact validation.',
        'live_contact_acceptance_pending':True}
    receipt_path.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--assembled',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(args.source,args.assembled,args.out,args.receipt),indent=2))
