"""Resume the owned map seal after a completed cook's base package check.

capture pins the successful cook and current inputs without invoking Unreal.
seal requires the independently verified 955 package and an unchanged capture,
then calls the original owned-cook verifier/snapshot without cooking again.
"""
from pathlib import Path
import argparse
import datetime
import json
import sys

if __package__:
    from .prepare_runtime_candidate import ROOT, NEW, OUT, CONFIG, VISUALS, sha, write
    from .install_candidate import config_tools, require, read
else:
    from prepare_runtime_candidate import ROOT, NEW, OUT, CONFIG, VISUALS, sha, write
    from install_candidate import config_tools, require, read

CAPTURE=OUT/'cook-resume-inputs.json'
PROJECT=ROOT/'unreal/MJOLNIRMaterials'
STAGED=PROJECT/'Saved/StagedBuilds/Windows/Meteorite/Content/Paks'
PIPELINE_LOG=OUT/'logs/editor-cook.log'
PACKAGE=ROOT/'out/pwr/base-runtime/cooked/package.receipt.json'


def capture(out):
    require(not out.exists(),'Resume capture exists; do not overwrite completed cook evidence')
    upgrade,m,p=config_tools()
    from owned_map_cook import input_files
    require(sha(CONFIG)==read(OUT/'visual-binding.json')['config_sha256'],'Configuration changed after visual binding')
    cook_log=PROJECT/'Saved_cook.log'
    text=cook_log.read_text(encoding='utf-8',errors='replace')
    require('BUILD SUCCESSFUL' in text and 'AutomationTool exiting with ExitCode=0 (Success)' in text,
            'Unreal cook did not complete successfully')
    errors=[line for line in text.splitlines() if 'error X' in line or ': error' in line]
    require(not errors,'Shader errors in completed cook')
    pipeline_text=PIPELINE_LOG.read_text(encoding='utf-8-sig',errors='replace')
    require('cook exit 0' in pipeline_text and 'retarget pakchunk955-Windows:' in pipeline_text
            and 'retarget pakchunk965-Windows:' in pipeline_text,'Expected successful PWR/base retarget output')
    snapshot=Path(m['retarget_snapshot']);stock=read(snapshot/'receipt.json')
    require(stock['schema']=='mjolnir-stock-retarget-snapshot-v1' and stock['before_any_retarget'] is True,
            'No preserved stock cook snapshot')
    files={str(Path(path).resolve()):sha(path) for path in input_files('PWR',m,p['work']).values()}
    for row in stock['files']:
        path=snapshot/row['name'];require(sha(path)==row['sha256'],'Stock cook snapshot changed')
        files[str(path.resolve())]=row['sha256']
    source_chunk=int(read(Path(m['conversion'])/'materials.spec.json')['chunk'])
    for chunk in ('global','pakchunk955-Windows',f"pakchunk{int(m['chunk'])}-Windows",f'pakchunk{source_chunk}-Windows'):
        for suffix in ('utoc','ucas'):
            path=STAGED/(chunk+'.'+suffix);files[str(path.resolve())]=sha(path)
    for path in (CONFIG,OUT/'visual-binding.json',cook_log,PIPELINE_LOG,snapshot/'receipt.json',VISUALS,
                 VISUALS.parent/'manifest.json',VISUALS.parent/'editor-import.receipt.json',
                 PROJECT/'Scripts/build_pwr_bases.py',ROOT/'out/pwr/base-runtime/native-refresh/refresh.receipt.json'):
        files[str(path.resolve())]=sha(path)
    # The generated editor assets must also remain unchanged until sealing.
    for folder in ('Content/MJOLNIR/Bases/PWRV1','Content/Levels/Halo1/Solo/LPW','Content/Levels/Halo1/Solo/LPG'):
        for path in (PROJECT/folder).rglob('*'):
            if path.is_file() and path.suffix in ('.uasset','.umap','.ubulk','.uexp'):
                files[str(path.resolve())]=sha(path)
    for path,digest in read(OUT/'editor-source-preservation.json')['files'].items():
        require(sha(path)==digest,'Frozen source changed during editor/cook: '+path)
        files[path]=digest
    evidence={'schema':'pwr-base-cook-resume-inputs-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'config_sha256':sha(CONFIG),'source_chunk':source_chunk,'files':files,
              'cook_complete':True,'retarget_complete':True,'base_package_verification_pending':True,
              'unreal_invoked':False,'game_modified':False}
    write(out,evidence)
    print(json.dumps({'capture':str(out),'pinned_files':len(files),'source_chunk':source_chunk}))


def seal(capture_path):
    evidence=read(capture_path)
    require(evidence.get('schema')=='pwr-base-cook-resume-inputs-v1' and evidence['cook_complete'] is True,
            'Unsupported cook handoff capture')
    for path,digest in evidence['files'].items():
        require(sha(path)==digest,'Cook handoff input changed; cannot seal old cook: '+path)
    package=read(PACKAGE)
    require(package.get('schema')=='pwr-native-base-package-v1' and package.get('passed') is True
            and package.get('chunk')==955 and package.get('unique_package_ownership_verified') is True,
            'Independent base package verification has not passed')
    require(package['visual_manifest_sha256']==sha(VISUALS.parent/'manifest.json')
            and package['editor_import_receipt_sha256']==sha(VISUALS.parent/'editor-import.receipt.json'),
            'Base package source/import binding is stale')
    require(package['native_readback_receipt_sha256']==sha(package['native_readback_receipt'])
            and read(package['native_readback_receipt'])['passed'] is True,'Base native readback proof changed')
    for suffix in ('pak','utoc','ucas'):
        row=package['files'][suffix]
        require(sha(row['path'])==row['sha256']==sha(STAGED/('pakchunk955-Windows.'+suffix)),
                'Verified base package no longer matches this staged cook: '+suffix)
    upgrade,m,p=config_tools()
    from owned_map_cook import snapshot_owned_cook
    package_hash=sha(PACKAGE)
    target=snapshot_owned_cook('PWR',m,p['work'],str(STAGED),__import__('os').environ['MJOLNIR'])
    for path,digest in evidence['files'].items():
        require(sha(path)==digest,'Input changed while sealing current owned cook: '+path)
    require(sha(PACKAGE)==package_hash,'Base package changed while sealing current owned cook')
    result={'schema':'pwr-base-resumed-cook-seal-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'capture':str(capture_path),'capture_sha256':sha(capture_path),'base_package_sha256':package_hash,
            'owned_cook':str(target),'owned_cook_receipt':str(Path(p['work'])/'owned-cook.json'),
            'owned_cook_receipt_sha256':sha(Path(p['work'])/'owned-cook.json'),
            'unreal_invoked':False,'game_modified':False,'passed':True}
    write(OUT/'resumed-cook-seal.json',result)
    print(json.dumps({'sealed':str(target),'receipt':str(OUT/'resumed-cook-seal.json'),'passed':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['capture','seal'])
    parser.add_argument('--capture',type=Path,default=CAPTURE)
    args=parser.parse_args()
    {'capture':capture,'seal':seal}[args.action](args.capture)
