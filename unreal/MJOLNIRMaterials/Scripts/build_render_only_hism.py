"""Apply and verify the optional exterior cliff bake; no runtime scripting."""
from pathlib import Path
import json
import struct
import sys


def apply_cliffs(spec, output_folder):
    import unreal
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools/level'))
    from render_only_hism import load, digest, PARENT, TEXTURES
    declared=spec.get('render_only_hism')
    if not declared:return None
    source, checked=load(declared['path'])
    if checked['sha256']!=declared['sha256'] or checked['instances']!=declared['instances']:
        raise RuntimeError('Exterior source changed after foliage bake')
    eal=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
    tools=unreal.AssetToolsHelpers.get_asset_tools()
    parent=unreal.load_asset(PARENT)
    if not parent or not parent.get_editor_property('used_with_instanced_static_meshes'):
        raise RuntimeError('PWR rock master must be compiled for instanced static meshes')
    # Native texture references resolve to shipped assets in game. These exact
    # proxy paths are never cooked, as with the native mesh stand-ins.
    textures={}
    for key,path in TEXTURES.items():
        package=path.split('.')[0];texture=unreal.load_asset(package)
        if not texture:
            donor='/Engine/EngineMaterials/DefaultNormal' if key=='RockN' else '/Engine/EngineResources/DefaultTexture'
            texture=eal.duplicate_asset(donor,package)
            if not texture or not eal.save_loaded_asset(texture):raise RuntimeError('Native cliff texture proxy failed')
        if not isinstance(texture,unreal.Texture2D):raise RuntimeError('Native cliff texture proxy has wrong class')
        textures[key]=texture
    name='MI_PWR_ExteriorCliffs_'+declared['sha256'][:12]
    mi=tools.create_asset(name,output_folder,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    if not mi:raise RuntimeError('Exterior cliff material creation failed')
    mel.set_material_instance_parent(mi,parent)
    for key,texture in textures.items():mel.set_material_instance_texture_parameter_value(mi,key,texture)
    for key,value in source['material']['vectors'].items():mel.set_material_instance_vector_parameter_value(mi,key,unreal.LinearColor(*value))
    if not eal.save_loaded_asset(mi):raise RuntimeError('Exterior cliff material save failed')
    for key,path in TEXTURES.items():
        texture=mel.get_material_instance_texture_parameter_value(mi,key)
        if not texture or texture.get_path_name()!=path:raise RuntimeError('Exterior material texture reference changed')
    wanted={f"MJFol_{r['group']}_1_0":r for r in declared['groups']}
    if len(wanted)!=declared['components']:raise RuntimeError('Exterior group inventory mismatch')
    report=[];worst_position=worst_rotation=worst_scale=0.
    for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            row=wanted.pop(component.get_name(),None)
            if row is None:continue
            group=spec['groups'][row['group']-1]
            if group['flags']!=35:raise RuntimeError('Exterior group must be rigid, shadowed, exact and never grass/cladding')
            if component.get_editor_property('static_mesh').get_path_name()!=group['mesh']:raise RuntimeError('Exterior mesh binding changed')
            if component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION:raise RuntimeError('Exterior collision unexpectedly enabled')
            if component.get_editor_property('evaluate_world_position_offset'):raise RuntimeError('Exterior WPO unexpectedly enabled')
            component.set_editor_property('can_ever_affect_navigation',False)
            if component.get_editor_property('can_ever_affect_navigation'):raise RuntimeError('Exterior navigation remained enabled')
            component.set_material(0,mi)
            if component.get_material(0)!=mi:raise RuntimeError('Exterior material override did not persist')
            expected=list(struct.iter_unpack('<10f',Path(f"{spec['bin']}.xf{row['group']}").read_bytes()))
            count=component.get_instance_count()
            if count!=len(expected) or count!=row['count']:raise RuntimeError('Exterior instance count changed')
            for index,target in enumerate(expected):
                t=component.get_instance_transform(index,world_space=True)
                worst_position=max(worst_position,*(abs(a-b) for a,b in zip([t.translation.x,t.translation.y,t.translation.z],target[:3])))
                worst_rotation=max(worst_rotation,abs(1-abs(sum(a*b for a,b in zip([t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],target[3:7])))))
                worst_scale=max(worst_scale,*(abs(a-b) for a,b in zip([t.scale3d.x,t.scale3d.y,t.scale3d.z],target[7:10])))
            actual_cull=[component.get_editor_property('instance_start_cull_distance'),component.get_editor_property('instance_end_cull_distance')]
            if actual_cull!=source['cull_cm']:raise RuntimeError('Exterior cull distances changed')
            report.append({'component':component.get_name(),'mesh':group['mesh'],'instances':count,'material':mi.get_path_name(),
                'collision':'NoCollision','navigation':False,'wpo':False,'cull_cm':actual_cull})
    if wanted or sum(r['instances'] for r in report)!=declared['instances'] or worst_position>.01 or worst_rotation>1e-5 or worst_scale>1e-5:
        raise RuntimeError('Exterior instance inventory/transform verification failed')
    receipt={'schema':'pwr-render-only-hism-editor-v1','source_sha256':declared['sha256'],'groups':report,
        'maximum_position_error_cm':worst_position,'maximum_quaternion_dot_error':worst_rotation,
        'maximum_scale_error':worst_scale,'no_native_collision_input':True,
        'status':'Editor source proof; final cooked component/material readback and live FPS still required'}
    target=Path(spec['bin']).parent/'render-only-hism.verification.json'
    target.write_text(json.dumps(receipt,indent=2)+'\n')
    unreal.log('MJOLNIR exterior cliff HISM verified: '+json.dumps(receipt))
    return receipt


def apply_pines(spec):
    import unreal
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools/level'))
    from render_only_pines import load, ASSETS
    declared=spec.get('render_only_pines')
    if not declared:return None
    source,checked=load(declared['path'])
    if checked['sha256']!=declared['sha256'] or checked['instances']!=declared['instances']:raise RuntimeError('Exterior pine source changed')
    wanted={f"MJFol_{r['group']}_1_0":r for r in declared['groups']}
    if len(wanted)!=declared['components']:raise RuntimeError('Exterior pine group inventory mismatch')
    report=[];position=rotation=scale=0.
    for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            row=wanted.pop(component.get_name(),None)
            if row is None:continue
            group=spec['groups'][row['group']-1];mesh=component.get_editor_property('static_mesh')
            if group['flags']!=35 or mesh.get_path_name()!=group['mesh']:raise RuntimeError('Exterior pine group flags/mesh changed')
            slots=[str(slot.material_slot_name) for slot in mesh.get_editor_property('static_materials')]
            if slots!=ASSETS[group['mesh']]['slot_names']:raise RuntimeError('Exterior pine native slot inventory changed')
            if len(component.get_editor_property('override_materials')):raise RuntimeError('Exterior pine material overrides forbidden')
            if component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION:raise RuntimeError('Exterior pine collision enabled')
            if component.get_editor_property('evaluate_world_position_offset'):raise RuntimeError('Exterior pine WPO enabled')
            component.set_editor_property('can_ever_affect_navigation',False)
            if component.get_editor_property('can_ever_affect_navigation'):raise RuntimeError('Exterior pine navigation enabled')
            if not component.get_editor_property('cast_shadow'):raise RuntimeError('Exterior pine shadow policy changed')
            expected=list(struct.iter_unpack('<10f',Path(f"{spec['bin']}.xf{row['group']}").read_bytes()))
            count=component.get_instance_count()
            if count!=len(expected) or count!=row['count']:raise RuntimeError('Exterior pine instance count changed')
            for i,target in enumerate(expected):
                t=component.get_instance_transform(i,world_space=True)
                position=max(position,*(abs(a-b) for a,b in zip([t.translation.x,t.translation.y,t.translation.z],target[:3])))
                rotation=max(rotation,abs(1-abs(sum(a*b for a,b in zip([t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],target[3:7])))))
                scale=max(scale,*(abs(a-b) for a,b in zip([t.scale3d.x,t.scale3d.y,t.scale3d.z],target[7:10])))
            cull=[component.get_editor_property('instance_start_cull_distance'),component.get_editor_property('instance_end_cull_distance')]
            if cull!=source['cull_cm']:raise RuntimeError('Exterior pine cull changed')
            report.append({'component':component.get_name(),'mesh':group['mesh'],'instances':count,'native_slot_names':slots,
                'material_overrides':0,'collision':'NoCollision','navigation':False,'wpo':False,'cast_shadow':True,'cull_cm':cull})
    if wanted or sum(r['instances'] for r in report)!=declared['instances'] or position>.01 or rotation>1e-5 or scale>1e-5:raise RuntimeError('Exterior pine transform/inventory readback failed')
    receipt={'schema':'pwr-render-only-pines-editor-v1','source_sha256':declared['sha256'],'groups':report,
        'maximum_position_error_cm':position,'maximum_quaternion_dot_error':rotation,'maximum_scale_error':scale,'no_native_collision_input':True}
    (Path(spec['bin']).parent/'render-only-pines.verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    unreal.log('MJOLNIR exterior pine HISM verified: '+json.dumps(receipt));return receipt


def apply(spec, output_folder):
    cliffs=apply_cliffs(spec,output_folder)
    apply_pines(spec)
    return cliffs
