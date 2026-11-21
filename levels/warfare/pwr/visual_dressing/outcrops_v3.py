# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "pillow>=11,<13", "shapely>=2,<3", "matplotlib>=3.10"]
# ///
"""Isolated, deterministic structural cliff dressing. No editor/game calls.

This is an authored geological assembly, not a claimed UE PCG run. Render and
native collision share each verified stock mesh transform. Existing terrain,
water, roads and installed artifacts are read-only inputs.
"""
from pathlib import Path
import argparse,json,math,struct,sys
import numpy as np
from scipy.ndimage import distance_transform_edt,gaussian_filter
from scipy.spatial import ConvexHull,cKDTree
import shapely
from shapely.geometry import shape,Point
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield,sha256
import b30_collision

OUT=ROOT/'out/pwr/visual-v5/outcrops-v3'
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
HULLS=ROOT/'out/pwr/visual-v5/outcrops-v2/hulls'
TREES=ROOT/'out/pwr/visual-v5/forest-v2/trees.selected.json'
ROCKS=ROOT/'out/pwr/visual-v5/outcrops-v2/rocks-and-outcrops.authored-decor.json'
PAVING=ROOT/'out/pwr/visual-v5/base-paving-v3/footprints.geojson'
PALETTE={'desert_a':'SM_Rock_Desert_Cliff_A','desert_b':'SM_Rock_Desert_Cliff_B',
         'desert_c':'SM_Rock_Desert_Cliff_C','desert_d':'SM_Rock_Desert_Cliff_D',
         'macro':'SM_PNWGL_Rock_Macro_B','cliff':'SM_Rock_Uluwatu_Cliff_B',
         'stratum':'SM_MassiveTundraRockFormation_01'}


def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2)+'\n')


def lod0_points(path):
    """Full native-export LOD0 vertices, not the coarse hull sample LOD."""
    raw=Path(path).read_bytes();length=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+length]);data=raw[28+length:]
    result=[]
    for primitive in doc['meshes'][0]['primitives']:
        accessor=doc['accessors'][primitive['attributes']['POSITION']]
        view=doc['bufferViews'][accessor['bufferView']]
        assert accessor['componentType']==5126 and accessor['type']=='VEC3'
        offset=view.get('byteOffset',0)+accessor.get('byteOffset',0)
        a=np.ndarray((accessor['count'],3),dtype='<f4',buffer=data,offset=offset,strides=(view.get('byteStride',12),4))
        result.append(a[:,[0,2,1]].astype(float)*100)
    return np.concatenate(result)


def surface_samples(points,faces,spacing=1.5):
    """Barycentric face sampling with a conservative spacing receipt."""
    output=[points]
    for face in faces:
        a,b,c=points[np.asarray(face)]
        n=max(1,int(math.ceil(max(np.linalg.norm(b-a),np.linalg.norm(c-a),np.linalg.norm(c-b))/spacing)))
        for i in range(n+1):
            j=np.arange(n-i+1)
            output.append(a+(b-a)*(i/n)+(c-a)*j[:,None]/n)
    return np.concatenate(output)


class World:
    def __init__(self):
        self.field=load_heightfield(MASTER)
        self.s=self.field.spacing_m[0]
        f=self.field
        self.water_distance=distance_transform_edt(f.masks['water']<.002,sampling=self.s)
        self.road_distance=distance_transform_edt(f.masks['road']<.002,sampling=self.s)
        self.base_distance=distance_transform_edt(f.masks['bases']<.002,sampling=self.s)
        self.paving=unary_union([shape(x['geometry']) for x in json.loads(PAVING.read_text())['features']]).buffer(1.)
        self.models={}
        for role,leaf in PALETTE.items():
            hull_path=OUT/'hulls'/(leaf+'.json')
            if not hull_path.is_file():hull_path=HULLS/(leaf+'.json')
            hull=json.loads(hull_path.read_text())
            path=(OUT/'assets' if role.startswith('desert') else ROOT/'out/pwr/visual-v4/assets')/(leaf+'.glb')
            self.models[role]={'leaf':leaf,'mesh':hull['mesh'],'points':np.array(hull['points'])/100,
                               'faces':np.array(hull['faces']),'render':lod0_points(path)/100,'source':path,'hull_source':hull_path}
        self.existing=json.loads(ROCKS.read_text())['decor']

    def sample_raster(self,raster,xy):
        grid=np.round((xy-self.field.origin_m)/self.s).astype(int)
        return raster[np.clip(grid[:,1],0,1008),np.clip(grid[:,0],0,1008)]

    def ground(self,xyz):return self.field.sample(xyz[:,0],xyz[:,1])

    def bank_crest(self,x,y):
        f=self.field
        gradient=np.array([float(f.sample(x+3,y)-f.sample(x-3,y)),float(f.sample(x,y+3)-f.sample(x,y-3))])
        gradient/=max(np.linalg.norm(gradient),1e-8)
        line=np.array([x,y])+np.linspace(15,48,18)[:,None]*gradient
        return float(np.quantile(f.sample(line[:,0],line[:,1]),.75))

    def transform(self,model,row,render=False):
        local=model['render'] if render else model['points']
        native=local*np.array(row['scale'])@b30_collision.rotator_matrix(*row['rot'])+np.array(row['pos'])/100
        return native*np.array([1,-1,1])

    def validate(self,model,row,full=False,minimum_exposure=3):
        points=self.transform(model,row)
        if np.max(abs(points[:,:2]))>=948:return None
        face_points=points[model['faces']]
        samples=surface_samples(points,model['faces'],2.5) if full else np.concatenate([points,face_points.mean(axis=1),face_points[:,[0,1]].mean(axis=1),face_points[:,[1,2]].mean(axis=1),face_points[:,[2,0]].mean(axis=1)])
        if full:samples=np.concatenate([samples,self.transform(model,row,True)])
        ground=self.ground(samples);above=samples[:,2]-ground
        exposed=above>.2
        if not np.any(exposed):return None
        visible=samples[exposed]
        water=self.sample_raster(self.water_distance,visible[:,:2])-math.sqrt(2)*self.s
        roads=self.sample_raster(self.road_distance,visible[:,:2])-math.sqrt(2)*self.s
        bases=self.sample_raster(self.base_distance,visible[:,:2])-math.sqrt(2)*self.s
        # Full exposed render and native surfaces must remain on the dry side
        # and clear the complete painted carriageway/shoulder footprint. Backs
        # buried at least20cm below immutable ground cannot block those paths.
        if water.min()<1.0 or roads.min()<3.0 or bases.min()<4.0:return None
        if np.any(shapely.intersects_xy(self.paving,visible[:,0],visible[:,1])):return None
        bottom=points[points[:,2]<=np.quantile(points[:,2],.18)]
        support=bottom[:,2]-self.ground(bottom)
        if support.max()>.15:return None
        projected=ConvexHull(points[:,:2])
        area=float(projected.volume)
        exposed_height=float(np.max(above))
        if exposed_height<minimum_exposure or exposed_height>65 or samples[:,2].max()>399:return None
        return {'exposed_height_max_m':exposed_height,'exposed_sample_fraction':float(exposed.mean()),
                'bottom_contact_max_above_ground_m':float(support.max()),'full_projected_area_m2':area,
                'minimum_exposed_water_clearance_m':float(water.min()),'minimum_exposed_road_clearance_m':float(roads.min()),
                'minimum_exposed_base_clearance_m':float(bases.min()),'sample_count':len(samples),
                'full_lod0_checked':full,'hull_face_spacing_m':2.5 if full else None,
                'original_bank_crest_m':self.bank_crest(row['pos'][0]/100,-row['pos'][1]/100),
                'highest_render_or_hull_point_m':float(samples[:,2].max())}

    def pose(self,role,xy,rng,index,region='bank'):
        model=self.models[role];f=self.field
        x,y=xy
        dx=float(f.sample(x+3,y)-f.sample(x-3,y))/6
        dy=float(f.sample(x,y+3)-f.sample(x,y-3))/6
        heading=math.atan2(dx,-dy)+rng.uniform(-.35,.35)
        if role.startswith('desert'):
            scale=[rng.uniform(1.05,1.75),rng.uniform(.38,.72),rng.uniform(1.15,1.75)]
            rot=[rng.uniform(-9,9),-math.degrees(heading),rng.uniform(-12,12)]
        elif role=='cliff':
            scale=[rng.uniform(.55,.9),rng.uniform(.2,.38),rng.uniform(.65,.95)]
            rot=[rng.uniform(-7,7),-math.degrees(heading),rng.uniform(-10,10)]
        elif role=='stratum':
            scale=[rng.uniform(.4,.75),rng.uniform(.35,.65),rng.uniform(.7,1.2)]
            rot=[rng.uniform(-9,9),-math.degrees(heading),rng.uniform(-12,12)]
        else:
            scale=[rng.uniform(.19,.28),rng.uniform(.08,.14),rng.uniform(.17,.24)]
            rot=[rng.uniform(-8,8),-math.degrees(heading),rng.uniform(-10,10)]
        if region=='ridge':
            # Follow the local strata with the rock's long axis along contour,
            # and bury most of its volume. These are exposed bedrock faces,
            # rather than freestanding pillars mounted on the hillside.
            scale[0]*=1.25;scale[2]*=.85
            rot[2]=-.65*math.degrees(math.atan(math.hypot(dx,dy)))+rng.uniform(-8,8)
        row={'id':f'pwr_scarp_{role}_{index:03d}','mesh':model['mesh'],'pos':[x*100,-y*100,0.],
             'rot':rot,'scale':scale,'static':True}
        points=self.transform(model,row)
        bottom=points[points[:,2]<=np.quantile(points[:,2],.18)]
        height=float(np.min(self.ground(bottom)-bottom[:,2])-rng.uniform(1,2.5))
        row['pos'][2]=height*100
        # Bank dressing follows the existing crest, instead of stacking a new
        # second cliff wall above it. Larger rocks may be mostly buried.
        transformed_top=float(self.transform(model,row)[:,2].max())
        crest=float(f.sample(x,y)) if region=='ridge' else self.bank_crest(x,y)
        row['pos'][2]-=max(0.,transformed_top-crest-rng.uniform(3,8 if region=='ridge' else 6))*100
        return row


def generate(pilot=False,region='bank'):
    OUT.mkdir(parents=True,exist_ok=True)
    world=World();f=world.field;rng=np.random.default_rng(20593)
    h=f.heights_m;gy,gx=np.gradient(gaussian_filter(h,1.3),world.s);slope=np.hypot(gx,gy)
    yy,xx=np.indices(h.shape);xy=np.c_[xx.ravel(),yy.ravel()]*world.s+f.origin_m
    bank=(slope>.6)&(world.water_distance>6)&(world.water_distance<95)&(h>58)&(h<135)
    if region=='ridge':
        bank=(slope>.55)&(world.water_distance>110)&(world.road_distance>45)&(world.base_distance>55)&(h>155)&(h<320)
        bank&=(abs(xx*world.s-1000)<900)&(abs(yy*world.s-1000)<900)
    elif pilot:bank&=(xx*world.s-1000>240)&(yy*world.s-1000<-370)&(yy*world.s-1000>-590)
    else:bank&=(yy*world.s-1000<550)
    target=xy[bank.ravel()];target_z=h[bank];target_weights=np.minimum(slope[bank],2.)
    covered=np.zeros(len(target),bool)
    limit=1400 if pilot else (2600 if region=='ridge' else 4500)
    candidates=target[rng.choice(len(target),min(len(target),limit),replace=False)]+rng.uniform(-1.5,1.5,(min(len(target),limit),2))
    proposals=[];failures=0
    for i,at in enumerate(candidates):
        if i%250==0:print(f'Candidate{i}/{len(candidates)}; viable{len(proposals)}',flush=True)
        role=tuple(PALETTE)[i%len(PALETTE)]
        row=world.pose(role,at,rng,i,region);row['id']=row['id'].replace('pwr_scarp_',f'pwr_{"lake_pilot" if pilot else region}_')
        report=world.validate(world.models[role],row)
        if report is None:failures+=1;continue
        hull=world.transform(world.models[role],row)
        lo,hi=hull.min(0),hull.max(0)
        ids=np.flatnonzero(np.all(target>=lo[:2]-1,axis=1)&np.all(target<=hi[:2]+1,axis=1)&(target_z>lo[2])&(target_z<hi[2]))
        if len(ids)<18:continue
        # A terrain point lies behind the rock's visible surface only when it
        # is in the actual placed convex hull, not merely its bounding box.
        faces=world.models[role]['faces'];a,b,c=(hull[faces[:,k]] for k in range(3))
        normal=np.cross(b-a,c-a);length=np.linalg.norm(normal,axis=1);normal/=length[:,None]
        centre=hull.mean(0);flip=np.sum((centre-a)*normal,axis=1)>0;normal[flip]*=-1
        terrain=np.c_[target[ids],target_z[ids]]
        inside=np.all(terrain@normal.T-np.sum(a*normal,axis=1)<=.5,axis=1)
        ids=ids[inside]
        if len(ids)<18:continue
        proposals.append((row,role,report,ids,hull))
    selected=[]
    # Keep the inspected lake assembly intact when extending it to the full map.
    if not pilot and region=='bank':
        prior=json.loads(Path(__file__).with_name('lake-pilot-v3.json').read_text())
        assert prior['runtime_master_sha256']==f.manifest_sha256
        for row in prior['decor']:
            role=next(k for k,m in world.models.items() if m['mesh']==row['mesh'])
            model=world.models[role];full=world.validate(model,row,full=True)
            if full is None:raise ValueError('Reviewed pilot fails final paving/route constraints: '+row['id'])
            hull=world.transform(model,row);qh=ConvexHull(hull);lo,hi=hull.min(0),hull.max(0)
            ids=np.flatnonzero(np.all(target>=lo[:2],axis=1)&np.all(target<=hi[:2],axis=1)&(target_z>lo[2])&(target_z<hi[2]))
            inside=np.all(np.c_[target[ids],target_z[ids]]@qh.equations[:,:3].T+qh.equations[:,3]<=.5,axis=1);ids=ids[inside]
            covered[ids]=True;centre=hull.mean(0)
            full.update(id=row['id'],role=role,centre_m=centre.tolist(),terrain_target_vertices_covered=len(ids))
            selected.append({'decor':row,'report':full,'centre_m':centre.tolist()})
    for count in range(60 if pilot else 160):
        if len(selected)>=(32 if pilot else (32 if region=='ridge' else 90)) or covered.mean()>.92:break
        scored=[float(target_weights[p[3][~covered[p[3]]]].sum()) for p in proposals]
        if not scored or max(scored)<24:break
        index=int(np.argmax(scored));row,role,report,ids,hull=proposals.pop(index)
        if sum(x['report']['role']==role for x in selected)>=(10 if pilot else 28):continue
        full=world.validate(world.models[role],row,full=True)
        if full is None:continue
        # Reject near-duplicate placements while allowing fractured faces to
        # overlap by a few metres; no equal-spacing chain or target count fill.
        centre=hull.mean(0)
        if any(np.linalg.norm(centre-np.array(x['centre_m']))<(20 if region=='ridge' else 10) for x in selected):continue
        covered[ids]=True
        full.update(id=row['id'],role=role,centre_m=centre.tolist(),terrain_target_vertices_covered=len(ids))
        selected.append({'decor':row,'report':full,'centre_m':centre.tolist()})
    stem='pilot' if pilot else region
    dump(OUT/(stem+'.json'),{'schema':'pwr-outcrops-v3','status':'authored stock assembly; actual runtime/native/PCG acceptance pending',
        'runtime_master_sha256':f.manifest_sha256,'source_rocks_sha256':sha256(ROCKS),'source_trees_sha256':sha256(TREES),
        'paving_sha256':sha256(PAVING),'seed':20593,'candidate_count':len(candidates),'coarse_rejected':failures,
        'region':region,'accepted':len(selected),'target_bank_vertices':len(target),'covered_target_vertices':int(covered.sum()),
        'target_surface_coverage_fraction':float(np.mean(covered)),'decor':[x['decor'] for x in selected],
        'checks':[x['report'] for x in selected],'preserves_frozen_height':True,
        'hull_sources':{role:{'path':str(model['hull_source']),'sha256':sha256(model['hull_source']),
            'faces':len(model['faces']),'source_lod0_vertices':len(model['render']),'glb_sha256':sha256(model['source'])} for role,model in world.models.items()}})
    np.savez_compressed(OUT/(stem+'-targets.npz'),xy=target,z=target_z,covered=covered)
    print(json.dumps({'file':str(OUT/(stem+'.json')),'pieces':len(selected),'coverage':float(covered.mean()),'valid_candidates':len(proposals)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pilot',action='store_true');p.add_argument('--region',choices=['bank','ridge'],default='bank');args=p.parse_args();generate(args.pilot,args.region)
