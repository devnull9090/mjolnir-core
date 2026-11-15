"""Record, plan and explicitly install the isolated PWR base candidate.

`plan` reads the game but changes only evidence under out/pwr/base-runtime.
`install` takes the saved plan, verifies every before/source hash, backs up
changed targets, and copies only map-owned files. Shared runtime and map
registration containers remain at their currently installed versions.
"""
from pathlib import Path
import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

if __package__:
    from .prepare_runtime_candidate import ROOT, NEW, OUT, CONFIG, GAME, VISUALS, sha, write
else:
    from prepare_runtime_candidate import ROOT, NEW, OUT, CONFIG, GAME, VISUALS, sha, write

PAKS=GAME/'Meteorite/Content/Paks'
DATA=GAME/'Meteorite/Binaries/Win64/ue4ss/MJOLNIRMaps/PWR'
WORK=NEW/'upgrade/PWR'
PLAN=OUT/'install-plan.json'
BAKE_RECEIPT=OUT/'bake-binding.json'
RUNTIME_ALIASES=OUT/'runtime-aliases.json'


def require(ok,message):
    if not ok:raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def snapshot(path):
    path=Path(path)
    return {'exists':path.is_file(),'sha256':sha(path) if path.is_file() else None}


def config_tools():
    os.environ['HCE_GAME']=str(GAME)
    os.environ.setdefault('MJOLNIR',str(ROOT/'out/pwr/toolchain-v3/mjolnir.exe'))
    os.environ.setdefault('OODLE','C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/AutomationTool/oo2core_9_win64.dll')
    sys.path.insert(0,str(ROOT/'tools/level'))
    import upgrade_ce_map as upgrade
    config=read(CONFIG)['PWR']
    return upgrade,config,upgrade.paths('PWR',config,str(NEW/'upgrade'))


def bake_inputs():
    return [NEW/'converted/pwr.level.json',WORK/'pwr.sbsp',WORK/'native-collision-receipt.json',
            NEW/'source-build/base-architecture-contract.json']


def verify_runtime_aliases():
    """Honor the measured installed material owner without replacing it."""
    proof=read(RUNTIME_ALIASES)
    require(proof.get('schema')=='pwr-verified-runtime-aliases-v1' and len(proof['aliases'])==1,
            'Unsupported runtime alias proof')
    entry=proof['aliases'][0]
    require(entry['required_stem']=='pakchunk988-MJOLNIRMAT-Windows'
            and entry['installed_stem']=='pakchunk988-MJOLNIRMATTEST_P','Unreviewed runtime alias')
    sys.path.insert(0,str(ROOT/'tools/iostore'))
    from iostore import load_container
    for ext in ('pak','utoc','ucas'):
        path=PAKS/(entry['installed_stem']+'.'+ext);row=entry['files'][ext]
        require(path.resolve()==Path(row['path']).resolve() and sha(path)==row['sha256'],
                'Pinned installed material runtime changed: '+ext)
    container=load_container(PAKS/(entry['installed_stem']+'.utoc'))
    require(container.indexed,'Installed material runtime lacks its package index')
    actual=sorted((container.mount_point.rstrip('/')+'/'+name).replace('\\','/').lstrip('./') for name in container.files)
    require(actual==entry['expected_packages'] and sum(x.endswith('.uasset') for x in actual)==33,
            'Installed material alias no longer supplies all 33 expected assets and shader archive')
    return {entry['required_stem']:entry['installed_stem']}


def record_bake():
    """Called by the runner only after a successful native bake stage."""
    upgrade,m,p=config_tools()
    upgrade.bake_sbsp(m,p)
    outputs=[WORK/'bake'/name for name in (
        'pakchunk997-MJOLNIRMAP-PWR_P.utoc','pakchunk997-MJOLNIRMAP-PWR_P.ucas',
        'pakchunk965-MJOLNIRLAND-Windows.utoc','pakchunk965-MJOLNIRLAND-Windows.ucas','PWR.registration.json')]
    latest=max(p.stat().st_mtime for p in bake_inputs())
    require(all(p.is_file() and p.stat().st_mtime>=latest for p in outputs),
            'Bake output predates the current native collision or scenario')
    receipt={'schema':'pwr-base-bake-binding-v1','recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'inputs':{str(p):sha(p) for p in bake_inputs()},'outputs':{str(p):sha(p) for p in outputs}}
    write(BAKE_RECEIPT,receipt)
    print(json.dumps({'bake_binding':str(BAKE_RECEIPT)}))


def verify_candidate():
    upgrade,m,p=config_tools()
    preserved=read(OUT/'editor-source-preservation.json')
    for path,digest in preserved['files'].items():
        require(sha(path)==digest,'A frozen pre-existing source/artifact changed: '+path)
    upgrade.bake_sbsp(m,p)
    native=read(ROOT/'out/pwr/base-runtime/native-refresh/refresh.receipt.json')
    require(native.get('success') is True and native.get('applied') is True,'Native refresh must pass and be applied')
    require(sha(NEW/'converted/pwr.level.json')==native['verified_level_sha256'],'Scenario changed after native preflight')
    for path,digest in native['inputs'].items():
        require(sha(path)==digest,'Native input changed: '+path)
    for key in ('probe_plan','contract'):
        require(sha(native[key])==native[key+'_sha256'],'Native evidence changed: '+key)
    require(read(native['contract']).get('layout3_permitted') is True,'Native layout contract failed')
    baked=read(BAKE_RECEIPT)
    require(baked.get('schema')=='pwr-base-bake-binding-v1','Missing base bake provenance')
    for path,digest in {**baked['inputs'],**baked['outputs']}.items():
        require(sha(path)==digest,'Baked collision/scenario/container changed: '+path)
    final=read(OUT/'assembled-level-finalization.json')
    require(final['after_sha256']==sha(WORK/'level.json'),'Assembled level was not finalized or changed afterwards')
    level=read(WORK/'level.json')
    ids={r['id'] for r in level['decor']}
    expected={r['id'] for r in read(VISUALS)['decor']}
    require(len(expected)==19 and expected<=ids,'Missing one or more of the 19 new base/bridge actors')
    require('pwr_terrain' not in ids and 'shadow_shell' not in level,'Retired monolithic base rendering remains')
    require(not any(i.startswith(('red_home_','blue_home_','citadel_plateau_')) for i in ids),'Retired base decorations remain')
    require(level.get('warfare',{}).get('protocol')==20569 and level['warfare'].get('layout_revision')==3,
            'Native warfare protocol/layout changed')
    binding=read(OUT/'visual-binding.json')
    require(binding['source_sha256']==sha(VISUALS) and binding['config_sha256']==sha(CONFIG),'Visual/config binding is stale')
    package=read(ROOT/'out/pwr/base-runtime/cooked/package.receipt.json')
    require(package.get('schema')=='pwr-native-base-package-v1' and package.get('passed') is True
            and package.get('chunk')==955,'Native base package has not passed its readback gate')
    require(package['visual_manifest_sha256']==sha(VISUALS.parent/'manifest.json'),'Base package uses another visual export')
    expected_stem=ROOT/'out/pwr/base-runtime/cooked/pakchunk955-MJOLNIRPWRBASES_P'
    require(Path(package['container_stem']).resolve()==expected_stem.resolve(),'Base package has another owner')
    for ext in ('pak','utoc','ucas'):
        row=package['files'][ext]
        require(Path(row['path']).resolve()==Path(str(expected_stem)+'.'+ext).resolve(),'Invalid packaged base path')
        require(sha(row['path'])==row['sha256'],'Base package changed: '+ext)
    old=read(DATA/'registration.json');new=read(WORK/'bake/PWR.registration.json')
    require(old==new,'Registration changed: this isolated installer does not rebuild shared registration')
    files,_=upgrade.local_install_plan('PWR',m,p,shared=False,runtime_aliases=verify_runtime_aliases())
    return upgrade,files


def destination(path):
    path=Path(path).resolve()
    require(path.is_relative_to(GAME.resolve()),'Install target escaped game root')
    require(path.is_relative_to(DATA.resolve()) or path.parent==PAKS.resolve(),'Unexpected install target')
    if path.parent==PAKS.resolve():
        require('PWR' in path.name or path.name.startswith('pakchunk965-MJOLNIRLAND-Windows.'),'Shared/foreign container rejected')
    return path


def plan():
    _,files=verify_candidate()
    rows=[];targets=set()
    for source,target in files:
        source=Path(source).resolve();target=destination(target)
        require(str(target) not in targets,'Duplicate target in install plan')
        targets.add(str(target))
        before=snapshot(target);source_hash=sha(source)
        rows.append({'source':str(source),'target':str(target),'source_sha256':source_hash,
                     'before':before,'changed':before['sha256']!=source_hash})
    prepared=read(OUT/'preparation.json')
    # Pin the actual runtime observed when this task began, including the
    # newer native tactical map DLLs. Never restore the older V8 binaries.
    protected={r['path']:{'exists':r['exists'],'sha256':r['sha256']} for r in prepared['installed_before']
               if str(Path(r['path']).resolve()) not in targets}
    for entry in read(RUNTIME_ALIASES)['aliases']:
        for row in entry['files'].values():
            require(str(Path(row['path']).resolve()) not in targets,'Runtime alias was scheduled as a map target')
            protected[row['path']]={'exists':True,'sha256':row['sha256']}
    for path,state in protected.items():
        require(snapshot(path)==state,'Preserved runtime changed during preparation: '+path)
    result={'schema':'pwr-base-install-plan-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'game':str(GAME),'config_sha256':sha(CONFIG),'files':rows,'protected':protected,
            'runtime_alias_proof_sha256':sha(RUNTIME_ALIASES),
            'shared_runtime_copied':False,'shared_registration_rebuilt':False,'live_acceptance_required':True}
    write(PLAN,result)
    print(json.dumps({'plan':str(PLAN),'files':len(rows),'changed':sum(r['changed'] for r in rows),
                      'preserved_runtime_files':len(protected)}))


def atomic_copy(source,target):
    target=destination(target);target.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(prefix=target.name+'.pwr-bases-',dir=target.parent)
    os.close(handle)
    try:
        shutil.copyfile(source,temp)
        os.replace(temp,target)
    finally:
        if Path(temp).exists():Path(temp).unlink()


def install():
    upgrade,_=verify_candidate()
    upgrade.require_game_closed()
    saved=read(PLAN)
    require(saved.get('schema')=='pwr-base-install-plan-v1' and saved['game']==str(GAME),'Invalid install plan')
    require(saved['config_sha256']==sha(CONFIG),'Config changed after installation planning')
    require(saved['runtime_alias_proof_sha256']==sha(RUNTIME_ALIASES),'Runtime alias proof changed after planning')
    for row in saved['files']:
        destination(row['target'])
        require(sha(row['source'])==row['source_sha256'],'Source changed after plan: '+row['source'])
        require(snapshot(row['target'])==row['before'],'Target changed after plan: '+row['target'])
    for path,state in saved['protected'].items():
        require(snapshot(path)==state,'Protected runtime changed: '+path)
    recovery=OUT/('install-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    recovery.mkdir(exist_ok=False)
    write(recovery/'plan.json',saved)
    backups=[]
    for row in saved['files']:
        if not row['changed']:continue
        target=destination(row['target'])
        backup=recovery/'before'/target.relative_to(GAME.resolve())
        if row['before']['exists']:
            backup.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(target,backup)
            require(sha(backup)==row['before']['sha256'],'Backup verification failed')
        backups.append({'target':str(target),'backup':str(backup) if row['before']['exists'] else None,
                        'before':row['before'],'after_sha256':row['source_sha256']})
    write(recovery/'recovery.json',{'schema':'pwr-base-install-recovery-v1','files':backups})
    changed=[]
    try:
        for row in saved['files']:
            if row['changed']:
                atomic_copy(row['source'],row['target']);changed.append(row['target'])
            require(sha(row['target'])==row['source_sha256'],'Installed hash mismatch: '+row['target'])
        for path,state in saved['protected'].items():
            require(snapshot(path)==state,'Protected runtime changed during install: '+path)
    except BaseException as error:
        write(recovery/'failed.json',{'error':str(error),'copied':changed,'recovery':str(recovery/'recovery.json')})
        raise
    receipt={'schema':'pwr-base-installed-v1','installed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'files':saved['files'],'protected':saved['protected'],'recovery':str(recovery),
             'native_sbsp_sha256':sha(WORK/'pwr.sbsp'),'level_sha256':sha(DATA/'level.json'),
             'live_acceptance_required':True,'game_launched':False}
    write(recovery/'installed.json',receipt)
    write(OUT/'installed.json',receipt)
    print(json.dumps({'installed_files':len(saved['files']),'changed_files':len(changed),'receipt':str(OUT/'installed.json'),
                      'recovery':str(recovery),'next':'Launch PWR warfare privately and run native acceptance.'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['record-bake','plan','install'])
    action=parser.parse_args().action
    {'record-bake':record_bake,'plan':plan,'install':install}[action]()
