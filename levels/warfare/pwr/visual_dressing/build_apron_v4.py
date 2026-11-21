# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "pyamg>=5,<6"]
# ///
"""Detailed native 8 km Gaea backdrop with the exact frozen 2 km seam.

Only a bounded 2D displacement collar joins the independent source to the
gameplay border. Beyond that collar every elevation samples native Gaea at
its original world spacing: no old-source upscaling, height amplification,
mirrored ridge field, radial slope extrusion or procedural Gaussian masses.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import build_apron_v3 as join
import build_apron_v2 as mesh

ROOT=Path(__file__).resolve().parents[4]
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
SOURCE=ROOT/'levels/warfare/pwr/terrain/gaea-apron-v4/source.json'
OUT=ROOT/'out/pwr/visual-v5/apron-v4'


def build(master=MASTER,source=SOURCE,out=OUT):
    out=Path(out)
    sample,receipt=join.sampler(master,source,out)
    if receipt.get('mapping_mode')!='native_8km':
        raise ValueError('A native-domain collar solve is required')
    # <=16 m radial sampling on the near ranges; tangential resolution slowly
    # decimates from the exact4032 boundary vertices. The 1024 Gaea source is
    # 7.82 m per sample, so retain it closely near the primary viewed ridges.
    specs=[(1000.,1),(1004.,1),(1012.,2),(1024.,2)]
    specs.extend((float(r),2) for r in range(1040,2201,16))
    if specs[-1][0]!=2200:specs.append((2200.,2))
    specs.extend((float(r),4) for r in range(2216,4001,16))
    if specs[-1][0]!=4000:specs.append((4000.,4))
    result=mesh.build(master,source,out,height_sampler=sample,ring_specs=specs,
        method_metadata={'schema':'pwr-apron-v4','source_mapping':receipt['source_mapping'],
            'join_method':receipt['method'],'join_receipt_sha256':join.sha256(out/'join.receipt.json'),
            'independent_domain_m':8000,'source_stretch':False,'height_amplification':False,
            'elevation_gain':1.,'blend_m':receipt['collar_m']})
    arrays=np.load(out/'apron.source.npz');vertices=arrays['vertices_m']
    outside=np.max(abs(vertices[:,:2]),axis=1)>1000+receipt['collar_m']+1
    native=join.load_heightfield(source).sample(vertices[outside,0],vertices[outside,1])
    if np.max(abs(native-vertices[outside,2]))>1e-7:
        raise ValueError('Outer backdrop must sample the native8km source exactly; stale sampler/mapping detected')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['solve','build'])
    p.add_argument('--master',type=Path,default=MASTER)
    p.add_argument('--source',type=Path,default=SOURCE)
    p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--collar-cells',type=int,default=150)
    a=p.parse_args()
    if a.command=='solve':join.solve(a.master,a.source,a.out,a.collar_cells,mapping='native_8km')
    else:build(a.master,a.source,a.out)
