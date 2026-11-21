# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3", "pillow>=11,<13"]
# ///
"""Read native meshes and create isolated full-LOD cliff hulls. Never installs."""
import argparse,json,subprocess
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from outcrops_v3 import ROOT,OUT,lod0_points,sha256,dump


def prepare(export=False):
    (OUT/'assets').mkdir(parents=True,exist_ok=True)
    (OUT/'hulls').mkdir(parents=True,exist_ok=True)
    catalogue=json.loads((ROOT/'out/pwr/visual-v4/assets/rock-bounds.json').read_text())
    reports=[]
    for suffix in 'ABCD':
        leaf='SM_Rock_Desert_Cliff_'+suffix
        path=OUT/'assets'/(leaf+'.glb')
        if export or not path.is_file():
            command=[str(ROOT/'target/release/mjolnir.exe'),'mesh','export','--paks',
                     'C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks',
                     '--asset',leaf,'--out',str(path)]
            result=subprocess.run(command,capture_output=True,text=True,check=True)
            (OUT/'assets'/(leaf+'.log')).write_text(result.stdout+result.stderr)
        source=next(x for x in catalogue if x['path'].split('.')[-1]==leaf)
        full=lod0_points(path);convex=ConvexHull(full)
        used=convex.vertices;remap=np.full(len(full),-1);remap[used]=np.arange(len(used))
        points=full[used];faces=remap[convex.simplices]
        a,b,c=(points[faces[:,i]] for i in range(3));normal=np.cross(b-a,c-a)
        flip=np.sum((points.mean(0)-a)*normal,axis=1)>0;faces[flip]=faces[flip][:,[0,2,1]]
        edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
        _,counts=np.unique(edges,axis=0,return_counts=True)
        if not np.all(counts==2):raise ValueError('Full source hull is not closed')
        cache={'mesh':source['path'],'points':points.round(8).tolist(),'faces':faces.tolist()}
        target=OUT/'hulls'/(leaf+'.json');target.write_text(json.dumps(cache))
        reports.append({'mesh':source['path'],'source_lod0_vertices':len(full),'hull_vertices':len(points),
            'faces':len(faces),'source_sha256':sha256(path),'hull_sha256':sha256(target),
            'paired_edges':True,'method':'scipy QHull over every LOD0 vertex; outward oriented; cm rounded8decimals',
            'native_serialization_and_compiler_acceptance':'must be checked on final transforms'})
    dump(OUT/'hulls/source.receipt.json',reports)
    # Scree reuses the already reviewed glacial collision recipes. Only export
    # render geometry here, for full-LOD clearance and the Blender preview.
    for suffix in 'ABC':
        leaf='SM_Rock_Glacial_Med_'+suffix;path=OUT/'assets'/(leaf+'.glb')
        if export or not path.is_file():
            subprocess.run([str(ROOT/'target/release/mjolnir.exe'),'mesh','export','--paks',
              'C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks',
              '--asset',leaf,'--out',str(path)],check=True)
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--export',action='store_true')
    prepare(p.parse_args().export)
