# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3", "pillow>=11,<13", "matplotlib>=3.10"]
# ///
"""Prepare isolated riparian/fringe/meadow candidates on the frozen native field.

Existing4470 trees and804 rocks are immutable inputs. Only a subsequent real UE
PCG run selects new objects and their yaw/scale. No editor/game is launched here.
"""
from pathlib import Path
import argparse, copy, json, math, shutil, struct, sys
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt
from scipy.spatial import ConvexHull, cKDTree
import shapely
from shapely.geometry import Polygon, Point, LineString, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools/level'))
from heightfield import load_heightfield, sha256
import b30_collision, pcg_foliage, pcg_tree_decor
from authored_decor import expand_background_trees

OUT = ROOT / 'out/pwr/visual-v6/scenery'
BASE = ROOT / 'out/pwr/visual-v5/outcrops-v4'
MASTER = ROOT / 'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
GEOMETRY = ROOT / 'levels/warfare/pwr/terrain/final-v5/terrain.geometry.json'
PAVING = ROOT / 'out/pwr/visual-v5/base-paving-v3/footprints.geojson'
PROBES = ROOT / 'out/pwr/world-v5/visual5/native-refresh/terrain-probe-plan.json'
TREE_PATH = BASE / 'trees/trees.selected.json'
ROCK_PATH = BASE / 'rocks-and-outcrops.authored-decor.json'
RECIPE_PATH = BASE / 'trees/recipes.json'
SEED = 20616


def dump(path, value, compact=False):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, separators=(',', ':') if compact else None,
                                    indent=None if compact else 2) + '\n')


def density_for_target(weight, target):
    if target > np.count_nonzero(weight):
        raise ValueError('Not enough measured eligible candidate locations for requested coverage')
    low, high = 0., 1000.
    for _ in range(48):
        factor = (low + high) / 2
        if np.minimum(weight * factor, 1).sum() < target: low = factor
        else: high = factor
    return np.minimum(weight * (low + high) / 2, 1)


class World:
    def __init__(self):
        self.field = load_heightfield(MASTER)
        self.s = self.field.spacing_m[0]
        self.trees = pcg_foliage.load(TREE_PATH)
        self.rocks = pcg_foliage.load(ROCK_PATH)
        if len(self.trees['instances']) != 4470 or len(self.rocks['decor']) != 804:
            raise ValueError('Reviewed installed scenery baseline changed')
        self.recipes = pcg_foliage.load(RECIPE_PATH)
        self.tree_xy = np.array([p['position'][:2] for p in self.trees['instances']])
        self.tree_index = cKDTree(self.tree_xy)
        self.paving = unary_union([shape(p['geometry']) for p in pcg_foliage.load(PAVING)['features']])
        self.pins = {str(p): sha256(p) for p in (MASTER, GEOMETRY, PAVING, PROBES, TREE_PATH, ROCK_PATH, RECIPE_PATH)}
        self.models = {}
        for path in (BASE / 'hulls').glob('SM_*.json'):
            doc = pcg_foliage.load(path)
            self.models[path.stem] = (np.asarray(doc['points'], float), np.asarray(doc['faces'], int), doc)
        self.rock_polygons = [self.footprint(row) for row in self.rocks['decor']]
        self.rock_area = unary_union(self.rock_polygons)
        tree_decor = pcg_tree_decor.convert(self.trees, self.recipes, max_trees=5000)
        tree_rows, leaves = expand_background_trees(tree_decor, self.recipes, {})
        if leaves or len(tree_rows) != 4470: raise ValueError('Unexpected native tree expansion')
        self.trunk_area = unary_union([self.footprint(row, tree=True) for row in tree_rows])
        self.tree_decor = tree_rows
        masks = self.field.masks
        self.road_distance = distance_transform_edt(~((masks['road'] > .002) | (masks['bases'] > .002)), sampling=self.s)
        self.water_distance = distance_transform_edt(~(masks['water'] > .001), sampling=self.s)
        gy, gx = np.gradient(self.field.heights_m, self.s)
        self.normal_z = 1 / np.sqrt(1 + gx*gx + gy*gy)
        self.protected = []
        prior = pcg_foliage.load(ROOT / 'out/pwr/visual-v5/forest-v2/inputs.receipt.json')
        for name, xy, radius in prior['clearance_discs']:
            self.protected.append(Point(xy).buffer(radius))
        for probe in pcg_foliage.load(PROBES)['probes']:
            self.protected.append(Point(probe['position_m'][:2]).buffer(max(8, probe.get('max_walk_metres', 0) + 4)))
        self.protected = unary_union(self.protected)
        self.structural_exclusion = unary_union([self.paving.buffer(3), self.rock_area.buffer(2), self.trunk_area.buffer(2), self.protected])
        self.grass_exclusion = unary_union([self.paving.buffer(1), self.rock_area.buffer(.55), self.trunk_area.buffer(.45), self.protected])
        water = []
        geometry = pcg_foliage.load(GEOMETRY)
        for course in geometry['watercourses']:
            points = np.asarray(course['surface_centreline_m'])
            for a, b in zip(points[:-1], points[1:]):
                for t in np.linspace(0, 1, max(2, int(np.linalg.norm(b[:2]-a[:2]) / 2) + 1)):
                    water.append(a*(1-t) + b*t)
        for lake in geometry['lakes']:
            water.extend([[x, y, lake['water_z_m']] for x, y in lake['polygon_m']])
        self.water_points = np.asarray(water)
        self.water_index = cKDTree(self.water_points[:, :2])

    def footprint(self, row, tree=False):
        leaf = row['mesh'].split('.')[-1]
        if tree and leaf == 'SM_PWR_MaturePine_A': leaf += '_bark_v1'
        elif tree: leaf += '_bark_v1' if leaf + '_bark_v1' in self.models else ''
        points, faces, _ = self.models[leaf]
        world = (points * row['scale']) @ b30_collision.rotator_matrix(*row['rot']) + row['pos']
        xy = world[:, :2] * [.01, -.01]
        return Polygon(xy[ConvexHull(xy).vertices])

    def indices(self, xy):
        ij = np.rint((xy - self.field.origin_m) / self.s).astype(int)
        return ij[:, 0].clip(0, 1008), ij[:, 1].clip(0, 1008)

    def eligible(self, xy, radius=3, grass=False, dry=False):
        ix, iy = self.indices(xy)
        #2.81m covers nearest-grid sampling uncertainty before footprint checks.
        okay = (self.road_distance[iy, ix] > radius + 2.81) & (self.water_distance[iy, ix] > radius + 2.81)
        okay &= self.normal_z[iy, ix] > (.8 if grass else .85)
        okay &= (np.max(np.abs(xy), axis=1) + radius < 945)
        exclusion = self.grass_exclusion if grass else self.structural_exclusion.buffer(radius)
        okay &= ~shapely.intersects_xy(exclusion, xy[:, 0], xy[:, 1])
        if dry:
            z = self.field.sample(xy[:, 0], xy[:, 1])
            water_z = self.water_points[self.water_index.query(xy)[1], 2]
            okay &= z > water_z + 1.5
        return okay


def grid(spacing, rng):
    axis = np.arange(-940 + spacing/2, 940, spacing)
    x, y = np.meshgrid(axis, axis)
    return np.c_[x.ravel(), y.ravel()] + rng.uniform(-.28*spacing, .28*spacing, (x.size, 2))


def source_document(world, xy, density, kind, start, biome, align=False):
    z = world.field.sample(xy[:, 0], xy[:, 1])
    if align:
        delta = world.s / 2
        gx = (world.field.sample(xy[:,0]+delta, xy[:,1])-world.field.sample(xy[:,0]-delta, xy[:,1]))/(2*delta)
        gy = (world.field.sample(xy[:,0], xy[:,1]+delta)-world.field.sample(xy[:,0], xy[:,1]-delta))/(2*delta)
        n = np.c_[-gx, -gy, np.ones(len(xy))]; n /= np.linalg.norm(n, axis=1)[:, None]
    else: n = np.tile([0., 0., 1.], (len(xy), 1))
    points = [{'id': start+i, 'position': [float(x), float(y), float(h)], 'normal': normal.tolist(),
               'density': float(density[i]), 'biome_mask': 1, 'kind': kind, 'biome': biome}
              for i, ((x,y),h,normal) in enumerate(zip(xy,z,n))]
    #Proof exclusions go through the real graph, not a hidden Python filter.
    for j in range(2):
        points.append({'id': start+len(xy)+j, 'position': points[0]['position'], 'normal': [0,0,1],
                       'density': 0. if j == 0 else 1., 'biome_mask': 1 if j == 0 else 0,
                       'kind': kind, 'biome': 'excluded_fixture'})
    return {'schema': 1, 'align_to_normal': align, 'master_sha256': world.field.manifest_sha256,
            'pins': world.pins, 'points': points, 'status': 'CPU candidates; real UE PCG selection pending'}


def prepare():
    world = World(); rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []; summary = {}; layers = {}
    def emit(name, xy, density, kind, start, biome, scale, palette, align=False):
        folder = OUT / name
        source = folder / 'candidates.json'
        document = source_document(world, xy, density, kind, start, biome, align)
        dump(source, document, compact=True)
        dump(folder/'palette.json', {'kinds': {kind: palette}})
        for suffix in ('', '_repeat'):
            jobs.append({'input': str(source), 'output': str(folder / ('generated'+suffix+'.json')),
                         'graph': '/Game/MJOLNIR/PCGAuthoring/PWRVisual6/PCG_'+name+suffix,
                         'seed': SEED, 'scale_min': scale[0], 'scale_max': scale[1]})
        summary[name] = {'candidates': len(xy), 'expected_selected': float(density.sum()),
                         'hard_maximum_selected': len(xy), 'scale_range': scale,
                         'source_sha256': sha256(source)}
        layers[name] = xy
    #Build a smooth stand-density field from the actual roots, not rectangles.
    raster = np.zeros(world.field.heights_m.shape)
    ix, iy = world.indices(world.tree_xy); np.add.at(raster, (iy, ix), 1)
    density = gaussian_filter(raster, 12) / world.s**2
    core = density > .0035
    distance = distance_transform_edt(~core, sampling=world.s)
    xy = grid(7, rng); ix, iy = world.indices(xy); dist = distance[iy, ix]
    allowed = world.eligible(xy, radius=3) & (world.tree_index.query(xy)[0] > 8)
    accepted = []
    for name, low, high, scale, recipe, start in (
        ('fringe_medium', 7, 34, [.35,.55], 'PWR_MaturePine_A', 6000000),
        ('fringe_sapling', 24, 60, [.7,1.1], 'Pine_Sapling_A', 6100000)):
        candidates = np.flatnonzero(allowed & (dist >= low) & (dist <= high))
        #Tapered suitability prioritizes the inner half without a density floor.
        score = np.maximum(1e-5, (1-(dist[candidates]-low)/(high-low))**1.5)
        order = candidates[np.argsort(-np.log(rng.random(len(candidates)))/score)]
        chosen = []
        for index in order:
            at = xy[index]
            if accepted and np.min(np.linalg.norm(np.asarray(accepted)-at, axis=1)) < 15: continue
            chosen.append(at); accepted.append(at)
            if len(chosen) == 120: break
        if len(chosen) < 100: raise ValueError('Insufficient safe forest fringe')
        emit(name, np.array(chosen), np.full(len(chosen), .97), 'tree', start,
             'graded_conifer_fringe', scale, {'recipe': recipe})
    #Dry upper-bank clusters, never a necklace of equally spaced stones.
    xy = grid(4, rng); ix, iy = world.indices(xy)
    dry = world.eligible(xy, radius=3.1, dry=True)
    dry &= (world.water_distance[iy,ix] < 24) & (world.tree_index.query(xy)[0] > 6)
    candidates = xy[dry]; candidates = candidates[rng.permutation(len(candidates))]
    centres = []; rock_xy = []; cluster_id = []
    for at in candidates:
        if centres and np.min(np.linalg.norm(np.asarray(centres)-at,axis=1)) < rng.uniform(23,42): continue
        centre_id = len(centres); centres.append(at)
        nearby = candidates[np.linalg.norm(candidates-at,axis=1) < rng.uniform(7,12)]
        for point in nearby[rng.permutation(len(nearby))]:
            if rock_xy and np.min(np.linalg.norm(np.asarray(rock_xy)-point,axis=1)) < 3.2: continue
            rock_xy.append(point); cluster_id.append(centre_id)
            if cluster_id.count(centre_id) >= int(rng.integers(2,8)) or len(rock_xy) >= 280: break
        if len(rock_xy) >= 280: break
    if len(rock_xy) < 200: raise ValueError('Insufficient dry riparian cluster locations')
    rocks = [world.models['SM_Rock_Glacial_Med_'+letter][2]['mesh'] for letter in 'ABC']
    emit('riparian_rocks', np.array(rock_xy), np.full(len(rock_xy), .97), 'rock', 6200000,
         'dry_riparian_cluster', [.25,.55], {'meshes': rocks})
    dump(OUT/'riparian_rocks/clusters.json', {'cluster_ids': cluster_id, 'centres_m': np.asarray(centres).tolist(),
        'dry_only': True, 'frozen_water_unmodified': True, 'maximum_candidate_count': 280})
    #A separate near-field grass layer; preserve the existing small turf layer.
    xy = grid(.9, rng)
    ix, iy = world.indices(xy)
    allowed = world.eligible(xy, radius=.65, grass=True)
    allowed &= world.field.masks['walkable'][iy,ix] > .5
    allowed &= world.field.masks['shore'][iy,ix] < .25
    noise = gaussian_filter(rng.normal(size=raster.shape), 8)
    noise /= noise.std()
    broad = gaussian_filter(rng.normal(size=raster.shape), 28); broad /= broad.std()
    patch = np.clip(.48 + .22*noise + .17*broad, 0, 1)
    #Coherent lush patches and open fallow pockets, instead of uniform tufts.
    weight = patch[iy,ix]**1.6
    allowed &= weight > .11
    xy, weight = xy[allowed], weight[allowed]
    split = rng.random(len(xy))
    assets = {
        'meadow_sedge': ('/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_C.SM_Grass_Sedges_A_Leaves_C', [.8,1.], 360000, split < .80),
        'meadow_tall': ('/Game/Megascans/3D_Plants/Tall_Grass_rbeki/SM_Tall_Grass_rbeki_01.SM_Tall_Grass_rbeki_01', [.5,.7], 80000, (split >= .80)&(split < .98)),
        'meadow_rush': ('/Game/Env/Bio/Grass/Rushes/Grass_Rushes_A/SM_Grass_Rushes_A.SM_Grass_Rushes_A', [.65,.8], 10000, split >= .98)}
    for n, (name, (mesh, scale, target, select)) in enumerate(assets.items()):
        chosen, weights = xy[select], weight[select]
        density = density_for_target(weights, target)
        emit(name, chosen, density, 'grass', 7000000+n*2000000, 'patch_meadow', scale,
             {'meshes':[mesh], 'rule':'visual6 meadow', 'cull':[4000,8000], 'bands':2,
              'shadow':False, 'static':True}, align=True)
    dump(OUT/'request.json', {'jobs': jobs})
    report = {'schema':'pwr-scenery-v6-input-v1', 'pins':world.pins, 'seed':SEED, 'jobs':summary,
        'baseline_trees':4470, 'baseline_rocks':804, 'baseline_records_immutable':True,
        'expected_additional_grass':450000, 'expected_total_grass_before_new_hull_exclusion':729388,
        'native_surface_baseline':1122959, 'hard_additional_native_surface_limit':54000,
        'hard_total_native_surface_limit':1200000, 'status':'CPU candidates; no UE generation/installed changes'}
    asset_receipt=OUT/'native-grass-source/assets.receipt.json'
    if asset_receipt.is_file():
        report['native_grass_asset_receipt']={'path':str(asset_receipt),'sha256':sha256(asset_receipt)}
    dump(OUT/'inputs.receipt.json',report)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(15,7), constrained_layout=True)
    for a in ax:
        a.imshow(world.field.heights_m,origin='lower',extent=(-1000,1000,-1000,1000),cmap='gist_earth',alpha=.4)
        a.scatter(*world.tree_xy.T,s=.5,c='#183925');a.set_aspect('equal');a.set_xlim(-1000,1000);a.set_ylim(-1000,1000)
    for name,color in [('fringe_medium','#83b84c'),('fringe_sapling','#d8c54f'),('riparian_rocks','#477eb3')]:
        ax[0].scatter(*layers[name].T,s=6,c=color,label=name)
    ax[0].legend(fontsize=7);ax[0].set_title('Immutable woodland + new PCG candidate fringes / dry stones')
    for name in assets:
        points=layers[name][::70];ax[1].scatter(*points.T,s=.3,c='#7ba13d')
    ax[1].set_title('Larger meadow patches (candidate subset preview; not PCG output)')
    fig.savefig(OUT/'candidate-plan.png',dpi=150);plt.close(fig)
    print(json.dumps(report))


def merge_tree_selection(baseline, additions, provenance):
    """Keep the exact old records; describe the union without inventing a run."""
    result = copy.deepcopy(baseline)
    original = result['instances']
    merged = original + [copy.deepcopy(row) for document in additions for row in document['instances']]
    if len({row['id'] for row in merged}) != len(merged):
        raise ValueError('Duplicate IDs in immutable-baseline/fringe tree union')
    if merged[:len(original)] != baseline['instances']:
        raise ValueError('Old tree transforms changed')
    result.update(instances=merged, selected_count=len(merged),
                  input_count=baseline['input_count'] + sum(row['input_count'] for row in additions),
                  generator='UE5.5 UPCGGraph / immutable installed selection + actual visual6 fringe',
                  graph=';'.join([baseline['graph']] + [row['graph'] for row in additions]),
                  source_sha256=provenance['input_receipt_sha256'],
                  pcg_output_sha256=provenance['output_receipt_sha256'])
    from collections import Counter
    result['selected_by_recipe'] = dict(Counter(row['recipe'] for row in merged))
    result['composition'] = {'schema':'pwr-pcg-filtered-union-v1',
        'base_count':len(original), 'base_sha256':sha256(TREE_PATH),
        'retained_base_records_exact':True, 'new_count':len(merged)-len(original),
        'base_seed':baseline.get('seed'),'addition_seeds':[row.get('seed') for row in additions],
        'actual_pcg_additions':provenance}
    return result


def finite_pose_check(points_cm, faces, row):
    """Measure finite native serialization, not infinite thin-face halfspaces."""
    world = (points_cm * row['scale']) @ b30_collision.rotator_matrix(*row['rot']) + row['pos']
    metres = world / 100
    stored = np.round(metres / 3.048, 4).astype('<f4').astype(float) * 3.048
    before, after = metres[faces], stored[faces]
    n0 = np.cross(before[:,1]-before[:,0], before[:,2]-before[:,0])
    n1 = np.cross(after[:,1]-after[:,0], after[:,2]-after[:,0])
    area = np.linalg.norm(n1,axis=1) * .5
    if np.min(area) <= 1e-9 or np.any(np.sum(n0*n1,axis=1) <= 0):
        raise ValueError('Serialized new scenery pose collapses or flips a facet: '+row['id'])
    return {'id':row['id'], 'faces':len(faces), 'minimum_triangle_area_m2':float(area.min()),
            'maximum_corresponding_vertex_shift_m':float(np.linalg.norm(stored-metres,axis=1).max())}


def export():
    world = World()
    inputs = pcg_foliage.load(OUT/'inputs.receipt.json')
    for path, expected in inputs['pins'].items():
        if sha256(path) != expected: raise ValueError('Frozen candidate input changed: '+path)
    asset_receipt=inputs.get('native_grass_asset_receipt')
    if not asset_receipt or sha256(asset_receipt['path'])!=asset_receipt['sha256']:
        raise ValueError('Missing or changed actual native grass geometry inspection')
    outputs = {}; comparisons = {}
    for name, declaration in inputs['jobs'].items():
        folder = OUT/name
        source, generated, repeat = [folder/leaf for leaf in ('candidates.json','generated.json','generated_repeat.json')]
        if sha256(source) != declaration['source_sha256']: raise ValueError('Candidate source changed: '+name)
        comparisons[name] = pcg_foliage.compare(source, generated, repeat)
        outputs[name] = pcg_foliage.adapt(source, generated, folder/'palette.json', folder/'adapted', name='selection')
        if outputs[name]['selected_count'] > declaration['hard_maximum_selected']:
            raise ValueError('PCG selected an excluded fixture')
    dump(OUT/'pcg-output.receipt.json', {'schema':'pwr-scenery-v6-pcg-output-v1', 'comparisons':comparisons,
        'input_receipt_sha256':sha256(OUT/'inputs.receipt.json'), 'request_receipt_sha256':sha256(OUT/'request.receipt.json')})
    provenance = {'input_receipt_sha256':sha256(OUT/'inputs.receipt.json'),
                  'output_receipt_sha256':sha256(OUT/'pcg-output.receipt.json'),
                  'graph_outputs':{name:sha256(OUT/name/'generated.json') for name in outputs}}
    added_trees = [outputs[name] for name in ('fringe_medium','fringe_sapling')]
    if any(row['selected_count']>120 for row in added_trees): raise ValueError('Approved fringe count exceeded')
    trees = merge_tree_selection(world.trees, added_trees, provenance)
    tree_dir=OUT/'trees';tree_dir.mkdir(exist_ok=True)
    dump(tree_dir/'trees.selected.json',trees,compact=True)
    shutil.copy2(RECIPE_PATH,tree_dir/'recipes.json')
    added_doc = copy.deepcopy(trees); added_doc['instances']=trees['instances'][4470:]
    added_doc['selected_count']=len(added_doc['instances'])
    added_decor,_=expand_background_trees(pcg_tree_decor.convert(added_doc,world.recipes,max_trees=240),world.recipes,{})
    new_tree_area=unary_union([world.footprint(row,tree=True) for row in added_decor])
    #Actual PCG determines asset/yaw/scale. A deterministic vertical grounding
    #adapter embeds each stone; its resulting render/native transform is shared.
    from outcrops_v3 import lod0_points
    render_points={letter:lod0_points(ROOT/f'out/pwr/visual-v5/outcrops-v3/assets/SM_Rock_Glacial_Med_{letter}.glb') for letter in 'ABC'}
    new_rocks=[];rock_checks=[];rejected=[]
    for point in outputs['riparian_rocks']['instances']:
        leaf=point['mesh'].split('.')[-1];letter=leaf[-1]
        mesh_points,faces,model=world.models[leaf]
        rot=[0,-point['yaw_degrees'],0];scale=point['scale']
        relative=(render_points[letter]*scale)@b30_collision.rotator_matrix(*rot)/100
        xy=np.asarray(point['position'][:2]);samplexy=relative[:,:2]*[1,-1]+xy
        bottom=relative[:,2]<=np.quantile(relative[:,2],.15)
        support=world.field.sample(samplexy[bottom,0],samplexy[bottom,1])
        height=float(np.ptp(relative[:,2]))
        z=float(np.quantile(support-relative[bottom,2],.05)-height*.22)
        row={'id':'pwr_v6_riparian_'+str(point['id']),'mesh':point['mesh'],
             'pos':[float(xy[0]*100),float(-xy[1]*100),z*100], 'rot':rot,'scale':[scale]*3,'static':True}
        footprint=world.footprint(row)
        radius=float(np.max(np.linalg.norm(samplexy-xy,axis=1)))
        rock_support=world.field.sample(samplexy[:,0],samplexy[:,1])
        clearance=relative[:,2]+z-rock_support
        nearest_water=float(world.water_points[world.water_index.query(xy)[1],2])
        ix,iy=world.indices(xy[None,:])
        water_clearance=float(world.water_distance[iy[0],ix[0]]-radius-2.81)
        road_clearance=float(world.road_distance[iy[0],ix[0]]-radius-2.81)
        #The source already passed a yaw-independent3.1m anchor guard. Check
        #the actual final footprint directly instead of rebuilding a several-
        #thousand-polygon Minkowski sum independently for every stone.
        if (radius>3.1 or road_clearance<=0 or water_clearance<=0
                or footprint.intersects(world.structural_exclusion)
                or footprint.buffer(.8).intersects(new_tree_area)
                or rock_support.min()<=nearest_water+.1
                or np.max(clearance)<.25 or np.quantile(clearance[bottom],.95)>.02):
            rejected.append({'id':point['id'],'reason':'full geometry grounding/dry footprint or new-tree exclusion'})
            continue
        new_rocks.append(row)
        rock_checks.append({'id':row['id'],'pcg_id':point['id'],'render_glb_sha256':sha256(ROOT/f'out/pwr/visual-v5/outcrops-v3/assets/{leaf}.glb'),
            'pcg_xy_yaw_scale_preserved':True,'deterministic_grounded_z_m':z,
            'grounding_delta_from_pcg_m':z-point['position'][2],
            'max_exposure_m':float(clearance.max()),'bottom_p95_above_soil_m':float(np.quantile(clearance[bottom],.95)),
            'dry_support_above_nearest_water_m':float(rock_support.min()-nearest_water),
            'water_footprint_clearance_m':water_clearance,'road_footprint_clearance_m':road_clearance})
    if not 180<=len(new_rocks)<=280:raise ValueError('Too many dry riparian stones rejected; inspect the pilot')
    rocks=copy.deepcopy(world.rocks);rocks['decor']+=new_rocks
    rocks['visual_v4_provenance'].update(source_rocks_sha256=sha256(ROCK_PATH),
        frozen_runtime_master_sha256=world.field.manifest_sha256,
        generation='804 immutable baseline rocks + actual UEPCG-selected dry riparian clusters, deterministic measured grounding',
        actual_pcg_provenance=provenance,source_rock_records_exact=True)
    if rocks['decor'][:804]!=world.rocks['decor']:raise ValueError('Baseline rock transforms changed')
    dump(OUT/'rocks-and-outcrops.authored-decor.json',rocks)
    new_rock_area=unary_union([world.footprint(row) for row in new_rocks])
    exclusion=unary_union([new_rock_area.buffer(.55),new_tree_area.buffer(.45)])
    final_groups=[];grass_reports=[]
    grass_sources=[('baseline',BASE/'grass/foliage.json')]+[(name,OUT/name/'adapted/selection.json') for name in ('meadow_sedge','meadow_tall','meadow_rush')]
    for name,path in grass_sources:
        _,groups=pcg_foliage.read_mjf_groups(path)
        for group,payload,sidecars,count in groups:
            xf=np.frombuffer(sidecars['xf'],dtype='<f4').reshape(count,10);xy=xf[:,:2]*[.01,-.01]
            keep=~shapely.intersects_xy(exclusion,xy[:,0],xy[:,1]);n=int(keep.sum())
            records=np.frombuffer(payload[4:],dtype=np.dtype((np.void,19)))
            filtered={suffix:np.frombuffer(value,dtype=np.dtype((np.void,40 if suffix=='xf' else 16)))[keep].tobytes() for suffix,value in sidecars.items()}
            final_groups.append((dict(group,pcg=True),struct.pack('<I',n)+records[keep].tobytes(),filtered,n))
            grass_reports.append({'source':name,'input':count,'retained':n,'local_new_hull_exclusions':count-n,'retained_transform_bytes_exact':True})
    total_grass=sum(row[3] for row in final_groups)
    if not 650000<=total_grass<=850000:raise ValueError('Actual meadow count outside approved first-pass cap')
    grass_dir=OUT/'grass';grass_dir.mkdir(exist_ok=True)
    binary=grass_dir/'foliage.bin';binary.write_bytes(b'MJF3'+struct.pack('<II',3,len(final_groups))+b''.join(row[1] for row in final_groups))
    for index,(_,_,sidecars,_) in enumerate(final_groups,1):
        for suffix,data in sidecars.items():Path(str(binary)+'.'+suffix+str(index)).write_bytes(data)
    dump(grass_dir/'foliage.json',{'file':'foliage.bin','groups':[row[0] for row in final_groups]})
    pcg_foliage.read_mjf_groups(grass_dir/'foliage.json')
    hull_dir=OUT/'hulls';hull_dir.mkdir(exist_ok=True)
    for path in (BASE/'hulls').glob('SM_*.json'):shutil.copy2(path,hull_dir/path.name)
    poses=[];native_added=0
    for row in added_decor+new_rocks:
        points,faces=b30_collision.hull_of(row['mesh'],str(hull_dir),expected_geometry_sha256=row.get('source_geometry_sha256'))
        native_added+=len(faces);poses.append(finite_pose_check(points,faces,row))
    if native_added>54000 or 1122959+native_added>1200000:raise ValueError('Strict additional/total native ceiling exceeded')
    pcg_tree_decor.convert(trees,world.recipes,max_trees=4710)
    report={'schema':'pwr-scenery-v6-handoff-v1','pins':world.pins,'actual_pcg':provenance,
        'native_grass_asset_receipt':asset_receipt,'source_generator_sha256':sha256(Path(__file__)),
        'baseline_trees_exact':True,'baseline_rocks_exact':True,'trees':len(trees['instances']),
        'new_medium':outputs['fringe_medium']['selected_count'],'new_saplings':outputs['fringe_sapling']['selected_count'],
        'rocks':len(rocks['decor']),'new_dry_riparian_rocks':len(new_rocks),'rock_grounding_checks':rock_checks,
        'post_pcg_rejected_rocks':rejected,'grass':total_grass,'grass_groups':grass_reports,
        'native_surface_baseline':1122959,'additional_native_surfaces':native_added,
        'projected_native_surfaces':1122959+native_added,'explicit_native_surface_cap':1200000,
        'finite_serialized_pose_checks':poses,'new_fluid_obstacles':False,'height_or_layout_changes':False,
        'status':'ActualPCG/offlinegeometry passed; compile/installedvisual/native/FPS acceptance pending'}
    dump(OUT/'receipt.json',report)
    fragment={'pcg_foliage':str(grass_dir/'foliage.json'),'pcg_trees':str(tree_dir/'trees.selected.json'),
        'tree_recipes':str(tree_dir/'recipes.json'),'collision_hulls':str(hull_dir),
        'authored_rocks':str(OUT/'rocks-and-outcrops.authored-decor.json'),'expected_rocks':len(rocks['decor']),
        'baseline_rocks':str(ROCK_PATH),'expected_trees':len(trees['instances']),'expected_grass':total_grass}
    dump(OUT/'config.fragment.json',fragment)
    files=[OUT/'receipt.json',OUT/'config.fragment.json',OUT/'rocks-and-outcrops.authored-decor.json',tree_dir/'trees.selected.json',tree_dir/'recipes.json',grass_dir/'foliage.json',binary]+list(grass_dir.glob('foliage.bin.*'))+list(hull_dir.glob('SM_*.json'))
    dump(OUT/'seal.json',{'schema':'pwr-scenery-v6-seal-v1','files':{str(p.relative_to(OUT)):sha256(p) for p in sorted(files)}})
    print(json.dumps({key:report[key] for key in ('trees','rocks','grass','additional_native_surfaces','projected_native_surfaces')}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','export'])
    args=parser.parse_args()
    globals()[args.command]()
