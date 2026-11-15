"""Seal an already audited pine cook into its standalone959 container.

No editor, game, or installation writes. Run verify_pwr_pine.py first against
the GLB exported from audit-paks. The final root cook rechecks ownership.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from owned_map_cook import check_external_assets
from verify_pwr_surface_cook import digest, imported_packages

ROOT=Path(__file__).resolve().parents[2]
ASSET='/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A'
STEM='pakchunk959-MJOLNIRPWRMATUREPINE_P'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--staged',type=Path,required=True)
    parser.add_argument('--map-chunk',type=int,required=True)
    parser.add_argument('--land-chunk',type=int,default=965)
    parser.add_argument('--cli',type=Path,required=True)
    parser.add_argument('--examples',type=Path,default=ROOT/'target/release/examples')
    parser.add_argument('--stub-pak',type=Path,required=True)
    args=parser.parse_args();out=args.audit.resolve();stem=out/STEM
    editor=json.loads((out/'editor-import.receipt.json').read_text())
    parity=json.loads((out/'parity.receipt.json').read_text())
    if not parity.get('passed') or parity['source_sha256']!=editor['source_sha256']:
        raise ValueError('Pine parity receipt does not match editor source')
    if digest(editor['source'])!=editor['source_sha256']:
        raise ValueError('Frozen pine source changed')
    # Re-export the sealed isolated container: a stale parity GLB cannot
    # validate a subsequently replaced or different959 package.
    result=subprocess.run([str(args.cli),'mesh','export','--paks',str(out/'audit-paks'),
                           '--asset','SM_PWR_MaturePine_A','--out',str(out/'package-readback.glb')],capture_output=True,text=True)
    (out/'package-readback.log').write_text(result.stdout+result.stderr)
    if result.returncode or digest(out/'package-readback.glb')!=parity['cooked_export_sha256']:
        raise ValueError('Audited GLB is not the container being packaged')
    native=out/'SM_PWR_MaturePine_A.uasset'
    subprocess.run([str(args.examples/'extract_file.exe'),str(out/'audit-paks'),
                    'SM_PWR_MaturePine_A.uasset',str(native)],check=True,capture_output=True)
    imports=imported_packages(native)
    if imports!=[value.split('.')[0] for value in editor['materials'].values()]:
        raise ValueError('Pine native material imports differ')
    for ext in ('.utoc','.ucas'):
        shutil.copy2(out/'audit-paks'/('pakchunk959-Windows'+ext),str(stem)+ext)
    shutil.copy2(args.stub_pak,str(stem)+'.pak')
    fragment={'extra_containers':[str(stem.relative_to(ROOT)).replace('\\','/')],
              'required_external_assets':[{'asset':ASSET,'container':str(stem.relative_to(ROOT)).replace('\\','/')}]}
    ownership=check_external_assets(fragment,args.staged,(args.map_chunk,args.land_chunk),args.cli)
    (out/'config-fragment.json').write_text(json.dumps(fragment,indent=2)+'\n')
    receipt={'schema':'pwr-mature-pine-package-v1','container_stem':str(stem),'mesh':editor['mesh'],
             'source_sha256':editor['source_sha256'],'parity_receipt_sha256':digest(out/'parity.receipt.json'),
             'editor_receipt_sha256':digest(out/'editor-import.receipt.json'),'native_imports':imports,
             'external_ownership':ownership,'root_z_cm':0,'height_including_buried_roots_m':parity['height_m'],
             'files':{ext:{'path':str(stem)+ext,'sha256':digest(str(stem)+ext),'size':Path(str(stem)+ext).stat().st_size}
                      for ext in ('.utoc','.ucas','.pak')},
             'installed':False,'live_appearance_and_performance':'pending root integration'}
    (out/'package.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
