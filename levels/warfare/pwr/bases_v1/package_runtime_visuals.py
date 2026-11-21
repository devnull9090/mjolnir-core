"""Copy the retargeted base chunk and verify native geometry before installation.

This only writes the isolated base-runtime workspace. It never installs or
launches anything. Invoke after the shared Unreal cook/retarget has completed.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/iostore'))
from iostore import load_container
DEFAULT_STAGE=ROOT/'unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks'
MANIFEST=ROOT/'out/pwr/base-runtime/visuals/manifest.json'
IMPORT=MANIFEST.parent/'editor-import.receipt.json'
STEM='pakchunk955-MJOLNIRPWRBASES_P'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def run(command,log):
    r=subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True)
    log.write_text(r.stdout+r.stderr,encoding='utf-8')
    if r.returncode:raise RuntimeError(str(log)+': '+(r.stdout+r.stderr)[-1800:])
    return r.stdout

def inventory(path):
    container=load_container(path)
    if not container.indexed:raise RuntimeError('Missing package directory index: '+str(path))
    files=[(container.mount_point.rstrip('/')+'/'+p).replace('\\','/').lstrip('./') for p in container.files]
    chunks={(x.chunk_id,x.chunk_index,x.chunk_type) for x in container.chunks}
    return files,chunks

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--staged',type=Path,default=DEFAULT_STAGE)
    p.add_argument('--out',type=Path,default=ROOT/'out/pwr/base-runtime/cooked')
    p.add_argument('--cli',type=Path,default=ROOT/'out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    receipt_path=a.out/'package.receipt.json'
    receipt_path.write_text(json.dumps({'schema':'pwr-native-base-package-v1','passed':False,'status':'building'})+'\n')
    manifest=json.loads(MANIFEST.read_text());editor=json.loads(IMPORT.read_text())
    seals={p:sha(p) for p in (MANIFEST,IMPORT,ROOT/'unreal/MJOLNIRMaterials/Scripts/build_pwr_bases.py')}
    if editor['manifest_sha256']!=sha(MANIFEST):raise RuntimeError('Native editor import is stale')
    if editor['script_sha256']!=seals[ROOT/'unreal/MJOLNIRMaterials/Scripts/build_pwr_bases.py']:
        raise RuntimeError('Native editor build script changed after import')
    if editor['chunk']!=955 or len(editor['meshes'])!=len(manifest['assets']):raise RuntimeError('Editor asset ownership/count mismatch')
    expected=['Meteorite/Content/'+s['asset'].removeprefix('/Game/')+'.uasset' for s in manifest['assets']]
    expected+=['Meteorite/Content/'+x.split('.')[0].removeprefix('/Game/')+'.uasset' for x in editor['materials'].values()]
    expected+=['Meteorite/Content/'+x.split('.')[0].removeprefix('/Game/')+'.uasset' for x in editor['textures']]
    expected+=['Meteorite/Content/MJOLNIR/Bases/PWRV1/Materials/M_PWR_BaseFinish.uasset']
    source=a.staged/'pakchunk955-Windows.utoc'
    files955,chunks955=inventory(source)
    if any(sum(p.endswith(name) for p in files955)!=1 for name in expected):
        raise RuntimeError('Base chunk missing or duplicating expected packages')
    ownership=[{'container':source.name,'files':files955}]
    duplicates=[]
    for other in sorted(a.staged.glob('pakchunk*-Windows.utoc')):
        if other==source:continue
        listed,chunks=inventory(other);ownership.append({'container':other.name,'files':listed})
        duplicates.extend({'container':other.name,'package':x} for x in expected if any(p.endswith(x) for p in listed))
        overlaps=chunks955 & chunks
        if overlaps:duplicates.append({'container':other.name,'overlapping_chunk_ids':list(overlaps)})
    if duplicates:raise RuntimeError('Base packages have duplicate owners: '+json.dumps(duplicates))
    (a.out/'ownership.json').write_text(json.dumps(ownership,indent=2)+'\n')
    files={}
    for suffix in ('pak','utoc','ucas'):
        src=a.staged/('pakchunk955-Windows.'+suffix);dest=a.out/(STEM+'.'+suffix)
        if not src.is_file():raise FileNotFoundError(src)
        expected_hash=sha(src);shutil.copy2(src,dest)
        if sha(dest)!=expected_hash:raise RuntimeError('Cooked container copy mismatch')
        files[suffix]={'path':str(dest.resolve()),'sha256':expected_hash,'bytes':dest.stat().st_size}
    audit=a.out/'audit-paks';audit.mkdir(exist_ok=True)
    for stem,folder in (('global',a.staged),(STEM,a.out)):
        for suffix in ('utoc','ucas'):
            src=folder/(stem+'.'+suffix);dest=audit/src.name
            # copy2, not hardlinks: an unrelated subsequent cook must not be
            # able to rewrite the verified artifact through a shared inode.
            shutil.copy2(src,dest)
    readback=ROOT/'out/pwr/base-runtime/visual-readback'
    run(['uv','run','--with','numpy','--with','scipy','python',
         ROOT/'levels/warfare/pwr/bases_v1/verify_runtime_visuals.py','--paks',audit,
         '--cli',a.cli,'--out',readback],a.out/'native-readback.log')
    proof=json.loads((readback/'receipt.json').read_text())
    if not proof['passed'] or proof['manifest_sha256']!=sha(MANIFEST) or proof['source_total_triangles']!=manifest['total_triangles'] or proof['total_triangles']+proof['removed_zero_area_triangles']!=proof['source_total_triangles']:
        raise RuntimeError('Native geometry verification is stale')
    if any(sha(path)!=sealed for path,sealed in seals.items()):
        raise RuntimeError('Visual source/import provenance changed during packaging')
    receipt={'schema':'pwr-native-base-package-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'passed':True,'chunk':955,'container_stem':str((a.out/STEM).resolve()),'files':files,
             'visual_manifest_sha256':sha(MANIFEST),'editor_import_receipt_sha256':sha(IMPORT),
             'native_readback_receipt_sha256':sha(readback/'receipt.json'),
             'native_readback_receipt':str(readback/'receipt.json'),'expected_packages':expected,
             'unique_package_ownership_verified':True,'source_stage':str(a.staged.resolve()),
             'installed':False,'native_physics_verified':False}
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'receipt':str(a.out/'package.receipt.json'),'passed':True,'assets':len(manifest['assets']),
                      'triangles':proof['total_triangles'],'container':receipt['container_stem']}))

if __name__=='__main__':main()
