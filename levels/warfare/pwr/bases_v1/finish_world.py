"""Finish court presentation and restore all four authoritative bridge decks."""
from pathlib import Path
import json,sys
import bpy
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'out/pwr/base-integration'
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent));sys.path.insert(0,str(ROOT/'tools/level'))

def court_material():
    name='PWR world | weathered modular court alloy'
    existing=bpy.data.materials.get(name)
    if existing:return existing
    m=bpy.data.materials.new(name);m.use_nodes=True
    n,l=m.node_tree.nodes,m.node_tree.links;b=n.get('Principled BSDF')
    b.inputs['Metallic'].default_value=.28;b.inputs['Roughness'].default_value=.74
    geo=n.new('ShaderNodeNewGeometry')
    scale=n.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs[3].default_value=.125
    l.new(geo.outputs['Position'],scale.inputs[0])
    brick=n.new('ShaderNodeTexBrick');l.new(scale.outputs[0],brick.inputs['Vector'])
    brick.inputs['Scale'].default_value=1
    brick.inputs['Brick Width'].default_value=1;brick.inputs['Row Height'].default_value=.75
    brick.inputs['Mortar Size'].default_value=.003;brick.inputs['Mortar Smooth'].default_value=.002
    brick.inputs['Color1'].default_value=(.17,.19,.20,1);brick.inputs['Color2'].default_value=(.145,.162,.173,1)
    brick.inputs['Mortar'].default_value=(.055,.065,.075,1)
    brick.offset=.5;brick.offset_frequency=2
    fine=n.new('ShaderNodeTexImage');fine.projection='BOX';fine.projection_blend=.3
    path=HERE/'textures/native-fr-diagonal-orhg.png';fine.image=bpy.data.images.load(str(path),check_existing=True)
    fine.image.colorspace_settings.name='Non-Color'
    tile=n.new('ShaderNodeVectorMath');tile.operation='SCALE';tile.inputs[3].default_value=.5
    l.new(geo.outputs['Position'],tile.inputs[0]);l.new(tile.outputs[0],fine.inputs[0])
    sep=n.new('ShaderNodeSeparateColor');l.new(fine.outputs[0],sep.inputs[0])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.68;rough.inputs['To Max'].default_value=.84
    l.new(sep.outputs['Green'],rough.inputs[0]);l.new(rough.outputs[0],b.inputs['Roughness'])
    l.new(brick.outputs['Color'],b.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.invert=True;bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.025
    l.new(brick.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])
    m['surface_scope']='Blender court appearance; native mask roughness and 8x6m modular seam grid'
    return m

def finish_world(scene,sites,plan):
    from integrate_world import array_mesh,collection,material
    from heightfield import load_heightfield
    from world_geometry import bridge_parts
    court=court_material()
    recess=bpy.data.materials.get('PWR world | recessed foundation bed') or material('PWR world | recessed foundation bed',(.095,.11,.12),.18,.8)
    col=next(c for c in scene.collection.children if c.name.startswith('04_WORLD'))
    existing={o.name for o in col.objects};added=[]
    for site in sites:
        for part in site['surfaces']:
            name='World '+site['team']+' '+part['id']
            if name not in existing:
                ob=array_mesh(name,part['vertices_m'],part['triangles'],col,court)
                ob['team']=site['team'];ob['part_role']=part['role'];ob['offline_collision_candidate']=True
                added.append(name)
    for ob in col.objects:
        ob.data.materials.clear();ob.data.materials.append(recess if ob.get('part_role') in ('recessed_foundation_bed','gallery_joint_backing') else court)
    for old in list(scene.objects):
        if old.name.startswith(('Bridge ','World bridge ')):bpy.data.objects.remove(old,do_unlink=True)
    bridgecol=bpy.data.collections.get('05_WORLD | authoritative bridges') or collection('05_WORLD | authoritative bridges')
    field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    geometry=json.loads((field.path.parent/field.metadata['geometry']).read_text())
    bridges=[]
    for p in bridge_parts(geometry,field):
        triangles=[]
        for f in p['faces']:
            for j in range(1,len(f)-1):triangles.append((f[0],f[j],f[j+1]))
        ob=array_mesh('World bridge '+p['name'],p['vertices_m'],triangles,bridgecol,court)
        ob['authoritative_geometry']=True;bridges.append({'id':p['name'],'triangles':len(triangles)})
    if len(bridges)!=4:raise RuntimeError('Expected three bridges and the braid culvert')
    return {'courts_material':court.name,'added_foundation_objects':added,'bridges':bridges,
            'source_road_and_terrain_modified':False}

def main():
    import importlib,world_dressing,integrate_world
    importlib.reload(world_dressing);importlib.reload(integrate_world)
    plan=json.loads((OUT/'placement-plan.json').read_text())
    sites=[dict(b,team=b['id'],center_world_m=b['terrace_center_m'],base_translation_world_m=b['normalize_then_translate_m'],
                surfaces=[p for p in plan['surfaces'] if p['id'] in b['surface_ids']]) for b in plan['bases']]
    scene=bpy.context.scene
    from heightfield import load_heightfield,sha256
    field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    terrain=integrate_world.build_exact_terrain(scene,field,sites)
    finishing=finish_world(scene,sites,plan)
    receipt=json.loads((OUT/'assembly-receipt.json').read_text())
    roots=world_dressing.repair_existing_sapling_roots(scene,receipt['dressing'])
    receipt['terrain']=terrain;receipt['finishing']=finishing;receipt['sapling_roots']=roots
    receipt['placement_plan_sha256']=sha256(OUT/'placement-plan.json')
    receipt['courts']=[{'name':o.name,'triangles':len(o.data.polygons)} for o in scene.objects if o.get('offline_collision_candidate')]
    for site in sites:
        cam=bpy.data.objects[receipt['cameras'][site['team']+'-integrated']]
        p=Vector(site['base_translation_world_m'])
        cam.location=p+Vector((-220 if site['team']=='blue' else 220,-310,170))
        cam.rotation_euler=(p+Vector((0,-5,6))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=45
    (OUT/'assembly-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    bpy.context.view_layer.update();bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'pwr-world-bases-v1.blend'))
    print(json.dumps({'finishing':finishing,'sapling_roots':roots}))

if __name__=='__main__':main()
