"""Hash the completed offline assembly and verify untouched source contracts."""
from pathlib import Path
import datetime,hashlib,json
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'out/pwr/base-integration'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    art=json.loads((ROOT/'out/pwr/base-art/source-manifest.json').read_text())
    changed=[x['path'] for x in art['files'] if sha(x['path'])!=x['sha256']]
    if changed:raise RuntimeError('Sealed art changed: '+str(changed))
    validation=json.loads((OUT/'world-clearance.json').read_text())
    plan=json.loads((OUT/'placement-plan.json').read_text())
    assembly=json.loads((OUT/'assembly-receipt.json').read_text())
    if not validation['passed'] or not plan['validation']['passed']:raise RuntimeError('Offline validation failed')
    if sha(OUT/'placement-plan.json')!=assembly['placement_plan_sha256']:raise RuntimeError('Stale placement plan')
    if sum(b['triangles'] for b in assembly['finishing']['bridges'])!=1808:raise RuntimeError('Bridge count mismatch')
    files=[OUT/'pwr-world-bases-v1.blend',OUT/'assembly-receipt.json',OUT/'placement-plan.json',
           OUT/'world-clearance.json',OUT/'runtime-handoff.json',OUT/'render-receipt.json',OUT/'save-receipt.json']
    files+=sorted(OUT.glob('*.png'))
    files+=[HERE/name for name in ('integrate_world.py','world_placement.py','world_dressing.py','finish_world.py',
                                   'validate_world.py','render_world.py','integrate_contract.py','INTEGRATION.md')]
    report={'schema':'pwr-completed-offline-base-integration-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files],
            'source_art_files_preserved':len(art['files']),'offline_clearance_passed':True,
            'route_support_samples':sum(c.get('support_samples',0) for b in validation['bases'].values() for c in b['checks'].values()),
            'source_shape_maximum_error_m':max(b['checks']['reviewed_base_shape_preserved']['maximum_bounds_error_m'] for b in validation['bases'].values()),
            'scope':'Completed offline Blender assembly and previews; runtime mesh/collision cook and installation pending.',
            'game_launched':False,'native_collision_rebuilt':False,'installed_game_modified':False}
    (OUT/'final-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'manifest':str(OUT/'final-manifest.json'),'files':len(files),
                      'world_bytes':files[0].stat().st_size,'passed':True,'source_art_files_preserved':len(art['files'])}))

if __name__=='__main__':main()
