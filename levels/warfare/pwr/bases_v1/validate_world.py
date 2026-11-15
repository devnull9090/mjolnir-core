"""Measure the placed bases and external approaches in the assembled Blender file."""
from pathlib import Path
import hashlib, json, sys, time, gc
import bpy
from mathutils import Matrix, Vector

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'out/pwr/base-integration'
sys.path.insert(0,str(HERE))
from validate_bases import EvaluatedScene, volume_audit, floor_and_cover

def base_shape_audit(records, expected, team, tolerance_m=1e-4):
    """Compare only base meshes against the reviewed art's canonical frame.

    EvaluatedScene already removes the map translation. The original blue
    report additionally reflects X to compare with its red master; reflect its
    bounds here too. Courts never contribute to counts or extrema. Tolerance
    permits float32 matrix cancellation at kilometre-scale world coordinates,
    not a changed authoring scale or presentation translation.
    """
    actual = {'mesh_objects': len(records),
              'evaluated_vertices': sum(len(r['vertices']) for r in records),
              'evaluated_triangles': sum(len(r['triangles']) for r in records)}
    if records:
        bounds = {'min': [min(r['bounds']['min'][k] for r in records) for k in range(3)],
                  'max': [max(r['bounds']['max'][k] for r in records) for k in range(3)]}
        if team == 'blue':
            bounds['min'][0], bounds['max'][0] = -bounds['max'][0], -bounds['min'][0]
        actual['bounds_m'] = bounds
        errors = {side: [abs(bounds[side][k] - expected['bounds_m'][side][k]) for k in range(3)]
                  for side in ('min', 'max')}
        maximum = max(v for values in errors.values() for v in values)
    else:
        actual['bounds_m'] = None; errors = None; maximum = None
    counts_equal = all(actual[key] == expected[key] for key in
                       ('mesh_objects', 'evaluated_vertices', 'evaluated_triangles'))
    return {'passed': counts_equal and maximum is not None and maximum <= tolerance_m,
            'counts_equal': counts_equal, 'expected': {key: expected[key] for key in
                ('mesh_objects', 'evaluated_vertices', 'evaluated_triangles', 'bounds_m')},
            'actual': actual, 'bounds_absolute_error_xyz_m': errors,
            'maximum_bounds_error_m': maximum, 'bounds_tolerance_m': tolerance_m,
            'normalization': 'Remove map translation, then reflect X for blue only; matches geometry-validation.json.',
            'scope': 'Evaluated base mesh counts and canonical bounds, excluding new court geometry.'}

def main():
    start=time.time();plan=json.loads((OUT/'placement-plan.json').read_text())
    art_path=ROOT/'out/pwr/base-art/geometry-validation.json'
    art_raw=art_path.read_bytes();art=json.loads(art_raw)
    art_hash=hashlib.sha256(art_raw).hexdigest()
    if not art.get('passed') or art_hash != plan['sources']['base_geometry_validation']['sha256']:
        raise RuntimeError('Reviewed base geometry report changed after placement planning')
    if not bpy.data.filepath.endswith('pwr-world-bases-v1.blend'):
        raise RuntimeError('Validate the assembled world, not the source art scene')
    scene=bpy.context.scene;reports={};failures=[]
    for site in plan['bases']:
        c=next(c for c in scene.collection.children if c.name.startswith(site['collection_prefix']))
        pos=site['normalize_then_translate_m']
        courts=[o for o in scene.objects if o.get('team')==site['id'] and o.get('offline_collision_candidate')]
        geometry=EvaluatedScene(list(c.all_objects)+courts,Matrix.Translation(-Vector(pos)))
        base_objects=set(c.all_objects)
        shape=base_shape_audit([r for r in geometry.records if r['object'] in base_objects],
                               art['scene_geometry'][site['id']],site['id'])
        checks={'reviewed_base_shape_preserved':shape}
        if not shape['passed']:failures.append(site['id']+'/reviewed_base_shape_preserved')
        for name,x,y0,y1 in [('main_through_and_forecourts',0,-65,57),
                             ('left_gallery_approach',-21.45,-50,-6.5),
                             ('right_gallery_approach',21.45,-50,-6.5),
                             ('left_vehicle_bypass',-50,-60,57),
                             ('right_vehicle_bypass',50,-60,57)]:
            air=volume_audit(geometry,{'min':[x-1.75,y0-3.5,.28],'max':[x+1.75,y1+3.5,4.7]})
            missing=[];heights=[]
            # Three tyre/body support lanes over each approach, sampled at
            # half-metre intervals; no assumption of a solid bounding box.
            for lane in (x-1.4,x,x+1.4):
                for j in range(round((y1-y0)*2)+1):
                    y=y0+j*.5;hit=geometry.ray((lane,y,1.0),(0,0,-1),2.0)
                    if hit is None or abs(hit['point_m'][2]-.2)>.085:
                        missing.append({'xy':[lane,y],'hit':hit})
                    else:heights.append(hit['point_m'][2])
            checks[name]={'air_clear':air['passed'],'obstructions':air,
                          'unsupported_samples':missing,'floor_passed':not missing,
                          'support_samples':len(heights)+len(missing)}
            if not air['passed'] or missing:failures.append(site['id']+'/'+name)
        roof=volume_audit(geometry,{'min':[-9.75,-9.75,11.0875],
                                   'max':[9.75,9.75,geometry.bounds['max'][2]+3]})
        checks['cannon_reservation']=roof
        if not roof['passed']:failures.append(site['id']+'/cannon_reservation')
        reports[site['id']]={'checks':checks,'base_meshes':sum(o.type=='MESH' for o in c.all_objects),
                            'court_meshes':len(courts),'world_translation_m':pos}
        del geometry;gc.collect()
    original=[o.name for o in scene.objects if o.name.startswith(('red_home_','blue_home_','citadel_plateau_'))]
    if original:failures.append('obsolete buildings remain')
    document={'schema':'pwr-offline-world-clearance-v1','passed':not failures,'failures':failures,
       'blend':bpy.data.filepath,'bases':reports,'obsolete_objects':original,
       'reviewed_base_geometry':{'path':str(art_path),'sha256':art_hash,
                                 'shape_checks_exclude_courts':True},
       'duration_seconds':time.time()-start,
       'scope':'Evaluated imported base meshes plus new court surfaces, with conservative 7x3.5x4.5m vehicle envelope. Approach floor support sampled every .5m. Terrain source remains separately hash-checked.',
       'limitations':['No native collision cook, game launch, articulated suspension test, vehicle steering or multiplayer test.',
                      'Blender water is an inspection proxy; Fluid Flux package unchanged.']}
    (OUT/'world-clearance.json').write_text(json.dumps(document,indent=2)+'\n')
    print(json.dumps({'passed':not failures,'failures':failures,'seconds':time.time()-start}))
    return document

if __name__=='__main__':main()
