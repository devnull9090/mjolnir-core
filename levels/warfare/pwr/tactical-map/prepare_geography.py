"""Freeze measured current dressing footprints; no game/editor access."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
from scipy.spatial import ConvexHull

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from world_geometry import base_parts

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    geometry=ROOT/'levels/warfare/pwr/terrain/final-v5/terrain.geometry.json'
    paving=ROOT/'out/pwr/visual-v5/base-paving-v3/footprints.geojson'
    trees=ROOT/'out/pwr/visual-v6/scenery/trees/trees.selected.json'
    data=json.loads(geometry.read_text())
    footprints=[]
    for piece in base_parts(data):
        if piece['material'] in ('energy','floor') or not piece['collision']:continue
        xy=np.unique(np.asarray(piece['vertices_m'])[:,:2],axis=0)
        if len(xy)<3:continue
        polygon=xy[ConvexHull(xy).vertices].tolist()
        footprints.append({'name':piece['name'],'polygon_m':polygon})
    selected=json.loads(trees.read_text())['instances']
    assert len(selected)==4702
    out={'schema':'pwr-tactical-map-geography-v1','coordinates':'authoring_metres_z_up',
         'tree_canopy_centres_m':[[r['position'][0],r['position'][1],r['scale']] for r in selected],
         'paving':json.loads(paving.read_text()),'structural_footprints':footprints,
         'limits':'Existing closed macro-body projected footprints; fine native cladding/spire details are intentionally below map scale. No proposed V9 architecture is included.',
         'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in (geometry,paving,trees,HERE.parent/'world_geometry.py',HERE.parent/'forerunner_kit.py',Path(__file__))]}
    (HERE/'geography.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    print(f'Frozen {len(selected)} tree positions, {len(footprints)} existing structural footprints and 3 paving groups')

if __name__=='__main__':main()
