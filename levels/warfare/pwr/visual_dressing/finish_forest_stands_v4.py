# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3"]
# ///
"""Preserve reviewed804 rocks and filter grass against measured new trunks."""
from pathlib import Path
import argparse,copy,json,shutil,struct,sys
import numpy as np
from scipy.spatial import ConvexHull
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
import b30_collision,pcg_foliage,pcg_tree_decor
from authored_decor import expand_background_trees
from heightfield import sha256

OUT=ROOT/'out/pwr/visual-v5/outcrops-v4'
BASE=ROOT/'out/pwr/visual-v5/outcrops-v3'
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
PAVING=ROOT/'out/pwr/visual-v5/base-paving-v3/footprints.geojson'


def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def preserve_rocks():
    OUT.mkdir(parents=True,exist_ok=True);hulls=OUT/'hulls';hulls.mkdir(exist_ok=True)
    baseline=BASE/'rocks-and-outcrops.authored-decor.json';document=json.loads(baseline.read_text())
    if len(document['decor'])!=804:raise ValueError('Reviewed804rock baseline changed')
    result=copy.deepcopy(document)
    result['visual_v4_provenance'].update(source_rocks_sha256=sha256(baseline),
        generation='Exact reviewed804rock reuse; independent new UEPCG woodland only',
        frozen_runtime_master_sha256=sha256(MASTER),paving_sha256=sha256(PAVING))
    dump(OUT/'rocks-and-outcrops.authored-decor.json',result)
    copied=[]
    for source in (BASE/'hulls').glob('SM_*.json'):
        destination=hulls/source.name
        if destination.exists() and sha256(destination)!=sha256(source):raise ValueError('Existing isolated cache differs: '+source.name)
        if not destination.exists():shutil.copy2(source,destination)
        copied.append({'source':str(source),'destination':str(destination),'sha256':sha256(source)})
    dump(OUT/'baseline-reuse.receipt.json',{'schema':'pwr-scenery-baseline-reuse-v1',
        'source':str(baseline),'source_sha256':sha256(baseline),'output_sha256':sha256(OUT/'rocks-and-outcrops.authored-decor.json'),
        'rock_records_exact':True,'rock_count':804,'hulls':copied})
    return result


def main(max_native_surfaces=800000):
    if max_native_surfaces<=0:raise ValueError('Explicit native surface budget must be positive')
    rocks=preserve_rocks();source=OUT/'trees/trees.selected.json';recipes=OUT/'trees/recipes.json'
    tree_doc=pcg_foliage.load(source);recipe_doc=pcg_foliage.load(recipes)
    authored=pcg_tree_decor.convert(tree_doc,recipe_doc,max_trees=5000)
    decor,leaves=expand_background_trees(authored,recipe_doc,{})
    if leaves or len(decor)!=len(tree_doc['instances']):raise ValueError('Expected one complete mesh per tree')
    footprints=[];tree_triangles=0
    for row in decor:
        points,faces=b30_collision.hull_of(row['mesh'],str(OUT/'hulls'),expected_geometry_sha256=row.get('source_geometry_sha256'))
        p=(points*np.asarray(row['scale']))@b30_collision.rotator_matrix(*row['rot'])+row['pos']
        xy=p[:,:2]*[.01,-.01];footprints.append(Polygon(xy[ConvexHull(xy).vertices]).buffer(.25))
        tree_triangles+=len(faces)
    area=unary_union(footprints)
    grass=BASE/'grass/foliage.json';spec,groups=pcg_foliage.read_mjf_groups(grass)
    out=OUT/'grass';out.mkdir(exist_ok=True);kept=[];summary=[]
    for index,(group,payload,sidecars,count) in enumerate(groups,1):
        xyz=np.frombuffer(sidecars['xf'],dtype='<f4').reshape(count,10)[:,:3]*[.01,-.01,.01]
        keep=~shapely.intersects_xy(area,xyz[:,0],xyz[:,1]);n=int(keep.sum())
        records=np.frombuffer(payload[4:],dtype=np.dtype((np.void,19)))
        filtered={suffix:np.frombuffer(data,dtype=np.dtype((np.void,40 if suffix=='xf' else 16)))[keep].tobytes() for suffix,data in sidecars.items()}
        kept.append((group,struct.pack('<I',n)+records[keep].tobytes(),filtered,n))
        summary.append({'group':index,'input':count,'retained':n,'removed_trunk_footprint':count-n})
    binary=out/'foliage.bin';binary.write_bytes(b'MJF3'+struct.pack('<II',3,len(kept))+b''.join(r[1] for r in kept))
    for index,(_,_,sidecars,_) in enumerate(kept,1):
        for suffix,data in sidecars.items():Path(str(binary)+'.'+suffix+str(index)).write_bytes(data)
    dump(out/'foliage.json',{'file':'foliage.bin','groups':[row[0] for row in kept]})
    pcg_foliage.read_mjf_groups(out/'foliage.json')
    rock_triangles=0
    for row in rocks['decor']:
        cache=OUT/'hulls'/(row['mesh'].split('.')[-1]+'.json')
        rock_triangles+=len(json.loads(cache.read_text())['faces'])
    total=9+144172+rock_triangles+tree_triangles
    if total>max_native_surfaces:raise ValueError('Predicted native surface budget exceeded')
    report={'schema':'pwr-forest-stand-foliage-handoff-v1','runtime_master_sha256':sha256(MASTER),
        'paving_sha256':sha256(PAVING),'rocks':804,'rock_records_exact':True,'trees':len(decor),
        'tree_selection_sha256':sha256(source),'recipes_sha256':sha256(recipes),
        'grass_source':str(grass),'grass_source_sha256':sha256(grass),'grass':sum(x['retained'] for x in summary),
        'grass_groups':summary,'retained_grass_transform_bytes_exact':True,'trunk_footprint_buffer_m':.25,
        'projected_native_surface_count':total,'explicit_native_surface_budget':max_native_surfaces,
        'tree_hull_triangles':tree_triangles,'rock_hull_triangles':rock_triangles,
        'native_compilation_live_acceptance_performance_pending':True}
    dump(OUT/'receipt.json',report)
    seal={'schema':'pwr-forest-stand-candidate-seal-v1','files':{str(p.relative_to(OUT)):sha256(p) for p in
        [OUT/'rocks-and-outcrops.authored-decor.json',source,recipes,out/'foliage.json',binary,OUT/'receipt.json']+
        sorted(out.glob('foliage.bin.*'))+sorted((OUT/'hulls').glob('SM_*.json'))}}
    dump(OUT/'seal.json',seal);print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-only',action='store_true')
    parser.add_argument('--max-native-surfaces',type=int,default=800000)
    args=parser.parse_args()
    preserve_rocks() if args.baseline_only else main(args.max_native_surfaces)
