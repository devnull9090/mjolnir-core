# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3", "pillow>=11,<13"]
# ///
"""Seal isolated authored cliff assemblies and preserve unaffected foliage bytes."""
from pathlib import Path
import argparse,copy,json,math,shutil,struct,sys
import numpy as np
from scipy.spatial import ConvexHull,cKDTree
import shapely
from shapely.geometry import shape,Polygon,mapping
from shapely.ops import unary_union
from outcrops_v3 import ROOT,OUT,MASTER,HULLS,TREES,ROCKS,PAVING,World,lod0_points,dump
from heightfield import sha256
import b30_collision,pcg_foliage
from collections import Counter

MATERIAL={'parent':'/Game/MJOLNIR/CETrial/M_CE_PWRRock.M_CE_PWRRock',
 'textures':{'RockD':'/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D.T_Rock_Jagged_udemcebew_NSVT_D',
             'RockN':'/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N.T_Rock_Jagged_udemcebew_NSVT_N'},
 'vectors':{'RockTint':[.8,.83,.84,1],'RockParams':[650,.85,.75,0]}}

def filtered_tree_metadata(source,result):
    """Describe the retained UE-PCG records without claiming another PCG run."""
    rows=result['instances'];original=source['instances']
    result['selected_count']=len(rows)
    result['selected_by_recipe']=dict(sorted(Counter(x['recipe'] for x in rows).items()))
    result['generator']=source['generator']+' / deterministic structural exclusion (no new PCG run)'
    if source.get('composition'):
        prior=source['composition'];base_count=prior.get('base_count',0)
        base_ids={x['id'] for x in original[:base_count]}
        retained_base=sum(x['id'] in base_ids for x in rows)
        result['composition']={'schema':'pwr-pcg-filtered-union-v1','source':str(TREES),
            'source_sha256':sha256(TREES),'source_composition':copy.deepcopy(prior),
            'source_selected_count':len(original),'retained_base_count':retained_base,
            'retained_infill_count':len(rows)-retained_base,'retained_records_exact':True}
    result.setdefault('structural_exclusion',{}).update(source_selected_count=len(original),
        selected_count=len(rows),removed_count=len(original)-len(rows),post_pcg_filter=True,new_pcg_run=False)
    return result

def scree(world,bank):
    f=world.field;rng=np.random.default_rng(20594)
    roles=[]
    for letter in 'ABC':
        leaf='SM_Rock_Glacial_Med_'+letter;path=HULLS/(leaf+'.json');hull=json.loads(path.read_text())
        glb=OUT/'assets'/(leaf+'.glb')
        model={'leaf':leaf,'mesh':hull['mesh'],'points':np.array(hull['points'])/100,'faces':np.array(hull['faces']),
               'render':lod0_points(glb)/100,'source':glb,'hull_source':path}
        world.models['scree_'+letter]=model;roles.append('scree_'+letter)
    h=f.heights_m;yy,xx=np.indices(h.shape)
    allowed=(world.water_distance>5)&(world.water_distance<24)&(h>55)&(h<90)&(world.road_distance>12)&(world.base_distance>15)
    xy=np.c_[xx[allowed],yy[allowed]]*world.s+f.origin_m
    centres=np.array([[r['pos'][0]/100,-r['pos'][1]/100] for r in bank['decor']])
    xy=xy[cKDTree(centres).query(xy)[0]<55]
    xy=xy[rng.permutation(len(xy))];selected=[];used=[]
    for index,at in enumerate(xy[:4000]):
        if len(selected)>=135:break
        if used and cKDTree(used).query(at)[0]<rng.uniform(3.0,6.0):continue
        role=roles[index%3];model=world.models[role]
        scale=rng.uniform(.6,1.5,3);scale[2]*=.7
        row={'id':f'pwr_scree_{index:04d}','mesh':model['mesh'],'pos':[at[0]*100,-at[1]*100,0.],
             'rot':[rng.uniform(-18,18),rng.uniform(-180,180),rng.uniform(-18,18)],'scale':scale.tolist(),'static':True}
        points=world.transform(model,row);bottom=points[points[:,2]<=np.quantile(points[:,2],.18)]
        row['pos'][2]=float(np.min(world.ground(bottom)-bottom[:,2])-rng.uniform(.25,.7))*100
        report=world.validate(model,row,minimum_exposure=.5)
        if report is None:continue
        report=world.validate(model,row,full=True,minimum_exposure=.5)
        if report is None:continue
        report.update(id=row['id'],role=role);selected.append({'decor':row,'report':report});used.append(at)
    return selected

def placed(world,row):
    model=next(m for m in world.models.values() if m['mesh']==row['mesh'])
    return model,world.transform(model,row)

def hull_polygons(world,decor):
    result=[]
    for row in decor:
        model,p=placed(world,row);q=ConvexHull(p[:,:2]);result.append(Polygon(p[q.vertices,:2]))
    return result

def inside_at_height(world,decor,xyz,margin=.65):
    """Finite convex occupancy at actual root height, not whole-canopy circles."""
    inside=np.zeros(len(xyz),bool)
    for row in decor:
        model,p=placed(world,row);ids=np.flatnonzero(~inside&np.all(xyz>=p.min(0)-margin,axis=1)&np.all(xyz<=p.max(0)+margin,axis=1))
        if not len(ids):continue
        # Refit the transformed points so mirrored authoring coordinates do not
        # accidentally invert every source hull normal.
        q=ConvexHull(p)
        inside[ids]=np.all(xyz[ids]@q.equations[:,:3].T+q.equations[:,3]<=margin,axis=1)
    return inside

def geometry_audit(world,decor):
    total=0;largest=0.;smallest=math.inf;reports=[];features=[]
    for row in decor:
        model,p=placed(world,row);faces=model['faces']
        # Same CE world-unit round4 and f32 storage as b30 and the compiler.
        stored=np.round(p/3.048,4).astype('<f4').astype(float)*3.048
        delta=float(np.linalg.norm(stored-p,axis=1).max());largest=max(largest,delta)
        tri=stored[faces];area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
        if np.min(area)<=1e-9:raise ValueError('Collapsed serialized native facet: '+row['id'])
        smallest=min(smallest,float(area.min()));total+=len(faces)
        reports.append({'id':row['id'],'faces':len(faces),'maximum_corresponding_vertex_shift_m':delta,'minimum_finite_triangle_area_m2':float(area.min())})
        q=ConvexHull(p[:,:2]);features.append({'type':'Feature','properties':{'id':row['id'],'mesh':row['mesh']},'geometry':mapping(Polygon(p[q.vertices,:2]))})
    if 601193+total>800000:raise ValueError(f'Native ceiling exceeded before tree removals: {601193+total}')
    dump(OUT/'footprints.geojson',{'type':'FeatureCollection','features':features})
    return {'additional_hull_triangles':total,'prior_compiled_surfaces':601193,'conservative_total_before_tree_removals':601193+total,
            'maximum_corresponding_vertex_shift_m':largest,'minimum_finite_triangle_area_m2':smallest,
            'claim':'Corresponding finite geometry displacement, not infinite halfspace containment; actual compiler/live proof pending','objects':reports}

def foliage(world,decor):
    paving=unary_union([shape(x['geometry']) for x in json.loads(PAVING.read_text())['features']]).buffer(.75)
    tree_doc=json.loads(TREES.read_text());trees=tree_doc['instances'];xyz=np.array([x['position'] for x in trees],float)
    # Test a short trunk segment, preserving harmless crown overhangs.
    hit=np.zeros(len(trees),bool)
    for dz in (0.,1.,2.,3.):hit|=inside_at_height(world,decor,xyz+[0,0,dz],.75)
    paving_hit=shapely.intersects_xy(paving,xyz[:,0],xyz[:,1]);remove=hit|paving_hit
    result=copy.deepcopy(tree_doc);result['instances']=[x for i,x in enumerate(trees) if not remove[i]]
    result['structural_exclusion']={'source_sha256':sha256(TREES),'paving_sha256':sha256(PAVING),'root_buffer_m':.75,
        'new_decor_sha256':sha256(OUT/'outcrops.authored-decor.json'),'retained_records_exact':True}
    filtered_tree_metadata(tree_doc,result)
    dump(OUT/'trees.selected.json',result)
    tree_report={'input':len(trees),'retained':len(result['instances']),'removed':int(remove.sum()),'paving_roots':int(paving_hit.sum()),
       'new_rock_trunks':int(hit.sum()),'removed_ids':[x['id'] for i,x in enumerate(trees) if remove[i]],'retained_records_exact':True}
    source=ROOT/'out/pwr/visual-v5/outcrops-v2/grass/foliage.json';spec,groups=pcg_foliage.read_mjf_groups(source)
    output=OUT/'grass';output.mkdir(exist_ok=True);kept=[];reports=[]
    for i,(group,payload,sidecars,n) in enumerate(groups,1):
        xf=np.frombuffer(sidecars['xf'],dtype='<f4').reshape(n,10);xyz=xf[:,:3].astype(float)*[.01,-.01,.01]
        hit=inside_at_height(world,decor,xyz+[0,0,.15],.65)
        paving_hit=shapely.intersects_xy(paving,xyz[:,0],xyz[:,1]);keep=~(hit|paving_hit);count=int(keep.sum())
        records=np.frombuffer(payload[4:],dtype=np.dtype((np.void,19)))
        filtered={suffix:np.frombuffer(value,dtype=np.dtype((np.void,40 if suffix=='xf' else 16)))[keep].tobytes() for suffix,value in sidecars.items()}
        kept.append((group,struct.pack('<I',count)+records[keep].tobytes(),filtered,count))
        reports.append({'group':i,'input':n,'retained':count,'removed':n-count,'paving':int(paving_hit.sum()),'new_rock':int(hit.sum())})
    binary=output/'foliage.bin';binary.write_bytes(b'MJF3'+struct.pack('<II',3,len(kept))+b''.join(row[1] for row in kept))
    for i,(_,_,sidecars,_) in enumerate(kept,1):
        for suffix,data in sidecars.items():Path(str(binary)+'.'+suffix+str(i)).write_bytes(data)
    dump(output/'foliage.json',{'file':'foliage.bin','groups':[row[0] for row in kept]});pcg_foliage.read_mjf_groups(output/'foliage.json')
    receipt={'runtime_master_sha256':world.field.manifest_sha256,'paving_sha256':sha256(PAVING),'trees':tree_report,
       'grass':{'source_sha256':sha256(source),'input':sum(x['input'] for x in reports),'retained':sum(x['retained'] for x in reports),'groups':reports,'retained_transform_bytes_exact':True}}
    dump(OUT/'foliage-exclusion.receipt.json',receipt);return receipt

def main():
    world=World();bank=json.loads((OUT/'bank.json').read_text());ridge=json.loads((OUT/'ridge.json').read_text())
    for source in (bank,ridge):assert source['runtime_master_sha256']==world.field.manifest_sha256 and source['paving_sha256']==sha256(PAVING)
    small=scree(world,bank);decor=bank['decor']+ridge['decor']+[x['decor'] for x in small]
    for row in decor:row['materials']=[copy.deepcopy(MATERIAL)]
    assert len({x['id'] for x in decor})==len(decor)
    provenance={'frozen_runtime_master_sha256':world.field.manifest_sha256,'generation':'Deterministic authored geological assembly; no UE PCG claim',
        'paving_sha256':sha256(PAVING),'source_rocks_sha256':sha256(ROCKS),'source_trees_sha256':sha256(TREES),
        'bank_sha256':sha256(OUT/'bank.json'),'ridge_sha256':sha256(OUT/'ridge.json'),'material_pending_shared_cook_and_live_review':True}
    dump(OUT/'scree.json',{'decor':[x['decor'] for x in small],'checks':[x['report'] for x in small]})
    dump(OUT/'outcrops.authored-decor.json',{'schema_version':1,'coordinates':'unreal_centimetres','decor':decor,'visual_v4_provenance':provenance})
    baseline=json.loads(ROCKS.read_text())['decor'];assert len(baseline)==574
    dump(OUT/'rocks-and-outcrops.authored-decor.json',{'schema_version':1,'coordinates':'unreal_centimetres','decor':baseline+decor,'visual_v4_provenance':provenance})
    hull_dir=OUT/'hulls';copied=[]
    for path in HULLS.glob('SM_*.json'):
        if any(token in path.stem for token in ('candidate','round2','default56')):continue
        destination=hull_dir/path.name
        if destination.exists():assert sha256(destination)==sha256(path)
        else:shutil.copy2(path,destination)
        copied.append({'source':str(path),'destination':str(destination),'sha256':sha256(path)})
    dump(hull_dir/'baseline-cache-reuse.receipt.json',{'entries':copied})
    geometry=geometry_audit(world,decor);fol=foliage(world,decor)
    receipt={'runtime_master_sha256':world.field.manifest_sha256,'paving_sha256':sha256(PAVING),'bank_count':len(bank['decor']),
      'ridge_count':len(ridge['decor']),'scree_count':len(small),'new_props':len(decor),'merged_rocks':len(baseline)+len(decor),
      'bank_coverage':bank['target_surface_coverage_fraction'],'geometry':geometry,'foliage':fol,
      'existing574_rock_records_unchanged':True,'height_geometry_layout_unchanged':True,'native_compile_live_acceptance_pending':True}
    dump(OUT/'receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('new_props','merged_rocks','bank_count','ridge_count','scree_count','bank_coverage')}))

if __name__=='__main__':main()
