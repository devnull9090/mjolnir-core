"""Bind verified linear LPW geology to the apron; never cooks or installs."""
import argparse
import copy
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
import alpine_geology
from heightfield import sha256


def binding(material,landscape):
    pbr=landscape['pbr']
    rect=np.asarray(pbr['rect'],dtype=float)
    if rect.shape!=(4,) or not np.all(np.isfinite(rect)) or np.any(rect[2:]<=0):
        raise ValueError('Invalid world-space geology rectangle')
    if pbr['alpine'][3]!=2 or pbr['base']!='/Game/MJOLNIR/Landscape/LPW/T_LandBase.T_LandBase':
        raise ValueError('This candidate requires verified LPW Alpine2 geology')
    result=copy.deepcopy(material)
    result['textures']['ApronGeology']=pbr['base']
    result['vectors']['ApronGeologyRect']=rect.tolist()
    result['vectors']['ApronGeologyBlend']=[0,15000,.72,1]
    result['vectors']['ApronGeologyMix']=[pbr['mix'][0],pbr['mix'][1],.8,.65]
    result['vectors']['ApronFarSnow']=[52000,76000,0,75000]
    result['vectors']['ApronSnowRetention']=[6500,1800,.4,1]
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--landscape',type=Path,default=Path('C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5/upgrade/PWR/land/landscape.json'))
    parser.add_argument('--geology',type=Path,default=ROOT/'out/pwr/visual-v5/geology/geology.json')
    parser.add_argument('--apron',type=Path,default=ROOT/'out/pwr/visual-v5/apron-v3')
    parser.add_argument('--material-source',type=Path,
                        help='optional reviewed material JSON or runtime-decor containing pwr_distant_apron; preserves field/ecology inputs')
    args=parser.parse_args()
    land=json.loads(args.landscape.read_text())
    data,spec=alpine_geology.load(args.geology,land['heightfield']['manifest_sha256'])
    base=args.landscape.parent/land['textures']['Base']
    image=np.asarray(Image.open(base).convert('RGBA'))
    expected=alpine_geology.sample_texture(data,image.shape[1],image.shape[0])
    if not np.array_equal(expected,image[:,:,:3]):
        raise ValueError('Current Base RGB does not match the linear geology bake')
    original_path=args.apron/'runtime_decor.json'
    original=json.loads(original_path.read_text())
    candidate=copy.deepcopy(original)
    source_material=candidate['decor'][0]['materials'][0]
    if args.material_source:
        source_material=json.loads(args.material_source.read_text())
        if 'decor' in source_material:
            rows=[r for r in source_material['decor'] if r.get('id')=='pwr_distant_apron']
            if len(rows)!=1 or len(rows[0].get('materials',[]))!=1:
                raise ValueError('Material source must contain one uniquely bound pwr_distant_apron')
            source_material=rows[0]['materials'][0]
        if source_material.get('parent')!='/Game/MJOLNIR/CETrial/M_CE_AlpineApron.M_CE_AlpineApron':
            raise ValueError('Material source must use the reviewed world-space Alpine apron parent')
    material=binding(source_material,land)
    candidate['decor'][0]['materials']=[material]
    target=args.apron/'runtime_decor.geology.json'
    target.write_text(json.dumps(candidate,indent=2)+'\n')
    material_path=args.apron/'geology.material.json'
    material_path.write_text(json.dumps(material,indent=2)+'\n')
    receipt={'schema':'pwr-apron-geology-seam-v1','runtime_master_sha256':land['heightfield']['manifest_sha256'],
        'source_decor_sha256':sha256(original_path),'candidate_decor_sha256':sha256(target),
        'candidate_decor':str(target.resolve()),'material_sha256':sha256(material_path),
        'landscape_spec_sha256':sha256(args.landscape),'base_png_sha256':sha256(base),
        'geology_spec_sha256':sha256(args.geology),'geology_rgb_byte_exact':True,
        'encoding':'linear UNORM8; editor sRGB=false and vector-displacement compression; linear/clamped sampler',
        'world_uv':'(UE.xy - ApronGeologyRect.xy)/ApronGeologyRect.zw; PNG rows follow UE+Y; no extra flip',
        'fade_outside_m':[0,150],'geometry_or_native_collision_changed':False,
        'outer_snow_range_m':[520,760],'outer_snow_transition_outside_m':[0,750],
        'outer_retention':'world-space65m/18m patches; exact edge geology overrides this result',
        'shader_source_sha256':sha256(ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'),
        'status':'candidate requires parent shared-shader cook and actual live seam review; not installed'}
    if args.material_source:
        receipt['reviewed_material_source']={'path':str(args.material_source.resolve()),'sha256':sha256(args.material_source)}
    (args.apron/'geology-seam.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
