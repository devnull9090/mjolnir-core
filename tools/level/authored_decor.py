"""Validated native mesh placements shared by runtime and Blender preparation."""
import json
import math
import re
from pathlib import Path

# Complete shipped sapling: bark and needles are both in the mesh. Bounds
# come from `mjolnir mesh list`, in centimetres. Only paths/metadata ship.
PINE_SAPLING='/Game/Env/Bio/Tree/Pine/Tree_Pine_Sapling_A/Meshes/SM_Tree_Pine_Sapling_A'
PINE_SAPLING_MIN_Z=-5.3125
PINE_SAPLING_HEIGHT=211.3125
PINE_OPTIMIZED='/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Sapling_Optimized'
PWR_MATURE_PINE='/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A'
PWR_MATURE_PINE_RECIPE='PWR_MaturePine_A'
PWR_MATURE_PINE_BARK=('MI_Pine_Tree_Mat',)


def complete_tree_recipe(variant, recipes):
    """Only the explicitly authored complete PWR pine accepts measured bounds.

    Bounds and the reviewed soil-contact root datum are centimetres in the
    final mesh's frame. The source hash identifies the assembly, not a template
    or an individual branch. Do not infer these measurements from its name.
    """
    if variant != PWR_MATURE_PINE_RECIPE:
        raise ValueError('Unsupported custom complete tree recipe')
    recipe=recipes.get(variant)
    if not isinstance(recipe,dict):
        raise ValueError('Missing measured complete tree recipe '+variant)
    mesh=recipe.get('complete_mesh')
    if mesh not in (PWR_MATURE_PINE,PWR_MATURE_PINE+'.'+PWR_MATURE_PINE.rsplit('/',1)[-1]):
        raise ValueError('Complete tree recipe must name the exact PWR mature pine')
    if (not _number(recipe.get('min_z')) or not _number(recipe.get('height'))
            or recipe['height']<=0):
        raise ValueError('Invalid measured complete tree bounds')
    if not _number(recipe.get('root_z')) or not recipe['min_z']<=recipe['root_z']<=recipe['min_z']+recipe['height']:
        raise ValueError('Invalid measured complete tree root datum')
    if not re.fullmatch(r'[0-9a-fA-F]{64}',str(recipe.get('geometry_sha256',''))):
        raise ValueError('Missing complete tree geometry hash')
    if recipe.get('bark_material_slots') != list(PWR_MATURE_PINE_BARK):
        raise ValueError('Complete tree bark slots do not match the measured source')
    return recipe


def _number(value):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)


def load_authored_decor_document(path,existing_ids=()):
    """Read native decor plus optional Blender-metre background trees.

    ``leaf_cluster_scale`` affects clusters about their own origins, never
    tree pivots or attachment positions. Omission preserves existing output.
    """
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('schema_version')!=1 or doc.get('coordinates')!='unreal_centimetres':
        raise ValueError('Unsupported authored decor coordinates/version')
    ids=set(existing_ids)
    for d in doc['decor']:
        if not isinstance(d.get('id'),str) or d['id'] in ids: raise ValueError('Duplicate/invalid native decor ID')
        ids.add(d['id'])
        if not isinstance(d.get('mesh'),str) or not d['mesh'].startswith('/Game/'): raise ValueError('Expected native /Game/ mesh')
        for field in ('pos','rot','scale'):
            if len(d.get(field,[]))!=3 or not all(_number(v) for v in d[field]):
                raise ValueError('Invalid native decor '+field)
        if any(v<=0 for v in d['scale']): raise ValueError('Native decor scale must be positive')
    trees=doc.get('background_trees',[])
    if not isinstance(trees,list): raise ValueError('background_trees must be a list')
    for tree in trees:
        if not isinstance(tree,dict): raise ValueError('Invalid background tree')
        if not isinstance(tree.get('id'),str) or not tree['id'] or tree['id'] in ids:
            raise ValueError('Duplicate/invalid background tree ID')
        ids.add(tree['id'])
        position=tree.get('position_m')
        if not isinstance(position,list) or len(position)!=3 or not all(_number(v) for v in position):
            raise ValueError('Background tree position_m must contain three finite metres')
        if not _number(tree.get('yaw_degrees',0)):
            raise ValueError('Invalid background tree yaw_degrees')
        if not _number(tree.get('height_m')) or tree['height_m']<=0:
            raise ValueError('Background tree height_m must be positive')
        if tree.get('variant','Lrg_A') not in ('Lrg_A','Pine_Sapling_A','Pine_Optimized',PWR_MATURE_PINE_RECIPE):
            raise ValueError('Unknown native background tree variant')
    factor=doc.get('leaf_cluster_scale',1.0)
    if not _number(factor) or factor<=0:
        raise ValueError('leaf_cluster_scale must be finite and positive')
    return doc


def load_authored_decor(path,existing_ids=()):
    """Compatibility API for consumers that need only explicit mesh decor."""
    return load_authored_decor_document(path,existing_ids)['decor']


def expand_background_trees(doc,recipes,bounds,existing_ids=(),leaf_mesh=None):
    """Build native tree parts and exact leaf records with shared runtime math.

    Authored positions/yaw use Blender metre axes; Unreal flips Y and yaw.
    Recipe part offsets use the existing scenery-swap convention, while leaf
    offsets retain the complete leaned trunk frame.
    """
    from scenery_swap import (LEAVES,TREE_CALM,object_path,rotation_rows,vmul,
                              mmul,foliage_pose,attached_leaves)
    trees=doc.get('background_trees',[])
    if any(t.get('variant','Lrg_A')=='Lrg_A' for t in trees) and leaf_mesh not in (None,LEAVES,object_path(LEAVES)):
        raise ValueError('Background Kuenovo trees require the existing Kuenovo leaf mesh')
    decor,leaves=[],[]
    ids=set(existing_ids)
    # Reserve authored IDs as well as generated IDs to prevent silent loader
    # replacement if a hand-authored mesh happens to use a tree-part ID.
    ids.update(d['id'] for d in doc.get('decor',[]))
    ids.update(tree['id'] for tree in trees)
    for tree in trees:
        variant=tree.get('variant','Lrg_A')
        if variant in ('Pine_Sapling_A','Pine_Optimized',PWR_MATURE_PINE_RECIPE):
            # Uniform sizing keeps the native tapered silhouette. Shipped
            # saplings retain their existing lowest-point convention. The
            # measured mature pine has a separate datum for buried roots.
            if variant==PWR_MATURE_PINE_RECIPE:
                recipe=complete_tree_recipe(variant,recipes)
                recorded=doc.get('complete_tree_provenance',{}).get(variant)
                if recorded is not None and any(recorded.get(k)!=recipe[k] for k in
                        ('complete_mesh','min_z','height','root_z','geometry_sha256','bark_material_slots')):
                    raise ValueError('Complete tree recipe changed after PCG conversion')
                mesh,min_z,height=PWR_MATURE_PINE,recipe['min_z'],recipe['height']
            else:
                mesh,min_z,height=(PINE_SAPLING,PINE_SAPLING_MIN_Z,PINE_SAPLING_HEIGHT) if variant=='Pine_Sapling_A' else (PINE_OPTIMIZED,-166.25,2150.125)
            scale=tree['height_m']*100/height
            root_z=recipe['root_z'] if variant==PWR_MATURE_PINE_RECIPE else min_z
            x,y,z=tree['position_m']
            ident=tree['id']+'_part_0'
            if ident in ids: raise ValueError('Duplicate native tree part ID '+ident)
            ids.add(ident)
            decor.append({'id':ident,'mesh':object_path(mesh),
                          'pos':[x*100,-y*100,z*100-root_z*scale],
                          'rot':[0,-tree.get('yaw_degrees',0),0],
                          'scale':[scale]*3,'static':True})
            if variant==PWR_MATURE_PINE_RECIPE:
                decor[-1]['source_geometry_sha256']=recipe['geometry_sha256']
            continue
        if variant not in recipes: raise ValueError('Missing background tree recipe '+variant)
        recipe=recipes[variant]
        if recipe.get('leaf_mesh',LEAVES)!=LEAVES:
            raise ValueError('Background tree recipe uses a different leaf mesh')
        if not _number(recipe.get('height')) or recipe['height']<=0:
            raise ValueError('Invalid background tree recipe height')
        x,y,z=(v*100 for v in tree['position_m']); y=-y
        yaw=-tree.get('yaw_degrees',0)
        height=tree['height_m']*100; scale=height/recipe['height']
        frame=[[scale*v for v in row] for row in rotation_rows(recipe['pitch'],yaw,recipe['roll'])]
        for leaf in attached_leaves(recipe,bounds):
            offset=vmul(leaf['off'],frame); world=mmul(leaf['m'],frame)
            fy,fs,fnx,fny=foliage_pose(world)
            leaves.append([round(x+offset[0],1),round(y+offset[1],1),round(z+offset[2],1),
                           round(fy,1),round(fs,3),round(fnx,3),round(fny,3)]
                          +[round(v,5) for row in world for v in row]
                          +[round(x,1),round(y,1),round(z,1),round(height,1)])
        c,sn=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
        for index,part in enumerate(recipe['parts']):
            ident=f"{tree['id']}_part_{index}"
            if ident in ids: raise ValueError('Duplicate native tree part ID '+ident)
            ids.add(ident)
            ox,oy,oz=(v*scale for v in part['off'])
            decor.append({'id':ident,'mesh':object_path(part['mesh']),
                          'pos':[round(x+ox*c-oy*sn,1),round(y+ox*sn+oy*c,1),round(z+oz,1)],
                          'rot':[recipe['pitch'],round(yaw,1),recipe['roll']],
                          'scale':[round(scale,3)]*3,'scalars':dict(TREE_CALM)})
    return decor,leaves


def scale_leaf_clusters(records,factor):
    """Scale leaf geometry in place without moving clusters or tree pivots."""
    if not _number(factor) or factor<=0:
        raise ValueError('leaf_cluster_scale must be finite and positive')
    if factor==1: return
    for record in records:
        record[4]=round(record[4]*factor,3)
        if len(record)>=16:
            record[7:16]=[round(v*factor,5) for v in record[7:16]]
