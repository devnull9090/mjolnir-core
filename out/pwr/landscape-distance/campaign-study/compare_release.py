"""Photograph a sealed solo Pelican Warfare release, with a verified reversible Steam overlay."""
import argparse
import hashlib
import math
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

STUDY=Path(__file__).resolve().parent
PWR=STUDY.parents[1]
sys.path.insert(0,str(PWR/'world-art'/'qa'))
import provision
import photo

GAME=provision.GAME
PAKS=provision.PAKS
UE=GAME/'Meteorite/Binaries/Win64/ue4ss'
# The developer install uses local names for the same map-owned content.
OLD_NAMES={955:'pakchunk955-MJOLNIRPWRBASES_P',959:'pakchunk959-MJOLNIRPWRMATUREPINE_P',961:'pakchunk961-MJOLNIRPWRPAVING_P',963:'pakchunk963-MJOLNIRPWRVISTA_P',964:'pakchunk964-MJOLNIRPWRCHUTE_P',965:'pakchunk965-MJOLNIRLAND-Windows',971:'pakchunk971-MJOLNIRPWRPELICAN_P'}
STUB_HASH='7dde1328a9650ead4f300ffcae4425d1ab3b32153a99d398262141ccfab3a51b'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def stage(build,review):
    info=json.loads((build/'receipt.json').read_text())
    rt=json.loads((build/'solo/developer-runtime-receipt.json').read_text())
    arc=build/info['archive'];runtime=build/'solo'/rt['archive']
    assert sha(arc)==info['sha256']==rt['paired_map']['sha256'] and sha(runtime)==rt['sha256']
    assert not (UE/'.pwr-rehearsal-owner').exists()
    assert 'process      running' not in provision.status()
    with zipfile.ZipFile(runtime) as z:
        m=json.loads(z.read('manifest.json'))
        mismatched=[n for n,h in m['baseline_sha256'].items() if (sha(GAME/n) if (GAME/n).is_file() else None)!=h]
        if mismatched:raise RuntimeError(f'Prerequisite mismatch: {mismatched}')
    review.mkdir(parents=True,exist_ok=False)
    b=review/'rehearsal-bundle';sat=review/'saturday';run=review/'steam';run.mkdir()
    def link(src,dst):provision.link(src,dst)
    link(arc,sat/arc.name);link(runtime,sat/runtime.name)
    prior=json.loads((provision.BASE/'rehearsal-receipt.json').read_text())
    mapping={}
    with zipfile.ZipFile(arc) as z:
        for n in z.namelist():
            if n=='mjolnir.json':continue
            if n.startswith('content/'):
                original=Path(n).name; stem=Path(n).stem; ext=Path(n).suffix
                assert ext in ('.ucas','.utoc') and original.startswith('pakchunk')
                no=int(stem.split('-')[0][8:])
                local=OLD_NAMES.get(no,stem)
                if local!=stem:assert not (PAKS/(stem+ext)).exists()
                dest=b/'Paks'/(local+ext)
                src=build/'map-input'/original
                if ext=='.utoc':
                    native_stub=PAKS/(local+'.pak')
                    empty=PAKS/'pakchunk997-MJOLNIRMAP-PWR_P.pak'
                    if not native_stub.is_file():
                        assert sha(empty)==STUB_HASH
                        link(empty,b/'Paks'/(local+'.pak'))
            elif n.startswith('map/'):
                asset=n.removeprefix('map/')
                assert '..' not in asset and not Path(asset).is_absolute()
                dest=b/'Win64/ue4ss/MJOLNIRMaps/PWR'/asset
                src=build/'map-input'/({'registration.json':'pwr.registration.json','level.json':'pwr.level.json'}.get(asset,asset))
            else:raise RuntimeError(n)
            expected=info['members_sha256'][n]
            if src.is_file() and sha(src)==expected:
                link(src,dest)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(n) as source,dest.open('xb') as destfile:shutil.copyfileobj(source,destfile)
            assert sha(dest)==expected,n
            mapping[n]=dest.relative_to(b).as_posix()
    with zipfile.ZipFile(runtime) as z:
        for n,h in m['payload_sha256'].items():
            target=b/('Win64/ue4ss/Mods/'+n[5:] if n.startswith('mods/') else 'Paks/'+Path(n).name)
            assert n.startswith(('mods/','content/paks/')) and target.resolve().is_relative_to(b.resolve())
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n));assert sha(target)==h
    for ext in ('.utoc','.ucas'):
        name='pakchunk997-MJOLNIRMAP-PWR_P'+ext
        src=provision.OLD/'saturday/map-input'/name
        assert sha(src)==sha(PAKS/name)
        link(src,sat/'map-input'/name)
    files={f.relative_to(b).as_posix():sha(f) for f in b.rglob('*') if f.is_file()}
    prior.update(map_sha256=info['sha256'],runtime_sha256=rt['sha256'],files=files,profile='private-distance-cameras',launched=False)
    (review/'rehearsal-receipt.json').write_text(json.dumps(prior,indent=2))
    (review/'source-map.json').write_text(json.dumps(mapping,indent=2))
    shutil.copy2(provision.PREVIOUS_RUN/'switch.py',run/'switch.py')
    print(f'Verified {len(mapping)} map members and {len(m["baseline_sha256"])} prerequisites')
if __name__=='__main__':
    cli=argparse.ArgumentParser(); cli.add_argument('action',choices=['stage','supervise','photo']);cli.add_argument('review',type=Path);cli.add_argument('--build',type=Path)
    a=cli.parse_args();review=a.review.resolve()
    if a.action=='stage':stage(a.build.resolve(),review)
    elif a.action=='supervise':provision.supervise(review)
    else:
        photo.POSES['meadow']=(-42000,43500,16500,-5,-76,73)
        photo.POSES['grass-road']=(-58100,38000,11000,-7,-33,81)
        wet=json.loads((STUDY.parent/'terrain/wet-spot-views.json').read_text())[:3]
        for i,site in enumerate(wet,1):
            eye=site['camera_ue_cm']; target=site['target_ue_cm']
            dx,dy,dz=(b-a for a,b in zip(eye,target)); ground=math.hypot(dx,dy)
            photo.POSES[f'wet-{i}']=(*eye,math.degrees(math.atan2(dz,ground)),math.degrees(math.atan2(dy,dx)),68)
        sys.argv=['photo','--out',str(review/'frames'),'--only','touchdown','meadow','grass-road','valley','shore','wet-1','wet-2','wet-3','aerial']
        photo.main()
