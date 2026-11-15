"""Create a separate material-only fix for the measured visual6 bank stones."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
PREFIX='pwr_v6_riparian_'
# Actual live component/default slots, visual6-riparian-materials-r2.txt:
# MedA and MedC both use LrgC; MedB uses MedB. Preserve their native recipe.
VARIANTS={'A':'Lrg_C','B':'Med_B','C':'Lrg_C'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def signature(rows):
    data=[{key:row.get(key) for key in ('id','mesh','pos','rot','scale','static')} for row in rows]
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def apply(document,expected=268):
    result=copy.deepcopy(document);changed=[]
    for row in result['decor']:
        if not row['id'].startswith(PREFIX):continue
        leaf=row['mesh'].split('.')[-1]
        if leaf not in ['SM_Rock_Glacial_Med_'+letter for letter in VARIANTS] or 'materials' in row:
            raise ValueError('Unexpected bank rock mesh or existing material: '+row['id'])
        variant=VARIANTS[leaf[-1]]
        package=f'/Game/Env/Bio/Rock/Glacial/Rock_Glacial_{variant}/Materials/MI_Rock_Glacial_{variant}_NoSnow'
        row['materials']=[{'parent':package+'.'+package.rsplit('/',1)[-1]}]
        changed.append({'id':row['id'],'mesh':row['mesh'],'material':row['materials'][0]['parent']})
    if len(changed)!=expected:raise ValueError(f'Expected {expected} unmodified bank rocks; found {len(changed)}')
    if signature(document['decor'])!=signature(result['decor']):raise AssertionError('Collision/geometry inputs changed')
    for before,after in zip(document['decor'],result['decor']):
        if not before['id'].startswith(PREFIX) and before!=after:raise AssertionError('Baseline changed')
    return result,changed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'out/pwr/visual-v6/scenery/rocks-and-outcrops.authored-decor.json')
    p.add_argument('--readback',type=Path,default=ROOT/'out/pwr/visual-v6-qa/visual6-riparian-materials-r2.txt')
    p.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v7/bank-rocks')
    args=p.parse_args();source_sha=sha(args.source);readback=args.readback.read_text()
    if 'RIPARIAN_TOTAL 268 ' not in readback or 'RIPARIAN_MATERIAL_COUNT 182 ' not in readback or 'RIPARIAN_MATERIAL_COUNT 86 ' not in readback:
        raise ValueError('Expected actual visual6 material readback')
    original=json.loads(args.source.read_text());result,changed=apply(original)
    args.out.mkdir(parents=True,exist_ok=True)
    path=args.out/'rocks-and-outcrops.authored-decor.json'
    if path.resolve()==args.source.resolve():raise ValueError('Must preserve source')
    path.write_text(json.dumps(result,indent=2)+'\n')
    if sha(args.source)!=source_sha:raise AssertionError('Source changed')
    receipt={'schema':'pwr-temperate-riparian-v1','status':'offline candidate; native NoSnow appearance awaits live review',
      'source':str(args.source.resolve()),'source_sha256':source_sha,'output':str(path.resolve()),'output_sha256':sha(path),
      'runtime_readback':str(args.readback.resolve()),'runtime_readback_sha256':sha(args.readback),
      'changed_materials':changed,'material_only_count':len(changed),'baseline_unchanged_count':len(result['decor'])-len(changed),
      'geometry_collision_input_sha256':signature(original['decor']),'geometry_collision_input_unchanged':True,
      'collision_hulls_modified':False,'installed':False,'generator_sha256':sha(__file__),
      'assembly':'Use this as --rocks with the same visual5 804-rock baseline and --expected-rocks 1072; material-customized rows use existing runtime actor path, not baked duplicates.'}
    (args.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    fragment={'authored_rocks':str(path.resolve()),
              'baseline_rocks':str((ROOT/'out/pwr/visual-v5/outcrops-v4/rocks-and-outcrops.authored-decor.json').resolve()),
              'expected_rocks':len(result['decor']),'material_receipt':str((args.out/'receipt.json').resolve()),
              'integration':'Input to assemble_dressing_v5.py; do not overwrite visual6 config or sealed scenery.'}
    (args.out/'config.fragment.json').write_text(json.dumps(fragment,indent=2)+'\n')
    print(json.dumps({'output':str(path),'changed_materials':len(changed),'unchanged_baseline':receipt['baseline_unchanged_count']}))


if __name__=='__main__':main()
