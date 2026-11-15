"""Extract actual mature native pine components into an isolated review cache.

The stock Tree_Pine recipe was recovered from A30 cells. It is an assembly,
not an unverified tree-shaped mesh name. This script never opens an app.
"""
from pathlib import Path
import argparse,json,struct,subprocess,hashlib

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'
PAKS='C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli',type=Path,default=ROOT/'target/release/mjolnir.exe')
    parser.add_argument('--require-attributes',action='store_true')
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    assets=OUT/('assets-attributes' if args.require_attributes else 'assets');assets.mkdir(parents=True,exist_ok=True)
    recipes=ROOT/'tools/level/data/b30_tree_recipes.json';recipe=json.loads(recipes.read_text())['Tree_Pine']
    sources=sorted({x['mesh'] for x in recipe['parts']}|{recipe['leaf_mesh']})
    metadata=[]
    for i,source in enumerate(sources):
        leaf=source.split('.')[-1].rsplit('/',1)[-1];path=assets/(leaf+'.glb')
        if args.force or not path.is_file():
            result=subprocess.run([str(args.cli),'mesh','export','--paks',PAKS,
                '--asset',source.split('.')[0].lstrip('/').removeprefix('Game/'),'--out',str(path)],capture_output=True,text=True,check=True)
            (assets/(leaf+'.export.log')).write_text(result.stdout+result.stderr)
        raw=path.read_bytes();doc=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
        lods=[{'name':m.get('name'),'triangles':sum(doc['accessors'][p['indices']]['count']//3 for p in m['primitives']),
               'native_attributes':m.get('extras',{}),
               'primitive_attributes':[sorted(p['attributes']) for p in m['primitives']]} for m in doc['meshes']]
        eligible=[i for i,lod in enumerate(lods) if lod['native_attributes'].get('decodedUvColorComplete') is True]
        if args.require_attributes and not eligible:
            raise ValueError('No verified classic UV/color-complete LOD: '+source)
        chosen=eligible[-1] if eligible else len(lods)-1
        if args.require_attributes:
            proof=lods[chosen]['native_attributes']
            expected={'TEXCOORD_'+str(i) for i in range(proof['nativeUvChannelCount'])}
            if proof['nativeColorVertexCount']>0:expected.add('COLOR_0')
            for attributes in lods[chosen]['primitive_attributes']:
                if not expected.issubset(attributes):raise ValueError('Exporter attribute declaration mismatch: '+source)
        metadata.append({'mesh':source,'glb':str(path),'sha256':digest(path),'lods':lods,
                         'selected_lod':chosen,'materials':[x['name'] for x in doc.get('materials',[])]})
        if i%10==0:print(f'Native tree asset {i+1}/{len(sources)}',flush=True)
    report={'schema':'pwr-native-conifer-source-v1','recipe_source':str(recipes),'recipe_sha256':digest(recipes),
        'recipe':recipe,'source_height_m':recipe['height']/100,'target_height_m':28.,
        'source_part_count':len(recipe['parts']),'source_leaf_clusters':len(recipe['leaves']),
        'materials_are_actual_native_slots':True,'attributes_required':args.require_attributes,
        'exporter':str(args.cli.resolve()),'exporter_sha256':digest(args.cli),
        'assets':metadata,'status':'source inspection only; no package or install'}
    (OUT/'source.json').write_text(json.dumps(report,indent=2)+'\n')
    triangles={x['mesh']:x['lods'][x['selected_lod']]['triangles'] for x in metadata}
    print(json.dumps({'assets':len(metadata),'native_fallback_triangles':sum(triangles[x['mesh']] for x in recipe['parts'])+len(recipe['leaves'])*triangles[recipe['leaf_mesh']]}))

if __name__=='__main__':main()
