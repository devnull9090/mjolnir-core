"""Regenerate the final PWR ecology from an explicitly selected tree file.

CPU/files only: never launches Unreal, Blender, the game, or installation.
Writes an isolated fragment; root owns upgrade configuration and integration.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/level'))
from alpine_ecology import generate,apply_to_bake
from heightfield import load_heightfield

MASTER_SHA='cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def checked_selection(path,field):
    spec=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    rows=spec.get('instances')
    if (spec.get('schema')!=1 or not isinstance(rows,list) or not rows
            or len(rows)!=spec.get('selected_count')):
        raise ValueError('Expected a nonempty schema1 selected tree placement file with exact count')
    ids=[row.get('id') for row in rows]
    if any(value is None for value in ids) or len(set(ids))!=len(ids):
        raise ValueError('Tree placement IDs must be present and unique')
    if any(row.get('kind')!='tree' for row in rows):
        raise ValueError('Ecology selection may contain only tree records')
    positions=np.asarray([row.get('position') for row in rows],dtype=float)
    if positions.shape!=(len(rows),3) or not np.isfinite(positions).all():
        raise ValueError('Tree positions must be finite authored-metres XYZ')
    # Sampling also checks inclusive runtime bounds. The result is recorded,
    # not silently reprojected: selected instances/physics remain immutable.
    expected=field.sample(positions[:,0],positions[:,1])
    error=abs(positions[:,2]-expected)
    if error.max()>.05:
        raise ValueError(f'Tree roots differ from runtime triangles by {error.max():.6f}m (limit0.05m)')
    return {'selected_count':len(rows),'max_root_height_error_m':float(error.max()),
            'selected_by_recipe':{name:sum(row.get('recipe')==name for row in rows)
                                  for name in sorted(set(row.get('recipe','') for row in rows))}}


def prepare(trees,master,paving,out,source_land=None,expected_master_sha=MASTER_SHA):
    trees=Path(trees).resolve();master=Path(master).resolve();paving=Path(paving).resolve();out=Path(out).resolve()
    if digest(master)!=expected_master_sha:
        raise ValueError('Runtime manifest differs from the explicitly accepted hash')
    field=load_heightfield(master)
    tree_audit=checked_selection(trees,field)
    shader=ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'
    material=json.loads(paving.read_text())
    if material.get('shader_source_sha256')!=digest(shader):
        raise ValueError('Paving receipt was generated for a different shader; refresh it before integration')
    for name,sha in material['files'].items():
        if digest(paving.parent/name)!=sha:
            raise ValueError('Paving texture differs from its receipt: '+name)
    sources=[trees,master,paving,shader]
    seals={str(path):digest(path) for path in sources}
    out.mkdir(parents=True,exist_ok=True)
    ecology=generate(master,trees,out/'ecology')
    manifest=out/'ecology/ecology.json'
    fragment={'ecology':str(manifest),'paving_materials':str(paving),
              'apron_material_additions':{'textures':{'ApronEcology':'/Game/MJOLNIR/Landscape/LPW/T_LandEcology.T_LandEcology'},
                                           'vectors':{'ApronEcologyInfo':[1,0,0,0]}}}
    (out/'config-fragment.json').write_text(json.dumps(fragment,indent=2)+'\n')
    bake_proof=None
    if source_land is not None:
        source_land=Path(source_land).resolve()
        document=copy.deepcopy(json.loads((source_land/'landscape.json').read_text()))
        original=source_land/document['textures']['Base']
        base_sha=digest(original)
        proof=out/'land-proof';proof.mkdir(exist_ok=True)
        leaf=Path(document['textures']['Base']).name
        document['textures']['Base']=leaf
        shutil.copyfile(original,proof/leaf)
        bake_proof=apply_to_bake(proof,document,manifest,field.manifest_sha256)
        (proof/'landscape.json').write_text(json.dumps(document,indent=2)+'\n')
        if digest(original)!=base_sha:
            raise ValueError('Source Landscape Base changed during proof')
        bake_proof['source_base_path']=str(original)
    if {str(path):digest(path) for path in sources}!=seals:
        raise ValueError('An input changed during ecology generation')
    report={'schema':'pwr-final-ecology-v1','status':'cpu_ready_pending_cook_and_live_acceptance',
            'source_seals':seals,'selection':tree_audit,'ecology':ecology,
            'outputs':{'ecology':str(manifest),'fragment':str(out/'config-fragment.json')},
            'config_modified':False,'inputs_modified':False,'base_bake_proof':bake_proof,
            'normal_fix_acceptance':'DXC/source seals are offline evidence only; full cook and actual distant lighting review are separate',
            'generator_sha256':digest(__file__)}
    (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trees',type=Path,required=True,help='Accepted final schema1 tree placement file')
    parser.add_argument('--master',type=Path,default=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    parser.add_argument('--expected-master-sha',default=MASTER_SHA)
    parser.add_argument('--paving',type=Path,default=ROOT/'out/pwr/visual-v5/paving-materials-v4/receipt.json')
    parser.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v5/surface-v5/final')
    parser.add_argument('--source-land',type=Path,help='Optional existing bake: prove unchanged Base/alpha in a separate copied folder')
    args=parser.parse_args()
    result=prepare(args.trees,args.master,args.paving,args.out,args.source_land,args.expected_master_sha)
    print(json.dumps({'status':result['status'],'outputs':result['outputs'],'selection':result['selection']},indent=2))
