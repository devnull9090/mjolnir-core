"""Prepare isolated PWR matte alloy bindings from shipped Forerunner maps.

The former native MIC clone depended on inherited white vertex masks. This
replacement is an explicit Default Lit master built by build_ce_materials.py
in the owned trial-material chunk; it needs no separate chunk960 container.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
PARENT='/Game/MJOLNIR/CETrial/M_CE_PWRPaving.M_CE_PWRPaving'
RECIPES={
 'alloy':{'PavingTint':[.38,.40,.38,1], 'PavingParams':[400,.74,.25,.35], 'PavingLayout':[1000,1500,30,1]},
 'joint':{'PavingTint':[.09,.11,.105,1], 'PavingParams':[400,.84,.12,.20], 'PavingLayout':[900,1400,18,.25]},
 'floor':{'PavingTint':[.28,.31,.30,1], 'PavingParams':[400,.76,.22,.28], 'PavingLayout':[750,1200,22,.85]},
 'wall':{'PavingTint':[.30,.32,.32,1], 'PavingParams':[600,.74,.25,.30], 'PavingLayout':[1000,1600,12,.60]},
}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def prepare(paks,out):
 out.mkdir(parents=True,exist_ok=True);textures=out/'textures';textures.mkdir(exist_ok=True)
 sources={}
 for asset,file in [('T_FR_Diagonal_01_N','diagonal-normal.png'),('T_FR_Diagonal_01_ORHG','diagonal-orhg.png')]:
  command=[str(ROOT/'target/release/mjolnir.exe'),'texture','export','--paks',str(paks),'--asset',asset,'--mip','0','--out',str(textures/file)]
  result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=True)
  (out/(asset+'.export.txt')).write_text(result.stdout+result.stderr)
  sources[asset]={'export':str(textures/file),'sha256':digest(textures/file),'mip':0,'dimensions':[2048,2048]}
 materials=[{'parent':PARENT,'vectors':RECIPES[k]} for k in ('alloy','joint')]
 overrides=json.loads((ROOT/'levels/warfare/pwr/material-overrides-v5.json').read_text())
 overrides['verified_source']='Explicit PWR Default Lit shader from shipped Diagonal N/ORHG exports; no vertex/COH/frost inputs. Only generated floor/wall slots change; native detailed buttresses retain stock materials.'
 for rule,kind in zip(overrides['overrides'][:2],('floor','wall')):
  rule['material']=PARENT;rule['vectors']=RECIPES[kind];rule.pop('scalars',None)
 (out/'materials.json').write_text(json.dumps(materials,indent=2)+'\n')
 (out/'material-overrides.json').write_text(json.dumps(overrides,indent=2)+'\n')
 report={'schema':'pwr-paving-materials-v2','parent':PARENT,'container_stem':None,'shared_trial_chunk':983,
         'requires_cook':True,'retired_candidate':'chunk960 native MIC clone; never integrate',
         'recipes':RECIPES,'sources':sources,
         'mapping':{'projection':'world triplanar','alloy_tile_m':4,'wall_tile_m':6,'geometry_effect':'none',
                    'coarse_panels':'original staggered chamfered plates, metre-scale inset joints and triangular service panels',
                    'PavingLayout':'plate width cm, length cm, joint width cm, strength'},
         'texture_encoding':{'PanelNormal':'linear UE/DirectX BC5; RG decoded -1..1; green not flipped',
                             'PanelData':'linear masks; R occlusion G roughness B unused height'},
         'roughness_bounds':[.65,.90], 'vertex_color_inputs':False,'mesh_coh_inputs':False,'frost_layers':False,
         'files':{str(p.relative_to(out)):digest(p) for p in textures.glob('*.png')},
         'generator_sha256':digest(__file__),
         'shader_source_sha256':digest(ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'),
         'validation':'Source/schema and imported shader proof; cooked/live appearance still requires root acceptance'}
 (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--paks',type=Path,default=Path('C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks'))
 p.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v5/paving-materials-v4')
 a=p.parse_args();prepare(a.paks,a.out)
