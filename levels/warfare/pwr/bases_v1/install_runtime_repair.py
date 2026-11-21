"""Plan/install the reviewed current-runtime + native Warfare integration.

The root agent runs install with the game closed. No map or asset is replaced.
All preimages are checked and backed up before the fourteen scoped replacements.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

from prepare_runtime_helpers import ROOT, GAME, MODS, OUT

PLAN = OUT/'install-plan.json'
MAP_RECEIPT = ROOT/'out/pwr/base-runtime/pipeline/installed.json'
NATIVE_READY = ROOT/'out/pwr/base-runtime/native-integration/ready.receipt.json'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for part in iter(lambda:f.read(8*1024*1024),b''): h.update(part)
    return h.hexdigest()

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def require(ok,message):
    if not ok: raise RuntimeError(message)
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def checked(p,digest):
    require(Path(p).is_file() and sha(p)==digest,'Hash changed: '+str(p))

def prepare():
    evidence=[OUT/'lua/entrypoints.receipt.json',OUT/'lua/helpers.receipt.json',
              OUT/'lua/tests.receipt.json',NATIVE_READY,MAP_RECEIPT]
    native=read(NATIVE_READY)
    require(native['passed'] and native['test_suites_passed']==7,'Native tests incomplete')
    exports=read(native['export_proof'])
    required={'mjolnir_warfare_'+x for x in ('open','close','action','pump','map_pump')}
    require(set(native['candidate']['exports'])==set(exports['installed']['exports'])|required
            and len(native['candidate']['exports'])==50,'Native exported interface was not preserved')
    checked(native['source_receipt'],native['source_receipt_sha256'])
    evidence += [Path(native[k]) for k in ('source_receipt','export_proof','tests_receipt','patch')]
    require(read(OUT/'lua/tests.receipt.json')['passed'],'Merged Lua regression test failed')
    rows=[]
    for report in evidence[:2]:
        for row in read(report)['files']:
            target=Path(row['installed']); source=Path(row['candidate'])
            require(target.resolve()==(MODS/row['relative']).resolve(),'Unexpected Lua target')
            require(source.resolve().is_relative_to((OUT/'lua/Mods').resolve()),'Unexpected Lua candidate')
            checked(target,row['before_sha256']);checked(source,row['candidate_sha256'])
            subprocess.run(['luac','-p',str(source)],check=True,capture_output=True)
            rows.append({'source':str(source),'target':str(target),'before_sha256':row['before_sha256'],
                         'source_sha256':row['candidate_sha256']})
    source=native['candidate'];before=exports['installed']
    require(Path(before['path']).resolve()==(MODS/'MJOLNIRLobby/native/mjolnir_lobby.dll').resolve(),'Wrong native destination')
    checked(source['path'],source['sha256']);checked(before['path'],before['sha256'])
    rows.append({'source':source['path'],'target':before['path'],'before_sha256':before['sha256'],
                 'source_sha256':source['sha256']})
    require(len(rows)==14 and len({x['target'] for x in rows})==14,'Expected thirteen Lua files and one DLL')
    modified={Path(x['target']).resolve() for x in rows}
    protected={}
    def protect(path,digest):
        path=Path(path)
        require(path.resolve() not in modified,'Protected/replaced overlap: '+str(path))
        checked(path,digest);protected[str(path)]=digest
    # Retain the already accepted native scenario, 19 base meshes, PCG, water,
    # landscape and shared material providers at their exact installed hashes.
    map_receipt=read(MAP_RECEIPT)
    for row in map_receipt['files']: protect(row['target'],row['source_sha256'])
    # The shared material provider was updated after the map install while
    # launching. Preserve that current provider, recording the exact exception
    # and proving it still owns the same complete required package inventory.
    material_now={
        'pakchunk988-MJOLNIRMATTEST_P.utoc':'956f9f93555073b5c4157e0e89591dfc73262430f46d3ffb6a17941651018358',
        'pakchunk988-MJOLNIRMATTEST_P.ucas':'a4524b80c52a6935af3fda8ec41218cd0d60fb3452f2487eaead2d67ea7c48a3',
    }
    import sys
    sys.path.insert(0,str(ROOT/'tools/iostore'))
    from iostore import load_container
    alias_proof=ROOT/'out/pwr/base-runtime/pipeline/runtime-aliases.json'
    evidence.append(alias_proof)
    current_material=GAME/'Meteorite/Content/Paks/pakchunk988-MJOLNIRMATTEST_P.utoc'
    mat=load_container(current_material)
    material_packages=sorted((mat.mount_point.rstrip('/')+'/'+n).replace('\\','/').lstrip('./') for n in mat.files)
    require(material_packages==read(alias_proof)['aliases'][0]['expected_packages'],
            'Current shared material provider lost a required package')
    for path,state in map_receipt['protected'].items():
        if state['exists'] and Path(path).resolve() not in modified:
            protect(path,material_now.get(Path(path).name,state['sha256']))
    # Every other module file and its declared version remains the actual
    # current installation; configuration/state files are deliberately excluded.
    versions={}
    for mod in ('MJOLNIRLobby','MJOLNIRLevelLoader','MJOLNIRHud'):
        meta=MODS/mod/'mod.json'; protect(meta,sha(meta));versions[mod]=read(meta)
        for p in (MODS/mod/'Scripts').glob('*.lua'):
            if p.resolve() not in modified: protect(p,sha(p))
        for p in (MODS/mod/'native').glob('*.dll'):
            if p.resolve() not in modified: protect(p,sha(p))
    helpers=read(OUT/'lua/helpers.receipt.json')
    for row in helpers['preserved_helpers']: protect(row['installed'],row['sha256'])
    # Bind the already working solo-preview Megalo and layout. The engine family
    # stays KOTH; the registered runtime descriptor supplies the Warfare mode.
    previous=ROOT/'out/pwr/runtime-20261109-103403/install-receipt.json'
    evidence.append(previous)
    variants=[r for r in read(previous)['files'] if Path(r['destination']).name in ('warfare.mglo','warfare.layout.json')]
    require(len(variants)==2,'Previous Warfare variant proof missing')
    for row in variants: protect(row['destination'],row['sha256'])
    tactical=ROOT/'out/pwr/tactical-map-v1/installed-20261110-002150.json'
    evidence.append(tactical)
    art=[r for r in read(tactical)['files'] if Path(r['installed']).suffix in ('.pak','.utoc','.ucas')]
    require(len(art)==3,'Tactical map package proof missing')
    for row in art: protect(row['installed'],row['installed_sha256'])
    # Dependencies/fonts are supplied by the preserved current HUD providers.
    # The owned tactical package itself must still expose the exact widget.
    container=load_container(next(Path(r['installed']) for r in art if r['installed'].endswith('.utoc')))
    packages=sorted(container.files)
    require(any('WBP_MJOLNIRTacticalMap.uasset' in p for p in packages),'Tactical widget package absent')
    plan={'schema':'pwr-native-runtime-repair-plan-v1','files':rows,'protected':protected,
          'evidence':{str(p):sha(p) for p in evidence},'preserved_versions':versions,
          'tactical_packages':packages,'native_export_count':50,'map_receipt':str(MAP_RECEIPT),
          'post_launch_shared_material_update':{'current_hashes':material_now,'same_required_packages':material_packages},
          'native_baseline':native['baseline_commit'],'installed':False,'live_validated':False}
    write(PLAN,plan)
    print(json.dumps({'plan':str(PLAN),'replacements':len(rows),'protected_files':len(protected)}))

def replace(source,target):
    target=Path(target)
    fd,tmp=tempfile.mkstemp(prefix='.pwr-runtime-',dir=target.parent)
    os.close(fd)
    try:
        shutil.copy2(source,tmp)
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def install():
    plan=read(PLAN)
    require(plan['schema']=='pwr-native-runtime-repair-plan-v1','Invalid install plan')
    # Read-only process guard; no termination or game automation here.
    tasks=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',
        'ConvertTo-Json -Compress -InputObject @(Get-Process | Select-Object -ExpandProperty ProcessName)'],text=True))
    names=[''.join(c for c in p.lower() if c.isalnum()) for p in tasks]
    require(not any('meteorite' in p or 'halocampaignevolved' in p for p in names),
            'Close the game before replacing runtime')
    for p,h in plan['evidence'].items():checked(p,h)
    for p,h in plan['protected'].items():checked(p,h)
    for row in plan['files']:
        checked(row['target'],row['before_sha256']);checked(row['source'],row['source_sha256'])
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=OUT/('backup-'+stamp)
    backup.mkdir(exist_ok=False)
    recovery=[]
    for i,row in enumerate(plan['files']):
        path=backup/(f'{i:02d}-'+Path(row['target']).name)
        shutil.copy2(row['target'],path);checked(path,row['before_sha256'])
        recovery.append({**row,'backup':str(path)})
    write(backup/'recovery.json',{'schema':'pwr-native-runtime-repair-recovery-v1','files':recovery,'plan':str(PLAN),'plan_sha256':sha(PLAN)})
    changed=[]
    try:
        for row in recovery:
            checked(row['target'],row['before_sha256'])
            replace(row['source'],row['target']);changed.append(row)
            checked(row['target'],row['source_sha256'])
        for p,h in plan['protected'].items():checked(p,h)
    except Exception:
        for row in reversed(changed):replace(row['backup'],row['target'])
        raise
    receipt={**plan,'schema':'pwr-native-runtime-repair-installed-v1','installed':True,
             'installed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'recovery':str(backup/'recovery.json'),'plan_sha256':sha(PLAN)}
    write(OUT/'installed.json',receipt)
    print(json.dumps({'installed':True,'files':len(recovery),'receipt':str(OUT/'installed.json'),'backup':str(backup)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['plan','install'])
    args=parser.parse_args();prepare() if args.action=='plan' else install()
