"""Assemble the reviewed bases into the real PWR terrain, entirely offline.

Run through the existing Blender MCP connection after inspect_world.py. This
creates a separate world file. It never cooks, installs, or launches a game.
"""
from pathlib import Path
import hashlib, json, math, sys, time
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'out/pwr/base-integration'
SOURCE = ROOT / 'out/pwr/visual-v8/foothills/preview-clustered/foothills-v8.blend'
ART = HERE / 'forerunner_bases.blend'
TARGET = OUT / 'pwr-world-bases-v1.blend'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'tools/level'))
from heightfield import load_heightfield, sha256

def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c

def array_mesh(name, vertices, triangles, col, material=None):
    v=np.asarray(vertices, dtype=np.float32); t=np.asarray(triangles, dtype=np.int32)
    me=bpy.data.meshes.new(name)
    me.vertices.add(len(v)); me.vertices.foreach_set('co',v.ravel())
    me.loops.add(t.size); me.loops.foreach_set('vertex_index',t.ravel())
    me.polygons.add(len(t)); me.polygons.foreach_set('loop_start',np.arange(len(t),dtype=np.int32)*3)
    me.polygons.foreach_set('loop_total',np.full(len(t),3,dtype=np.int32))
    # Blender 5.3 defaults added faces to smooth. Flat structural slabs must
    # not average their top normals with the vertical perimeter faces.
    me.polygons.foreach_set('use_smooth',np.zeros(len(t),dtype=bool));me.update(calc_edges=True)
    ob=bpy.data.objects.new(name,me);col.objects.link(ob)
    if material:me.materials.append(material)
    return ob

def material(name, color, metal=0, rough=.85):
    m=bpy.data.materials.new(name);m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value=(*color,1)
    b.inputs['Metallic'].default_value=metal;b.inputs['Roughness'].default_value=rough
    return m

def terrain_material():
    m=material('PWR world | measured ecology and native ground detail',(.2,.25,.1))
    n,l=m.node_tree.nodes,m.node_tree.links;b=n.get('Principled BSDF')
    attr=n.new('ShaderNodeVertexColor');attr.layer_name='PWR_SurfaceColor'
    geo=n.new('ShaderNodeNewGeometry')
    scale=n.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs[3].default_value=.32
    l.new(geo.outputs['Position'],scale.inputs[0])
    tex=n.new('ShaderNodeTexImage')
    path=Path('C:/haloce/ce_conversions/release11/DCN/staging/textures/levels_a30_bitmaps_detail_ground.png')
    if not path.exists():raise FileNotFoundError(path)
    tex.image=bpy.data.images.load(str(path),check_existing=True);tex.projection='BOX';tex.projection_blend=.25
    l.new(scale.outputs[0],tex.inputs[0])
    gray=n.new('ShaderNodeRGBToBW');l.new(tex.outputs['Color'],gray.inputs[0])
    remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=.68;remap.inputs['To Max'].default_value=1.3
    l.new(gray.outputs[0],remap.inputs[0])
    mul=n.new('ShaderNodeMixRGB');mul.blend_type='MULTIPLY';mul.inputs[0].default_value=1
    l.new(attr.outputs['Color'],mul.inputs[1]);l.new(remap.outputs[0],mul.inputs[2]);l.new(mul.outputs[0],b.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.25;bump.inputs['Distance'].default_value=.055
    l.new(gray.outputs[0],bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal'])
    m['shader_scope']='Blender approximation; native Unreal terrain/Flux materials are not evaluated here'
    return m

def build_exact_terrain(scene,field,plans):
    old=next(o for o in scene.objects if o.name.startswith(('Actual master heightfield','PWR exact runtime-v5 terrain')))
    col=old.users_collection[0]
    w,h=field.dimensions; ox,oy=field.origin_m;dx,dy=field.spacing_m
    xx,yy=np.meshgrid(ox+np.arange(w)*dx,oy+np.arange(h)*dy)
    v=np.column_stack((xx.ravel(),yy.ravel(),field.heights_m.ravel()))
    j,i=np.mgrid[:h-1,:w-1];a=(j*w+i).ravel()
    tris=np.concatenate((np.c_[a,a+1,a+w],np.c_[a+w+1,a+w,a+1]))
    ob=array_mesh('PWR exact runtime-v5 terrain | 1009 square',v,tris,col,terrain_material())
    ob['heightfield_sha256']=field.manifest_sha256
    ob['triangle_diagonal']='triangle_nw_se; identical authoritative interpolation'
    ob.data.polygons.foreach_set('use_smooth',np.ones(len(tris),dtype=bool))
    gy,gx=np.gradient(field.heights_m,dy,dx)
    rock=np.clip((np.hypot(gx,gy)-.32)/.65,0,1)
    ecology=ROOT/'out/pwr/visual-v6/surface/ecology/ecology.rgba.npy'
    eco=np.load(ecology)
    if eco.shape[:2] != (h,w): raise ValueError('Ecology dimensions no longer match')
    soil=np.clip((eco[...,2]-.13)/.30,0,1)*.65
    rgb=np.ones((h,w,3))*[.145,.205,.073]
    rgb*=1-eco[...,:1]*.22
    rgb=rgb*(1-soil[...,None])+np.array([.22,.18,.12])*soil[...,None]
    rgb=rgb*(1-rock[...,None])+np.array([.26,.285,.285])*rock[...,None]
    road=field.masks['road'].copy()
    for site in plans:
        # Visual-only road mask trimming under a replacement court. Exact
        # terrain samples, waterbed and authoritative road data stay immutable.
        poly=site['court_outer_polygon_m'];inside=np.zeros(xx.shape,dtype=bool)
        for k, (ax,ay) in enumerate(poly):
            bx,by=poly[(k+1)%len(poly)]
            if abs(by-ay)>1e-12:
                inside ^= ((ay>yy)!=(by>yy)) & (xx < (bx-ax)*(yy-ay)/(by-ay)+ax)
        road[inside]=0
    rgb=rgb*(1-road[...,None])+np.array([.245,.20,.139])*road[...,None]
    c=ob.data.color_attributes.new(name='PWR_SurfaceColor',type='FLOAT_COLOR',domain='POINT')
    c.data.foreach_set('color',np.c_[rgb.reshape(-1,3),np.ones(w*h)].astype(np.float32).ravel())
    delta=np.max(np.abs(v.astype(np.float32).astype(float)-v),axis=0)
    bpy.data.objects.remove(old,do_unlink=True)
    return {'vertices':len(v),'triangles':len(tris),'maximum_float_storage_error_xyz_m':delta.tolist(),
            'runtime_master_sha256':field.manifest_sha256,'original_heightfield_file_changed':False,
            'road_mask_trim':'Only shader color beneath the replacement court; original road geometry unchanged'}

def lighting(scene):
    for o in list(scene.objects):
        if o.type=='LIGHT':bpy.data.objects.remove(o,do_unlink=True)
    world=bpy.data.worlds.new('PWR integrated world daylight');world.use_nodes=True
    n,l=world.node_tree.nodes,world.node_tree.links
    env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(HERE/'textures/daylight-presentation.exr'),check_existing=True)
    l.new(env.outputs['Color'],n['Background'].inputs['Color']);n['Background'].inputs['Strength'].default_value=.5
    scene.world=world
    data=bpy.data.lights.new('PWR world afternoon sun','SUN');data.energy=2.7;data.angle=math.radians(1.3);data.color=(1,.94,.84)
    sun=bpy.data.objects.new(data.name,data);scene.collection.objects.link(sun)
    sun.rotation_euler=Vector((.45,.65,-1)).to_track_quat('-Z','Y').to_euler()
    scene.render.engine='CYCLES';scene.cycles.device='GPU';scene.cycles.samples=48;scene.cycles.use_denoising=True
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for device in prefs.devices:device.use=device.type=='OPTIX'
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0
    scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'

def camera(scene,name,position,target,lens=40,ortho=None):
    data=bpy.data.cameras.new(name);ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob)
    ob.location=position;ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
    data.lens=lens;data.clip_start=.15;data.clip_end=25000
    if ortho:data.type='ORTHO';data.ortho_scale=ortho
    return ob

def main():
    started=time.time();OUT.mkdir(parents=True,exist_ok=True)
    if Path(bpy.data.filepath).resolve()!=SOURCE.resolve():raise RuntimeError('Start from the inspected V8 world source')
    if bpy.data.is_dirty:raise RuntimeError('World source was edited after inspection; save separately before rebuilding')
    plan=json.loads((OUT/'placement-plan.json').read_text())
    # Accept the explicit placement schema through a small normalized adapter.
    sites=[dict(b,team=b['id'],center_world_m=b['terrace_center_m'],
                base_translation_world_m=[b['terrace_center_m'][0],b['terrace_center_m'][1],b['floor_world_z_m']-.2],
                surfaces=[p for p in plan['surfaces'] if p['id'] in b['surface_ids']]) for b in plan['bases']]
    scene=bpy.context.scene;scene.name='PWR | full world and reviewed Forerunner bases'
    retained=set(scene.objects)
    for other in list(bpy.data.scenes):
        if other!=scene:bpy.data.scenes.remove(other)
    for o in list(bpy.data.objects):
        if o not in retained:bpy.data.objects.remove(o,do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
    old_names=[]
    for o in list(scene.objects):
        if o.name.startswith(('red_home_','blue_home_','citadel_plateau_')):
            old_names.append(o.name);bpy.data.objects.remove(o,do_unlink=True)
    if len(old_names)!=96:raise RuntimeError(f'Unexpected old structure count {len(old_names)}')
    prefixes=('01_RED','02_BLUE','03_GREEN')
    with bpy.data.libraries.load(str(ART),link=False) as (available,loaded):
        loaded.collections=[next(n for n in available.collections if n.startswith(p)) for p in prefixes]
    cols=loaded.collections
    # Appended objects need an evaluated dependency graph before matrix_world
    # is read. Otherwise Blender reports stale identity matrices and loses the
    # reviewed 0.65 architecture scale / native module poses on translation.
    for c in cols:
        scene.collection.children.link(c);c.hide_render=False;c.hide_viewport=False
    bpy.context.view_layer.update()
    placement_records=[]
    for site,c,origin in zip(sites,cols,((0,0,0),(135,0,0),(0,150,0))):
        offset=Vector(site['base_translation_world_m'])-Vector(origin)
        T=Matrix.Translation(offset)
        before={o:o.matrix_world.copy() for o in c.all_objects}
        # Apply a common world translation once; current sources have no
        # hierarchy, and future parented sources must not receive it twice.
        for o in before:
            if o.parent is None or o.parent not in before:o.matrix_world=T@before[o]
            o.hide_render=False;o.hide_set(False);o['world_base_team']=site['team']
        c['placement_world_m']=site['base_translation_world_m'];c['authoring_only']=False
        c['integration_scope']='offline world assembly; native collision not rebuilt'
        bpy.context.view_layer.update()
        error=max(max(abs(v) for row in (o.matrix_world-T@old) for v in row) for o,old in before.items())
        if error>1e-4:raise RuntimeError('Non-rigid base placement')
        placement_records.append({'team':site['team'],'objects':len(before),'matrix_error':error,'translation':site['base_translation_world_m']})
    field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    terrain=build_exact_terrain(scene,field,sites)
    # Courts and access thresholds are explicit triangulated surfaces from
    # world_placement.py, with a real hole around each reviewed base.
    courts=collection('04_WORLD | connected courts and approach thresholds')
    courtmat=next(m for m in bpy.data.materials if m.name.startswith('FR • finish exterior apron'))
    accessmat=material('PWR road access | compacted pale earth',(.245,.20,.139),0,.93)
    court_records=[]
    for site in sites:
        for part in site['surfaces']:
            ob=array_mesh('World '+site['team']+' '+part['id'],part['vertices_m'],part['triangles'],courts,
                          accessmat if part.get('material_role')=='road' else courtmat)
            ob['team']=site['team'];ob['part_role']=part.get('role','court');ob['offline_collision_candidate']=True
            uv=ob.data.uv_layers.new(name='FinishUV')
            for poly in ob.data.polygons:
                for li in poly.loop_indices:
                    v=ob.data.vertices[ob.data.loops[li].vertex_index].co
                    uv.data[li].uv=((v.x-site['center_world_m'][0])/4,(v.y-site['center_world_m'][1])/4)
            court_records.append({'name':ob.name,'triangles':len(part['triangles'])})
    import importlib, world_dressing
    importlib.reload(world_dressing)
    dressing=world_dressing.add_world_dressing(scene,sites)
    import finish_world
    importlib.reload(finish_world)
    finishing=finish_world.finish_world(scene,sites,plan)
    for ob in scene.objects:
        if ob.name.startswith(('River ','Water ')):
            ob['water_scope']='Blender water proxy. Existing Fluid Flux state and runtime package unchanged.'
            for m in ob.data.materials:
                m.use_nodes=True;b=m.node_tree.nodes.get('Principled BSDF')
                if b:
                    b.inputs['Base Color'].default_value=(.025,.105,.105,1)
                    b.inputs['Roughness'].default_value=.16;b.inputs['Metallic'].default_value=.25
    lighting(scene)
    for o in list(scene.objects):
        if o.type=='CAMERA':bpy.data.objects.remove(o,do_unlink=True)
    cameras={}
    cameras['world-overview']=camera(scene,'Review | world overview',(0,-2440,2400),(0,80,140),40)
    cameras['world-topdown']=camera(scene,'Review | tactical topdown',(0,0,3000),(0,0,0),40,2450)
    for site in sites:
        p=Vector(site['base_translation_world_m']);team=site['team']
        cameras[team+'-integrated']=camera(scene,'Review | '+team+' integrated',p+Vector((-220 if team=='blue' else 220,-310,170)),p+Vector((0,-5,6)),45)
        cameras[team+'-connections']=camera(scene,'Review | '+team+' site connections',p+Vector((0,-.001,320)),p,40,205)
    scene.camera=cameras['red-integrated']
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    scene['runtime_installed']=False;scene['game_launched']=False;scene['base_authoring_scale']=.65
    scene['design_stage']='Reviewed bases integrated with full world offline; replacement native collision still required'
    scene['roof_deck_z_m']=10.5675
    bpy.context.view_layer.update()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(TARGET))
    receipt={'schema':'pwr-offline-world-bases-v1','blend':str(TARGET),'source_world':str(SOURCE),
        'source_world_sha256':sha256(SOURCE),'source_art_sha256':sha256(ART),
        'terrain':terrain,'placement_plan_sha256':sha256(OUT/'placement-plan.json'),
        'placements':placement_records,'removed_obsolete_objects':old_names,
        'courts':court_records,'dressing':dressing,'finishing':finishing,'cameras':{k:v.name for k,v in cameras.items()},
        'runtime_installed':False,'game_launched':False,'native_collision_rebuilt':False,
        'duration_seconds':time.time()-started}
    (OUT/'assembly-receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n')
    print(json.dumps({'blend':str(TARGET),'objects':len(scene.objects),'receipt':str(OUT/'assembly-receipt.json')}))

if __name__=='__main__':main()
