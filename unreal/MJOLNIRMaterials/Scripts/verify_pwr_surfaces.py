"""Read back PWR editor texture settings and material statistics, no mutations."""
import json
import os
import unreal

root='/Game/MJOLNIR/CETrial'
report={'textures':{},'materials':{}}
for name,normal in [('T_PWR_PavingNormal',True),('T_PWR_PavingData',False)]:
    texture=unreal.load_asset(root+'/'+name)
    if not texture:raise RuntimeError('Missing '+name)
    values={key:texture.get_editor_property(key) for key in ('srgb','virtual_texture_streaming','flip_green_channel')}
    if any(values.values()):raise RuntimeError('PWR linear texture settings changed: '+name)
    compression=texture.get_editor_property('compression_settings')
    expected=unreal.TextureCompressionSettings.TC_NORMALMAP if normal else unreal.TextureCompressionSettings.TC_MASKS
    if compression!=expected:raise RuntimeError('Wrong compression: '+name)
    values['compression']=str(compression);report['textures'][name]=values
for name in ['M_CE_PWRPaving','M_CE_LandscapePBR','M_CE_GroundPBR']:
    material=unreal.load_asset(root+'/'+name)
    if not material:raise RuntimeError('Missing '+name)
    stats=unreal.MaterialEditingLibrary.get_statistics(material)
    report['materials'][name]={key:stats.get_editor_property(key) for key in (
        'num_pixel_shader_instructions','num_samplers','num_pixel_texture_samples','num_virtual_texture_samples')}
    if name=='M_CE_PWRPaving':
        if material.get_editor_property('tangent_space_normal'):raise RuntimeError('Paving requires world-space normals')
report['scope']='Editor import readback; cooked game layout and live performance are separate acceptance gates.'
out=os.environ.get('MJ_PWR_SURFACE_RECEIPT',os.path.abspath(os.path.join(os.path.dirname(__file__),
    '../../../out/pwr/visual-v5/surface-v4/editor-readback.json')))
os.makedirs(os.path.dirname(out),exist_ok=True)
with open(out,'w') as stream:json.dump(report,stream,indent=2)
unreal.log('PWR surface readback: '+json.dumps(report))
