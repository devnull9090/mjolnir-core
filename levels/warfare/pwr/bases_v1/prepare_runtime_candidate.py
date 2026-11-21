"""Prepare an isolated PWR base candidate, never installing or launching apps.

prepare: copy the frozen V8 workspace once and write a private upgrade config.
bind: attach the completed base visual manifest to the preserved runtime decor.
finalize-level: remove retired monolithic kit/shadow actors after assembly.
"""
from pathlib import Path
import argparse, copy, datetime, hashlib, json, shutil

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'out/pwr/base-runtime/pipeline'
OLD=Path('C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5-visual8')
NEW=Path('C:/haloce/ce_conversions/warfare/PWR/expansion/world-bases-v1')
CONFIG=HERE.parent/'upgrade-bases-v1.json'
BASE_CONFIG=HERE.parent/'upgrade-v5-visual8.json'
VISUALS=ROOT/'out/pwr/base-runtime/visuals/runtime_decor.json'
CHUNK=955
CONTAINER=ROOT/f'out/pwr/base-runtime/cooked/pakchunk{CHUNK}-MJOLNIRPWRBASES_P'
GAME=Path('C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved')

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')

def inside(path,root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())

def source_records():
    r=json.loads((ROOT/'out/pwr/world-v5/installed-visual-v8.receipt.json').read_text())
    records=[]
    for row in r['files']:
        p=Path(row['installed'])
        records.append({'path':str(p),'exists':p.exists(),'sha256':sha(p) if p.exists() else None,
                        'v8_sha256':row['sha256']})
    return records

def candidate_config():
    d=copy.deepcopy(json.loads(BASE_CONFIG.read_text()));m=d['PWR']
    m['conversion']=str(NEW/'converted')
    m['surface_policy']=str(NEW/'source-build/pwr.surfaces.json')
    m['authored_collision']=str(NEW/'source-build/terrain-collision-extra.json')
    m['authored_decor']=str(OUT/'authored-decor.json')
    m['runtime_decor']=str(OUT/'runtime-decor.json')
    m['retarget_snapshot']=str(ROOT/'out/pwr/base-runtime/stock-cook-snapshot')
    m['native_grass_pilot']=str(ROOT/'out/pwr/base-runtime/landscape-grass-pilot/pilot.json')
    m['paving_graphic']=str(ROOT/'out/pwr/base-runtime/paving/graphic.json')
    m['extra_containers'].append(str(CONTAINER))
    # Keep native assets in their independent original owners. The new base
    # container has its own asset root and is required only after bind.
    return d

def prepare():
    if not inside(NEW,OLD.parent) or NEW==OLD:raise RuntimeError('Candidate escapes the intended expansion root')
    if NEW.exists():raise FileExistsError('Candidate exists; never overwrite a partially built workspace: '+str(NEW))
    if list((GAME/'Meteorite/Content/Paks').glob(f'pakchunk{CHUNK}-*.utoc')):
        raise RuntimeError('Dedicated base chunk is already installed; inspect ownership first')
    before={str(p):sha(p) for p in (BASE_CONFIG,OLD/'converted/pwr.level.json',OLD/'upgrade/PWR/pwr.sbsp')}
    OUT.mkdir(parents=True,exist_ok=True)
    installed=source_records()
    for name in ('source-build','converted'):
        shutil.copytree(OLD/name,NEW/name)
    # Reuse immutable terrain, foliage and Flux input caches. Never bring an
    # old compiled collision or final bake forward as if it certified bases.
    skip={'pwr.sbsp','native-collision-receipt.json','collision_scene.json','collision_scene.bin',
          'b30_collision.json','level.json','bake'}
    def ignore(path,names):
        return list(skip.intersection(names)) if Path(path).resolve()==(OLD/'upgrade/PWR').resolve() else []
    shutil.copytree(OLD/'upgrade',NEW/'upgrade',ignore=ignore)
    old_config=json.loads(BASE_CONFIG.read_text())['PWR']
    decor_source=ROOT/old_config['authored_decor'];doc=json.loads(decor_source.read_text())
    retired=[r for r in doc['decor'] if r['id'].startswith(('red_home_','blue_home_','citadel_plateau_'))]
    keep=[r for r in doc['decor'] if r not in retired]
    if len(retired)!=69 or len(keep)!=1072:raise RuntimeError('Reviewed scenery inventory changed')
    doc['decor']=keep
    doc['base_replacement']={'source':str(decor_source),'sha256':sha(decor_source),
                             'removed_ids':[r['id'] for r in retired],'retained_records_exact':True}
    write(OUT/'authored-decor.json',doc)
    runtime=json.loads((ROOT/old_config['runtime_decor']).read_text())
    runtime['base_visual_binding_pending']=True
    write(OUT/'runtime-decor.json',runtime)
    config=candidate_config();write(CONFIG,config)
    after={p:sha(p) for p in before}
    if before!=after:raise RuntimeError('Frozen source changed during clone')
    record={'schema':'pwr-base-runtime-candidate-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source':str(OLD),'candidate':str(NEW),'config':str(CONFIG),'config_sha256':sha(CONFIG),
            'source_hashes':before,'sources_unchanged':True,'installed_before':installed,
            'retired_native_decor_ids':[r['id'] for r in retired],'retained_scenery':len(keep),
            'dedicated_base_chunk':CHUNK,'game_modified':False,'apps_launched':False,
            'next':['Export/cook base visuals; bind visual manifest.','Replace authored collision and compile.',
                    'Refresh native probes with new architecture contract.','Cook/bake/assemble, then finalize-level before packaging.']}
    write(OUT/'preparation.json',record)
    print(json.dumps({'candidate':str(NEW),'config':str(CONFIG),'retired_decor':len(retired),'retained_scenery':len(keep)}))

def bind():
    if not (OUT/'preparation.json').exists():raise RuntimeError('Prepare the isolated workspace first')
    additions=json.loads(VISUALS.read_text());base_config=json.loads(BASE_CONFIG.read_text())['PWR']
    # The grass builder writes readbacks beside its input. Isolate those writes
    # instead of replacing the sealed V8 audit evidence during a fresh cook.
    pilot_source=ROOT/base_config['native_grass_pilot']
    pilot_target=ROOT/'out/pwr/base-runtime/landscape-grass-pilot/pilot.json'
    if not pilot_target.parent.exists():
        shutil.copytree(pilot_source.parent,pilot_target.parent)
    graphic_source=ROOT/base_config['paving_graphic']
    graphic_target=ROOT/'out/pwr/base-runtime/paving/graphic.json'
    if not graphic_target.parent.exists():
        shutil.copytree(graphic_source.parent,graphic_target.parent)
    if additions.get('schema')!='mjolnir-runtime-decor-v1' or additions.get('render_only') is not True:
        raise RuntimeError('Invalid base runtime decor manifest')
    original=json.loads((ROOT/base_config['runtime_decor']).read_text())
    rows=original['decor']+additions['decor'];ids=[r['id'] for r in rows]
    if len(ids)!=len(set(ids)):raise RuntimeError('Base runtime decor identifiers overlap')
    if not additions['decor'] or any(not r['mesh'].startswith('/Game/MJOLNIR/Bases/PWRV1/') for r in additions['decor']):
        raise RuntimeError('Base visuals must use the independent PWRV1 asset root')
    result=dict(original,decor=rows,base_visual_binding_pending=False)
    result['base_visual_source']={'path':str(VISUALS),'sha256':sha(VISUALS)}
    write(OUT/'runtime-decor.json',result)
    config=candidate_config();m=config['PWR']
    for row in additions['decor']:
        package=row['mesh'].split('.')[0]
        if not any(x['asset']==package for x in m['required_external_assets']):
            m['required_external_assets'].append({'asset':package,'container':str(CONTAINER)})
    write(CONFIG,config)
    write(OUT/'visual-binding.json',{'schema':'pwr-base-visual-binding-v1','source':str(VISUALS),'source_sha256':sha(VISUALS),
          'runtime_decor_sha256':sha(OUT/'runtime-decor.json'),'config_sha256':sha(CONFIG),'added_actors':len(additions['decor'])})
    print(json.dumps({'bound_actors':len(additions['decor']),'runtime_decor':str(OUT/'runtime-decor.json')}))

def finalize_level():
    path=NEW/'upgrade/PWR/level.json';raw=path.read_bytes();level=json.loads(raw)
    binding=json.loads((OUT/'visual-binding.json').read_text())
    if sha(VISUALS)!=binding['source_sha256']:raise RuntimeError('Base visuals changed after binding')
    source_ids={r['id'] for r in json.loads(VISUALS.read_text())['decor']}
    if not source_ids <= {r['id'] for r in level['decor']}:raise RuntimeError('Assembled level is missing bound bases')
    if any(r['id'].startswith(('red_home_','blue_home_','citadel_plateau_')) for r in level['decor']):
        raise RuntimeError('Retired native decorations leaked into assembly')
    retired=[r for r in level['decor'] if r['id']=='pwr_terrain']
    shadow=level.pop('shadow_shell',None)
    level['decor']=[r for r in level['decor'] if r['id']!='pwr_terrain']
    # SM_PWR_Terrain holds legacy kit + membership floor + bridge rendering.
    # The actual Landscape remains and all four bridges are in the new asset
    # manifest. Its old shadow shell must not shadow through the new tunnels.
    if not retired and shadow is None:
        print(json.dumps({'already_finalized':True,'level':str(path)}));return
    backup=OUT/'level-before-retired-visual-removal.json'
    if not backup.exists():backup.write_bytes(raw)
    write(path,level)
    write(OUT/'assembled-level-finalization.json',{'schema':'pwr-base-level-finalization-v1','path':str(path),
          'before_sha256':hashlib.sha256(raw).hexdigest(),'after_sha256':sha(path),'removed_decor':retired,
          'removed_shadow_shell':shadow,'new_base_actor_count':len(source_ids),'gameplay_metadata_changed':False})
    print(json.dumps({'level':str(path),'removed_old_actor':len(retired),'removed_shadow_shell':shadow is not None}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','bind','finalize-level']);a=p.parse_args()
    {'prepare':prepare,'bind':bind,'finalize-level':finalize_level}[a.action]()
