"""Merge reviewed render-only apron/courts with verified native materials.

Produces an isolated fragment; does not edit the upgrade configuration or
installed map. Re-run after changing any packaged mesh or material.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apron',type=Path,default=ROOT/'out/pwr/visual-v5/apron-v3')
    parser.add_argument('--paving',type=Path,default=ROOT/'out/pwr/visual-v5/base-paving-v3/native')
    parser.add_argument('--materials',type=Path,default=ROOT/'out/pwr/visual-v5/paving-materials-v3')
    parser.add_argument('--surface-fragment',type=Path,help='Optional reviewed apron material additions')
    parser.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v5/runtime-decor-v4.json')
    args=parser.parse_args()
    apron=args.apron/'runtime_decor.geology.json'
    paving=args.paving/'runtime_decor.json'
    material=args.materials/'materials.json'
    material_receipt=args.materials/'receipt.json'
    sources=[apron,paving,material,material_receipt,args.paving/'package.receipt.json']
    parents=read(material)
    expected_parent='/Game/MJOLNIR/CETrial/M_CE_PWRPaving.M_CE_PWRPaving'
    if len(parents)!=2 or any(row['parent']!=expected_parent for row in parents):
        raise ValueError('Expected two explicit PWR paving material bindings')
    material_proof=read(material_receipt)
    if material_proof.get('vertex_color_inputs') or material_proof.get('mesh_coh_inputs') or material_proof.get('frost_layers'):
        raise ValueError('Paving must not depend on absent native vertex masks')
    for name,expected in read(material_receipt)['files'].items():
        if digest(args.materials/name)!=expected:
            raise ValueError('Material input differs from its readback receipt: '+name)
    court=read(paving)
    if not court.get('render_only') or len(court['decor'])!=3:
        raise ValueError('Expected three verified render-only base courts')
    for actor in court['decor']:
        if len(actor.get('materials',[]))!=2:
            raise ValueError('Native paving material slot count changed')
        actor['materials']=copy.deepcopy(parents)
    backdrop=read(apron)['decor']
    if args.surface_fragment:
        additions=read(args.surface_fragment)['apron_material_additions']
        if set(additions)-{'textures','vectors','scalars'}:
            raise ValueError('Unexpected apron material binding category')
        if len(backdrop)!=1 or len(backdrop[0].get('materials',[]))!=1:
            raise ValueError('Expected one explicit apron material')
        for category,bindings in additions.items():
            backdrop[0]['materials'][0].setdefault(category,{}).update(bindings)
        sources.append(args.surface_fragment)
    decor=backdrop+court['decor']
    if len({actor['id'] for actor in decor})!=len(decor):
        raise ValueError('Duplicate runtime decoration id')
    # The explicit paving master cooks into the existing shared trial983.
    # The rejected native MIC clone960 is deliberately never included.
    stems=[args.apron/'pakchunk963-MJOLNIRPWRVISTA_P',
           args.paving/'pakchunk961-MJOLNIRPWRPAVING_P']
    files=[]
    for stem in stems:
        for ext in ('.pak','.utoc','.ucas'):
            path=Path(str(stem)+ext)
            if not path.is_file():raise FileNotFoundError(path)
            files.append(path)
    provenance={str(path.resolve()):digest(path) for path in sources+files}
    result={'schema':'mjolnir-runtime-decor-v1','render_only':True,'decor':decor,
            'provenance':provenance,'assembly_source_sha256':digest(Path(__file__))}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    fragment={'runtime_decor':str(args.out.resolve()),'extra_containers':[str(p.resolve()) for p in stems],
              'runtime_decor_sha256':digest(args.out),'provenance':provenance}
    fragment_path=args.out.with_suffix('.fragment.json')
    fragment_path.write_text(json.dumps(fragment,indent=2)+'\n')
    print(json.dumps({'runtime_decor':str(args.out),'actors':len(decor),'fragment':str(fragment_path)}))


if __name__=='__main__':main()
