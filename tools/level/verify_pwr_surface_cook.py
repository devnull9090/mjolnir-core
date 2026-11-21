"""Read-only verification of explicit final PWR Landscape/trial containers.

Run only after the root hands over final owned-cook and965/983 container stems.
Copies are audited in a new output directory. No editor, cook, install or game
commands are executed. NumPy/Pillow: requirements-alpine.txt.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/iostore'))
from zen_class import load_name_batch

ROAD_ALPHA='59bd09246f97476cce3cbdc75ec5b6b09473878ba4fbb642926ea0dda258752b'
BASE_RGB='74d2c0cf69fe4b1025c239ec758e8d2a12bdd248bed2b02668ab964dad09e169'


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def pixels(path):return np.asarray(Image.open(path).convert('RGBA'))


def compare_pixels(source,cooked,exact=True,channels=(0,1,2,3)):
    a,b=pixels(source),pixels(cooked)
    if a.shape!=b.shape:raise ValueError('Texture dimensions changed')
    error=abs(a.astype(np.int16)-b.astype(np.int16))
    maximum=error.max(axis=(0,1)).tolist()
    if exact and any(maximum[channel] for channel in channels):
        raise ValueError(f'Cooked texture bytes differ: max RGBA error{maximum}')
    return {'dimensions':[a.shape[1],a.shape[0]],'pixels_compared':int(a.shape[0]*a.shape[1]),
            'source_sha256':digest(source),'export_sha256':digest(cooked),
            'max_rgba_byte_error':maximum,'mean_rgba_byte_error':error.mean(axis=(0,1)).tolist(),
            'different_rgba_pixels':int(np.any(error,axis=-1).sum()),
            'source_alpha_sha256':hashlib.sha256(a[...,3].tobytes()).hexdigest(),
            'cooked_alpha_sha256':hashlib.sha256(b[...,3].tobytes()).hexdigest(),
            'source_rgb_sha256':hashlib.sha256(a[...,:3].tobytes()).hexdigest(),
            'cooked_rgb_sha256':hashlib.sha256(b[...,:3].tobytes()).hexdigest()}


def property_value(text,name):
    pattern=r'^\s*'+re.escape(name)+r'\s*=\s*(.+)$'
    match=re.search(pattern,text,re.M)
    if not match:raise ValueError('Required cooked property absent: '+name)
    return match.group(1).strip()


def require_false(text,name):
    value=property_value(text,name)
    if not re.match(r'^(?:false|0 \(zeroed\))(?:\s|$)',value):
        raise ValueError(f'{name} must be false, got{value}')


def require_tangent_normal_default(text):
    """A cooked Material may omit its unchanged true class default.

    UE5.5 Engine/Private/Materials/Material.cpp:1053, UMaterial constructor:
    bTangentSpaceNormal = true. Do not extend this to missing texture flags,
    unknown exports, explicit false, or a malformed serialized value.
    """
    if not re.search(r'^\s*bTangentSpaceNormal\b',text,re.M):
        if not re.search(r'^\s*export\s+\d+:.*\s:\sMaterial,\s\d+\sbytes',text,re.M):
            raise ValueError('Missing tangent property without a verified Material export')
        return 'omitted_UE5.5_UMaterial_default_true'
    if not re.match(r'^true(?:\s|$)',property_value(text,'bTangentSpaceNormal')):
        raise ValueError('Apron material must retain its tangent-space normal contract')
    return 'explicit_true'


def require_compression(text,value):
    actual=property_value(text,'CompressionSettings').split()[0]
    if actual!=str(value):raise ValueError(f'Wrong cooked compression {actual}, expected{value}')


def verify_graphic_properties(info,props):
    if not re.search(r'^\s*size\s+1024x1024\s*$',info,re.M) or not re.search(r'^\s*mips\s+11\s*$',info,re.M):
        raise ValueError('Paving graphic must have the declared1024 size and11 mips')
    if 'PF_BC7' not in info or 'classic mip chain' not in info:
        raise ValueError('Paving graphic must be a classic BC7 texture')
    require_compression(props,11)
    for name in ('AddressX','AddressY'):
        if property_value(props,name).split()[0]!='2':
            raise ValueError('Paving graphic must retain mirrored addressing')
    if re.search(r'^\s*SRGB\b',props,re.M):
        if not re.match(r'^true(?:\s|$)',property_value(props,'SRGB')):
            raise ValueError('Paving graphic must use sRGB albedo decoding')
        return 'explicit_true'
    # UTexture2D constructor, UE5.5 Texture2D.cpp:69, initializes SRGB=true.
    if not re.search(r'^export\s+\d+\s+Texture2D\s+\(native tail \d+ bytes\)',props,re.M):
        raise ValueError('Missing sRGB property without verified Texture2D export')
    return 'omitted_UE5.5_UTexture2D_default_true'


def compare_graphic_build(source,cooked):
    """Numeric area statistics verify resize/compression without editing an image.

    These are bounded spatial comparisons, not lossless or per-pixel claims.
    The original1254 and UE-built1024 images intentionally differ in dimensions.
    """
    a,b=pixels(source)[...,:3],pixels(cooked)[...,:3]
    if a.shape!=(1254,1254,3) or b.shape!=(1024,1024,3):
        raise ValueError('Paving graphic original/build dimensions do not match')
    def grid(data):
        return np.asarray([[part.mean(axis=(0,1)) for part in np.array_split(row,16,axis=1)]
                           for row in np.array_split(data,16,axis=0)])
    error=abs(grid(a)-grid(b))
    if error.max()>8 or error.mean()>2:
        raise ValueError('Paving graphic spatial colour changed beyond resize/BC7 tolerance')
    return {'source_dimensions':[1254,1254],'cooked_dimensions':[1024,1024],
            'source_sha256':digest(source),'export_sha256':digest(cooked),
            'comparison':'16x16 area RGB means, not exact pixels',
            'max_block_mean_rgb_error':float(error.max()),'mean_block_mean_rgb_error':float(error.mean()),
            'limits':{'max':8,'mean':2}}


def imported_packages(path):
    data=Path(path).read_bytes()
    if len(data)<52:raise ValueError('Truncated Zen package')
    offset=struct.unpack_from('<IIIIIIiiiiiii',data)[-1]
    if not 52<=offset<len(data):raise ValueError('Invalid imported package name offset')
    names,_=load_name_batch(data,offset)
    return names


def container_files(stem):return [Path(str(stem)+suffix) for suffix in ('.utoc','.ucas')]


def data_texture_inputs(landscape,require_ecology=False):
    inputs=[('T_LandBase','base.png'),('T_LandSurfaceData','surface-detail.png')]
    enabled=landscape.get('pbr',{}).get('ecology')
    if require_ecology and not enabled:
        raise ValueError('Final surface acceptance requires an enabled Ecology binding')
    if enabled:
        file=landscape.get('textures',{}).get('Ecology')
        if not file:raise ValueError('Ecology binding has no source texture')
        if enabled.get('texture')!='/Game/MJOLNIR/Landscape/LPW/T_LandEcology.T_LandEcology':
            raise ValueError('Ecology binding does not identify the owned LPW texture')
        inputs.append(('T_LandEcology',file))
    return inputs


def apron_texture_input(manifest,landscape):
    """Validate source projection and provenance before opening cooked bytes."""
    if manifest is None:return None
    from alpine_surface_v6 import load_apron_texture
    runtime_sha=landscape.get('heightfield',{}).get('manifest_sha256')
    # Direct Landscape bakes record this under their source receipt.
    if runtime_sha is None:
        runtime_sha=landscape.get('source_heightfield',{}).get('manifest_sha256')
    if runtime_sha is None:
        raise ValueError('Apron readback requires Landscape runtime manifest provenance')
    return load_apron_texture(manifest,runtime_sha)


def verify_seals(files,seals):
    actual={str(path.resolve()):digest(path) for path in files}
    if actual!=seals:raise ValueError('Source container changed during audit')


def verify_owned_snapshot(cook,land_stem):
    receipt_path=cook.parent/'owned-cook.json'
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('dir')!=cook.name or receipt.get('code')!='PWR':
        raise ValueError('Owned cook receipt does not identify requested final snapshot')
    for file in container_files(land_stem):
        if digest(file)!=receipt.get('landscape',{}).get(file.suffix[1:]):
            raise ValueError('Final Landscape container differs from owned-cook seal')
    owned=list(cook.glob('*.utoc'))
    if len(owned)!=1:raise ValueError('Expected exactly one owned map container')
    for file in container_files(owned[0].with_suffix('')):
        if digest(file)!=receipt.get('containers',{}).get(file.suffix[1:]):
            raise ValueError('Owned map container hash mismatch')
    return {'path':str(cook.resolve()),'receipt_sha256':digest(receipt_path),'receipt':receipt}


def run(args):
    for stem,chunk in ((args.land_stem,965),(args.material_stem,983)):
        if not stem.name.startswith(f'pakchunk{chunk}-'):
            raise ValueError(f'Expected explicit chunk{chunk} stem, got{stem.name}')
    # Refuse an old audit directory; stale extracted files cannot satisfy this run.
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    paks=out/'paks';paks.mkdir()
    source_files=container_files(args.land_stem)+container_files(args.material_stem)
    globals_=[args.global_paks/'global.utoc',args.global_paks/'global.ucas']
    source_files+=globals_
    seals={str(path.resolve()):digest(path) for path in source_files}
    report={'schema':'pwr-surface-cooked-verification-v1','status':'running',
            'scope':'Cooked bytes, properties and package references only; no live rendering or shader performance claim.',
            'verifier_sha256':digest(__file__),
            'container_seals':seals,'textures':{},'materials':{}}
    def command(argv,log):
        process=subprocess.run([str(part) for part in argv],cwd=ROOT,capture_output=True,text=True)
        (out/log).write_text(process.stdout+process.stderr,encoding='utf-8')
        if process.returncode:raise RuntimeError('Readback command failed; see '+str(out/log))
        return process.stdout
    def extract(package,leaf):
        path=out/(leaf+'.uasset')
        command([args.examples/'extract_file.exe',paks,package+'.uasset',path],leaf+'.extract.txt')
        if not path.is_file():raise ValueError('Package extract missing '+package)
        return path
    try:
        report['owned_cook']=verify_owned_snapshot(args.cook.resolve(),args.land_stem)
        for source in source_files:
            target=paks/source.name
            if target.exists():raise ValueError('Duplicate container filename '+source.name)
            shutil.copyfile(source,target)
            if digest(target)!=seals[str(source.resolve())]:raise ValueError('Audit copy changed')
        # Exact full-resolution data textures: colour and road alpha, no mips or
        # display-gamma conversion may substitute for these byte comparisons.
        landscape=json.loads((args.source_land/'landscape.json').read_text())
        data_inputs=[(leaf,'/Game/MJOLNIR/Landscape/LPW/'+leaf,args.source_land/file)
                     for leaf,file in data_texture_inputs(landscape,getattr(args,'require_ecology',False))]
        apron=apron_texture_input(getattr(args,'apron_geology',None),landscape)
        if apron is not None:
            data_inputs.append(('T_PWR_ApronField','/Game/MJOLNIR/CETrial/T_PWR_ApronField',apron[0]))
            report['apron_geology']={'manifest':str(args.apron_geology.resolve()),
                                    'manifest_sha256':digest(args.apron_geology),'spec':apron[1]}
        input_files=[source for _,_,source in data_inputs]
        if apron is not None:input_files.append(args.apron_geology)
        graphic=None
        if getattr(args,'paving_graphic',None):
            from pwr_paving_graphic import load_graphic_manifest,graphic_cook_inputs
            graphic=load_graphic_manifest(args.paving_graphic)
            input_files+=graphic_cook_inputs(args.paving_graphic)
            report['paving_graphic']={'manifest':str(args.paving_graphic.resolve()),
                                      'manifest_sha256':digest(args.paving_graphic),'spec':graphic[1]}
        input_seals={str(path.resolve()):digest(path) for path in input_files}
        report['data_source_seals']=input_seals
        for leaf,package,source in data_inputs:
            info=command([args.cli,'texture','info','--paks',paks,'--asset',package.removeprefix('/Game/')],leaf+'.info.txt')
            if 'PF_B8G8R8A8' not in info or not re.search(r'size\s+1024x1024',info):
                raise ValueError('Landscape data must be uncompressed1024RGBA')
            asset=extract(leaf,leaf)
            props=[]
            for schema in ('UE-5.5-stock.usmap','Meteorite-2607-CU3.usmap'):
                text=command([args.examples/'props_dump.exe',paks,ROOT/'defs/ue'/schema,asset],leaf+'.'+schema+'.props.txt')
                require_false(text,'SRGB');require_compression(text,5);props.append(text)
            if props[0]!=props[1]:raise ValueError('Texture properties differ between stock and game layout decoding')
            exported=out/(leaf+'.png')
            command([args.cli,'texture','export','--paks',paks,'--asset',package.removeprefix('/Game/'),'--mip','0','--out',exported],leaf+'.export.txt')
            check=compare_pixels(source,exported)
            if leaf=='T_LandBase' and (check['source_alpha_sha256']!=ROAD_ALPHA or check['source_rgb_sha256']!=BASE_RGB):
                raise ValueError('Source Base geology/road bytes changed from the approved proof')
            report['textures'][leaf]={**check,'srgb':False,'compression_settings':5,'property_decodes_identical':True}
        # Native source scans are compressed normally, so report their actual
        # decode error rather than incorrectly requiring lossless BC5/masks.
        for leaf,file,compression in [('T_PWR_PavingNormal','diagonal-normal.png',1),('T_PWR_PavingData','diagonal-orhg.png',2)]:
            package='/Game/MJOLNIR/CETrial/'+leaf
            info=command([args.cli,'texture','info','--paks',paks,'--asset',package.removeprefix('/Game/')],leaf+'.info.txt')
            if not re.search(r'size\s+2048x2048',info) or 'classic mip chain' not in info:
                raise ValueError('Paving texture must be2048classic Texture2D')
            if compression==1 and 'PF_BC5' not in info:raise ValueError('Paving normal is not BC5')
            asset=extract(leaf,leaf)
            props=command([args.examples/'props_dump.exe',paks,ROOT/'defs/ue/Meteorite-2607-CU3.usmap',asset],leaf+'.props.txt')
            require_false(props,'SRGB');require_compression(props,compression)
            exported=out/(leaf+'.png')
            command([args.cli,'texture','export','--paks',paks,'--asset',package.removeprefix('/Game/'),'--mip','0','--out',exported],leaf+'.export.txt')
            check=compare_pixels(args.paving_source/'textures'/file,exported,exact=False)
            check.update({'srgb':False,'compression_settings':compression,'lossless_comparison_required':False})
            report['textures'][leaf]=check
        if graphic is not None:
            leaf='T_PWR_PavingGraphic';package='/Game/MJOLNIR/CETrial/'+leaf
            info=command([args.cli,'texture','info','--paks',paks,'--asset',package.removeprefix('/Game/')],leaf+'.info.txt')
            asset=extract(leaf,leaf)
            props=command([args.examples/'props_dump.exe',paks,ROOT/'defs/ue/Meteorite-2607-CU3.usmap',asset],leaf+'.props.txt')
            storage=verify_graphic_properties(info,props)
            exported=out/(leaf+'.png')
            command([args.cli,'texture','export','--paks',paks,'--asset',package.removeprefix('/Game/'),'--mip','0','--out',exported],leaf+'.export.txt')
            check=compare_graphic_build(graphic[0],exported)
            check.update({'srgb':True,'srgb_property_storage':storage,'compression_settings':11,
                          'addressing':'mirror','mips':11,'source_image_unchanged':True})
            report['textures'][leaf]=check
        material_leaves=['M_CE_PWRPaving','M_CE_PWRRock']
        if apron is not None:material_leaves.append('M_CE_AlpineApron')
        for leaf in material_leaves:
            package='/Game/MJOLNIR/CETrial/'+leaf
            asset=extract(leaf,leaf)
            props=command([args.cli,'ue','get','--paks',paks,'--package',package],leaf+'.props.txt')
            tangent_space_normal=leaf=='M_CE_AlpineApron'
            if tangent_space_normal:
                normal_storage=require_tangent_normal_default(props)
            else:
                require_false(props,'bTangentSpaceNormal')
                normal_storage='explicit_false'
            if leaf=='M_CE_PWRRock' and getattr(args,'require_instanced_rock',False):
                if not re.match(r'^true(?:\s|$)',property_value(props,'bUsedWithInstancedStaticMeshes')):
                    raise ValueError('Render-only cliff rock material must include instanced-mesh usage')
            imports=imported_packages(asset)
            if leaf=='M_CE_PWRPaving':
                for texture in ('T_PWR_PavingNormal','T_PWR_PavingData'):
                    if '/Game/MJOLNIR/CETrial/'+texture not in imports:
                        raise ValueError('Paving material does not import its owned texture '+texture)
                if graphic is not None and '/Game/MJOLNIR/CETrial/T_PWR_PavingGraphic' not in imports:
                    raise ValueError('Paving material does not import its original graphic')
            if leaf=='M_CE_AlpineApron' and '/Game/MJOLNIR/CETrial/T_PWR_ApronField' not in imports:
                raise ValueError('Apron material does not import its actual8km geology texture')
            report['materials'][leaf]={'package':package,'asset_sha256':digest(asset),
                                       'tangent_space_normal':tangent_space_normal,'normal_property_storage':normal_storage,
                                       'imported_packages':imports}
            if leaf=='M_CE_PWRRock' and getattr(args,'require_instanced_rock',False):
                report['materials'][leaf]['instanced_static_meshes']=True
        verify_seals(source_files,seals)
        verify_seals(input_files,input_seals)
        report['source_containers_unchanged']=True;report['status']='passed'
    except Exception as error:
        report['status']='failed';report['error']=str(error)
        raise
    finally:
        (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'receipt':str(out/'receipt.json')}))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cook',type=Path,required=True,help='Final owned-cook-<id> directory')
    parser.add_argument('--land-stem',type=Path,required=True,help='Explicit final965 stem without extension')
    parser.add_argument('--material-stem',type=Path,required=True,help='Explicit final983 stem without extension')
    parser.add_argument('--source-land',type=Path,required=True)
    parser.add_argument('--require-ecology',action='store_true',help='Fail if final visual5 bake omitted the new linear ecology binding')
    parser.add_argument('--apron-geology',type=Path,help='Optional visual6 manifest: require exact linear T_PWR_ApronField and material import')
    parser.add_argument('--paving-graphic',type=Path,help='Optional visual7 manifest: require original albedo provenance,1024 BC7/mirror/sRGB and11 mips')
    parser.add_argument('--require-instanced-rock',action='store_true',help='Require the render-only cliff HISM usage flag on M_CE_PWRRock')
    parser.add_argument('--out',type=Path,required=True,help='New isolated audit directory')
    parser.add_argument('--global-paks',type=Path,default=Path('C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks'))
    parser.add_argument('--paving-source',type=Path,default=ROOT/'out/pwr/visual-v5/paving-materials-v3')
    parser.add_argument('--cli',type=Path,default=ROOT/'target/release/mjolnir.exe')
    parser.add_argument('--examples',type=Path,default=ROOT/'target/release/examples')
    run(parser.parse_args())


if __name__=='__main__':main()
