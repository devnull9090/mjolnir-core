"""Material-only visual6 candidates from sealed terrain and ecology inputs.

No editor, height writes, mesh/collision changes, or installed files. NumPy,
SciPy and Pillow versions are pinned by requirements-alpine.txt.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from heightfield import load_heightfield
from alpine_geology import sample_texture
from alpine_ecology import load as load_ecology

ROOT=Path(__file__).resolve().parents[2]
PARENT='/Game/MJOLNIR/CETrial/M_CE_PWRPaving.M_CE_PWRPaving'
RECIPES={
 'alloy':{'PavingTint':[.38,.40,.38,1],'PavingParams':[400,.72,.30,.30],
          'PavingLayout':[2400,3600,3.5,1],'PavingPattern':[30,.03,.18,.25]},
 'joint':{'PavingTint':[.16,.18,.175,1],'PavingParams':[400,.82,.15,.18],
          'PavingLayout':[2400,3600,3.5,0],'PavingPattern':[30,0,0,0]},
 'floor':{'PavingTint':[.30,.33,.32,1],'PavingParams':[400,.74,.28,.25],
          'PavingLayout':[2000,3200,3.5,1],'PavingPattern':[25,.025,.18,.20]},
 'wall':{'PavingTint':[.31,.33,.33,1],'PavingParams':[600,.72,.30,.28],
          'PavingLayout':[2400,3600,3.0,1],'PavingPattern':[25,.025,.16,.20]},
}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def smooth(lo,hi,value):
    t=np.clip((value-lo)/(hi-lo),0,1);return t*t*(3-2*t)
def invert_smooth(value):
    grid=np.linspace(0,1,8193)
    return np.interp(np.clip(value,0,1),grid*grid*(3-2*grid),grid)


def normalized_channel(value,low,high):
    # Gaea channels are sparse scalar masks, not display images. Calibrated
    # source-specific ranges are explicit and included in the receipt.
    return smooth(low,high,value)


def compose_apron_height(field,join):
    """Sample the real final collar; all other samples retain native Gaea Z."""
    z=field.heights_m.copy();h,w=z.shape
    x=field.origin_m[0]+np.arange(w)*field.spacing_m[0]
    y=field.origin_m[1]+np.arange(h)*field.spacing_m[1]
    xx,yy=np.meshgrid(x,y)
    join_z=join['heights_m'];origin=join['origin_m'];spacing=float(join['spacing_m'])
    ix=(xx-origin[0])/spacing;iy=(yy-origin[1])/spacing
    inside=(ix>=0)&(iy>=0)&(ix<=join_z.shape[1]-1)&(iy<=join_z.shape[0]-1)
    z[inside]=map_coordinates(join_z,[iy[inside],ix[inside]],order=1,mode='nearest')
    return z,xx,yy


def derive_apron(field,join):
    z,xx,yy=compose_apron_height(field,join);spacing=field.spacing_m[0]
    z12=gaussian_filter(z,12/spacing);z40=gaussian_filter(z,40/spacing)
    gy,gx=np.gradient(z12,*field.spacing_m);slope=np.hypot(gx,gy)
    concave=smooth(.4,6,z40-z12);ridge=smooth(.5,7,z12-z40)
    north=np.clip(-gy/np.maximum(slope,.05),0,1)
    valid_source=1-smooth(1,10,abs(z-field.heights_m))
    flow=normalized_channel(field.masks['flow'],.001,.06)*valid_source
    wear=normalized_channel(field.masks['wear'],.001,.025)*valid_source
    deposits=normalized_channel(field.masks['deposits'],.0001,.0025)*valid_source
    # Exposed ridges are rock even where rounded by the 8m source grid.
    # High sheltered surfaces retain snow; rock survives in wind-scoured crests.
    altitude=smooth(280,560,z)
    rock=np.maximum.reduce([smooth(.22,.75,slope),wear*.85,ridge*.85,
                            altitude*(.50+.35*(1-deposits))])
    shelter=np.clip(.25+.42*concave+.23*flow+.24*north+.15*deposits-.38*ridge,0,1)
    snowline=420-75*shelter+35*ridge
    snow=smooth(snowline,snowline+150,z)*(1-smooth(.72,1.75,slope))
    snow*=np.clip(.48+.72*shelter-.35*ridge,.10,1)
    # Exposed crests stay dark; continuous channels and sheltered bowls carry
    # snow instead of multiplying by unrelated procedural patch noise.
    soil=(.20*deposits+.16*flow+.12*concave)*(1-rock)*(1-snow)
    moisture=np.clip(.18+.40*flow+.30*concave+.15*north,0,1)
    rgba=np.stack([rock,snow,soil,moisture],-1).astype(np.float32)
    outside=np.maximum(abs(xx),abs(yy))>1300
    report={'height_percentiles_m':np.quantile(z[outside],[.1,.5,.75,.9,.99]).tolist(),
            'outside_collar_weighted_rock':float(rock[outside].mean()),
            'outside_collar_weighted_snow':float(snow[outside].mean()),
            'outside_collar_snow_above_half_fraction':float((snow[outside]>.5).mean()),
            'high_flanks_weighted_snow':float(snow[outside&(z>400)].mean()),
            'source_channel_ranges':{'flow':[.001,.06],'wear':[.001,.025],'deposits':[.0001,.0025]},
            'snow_policy':'sheltered start345..420m, ridge penalty35m,150m transition; rock crests retained',
            'procedural_noise':False}
    return rgba,report


def derive_meadow(field,previous,target=.08):
    """Recalibrate existing hydrology and broad actual curvature, not noise."""
    z=field.heights_m;dx,dy=field.spacing_m
    z24=gaussian_filter(z,24/dx);z80=gaussian_filter(z,80/dx)
    gy,gx=np.gradient(z,dy,dx);slope=np.hypot(gx,gy)
    protected=np.maximum.reduce([field.masks.get(k,np.zeros_like(z)) for k in ('road','water','bases')])
    available=1-smooth(.05,.65,protected)
    moisture=.04+.90*smooth(.16,.50,previous[...,0])
    dry_crests=smooth(.10,1.8,z24-z80)*(1-moisture)
    runnels=smooth(.015,.12,previous[...,2])*.65
    broad=gaussian_filter(dry_crests,14/dx)*.34
    signal=(runnels+broad)*(1-.65*previous[...,1])*available
    baseline=smooth(.13,.43,previous[...,2])*.85
    meadow=(z<165)&(slope<.25)&(protected<.05)&(previous[...,1]<.2)
    if meadow.sum()<16:raise ValueError('No representative open meadow samples')
    low,high=0.,12.
    for _ in range(32):
        gain=(low+high)/2
        value=np.maximum(baseline,np.clip(signal*gain,0,.52))
        if value[meadow].mean()<target:low=gain
        else:high=gain
    soil=np.maximum(baseline,np.clip(signal*high,0,.52))*available
    data=previous.copy();data[...,0]=moisture
    # Preserve the current ecology texture codec and shader; encode the exact
    # desired mix through its documented smoothstep(.13,.43,B)*.85 decoder.
    data[...,2]=np.where(soil>0,.13+.30*invert_smooth(soil/.85),0)
    report={'open_meadow_samples':int(meadow.sum()),'soil_mix_before':float(baseline[meadow].mean()),
            'soil_mix_after':float(soil[meadow].mean()),'soil_gain':high,
            'soil_mix_above_15pct_fraction':float((soil[meadow]>.15).mean()),
            'moisture_before_percentiles':np.quantile(previous[...,0][meadow],[.1,.5,.9]).tolist(),
            'moisture_after_percentiles':np.quantile(moisture[meadow],[.1,.5,.9]).tolist(),
            'coherence_metres':[24,80,14],'protected_soil_max':float(soil[protected>=.65].max(initial=0)),
            'random_noise':False,'height_changes':False}
    return np.clip(data,0,1).astype(np.float32),report


def prepare_paving(source,out):
    out.mkdir(parents=True,exist_ok=True);(out/'textures').mkdir(exist_ok=True)
    old=json.loads((source/'receipt.json').read_text())
    for file,expected in old['files'].items():
        if digest(source/file)!=expected:raise ValueError('Frozen paving texture changed')
        shutil.copy2(source/file,out/file)
    overrides=json.loads((source/'material-overrides.json').read_text())
    for rule,kind in zip(overrides['overrides'][:2],('floor','wall')):rule['vectors']=RECIPES[kind]
    dump(out/'materials.json',[{'parent':PARENT,'vectors':RECIPES[k]} for k in ('alloy','joint')])
    dump(out/'material-overrides.json',overrides)
    result=copy.deepcopy(old);result['schema']='pwr-paving-materials-v3';result['recipes']=RECIPES
    result['mapping']['coarse_panels']='20..36m coherent alloy plates;3..3.5cm joints;25..30cm chamfers;finish variation<=3%;sparse service lines'
    result['mapping']['PavingPattern']='chamfer cm, finish variance, seam darkening, service fraction'
    result['generator_sha256']=digest(__file__)
    result['shader_source_sha256']=digest(ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py')
    for key,entry in result['sources'].items():entry['export']=str(out/'textures'/Path(entry['export']).name)
    dump(out/'receipt.json',result)


def verify_tree_binding(path,ecology_spec):
    """Finalization must identify the exact selection used by raw ecology."""
    spec=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    instances=spec.get('instances')
    if (spec.get('schema')!=1 or not isinstance(instances,list)
            or len(instances)!=spec.get('selected_count')
            or len(instances)!=ecology_spec.get('tree_count')
            or digest(path)!=ecology_spec.get('trees_sha256')):
        raise ValueError('Ecology does not match the exact final tree selection')
    return {'path':str(Path(path).resolve()),'sha256':digest(path),'count':len(instances)}


def load_apron_texture(manifest,runtime_sha256):
    path=Path(manifest);spec=json.loads(path.read_text())
    if (spec.get('schema')!='pwr-apron-geology-v1' or spec.get('coordinates')!='authoring_metres_z_up'
            or spec.get('row_order')!='+y' or spec.get('runtime_master_sha256')!=runtime_sha256):
        raise ValueError('Apron geology coordinate/runtime provenance mismatch')
    if spec.get('encoding')!={'srgb':False,'compression':'vector_displacement'}:
        raise ValueError('Apron geology must be linear data')
    for key,sealed in [('source_master','source_master_sha256'),('collar','collar_sha256')]:
        if digest(spec[key])!=spec[sealed]:raise ValueError('Apron geometry source changed: '+key)
    source=load_heightfield(spec['source_master']) # verifies height/mask seals
    if (spec.get('dimensions')!=list(source.dimensions)
            or spec.get('origin_m')!=list(source.origin_m)
            or spec.get('spacing_m')!=list(source.spacing_m)):
        raise ValueError('Apron geology grid differs from its source')
    (x0,y0),(x1,y1)=source.bounds_m
    expected_rect=[x0*100,-y1*100,(x1-x0)*100,(y1-y0)*100]
    if (spec.get('world_rect_cm')!=expected_rect
            or spec.get('exact_edge_blend_m')!=[0,150]
            or spec.get('channels')!=['rock','snow','colluvium','moisture']):
        raise ValueError('Apron geology world projection/channel contract differs')
    data=path.parent/spec['data'];texture=path.parent/spec['texture']
    if digest(data)!=spec['data_sha256'] or digest(texture)!=spec['texture_sha256']:
        raise ValueError('Apron geology data/texture hash changed')
    rgba=np.load(data,allow_pickle=False)
    if rgba.dtype!=np.float32 or rgba.shape!=(*spec['dimensions'][::-1],4) or not np.isfinite(rgba).all():
        raise ValueError('Invalid apron geology array')
    if rgba.min()<0 or rgba.max()>1:raise ValueError('Apron geology weights outside0..1')
    actual=np.asarray(Image.open(texture).convert('RGBA'))
    if actual.shape!=(1024,1024,4) or not np.array_equal(actual,sample_texture(rgba,1024,1024)):
        raise ValueError('Apron geology projection/linear texture bytes differ')
    return texture.resolve(),spec


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v6/surface')
    p.add_argument('--master',type=Path,default=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    p.add_argument('--apron-master',type=Path,default=ROOT/'levels/warfare/pwr/terrain/gaea-apron-v4/source.json')
    p.add_argument('--apron-collar',type=Path,default=ROOT/'out/pwr/visual-v5/apron-v4/harmonic-field.npz')
    p.add_argument('--ecology',type=Path,default=ROOT/'out/pwr/visual-v5/surface-v5/final/ecology/ecology.json')
    p.add_argument('--trees',type=Path,help='Final selected tree file; require raw ecology count/hash match (omit only for provisional review)')
    p.add_argument('--paving',type=Path,default=ROOT/'out/pwr/visual-v5/paving-materials-v4')
    p.add_argument('--base',type=Path,default=Path('C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5-visual5/upgrade/PWR/land/base.png'))
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    inputs=[args.master,args.apron_master,args.apron_collar,args.ecology,args.paving/'receipt.json',args.base]
    field=load_heightfield(args.master);apron=load_heightfield(args.apron_master)
    for source in (field,apron):
        inputs.append(source.path.parent/source.metadata['height']['path'])
        inputs.extend(source.path.parent/mask['path'] for mask in source.metadata.get('masks',{}).values())
    old_manifest=json.loads(args.ecology.read_text());inputs.append(args.ecology.parent/old_manifest['data'])
    tree_binding=verify_tree_binding(args.trees,old_manifest) if args.trees else None
    if args.trees:inputs.append(args.trees)
    seals={str(path.resolve()):digest(path) for path in inputs}
    road_alpha=hashlib.sha256(np.asarray(Image.open(args.base).convert('RGBA'))[...,3].tobytes()).hexdigest()
    if road_alpha!='59bd09246f97476cce3cbdc75ec5b6b09473878ba4fbb642926ea0dda258752b':
        raise ValueError('Base road alpha differs from approved visual5')
    old,old_spec=load_ecology(args.ecology,field.manifest_sha256)
    data,meadow_report=derive_meadow(field,old)
    eco=args.out/'ecology';eco.mkdir(exist_ok=True);np.save(eco/'ecology.rgba.npy',data)
    spec=copy.deepcopy(old_spec);spec.update(data='ecology.rgba.npy',data_sha256=digest(eco/'ecology.rgba.npy'),
        generator_sha256=digest(__file__),mean=data.mean((0,1)).tolist(),visual6=meadow_report)
    dump(eco/'ecology.json',spec);Image.fromarray(sample_texture(data,1024,1024)).save(eco/'ecology.png')
    masks,apron_report=derive_apron(apron,np.load(args.apron_collar))
    far=args.out/'apron';far.mkdir(exist_ok=True);np.save(far/'geology.rgba.npy',masks)
    Image.fromarray(sample_texture(masks,1024,1024)).save(far/'apron-geology.png')
    apron_spec={'schema':'pwr-apron-geology-v1','coordinates':'authoring_metres_z_up','row_order':'+y',
      'source_master':str(args.apron_master.resolve()),'source_master_sha256':apron.manifest_sha256,
      'runtime_master_sha256':field.manifest_sha256,
      'collar':str(args.apron_collar.resolve()),'collar_sha256':digest(args.apron_collar),'dimensions':list(apron.dimensions),
      'origin_m':list(apron.origin_m),'spacing_m':list(apron.spacing_m),
      'data':'geology.rgba.npy','data_sha256':digest(far/'geology.rgba.npy'),
      'texture':'apron-geology.png','texture_sha256':digest(far/'apron-geology.png'),
      'channels':['rock','snow','colluvium','moisture'],'encoding':{'srgb':False,'compression':'vector_displacement'},
      'world_rect_cm':[-400000,-400000,800000,800000],'exact_edge_blend_m':[0,150],**apron_report}
    dump(far/'geology.json',apron_spec)
    prepare_paving(args.paving,args.out/'paving')
    fragment={'ecology':str((eco/'ecology.json').resolve()),'paving_materials':str((args.out/'paving/receipt.json').resolve()),
      'apron_geology':str((far/'geology.json').resolve()),
      'apron_material_additions':{'textures':{'ApronField':'/Game/MJOLNIR/CETrial/T_PWR_ApronField.T_PWR_ApronField',
          'ApronEcology':'/Game/MJOLNIR/Landscape/LPW/T_LandEcology.T_LandEcology'},
        'vectors':{'ApronFieldInfo':[1,0,0,0],'ApronFieldRect':[-400000,-400000,800000,800000],
          'ApronEcologyInfo':[1,0,0,0]}}}
    dump(args.out/'config-fragment.json',fragment)
    if seals!={str(path.resolve()):digest(path) for path in inputs}:raise ValueError('Frozen source changed')
    dump(args.out/'receipt.json',{'schema':'pwr-visual6-surface-v1','inputs':seals,'meadow':meadow_report,'apron':apron_report,
       'final_tree_binding':tree_binding,'ecology_provisional':tree_binding is None,
       'source_heights_unchanged':True,'source_road_alpha_unchanged':True,'source_road_alpha_sha256':road_alpha,'generator_sha256':digest(__file__),
       'shader_sha256':digest(ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'),
       'status':'CPU candidate; actual cook and live appearance pending'})
    print(json.dumps({'output':str(args.out),'meadow':meadow_report,'apron':apron_report},indent=2))


if __name__=='__main__':main()
