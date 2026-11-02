"""Export original Roadworks models with Blender, then render a contact sheet.

blender --background --factory-startup --python build_blender.py -- --render
Exports are full-size metre glTF (Y-up), while collision JSON/OBJ stays Z-up.
Presentation placement/scaling occurs only AFTER export and is not gameplay.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from generate import write_sources, box
from validate import main as validate_sources


def material(name, spec):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = spec['base_color']
    shader.inputs['Metallic'].default_value = spec['metallic']
    shader.inputs['Roughness'].default_value = spec['roughness']
    mat.diffuse_color = spec['base_color']
    return mat


def mesh_object(name, geometry, collection):
    data = bpy.data.meshes.new(name)
    data.from_pydata(geometry['vertices'],[],geometry['triangles'])
    data.update()
    obj = bpy.data.objects.new(name,data)
    collection.objects.link(obj)
    return obj


def select_only(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def label(text,x,y,size,mat,collection):
    curve = bpy.data.curves.new(text,'FONT')
    curve.body,curve.size = text,size
    curve.materials.append(mat)
    obj = bpy.data.objects.new(text,curve)
    collection.objects.link(obj)
    obj.location = (x,y,.02)
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'build')
    options = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    output = options.output.resolve()
    for path in (output,output/'models',output/'collision'):
        path.mkdir(parents=True,exist_ok=True)
    source = write_sources()
    validate_sources()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    mats = {name:material('Roadworks / '+name,spec) for name,spec in source['materials'].items()}
    assets = bpy.data.collections.new('Roadworks / Assets')
    collision_collection = bpy.data.collections.new('Roadworks / Collision')
    studio = bpy.data.collections.new('Roadworks / Presentation')
    for collection in (assets,collision_collection,studio):
        scene.collection.children.link(collection)
    collision_collection.hide_render = True
    models,report = [],[]
    for piece in source['pieces']:
        parts = []
        for index,component in enumerate(piece['visual']):
            obj = mesh_object(f"{piece['id']}_{index:03}",component,assets)
            obj.data.materials.append(mats[component['material']])
            parts.append(obj)
        select_only(parts)
        bpy.ops.object.join()
        model = bpy.context.view_layer.objects.active
        model.name = 'roadworks_'+piece['id']
        model['forge_pack'],model['forge_id'] = 'roadworks',piece['id']
        model['origin_convention'] = 'entry_floor'
        model['dimensions_m'],model['snap_m'] = piece['dimensions_m'],.5
        model['road_connectors_json'] = json.dumps(piece['road']['connectors'])
        model.asset_mark()
        model.asset_data.author = 'MJOLNIR Core contributors'
        model.asset_data.description = piece['name']+'. '+piece['notes']
        model.asset_data.tags.new('Roadworks')
        model.asset_data.tags.new(piece['category'])
        select_only([model])
        for extension,format_name in (('gltf','GLTF_SEPARATE'),('glb','GLB')):
            bpy.ops.export_scene.gltf(filepath=str(output/'models'/f"{piece['id']}.{extension}"),
                                     export_format=format_name,use_selection=True,export_yup=True,
                                     export_apply=True,export_extras=True,export_cameras=False,export_lights=False)
        collider = {'id':piece['id'],'units':'meters','axes':'right_handed_z_up',
                    'dimensions_m':piece['dimensions_m'],**piece['collision']}
        (output/'collision'/f"{piece['id']}.json").write_text(json.dumps(collider,indent=2)+'\n')
        with (output/'collision'/f"{piece['id']}.obj").open('w') as stream:
            stream.write('# Original Roadworks convex hulls; metres; right-handed Z-up\n')
            for v in collider['vertices']:
                stream.write('v '+' '.join(f'{x:.9f}' for x in v)+'\n')
            offset = 0
            for index,hull in enumerate(collider['hulls']):
                stream.write(f'g hull_{index:03}\n')
                for tri in hull['triangles']:
                    stream.write('f '+' '.join(str(x+offset+1) for x in tri)+'\n')
                offset += len(hull['vertices'])
        collision_obj = mesh_object('COL_'+piece['id'],piece['collision'],collision_collection)
        collision_obj.display_type = 'WIRE'
        collision_obj.hide_set(True)
        model.data.calc_loop_triangles()
        models.append((model,piece))
        report.append({'id':piece['id'],'visual_triangles':len(model.data.loop_triangles),
                       'collision_hulls':len(collider['hulls']),'collision_triangles':len(collider['triangles']),
                       'origin':'entry_floor','gltf_bytes':(output/'models'/f"{piece['id']}.gltf").stat().st_size})
    (output/'export-report.json').write_text(json.dumps({'blender':bpy.app.version_string,'pieces':report},indent=2)+'\n')
    print('ROADWORKS_EXPORTS_READY: 10 separate glTF+bin, GLB, collision JSON/OBJ files',flush=True)

    backdrop = material('Studio / background',{'base_color':[.017,.025,.032,1],'metallic':0,'roughness':.9})
    cards = material('Studio / cards',{'base_color':[.045,.063,.072,1],'metallic':0,'roughness':.85})
    white = material('Studio / type',{'base_color':[.85,.9,.88,1],'metallic':0,'roughness':.7})
    gray = material('Studio / secondary',{'base_color':[.42,.53,.57,1],'metallic':0,'roughness':.8})
    ground = mesh_object('Ground',box(65,42,.1,z=-.25),studio)
    ground.data.materials.append(backdrop)
    scale = .17
    for index,(model,piece) in enumerate(models):
        x,y = (index%5-2)*11,(.5-index//5)*14
        vertices = piece['collision']['vertices']
        center = [(min(v[i] for v in vertices)+max(v[i] for v in vertices))/2 for i in (0,1)]
        model.scale = (scale,scale,scale)
        model.location = (x-center[0]*scale,y+1-center[1]*scale,0)
        card = mesh_object('Tile '+piece['id'],box(10.6,13.6,.06,x,y,-.1),studio)
        card.data.materials.append(cards)
        name = piece['name'].replace(' + Rails','')
        label(name.upper(),x-4.8,y-5,.4,white,studio)
        subtitle = 'GUARDED / 1.5 m RAIL' if piece['road']['guardrail_height_m'] else 'OPEN / 16 m CLEAR'
        label(subtitle,x-4.8,y-5.75,.3,mats['amber'],studio)
    label('ROADWORKS',-26.8,17.2,1.8,white,studio)
    label('10 ORIGINAL ROAD PIECES  /  ALL SHOWN AT THE SAME SCALE',-26.6,15.8,.44,mats['amber'],studio)
    label('16 m CLEAR ROAD  /  24 + 48 m STRAIGHTS  /  R40 CURVES  /  48 m EASED RAMP',-26.6,-16.2,.42,white,studio)
    label('Actual Blender meshes. Entry-anchored origins; flush deck edges; separate convex curve slices.',-26.6,-17.15,.34,gray,studio)
    camera_data = bpy.data.cameras.new('Contact sheet camera')
    camera = bpy.data.objects.new('Contact sheet camera',camera_data)
    studio.objects.link(camera)
    camera.location = (0,-24,76)
    camera.rotation_euler = (Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.type,camera_data.ortho_scale = 'ORTHO',59
    scene.camera = camera
    for name,position,energy,size in [('Key',(-18,-12,35),17000,25),('Fill',(18,5,25),13000,20),('Rim',(0,20,18),9000,15)]:
        data = bpy.data.lights.new(name,'AREA')
        data.energy,data.shape,data.size = energy,'DISK',size
        light = bpy.data.objects.new(name,data)
        studio.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector((0,0,0))-light.location).to_track_quat('-Z','Y').to_euler()
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.23,.27,.3,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .35
    scene.render.engine = 'CYCLES'
    scene.cycles.samples,scene.cycles.use_denoising = 32,True
    scene.render.resolution_x,scene.render.resolution_y = 2400,1600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(output/'roadworks-contact-sheet.png')
    scene.view_settings.view_transform = 'AgX'
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'roadworks.blend'))
    if options.render:
        bpy.ops.render.render(write_still=True)
    print('ROADWORKS_BUILD_OK',flush=True)


if __name__ == '__main__':
    main()
