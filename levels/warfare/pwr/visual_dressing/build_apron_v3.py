# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "pyamg>=5,<6"]
# ///
"""Join the fixed boundary to continuous Gaea relief through a 2D displacement.

No boundary height or slope is extruded down a radial ray. A clamped thin-plate
solve spreads displacement in both planar directions while matching the
boundary slope and retaining the source's eroded relief. Blender MCP constructs the
review mesh from this exact sampled field. Never installs or edits gameplay.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'tools/level'))
from heightfield import load_heightfield, sha256

MASTER = ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
SOURCE = ROOT/'levels/warfare/pwr/terrain/gaea-v5c/source.json'
OUT = ROOT/'out/pwr/visual-v5/apron-v3'


def eroded(gaea, x, y, gain=2.45):
    # Smooth, strictly monotonic mapping of one continuous field. It places the
    # real Gaea ridge belt at source0.71–0.82km around world1.3–1.7km rather
    # than stretching the source's flat central valley around the entire map.
    sx=1000*np.tanh(np.asarray(x)/1500)/np.tanh(4000/1500)
    sy=1000*np.tanh(np.asarray(y)/1500)/np.tanh(4000/1500)
    return 70 + (gaea.sample(sx,sy)-70)*gain


def source_height(gaea,x,y,mapping='ridge_belt'):
    if mapping=='native_8km':
        maximum=np.asarray(gaea.origin_m)+(np.asarray(gaea.dimensions)-1)*np.asarray(gaea.spacing_m)
        if not np.allclose(gaea.origin_m,[-4000,-4000]) or not np.allclose(maximum,[4000,4000]):
            raise ValueError('Direct backdrop sampling requires the independent native 8 km source')
        return gaea.sample(x,y)
    if mapping!='ridge_belt':raise ValueError('Unknown backdrop source mapping')
    return eroded(gaea,x,y)


def solve(master=MASTER, source=SOURCE, out=OUT, padding=252, mapping='ridge_belt'):
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import cg, LinearOperator
    from scipy.ndimage import binary_dilation
    import pyamg
    started = time.monotonic()
    master, source, out = Path(master), Path(source), Path(out)
    field, gaea = load_heightfield(master), load_heightfield(source)
    if field.dimensions != (1009, 1009) or not 150 <= padding <= 400:
        raise ValueError('Expected reviewed runtime grid and a bounded outer collar')
    out.mkdir(parents=True, exist_ok=True)
    spacing = field.spacing_m[0]
    n = 1009 + 2*padding
    axis = (np.arange(n)-padding)*spacing - 1000
    x, y = np.meshgrid(axis, axis)
    base = source_height(gaea, x, y, mapping)
    fixed = np.zeros((n,n), bool)
    fixed[padding:padding+1009, padding:padding+1009] = True
    fixed[[0,1,-2,-1],:] = True
    fixed[:,[0,1,-2,-1]] = True
    displacement = np.zeros_like(base)
    displacement[padding:padding+1009,padding:padding+1009] = field.heights_m-base[padding:padding+1009,padding:padding+1009]
    free = ~fixed
    row, col = np.nonzero(free)
    count = len(row)
    index = np.full((n,n), -1, dtype=np.int32)
    index[free] = np.arange(count, dtype=np.int32)
    ids = np.arange(count, dtype=np.int32)
    rows, cols, values = [ids], [ids], [np.full(count,4.)]
    rhs = np.zeros(count)
    for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
        nr, nc = row+dr, col+dc
        ni = index[nr,nc]
        active = ni >= 0
        rows.append(ids[active]); cols.append(ni[active]); values.append(np.full(active.sum(),-1.))
        rhs[~active] += displacement[nr[~active],nc[~active]]
    matrix = coo_matrix((np.concatenate(values),(np.concatenate(rows),np.concatenate(cols))), shape=(count,count)).tocsr()
    del rows,cols,values
    hierarchy = pyamg.ruge_stuben_solver(matrix)
    residuals=[]
    solution, status = cg(matrix,rhs,M=hierarchy.aspreconditioner(),rtol=1e-10,atol=1e-9,maxiter=100,
                          callback=lambda z: residuals.append(float(np.linalg.norm(rhs-matrix@z))))
    if status != 0:
        raise RuntimeError(f'Harmonic solve failed: {status}')
    residual = float(np.max(abs(matrix@solution-rhs)))
    if residual > 1e-5:
        raise ValueError(f'Unexpected Laplacian residual {residual}')
    # Full-grid Laplacian rows adjacent to both fixed regions constrain the
    # slope as well as height. Minimizing only free rows would be the harmonic
    # solution above and would leave a visible crease at the clipped mountain.
    active_rows = binary_dilation(free)
    rr, cc = np.nonzero(active_rows)
    equation_ids = np.arange(len(rr),dtype=np.int32)
    br, bc, bv = [], [], []
    fixed_laplacian = np.zeros(len(rr))
    for dr,dc,coefficient in ((0,0,4.),(0,1,-1.),(0,-1,-1.),(1,0,-1.),(-1,0,-1.)):
        nr,nc=rr+dr,cc+dc
        ni=index[nr,nc]
        is_free=ni>=0
        br.append(equation_ids[is_free]);bc.append(ni[is_free]);bv.append(np.full(is_free.sum(),coefficient))
        fixed_laplacian[~is_free]+=coefficient*displacement[nr[~is_free],nc[~is_free]]
    operator=coo_matrix((np.concatenate(bv),(np.concatenate(br),np.concatenate(bc))),shape=(len(rr),count)).tocsr()
    del br,bc,bv
    transpose=operator.T.tocsr()
    normal=LinearOperator((count,count),matvec=lambda z:transpose@(operator@z))
    pre=hierarchy.aspreconditioner()
    squared_pre=LinearOperator((count,count),matvec=lambda z:pre@(pre@z))
    thin_rhs=-(transpose@fixed_laplacian)
    iterations=[]
    solution,status=cg(normal,thin_rhs,x0=solution,M=squared_pre,rtol=1e-8,atol=1e-9,maxiter=300,
                       callback=lambda z:iterations.append(len(iterations)))
    if status!=0:
        raise RuntimeError(f'Clamped thin-plate solve failed: {status}')
    normal_residual=float(np.linalg.norm(normal@solution-thin_rhs)/np.linalg.norm(thin_rhs))
    displacement[free] = solution
    # Outer two fixed rings are exactly zero correction. Boundary-crossing
    # Laplacian stencils clamp its slope without an explicit radial blend.
    extent = padding*spacing
    correction = displacement
    height = base+correction
    height[padding:padding+1009,padding:padding+1009] = field.heights_m
    assert np.array_equal(height[padding:padding+1009,padding:padding+1009],field.heights_m)
    assert np.array_equal(height[[0,-1],:],base[[0,-1],:])
    gy,gx = np.gradient(height,spacing)
    slope = np.hypot(gx,gy)
    # Matched one-sided slope evidence, not a claim of exact C1 continuity.
    seam_jumps=[]
    for view in (height,height.T,height[::-1],height.T[::-1]):
        r=padding
        seam_jumps.append((view[r-1,r:r+1009]-2*view[r,r:r+1009]+view[r+1,r:r+1009])/spacing)
    jumps=abs(np.concatenate(seam_jumps))
    np.savez_compressed(out/'harmonic-field.npz',heights_m=height,origin_m=np.array([axis[0],axis[0]]),spacing_m=spacing)
    receipt={'schema':'pwr-apron-thin-plate-join-v1','runtime_master_sha256':field.manifest_sha256,
        'source_gaea_sha256':gaea.manifest_sha256,'source_gaea_height_sha256':gaea.metadata['height']['sha256'],
        'method':'2D clamped thin-plate displacement; full-grid boundary stencils preserve slope; no radial tangent extrusion',
        'source_mapping':'source_axis=1000*tanh(world_axis/1500)/tanh(4000/1500); z=70+(source-70)*2.45','spacing_m':spacing,
        'source_mapping_derivative_strictly_positive':True,'source_radius_at_world1300_1700_m':[float(1000*np.tanh(v/1500)/np.tanh(4000/1500)) for v in (1300,1700)],
        'collar_m':extent,'unknowns':count,'cg_iterations':len(residuals),'max_laplacian_residual_m':residual,
        'thin_plate_iterations':len(iterations),'thin_plate_relative_residual':normal_residual,
        'solve_seconds':time.monotonic()-started,'field_sha256':sha256(out/'harmonic-field.npz'),
        'exact_playable_grid_preserved':True,'no_native_collision':True,
        'join_normal_gradient_jump_percentiles':dict(zip(['p50','p90','p99','max'],np.quantile(jumps,[.5,.9,.99,1]).tolist())),
        'collar_slope_percentiles':dict(zip(['p50','p90','p99','max'],np.quantile(slope[free],[.5,.9,.99,1]).tolist()))}
    if mapping=='native_8km':
        receipt.update(mapping_mode=mapping,source_mapping='Independent native 8000 m source at world XY; original calibrated elevation, no stretch or amplification')
        receipt.pop('source_radius_at_world1300_1700_m')
    (out/'join.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    return receipt


def sampler(master=MASTER,source=SOURCE,out=OUT):
    """NumPy-only sampler used in Blender; solver provenance checked first."""
    out=Path(out)
    receipt=json.loads((out/'join.receipt.json').read_text())
    if receipt['runtime_master_sha256']!=sha256(master) or receipt['source_gaea_sha256']!=sha256(source):
        raise ValueError('Apron source provenance changed')
    if receipt['field_sha256']!=sha256(out/'harmonic-field.npz'):
        raise ValueError('Apron joined field hash changed')
    data=np.load(out/'harmonic-field.npz')
    h,origin,spacing=data['heights_m'],data['origin_m'],float(data['spacing_m'])
    gaea=load_heightfield(source)
    maximum=origin+(np.array(h.shape[::-1])-1)*spacing
    def sample(x,y):
        x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
        result=np.array(source_height(gaea,x,y,receipt.get('mapping_mode','ridge_belt')),copy=True)
        valid=(x>=origin[0])&(x<=maximum[0])&(y>=origin[1])&(y<=maximum[1])
        u=(x[valid]-origin[0])/spacing;v=(y[valid]-origin[1])/spacing
        ix=np.minimum(np.floor(u).astype(int),h.shape[1]-2);iy=np.minimum(np.floor(v).astype(int),h.shape[0]-2)
        tx=u-ix;ty=v-iy
        result[valid]=(h[iy,ix]*(1-tx)+h[iy,ix+1]*tx)*(1-ty)+(h[iy+1,ix]*(1-tx)+h[iy+1,ix+1]*tx)*ty
        return result
    return sample,receipt


def build(master=MASTER,source=SOURCE,out=OUT):
    import build_apron_v2
    sample,receipt=sampler(master,source,out)
    metadata={'schema':'pwr-apron-v3','source_mapping':receipt['source_mapping'],
              'join_method':receipt['method'],'join_receipt_sha256':sha256(Path(out)/'join.receipt.json')}
    specs=[(1000.,1),(1004.,1),(1012.,2),(1024.,2)]
    radius=1040.
    while radius<2200:
        specs.append((radius,4));radius+=16
    specs.append((2200.,4))
    radius=2200.
    while radius<4000:
        tangent=(radius+32)/1000*(2000/1008)*8
        radius+=min(32.,(95.-tangent)/math.sqrt(2),4000-radius)
        specs.append((radius,8))
    return build_apron_v2.build(master,source,out,height_sampler=sample,method_metadata=metadata,ring_specs=specs)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['solve','build'])
    parser.add_argument('--master',type=Path,default=MASTER)
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args()
    globals()[args.command](args.master,args.source,args.out)
