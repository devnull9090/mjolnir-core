"""Cache actual native assets used by an MJF3 scatter output for Blender."""
import argparse
import json
import struct
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'mjolnir_level'))
from asset_cache import cache_asset

p=argparse.ArgumentParser(description=__doc__)
for name in ('foliage','cli','paks','cache'):
    p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
foliage=json.loads(a.foliage.read_text())
models={}; materials={}; textures={}; material_slots={}
def texture(asset):
    if asset not in textures:
        textures[asset]=str(cache_asset(a.cli,a.paks,a.cache,asset,'texture').resolve())
    return textures[asset]
for mesh in sorted({g['mesh'] for g in foliage['groups']}):
    print('PCG cache',mesh,flush=True)
    models[mesh]=str(cache_asset(a.cli,a.paks,a.cache,mesh).resolve())
    raw=Path(models[mesh]).read_bytes()
    gltf=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
    material_slots[mesh]=[m.get('name','') for m in gltf.get('materials',[])]
    grass='Wild_Grass_' in mesh
    if grass:
        code=next((code for code in ('vdilbaiia','vczndjqja') if code in mesh),None)
        if code is None: raise ValueError('Unsupported wild grass texture set: '+mesh)
        prefix=f'/Game/Megascans/3D_Plants/Wild_Grass_{code}/T_Wild_Grass_{code}_4K'
    elif '/GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A' in mesh:
        # Its exported slot is MI_Tundra_Grass_wk2oaeyqx_4K1. The cooked
        # material uses the highlight-removed albedo and opacity in ART red.
        if material_slots[mesh]!=['MI_Tundra_Grass_wk2oaeyqx_4K1']:
            raise ValueError('Groundcover material slots changed; verify native bindings: '+repr(material_slots[mesh]))
        prefix='/Game/Megascans/3D_Plants/Tundra_Grass_wk2oaeyqx/'
        materials[mesh]={'albedo':texture(prefix+'T_MI_Tundra_Grass_Removed_Highlights_D'),
            'normal_dx':texture(prefix+'T_Tundra_Grass_wk2oaeyqx_4K_N'),
            'normal_xy':True,'alpha':True,
            'opacity_red':texture(prefix+'T_TundraGrass_wk2oaeyqx_4K_ART')}
        continue
    elif any('/'+plant+'/' in mesh for plant in ('Leafy_Dandelions_qmbrl','Clovers_rbdjz','Leafy_Weeds_rbcuh')):
        if material_slots[mesh]!=['lambert1']:
            raise ValueError('Weed material slots changed; verify native bindings: '+repr(material_slots[mesh]))
        plant=next(plant for plant in ('Leafy_Dandelions_qmbrl','Clovers_rbdjz','Leafy_Weeds_rbcuh') if '/'+plant+'/' in mesh)
        prefix=f'/Game/Megascans/3D_Plants/{plant}/T_{plant}'
        materials[mesh]={'albedo':texture(prefix+'_D'),'normal_dx':texture(prefix+'_N'),
            'normal_xy':True,'alpha':True,'opacity_red':texture(prefix+'_ART')}
        continue
    elif 'Uluwatu_' in mesh:
        variant=mesh.split('/Rock_Uluwatu_')[1].split('/')[0]
        prefix=f'/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_{variant}/Materials/T_Rock_Uluwatu_{variant}'
    else:
        raise ValueError('No explicit material binding for '+mesh)
    materials[mesh]={'albedo':texture(prefix+'_D'),'normal_dx':texture(prefix+'_N'),
                     'normal_xy':True,'alpha':grass}
    if grass:
        materials[mesh]['opacity_red']=texture(f'/Game/Megascans/3D_Plants/Wild_Grass_{code}/T_WildGrass_{code}_4K_ART')
doc={'schema_version':1,'foliage':str(a.foliage.resolve()),'models':models,'materials':materials,
     'native_material_slots':material_slots,
     'opacity_binding':'Plant albedo alpha is opaque; native ART red provides cutout opacity, green roughness. Verified on extracted mesh previews.',
     'source':json.loads((a.foliage.parent/'source.json').read_text()),
     'fidelity':'Actual game meshes and textures; runtime scatter algorithm on current Blender BSP with selected rules and neutral unbaked lightmap. Exact records for this preview run, not final-build placement parity. Preview shaders approximate UE materials.'}
path=a.foliage.parent/'pcg-preview.json'; path.write_text(json.dumps(doc,indent=2),encoding='utf-8')
print(path)
