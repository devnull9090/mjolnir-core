"""Enable release-specific mount exclusions in this review's recoverable switch."""
from pathlib import Path
import json, hashlib, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"landscape-distance"/"campaign-study"))
from compare_release import OLD_NAMES, PAKS, sha, STUB_HASH

def prepare(review):
    work=Path(review).resolve()
    rfile=work/'rehearsal-receipt.json'
    plan=json.loads(rfile.read_text())
    base=work.parents[2]/'landscape-distance'/'saturday.8'
    old=json.loads((base/'receipt.json').read_text())
    stem=OLD_NAMES[961]
    retired={stem+'.pak':STUB_HASH}
    for key,h in old['members_sha256'].items():
        if key.startswith('content/pakchunk961-'):retired[stem+Path(key).suffix]=h
    live={f.name for f in PAKS.glob('pakchunk961-*')}
    assert set(retired)==live and len(live)==3
    assert all(sha(PAKS/n)==h and 'Paks/'+n not in plan['files'] for n,h in retired.items())
    plan['retired_961_sha256']=retired;rfile.write_text(json.dumps(plan,indent=2))
    switch=work/'steam/switch.py';s=switch.read_text()
    def replace(old,new):
        nonlocal s
        assert s.count(old)==1; s=s.replace(old,new)
    replace('    write(state,{"original_files":before,"paks":changes})','''    for name,h in plan['retired_961_sha256'].items():
        dest=paks/name
        assert dest.resolve().parent==paks and name.startswith('pakchunk961-MJOLNIRPWRPAVING_P.') and sha(dest)==h
        saved=backups/name
        shutil.copy2(dest,saved)
        assert sha(saved)==h and name not in changes
        changes[name]={'old':h,'new':None}
    write(state,{"original_files":before,"paks":changes})''')
    replace('    assert set(expected)==set(s["paks"])','''    for name in plan['retired_961_sha256']:
        assert name not in expected and s['paks'][name]['new'] is None
        expected[name]=None
    assert set(expected)==set(s["paks"])''')
    replace('            replace(bundle/"Paks"/name,paks/name)','''            if name in plan['retired_961_sha256']:
                parked=run/'parked-paks'
                parked.mkdir(exist_ok=True)
                src=paks/name;dst=parked/name
                assert src.resolve().parent==paks and dst.resolve().parent==parked and not dst.exists()
                assert sha(src)==plan['retired_961_sha256'][name]
                os.replace(src,dst)
                assert sha(dst)==plan['retired_961_sha256'][name] and not src.exists()
            else:
                replace(bundle/"Paks"/name,paks/name)''')
    switch.write_text(s)
    print('Pinned and backed up at apply',list(retired))
if __name__=='__main__':prepare(sys.argv[1])
