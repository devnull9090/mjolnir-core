"""Audit native packaged apron geometry against its fixed field and source mesh."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield,sha256
from b30_collision import glb_positions


def main(out=ROOT/'out/pwr/visual-v5/apron-v2', maximum_error_m=.005):
    out=Path(out).resolve()
    if not 0<maximum_error_m<=.005:raise ValueError('Readback tolerance must be between0 and5mm')
    field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    source=np.load(out/'apron.source.npz');v=source['vertices_m'];tri=source['triangles']
    receipt=json.loads((out/'receipt.json').read_text());actor=json.loads((out/'runtime_decor.json').read_text())['decor'][0]
    assert receipt['runtime_master_sha256']==field.manifest_sha256
    h=field.heights_m
    boundary_heights=np.concatenate([h[0,:-1],h[:-1,-1],h[-1,:0:-1],h[:0:-1,0]])
    assert np.array_equal(v[:4032,2],boundary_heights)
    actual=glb_positions(out/'roundtrip.glb')*np.array(actor['scale'])+actor['pos']
    assert len(actual)==len(v)
    error=np.linalg.norm(actual-v*np.array([100,-100,100]),axis=1)/100
    assert error.max()<=maximum_error_m and error[:4032].max()<=maximum_error_m
    edges=np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    assert counts.max()==2
    boundary=unique[counts==1]
    if receipt.get('schema') == 'pwr-apron-v7':
        outer_count=receipt['outer_boundary_edges']
        assert isinstance(outer_count,int) and outer_count>0
        inner=np.all(np.max(abs(v[boundary,:2]),axis=2)==1000,axis=1)
        outer=np.all(np.max(abs(v[boundary,:2]),axis=2)==4000,axis=1)
        assert np.count_nonzero(inner)==4032 and np.count_nonzero(outer)==outer_count
        assert np.all(inner|outer)
        expected_edges=4032+outer_count
    else:
        outer_stride=receipt['radial_rings'][-1][1]
        assert isinstance(outer_stride,int) and outer_stride>0 and 4032%outer_stride==0
        expected_edges=4032+4032//outer_stride
    assert len(boundary)==expected_edges
    assert not np.any((boundary[:,0]<4032)!=(boundary[:,1]<4032))
    t=v[tri];xy=t[:,:,:2]
    # Every triangle lies wholly beyond at least one side of the fixed square.
    assert np.all(np.any(np.all(xy>=1000-1e-8,axis=1)|np.all(xy<=-1000+1e-8,axis=1),axis=1))
    maximum_edge=max(float(np.linalg.norm(xy[:,a]-xy[:,b],axis=1).max()) for a,b in ((0,1),(1,2),(2,0)))
    assert maximum_edge<=100
    doc={'schema':receipt['schema']+'-native-readback','runtime_master_sha256':field.manifest_sha256,
         'geometry_receipt_sha256':sha256(out/'receipt.json'),'package_receipt_sha256':sha256(out/'package.receipt.json'),
         'native_roundtrip_vertices':len(actual),'native_max_position_error_m':float(error.max()),
         'native_max_seam_error_m':float(error[:4032].max()),'manifold_edge_max_incidence':int(counts.max()),
         'maximum_permitted_readback_error_m':maximum_error_m,
         'open_edges':len(boundary),'expected_inner_plus_outer_edges':expected_edges,'maximum_horizontal_edge_m':maximum_edge,
         'triangles_do_not_enter_playable_square':True,'installed':False,'live_visual_acceptance':'pending'}
    (out/'roundtrip.verification.json').write_text(json.dumps(doc,indent=2)+'\n');print(json.dumps(doc,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v5/apron-v2')
    parser.add_argument('--maximum-error-m',type=float,default=.005)
    args=parser.parse_args();main(args.out,args.maximum_error_m)
