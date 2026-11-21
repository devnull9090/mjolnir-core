"""Bind a separate base support/drive plan to the compiled native triangles.

No game calls. Patching only adds acceptance cutscene flags to a staged
scenario; gameplay flags, spawn/vehicle layout and the terrain plan remain.
"""
from pathlib import Path
import argparse
import copy
import math
import re
if __package__:
    from .prepare_runtime_candidate import ROOT, NEW, sha, write
    from .install_candidate import require, read
else:
    from prepare_runtime_candidate import ROOT, NEW, sha, write
    from install_candidate import require, read

DEFAULT=ROOT/'out/pwr/base-runtime/base-probe-plan.json'
PROOF=ROOT/'out/pwr/base-runtime/compiled-base-collision-proof.json'
CONTRACT=NEW/'source-build/base-architecture-contract.json'
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
LAYOUT=ROOT/'out/pwr/world-v5/layout.json'


def verify_plan(plan_path):
    plan_path=Path(plan_path).resolve();plan=read(plan_path)
    require(plan.get('schema')=='pwr-terrain-probe-v1' and plan.get('base_probe_revision')==1
            and plan.get('protocol')==20569 and plan.get('layout_revision')==3,'Invalid separate base probe plan')
    provenance=plan['provenance'];inputs=provenance['input_hashes']
    require(isinstance(inputs,dict) and len(inputs)>=10,'Incomplete base probe provenance')
    for path,digest in inputs.items():
        require(Path(path).is_absolute() and sha(path)==digest,'Base probe source changed: '+path)
    proof=read(provenance['architecture_proof_path']);compiled=read(provenance['receipt_path'])
    require(proof.get('passed') is True and proof.get('all_source_triangles_exact_float32') is True
            and proof.get('compiled_boundaries_verified') is True and proof['architecture_audit']['passed'] is True,
            'Base probes require exact float32 native readback and piece ownership')
    require(proof['compiled_receipt_sha256']==provenance['receipt_sha256']==sha(provenance['receipt_path'])
            and proof['compiled_collision_sha256']==provenance['compiled_tag_sha256']==compiled['output_sha256']
            and sha(compiled['output'])==compiled['output_sha256'],'Base probes belong to another compiled collision')
    require(sha(plan['master_path'])==plan['master_manifest_sha256'],'Base probe terrain master changed')
    probes=plan['probes'];require(len(probes)==13 and probes[0]['kind']=='calibration','Expected calibration + four supports per base')
    names=set()
    for p in probes:
        require(re.fullmatch(r'terrain_probe_bv1_[a-z_]{1,13}',p['flag']) and p['flag'] not in names,'Invalid base probe flag')
        names.add(p['flag'])
        require(len(p['position_m'])==3 and all(math.isfinite(x) for x in p['position_m'])
                and math.isfinite(p['floor_m']) and p['surface']=='base_plaza'
                and 0<p['max_residual_m']<=.35,'Invalid base support measurement')
    expected={p['id']:p for p in proof['architecture_audit']['probes']}
    for p in probes[1:]:
        original=expected[p['id']]
        require(p['position_m']==original['position_m'] and p['floor_m']==original['floor_m'],
                'Base support was not taken from actual native readback')
    require([r['team'] for r in plan['vehicle_routes']]==['red','blue','green'],'Expected all three vehicle routes')
    return {str(plan_path):sha(plan_path),**inputs}


def build(proof_path=PROOF,out=DEFAULT):
    proof_path=Path(proof_path).resolve();proof=read(proof_path);contract=read(CONTRACT)
    require(proof['contract_sha256']==sha(CONTRACT),'Compiled proof has another architecture contract')
    receipt_path=Path(proof['compiled_receipt']);receipt=read(receipt_path)
    paths=[proof_path,CONTRACT,MASTER,LAYOUT,receipt_path,Path(receipt['output']),Path(receipt['source_manifest']),
           Path(receipt['source_manifest']).with_suffix('.bin')]
    paths += [Path(contract[k]['path']) for k in ('source','source_blend','placement_plan','handoff','baseline_extra','output_extra','ordered','audit')]
    master=read(MASTER);layout=read(LAYOUT)
    home=layout['homes_m']['red']
    probes=[{'id':'base_calibration','flag':'terrain_probe_bv1_cal','kind':'calibration','surface':'base_plaza',
             'position_m':[home[0],home[1],home[2]+.8],'floor_m':home[2],'yaw':0,'max_residual_m':.35}]
    samples={p['id']:p for p in proof['architecture_audit']['probes']};routes=[]
    for team in ('red','blue','green'):
        chosen={}
        for role,short in (('front_court','front'),('main_tunnel','hall'),('rear_court','rear'),('roof','roof')):
            p=copy.deepcopy(samples[team+'_'+role]);p.update(flag=f'terrain_probe_bv1_{team[0]}_{short}',surface='base_plaza',yaw=-90)
            probes.append(p);chosen[short]=p
        routes.append({'team':team,'start_flag':chosen['front']['flag'],'end_flag':chosen['rear']['flag'],
                       'start_m':chosen['front']['position_m'],'end_m':chosen['rear']['position_m'],
                       'hall_m':chosen['hall']['position_m'],'floor_m':chosen['hall']['floor_m'],
                       'direction':[0,1],'max_lateral_m':3.0,'max_step_m':12,'max_duration_ms':20000})
    plan={'schema':'pwr-terrain-probe-v1','base_probe_revision':1,'protocol':20569,'layout_revision':3,
          'master_path':str(MASTER),'master_manifest_sha256':sha(MASTER),'height_sha256':master['height']['sha256'],
          'provenance':{'compiled_boundaries_verified':True,'receipt_path':str(receipt_path),
                        'receipt_sha256':sha(receipt_path),'compiled_tag_sha256':receipt['output_sha256'],
                        'architecture_proof_path':str(proof_path),'input_hashes':{str(p.resolve()):sha(p) for p in paths}},
          'contact_method':'Stable native positions against exact compiled base supports; no raw contact flag or ray hit.',
          'probes':probes,'vehicle_routes':routes,
          'coverage':'All three main halls, front/rear courts and rooftop cannon platforms. Vehicle clearance remains live-unvalidated.'}
    write(out,plan);verify_plan(out)
    print({'plan':str(out),'probes':len(probes),'routes':len(routes)})


def patch_level(plan_path,level_path):
    verify_plan(plan_path)
    plan=read(plan_path);level=read(level_path)
    require(level.get('warfare')=={'protocol':20569,'layout_revision':3},'Expected native layout3 staged scenario')
    stamp='terrain_probe_hash_'+sha(plan_path)[:12]
    flags=level['blam'].setdefault('cutscene_flags',[])
    original=[f for f in flags if not f['name'].startswith('terrain_probe_bv1_') and f['name']!=stamp]
    additions=[{'name':p['flag'],'pos':[100*p['position_m'][0],-100*p['position_m'][1],100*p['position_m'][2]],'yaw':p['yaw']}
               for p in plan['probes']]
    additions.append({'name':stamp,'pos':additions[-1]['pos'],'yaw':0})
    flags[:]=[f for f in original if not f['name'].startswith('pwr_')]+additions+[f for f in original if f['name'].startswith('pwr_')]
    require(len({f['name'] for f in flags})==len(flags),'Duplicate acceptance or gameplay cutscene flag')
    write(level_path,level)
    return stamp


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--proof',type=Path,default=PROOF);b.add_argument('--out',type=Path,default=DEFAULT)
    p=sub.add_parser('patch');p.add_argument('plan',type=Path);p.add_argument('level',type=Path)
    v=sub.add_parser('verify');v.add_argument('plan',type=Path)
    args=parser.parse_args()
    if args.action=='build':build(args.proof,args.out)
    elif args.action=='patch':print(patch_level(args.plan,args.level))
    else:print(verify_plan(args.plan))
