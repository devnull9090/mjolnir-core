"""Restrained shipped Forerunner details, isolated from the frozen PWR world.

Creates a reviewable placement proposal first. --export additionally writes
authored-decor.json and native-collision-extra.json after clearance checks.
No game, Blender, terrain, scenario, or upgrade configuration is changed.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import MultiPoint, Point, Polygon, box

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
sys.path.insert(0,str(REPO/'tools/level'))
from b30_collision import glb_positions,rotator_matrix
from heightfield import load_heightfield,sha256
from world_placements import placements as gameplay_placements

ASSET_NAMES={
    'cover':'SM_FR_ACR_Ext_Canyon_A_Bridge_A_Pillar_w8_d3_h3_A',
    'threshold':'SM_FR_ACR_Ext_Canyon_A_Bridge_A_Pillar_w1i5_d6_h4_A',
    'bay_wall':'SM_FR_ACR_Int_Canyon_A_SmallRoom_Wall_w9_d1_h5_A',
    'rib':'SM_FR_ACR_Int_Canyon_A_SmallRoom_Pillar_w2_d0i5_h5i5_A',
}

def palette_from(candidates):
    return {role:next(row for row in candidates if row['path'].rsplit('/',1)[-1].split('.')[0]==name)
            for role,name in ASSET_NAMES.items()}

def prepare_palette(source,cache,cli,paks):
    cache.mkdir(parents=True,exist_ok=True)
    document=json.loads(source.read_text())
    entries=document if isinstance(document,list) else document['assets']
    for entry in entries:
        name=entry['path'].rsplit('/',1)[-1].split('.')[0]
        glb=cache/(name+'.glb')
        if not glb.is_file():
            subprocess.run([str(cli),'mesh','export','--paks',str(paks),'--asset',name,'--out',str(glb)],check=True)
        entry['glb']=str(glb.resolve())
    return palette_from(entries)

def local_hull(entry):
    """Exact convex hull of the existing collision reader's selected native LOD.

    All four candidates are compact solid trim/cover, without a traversable
    opening. This must not be reused for doorframes or complete rooms.
    glb_positions explicitly restores Unreal centimetres from CE export units.
    """
    points=np.unique(glb_positions(entry['glb']),axis=0)
    error=max(np.max(np.abs(points.min(0)-entry['min'])),np.max(np.abs(points.max(0)-entry['max'])))
    if error>5:raise ValueError(f"Shipped bounds changed by {error}cm: {entry['path']}")
    hull=ConvexHull(points)
    used=np.unique(hull.simplices);remap={int(old):new for new,old in enumerate(used)}
    faces=[]
    for face,plane in zip(hull.simplices,hull.equations):
        face=list(map(int,face))
        a,b,c=points[face]
        if np.dot(np.cross(b-a,c-a),plane[:3])<0:face[1],face[2]=face[2],face[1]
        faces.append([remap[i] for i in face])
    return points[used],np.asarray(faces,dtype=np.int64)

def build(geometry,field,palette):
    hulls={role:local_hull(entry) for role,entry in palette.items()}
    output=[]
    for site in geometry['sites']:
        if site['role'] not in ('permanent_base','dominant_northern_citadel'):continue
        factor=1.45 if site['role']=='dominant_northern_citadel' else 1.0
        centre=np.asarray(site['position_m']);heading=site.get('heading_degrees',0)
        h=math.radians(heading);rotation=np.array([[math.cos(h),math.sin(h)],[-math.sin(h),math.cos(h)]])
        rules=[]
        for arm,angle in enumerate((0,120,240)):
            a=math.radians(angle)
            for side in (-1,1):
                x,y=side*11.35,47
                rules.append(('rib',f'wing{arm}_{side}',(x*math.cos(a)-y*math.sin(a),20+x*math.sin(a)+y*math.cos(a)),angle+side*90,1.1))
                # Patterned native wall panels sit against the closed wing
                # sides, adding readable relief without occupying the apron.
                x,y=side*11.3,35
                rules.append(('bay_wall',f'wing_panel{arm}_{side}',(x*math.cos(a)-y*math.sin(a),20+x*math.sin(a)+y*math.cos(a)),angle+side*90,1.35))
        for side in (-1,1):
            rules += [('cover',f'cover_{side}_{y}',(side*62,y),0,.65) for y in (-29,28)]
            rules += [('bay_wall',f'bay_{side}',(side*62,-52),side*90,.85),
                      ('threshold',f'threshold_{side}',(side*22,-90),0,.9)]
        for role,label,local_xy,angle,size in rules:
            entry=palette[role];lo=np.asarray(entry['min']);hi=np.asarray(entry['max'])
            anchor=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
            xy=centre[:2]+(np.asarray(local_xy)*factor)@rotation
            floor=centre[2]+.35*factor if np.linalg.norm(local_xy)<75 else float(field.sample(*xy))
            # Tiny embed avoids a visible gap without lifting any gameplay floor.
            target=np.array([xy[0]*100,-xy[1]*100,(floor-.035)*100])
            yaw=-(heading+angle);scale=factor*size;matrix=rotator_matrix(0,yaw,0)
            origin=target-(anchor*scale)@matrix
            points,faces=hulls[role];world=(points*scale)@matrix+origin
            authoring=world*np.array([.01,-.01,.01])
            decor={'id':site['id']+'_detail_'+label,'mesh':entry['path'],
                   'pos':origin.tolist(),'rot':[0,yaw,0],'scale':[scale]*3,'static':True}
            output.append({'decor':decor,'role':role,'site':site['id'],'anchor_local_m':list(local_xy),
                           'anchor_world_m':[xy[0],xy[1],floor-.035],
                           'bounds_m':{'min':authoring.min(0).tolist(),'max':authoring.max(0).tolist()},
                           'vertices_m':authoring.tolist(),'faces':faces[:,[0,2,1]].tolist()})
    return output,hulls

def clearance(items,layout,geometry,field):
    sites={s['id']:s for s in geometry['sites']}
    gameplay=gameplay_placements(layout,geometry,field)
    checks=[];failures=[]
    protected=[]
    for team,points in layout['spawns_m'].items():
        protected.extend((f'{team}_spawn_{i}',p,4) for i,p in enumerate(points))
    for i,item in enumerate(gameplay['vehicles']):
        radius=10 if 'scorpion' in item['tag'] else 8 if 'banshee' in item['tag'] else 7
        protected.append((f'vehicle_{i}',item['position_m'],radius))
    for i,p in enumerate(layout['captures_m']):protected.append((f'capture_{i}',p,20))
    protected.append(('warmup',layout['warmup_m'],5))
    for item in items:
        pts=np.asarray(item['vertices_m']);foot=MultiPoint(pts[:,:2]).convex_hull
        closest=min(((foot.distance(Point(p[:2]))-radius,name,radius) for name,p,radius in protected),key=lambda v:v[0])
        site=sites[item['site']];factor=1.45 if site['role']=='dominant_northern_citadel' else 1
        cx,cy=site['position_m'][:2]
        # Existing sites have heading zero. Refuse a future rotated layout
        # until its protected approach is rotated by the same transform.
        if site.get('heading_degrees',0)!=0:raise ValueError('approach clearance needs heading-zero sites')
        corridor=box(cx-18*factor,cy-110*factor,cx+18*factor,cy-25*factor)
        approach_overlap=foot.intersection(corridor).area
        road_overlap=0.0
        for road in geometry['roads']:
            sections=np.asarray(road['cross_sections_m'])
            for a,b in zip(sections[:-1],sections[1:]):
                lane=Polygon([a[1,:2],a[3,:2],b[3,:2],b[1,:2]])
                if lane.is_valid:road_overlap+=foot.intersection(lane).area
        check={'id':item['decor']['id'],'nearest_reserved':closest[1],
               'clearance_beyond_required_m':float(closest[0]),'reserved_radius_m':closest[2],
               'approach_overlap_m2':float(approach_overlap),'road_lane_overlap_m2':float(road_overlap)}
        checks.append(check)
        if closest[0]<0 or approach_overlap>1e-6 or road_overlap>1e-6:failures.append(check)
    return {'schema':'pwr-base-details-clearance-v1','instances':len(items),'checks':checks,'failures':failures,
            'minimum_clearance_beyond_required_m':min(c['clearance_beyond_required_m'] for c in checks),
            'scope':'Offline convex footprint versus unchanged spawn/vehicle/capture/warmup buffers, 36m approach and authored 24m road lanes; live traversal remains required.'}

def validate_hulls(items):
    results=[]
    for item in items:
        points=np.asarray(item['vertices_m']);faces=np.asarray(item['faces'])
        edges={}
        for face in faces:
            for a,b in zip(face,np.roll(face,-1)):
                edge=tuple(sorted((int(a),int(b))));edges[edge]=edges.get(edge,0)+1
        centered=points-points.mean(0);tri=centered[faces]
        volume=float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6)
        if any(count!=2 for count in edges.values()) or volume<=0:
            raise ValueError('Nonmanifold or inward native hull: '+item['decor']['id'])
        results.append({'id':item['decor']['id'],'triangles':len(faces),'closed':True,'outward_volume_m3':volume})
    return results

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=REPO/'out/pwr/visual-v4/base-details')
    ap.add_argument('--palette',type=Path,default=HERE/'base-details-palette-v4.json')
    ap.add_argument('--cli',type=Path,default=REPO/'target/release/mjolnir.exe')
    ap.add_argument('--paks',type=Path,default=Path(os.environ.get('HCE_PAKS','C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks')))
    ap.add_argument('--geometry',type=Path,default=HERE/'terrain/final-v3/terrain.geometry.json')
    ap.add_argument('--heightfield',type=Path,default=HERE/'terrain/runtime-v3/runtime-master.json')
    ap.add_argument('--layout',type=Path,default=HERE/'layout.json')
    ap.add_argument('--export',action='store_true')
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    geometry=json.loads(args.geometry.read_text());layout=json.loads(args.layout.read_text());field=load_heightfield(args.heightfield)
    palette=prepare_palette(args.palette,args.out,args.cli,args.paks);items,hulls=build(geometry,field,palette)
    hull_validation=validate_hulls(items)
    report=clearance(items,layout,geometry,field)
    provenance={'layout_sha256':sha256(args.layout),'geometry_sha256':sha256(args.geometry),
                'master_manifest_sha256':field.manifest_sha256,
                'assets':{k:{'mesh':v['path'],'glb_sha256':sha256(v['glb']),'bounds_cm':{'min':v['min'],'max':v['max']}}
                          for k,v in palette.items()}}
    proposal={'schema':'pwr-base-details-v1','provenance':provenance,'palette':palette,'items':items,
              'instances':len(items),'triangles':sum(len(x['faces']) for x in items),'clearance':report,
              'hull_validation':hull_validation,'status':'Independent reusable detail pass; not integrated or live-tested.'}
    (args.out/'proposal.json').write_text(json.dumps(proposal,indent=2)+'\n')
    (args.out/'clearance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'instances':len(items),'collision_triangles':proposal['triangles'],
                      'clearance_failures':len(report['failures']),'minimum_clearance_margin_m':report['minimum_clearance_beyond_required_m']}))
    if report['failures']:raise ValueError('Base detail clearance failed; inspect clearance.json')
    if args.export:
        (args.out/'authored-decor.json').write_text(json.dumps({'schema_version':1,'coordinates':'unreal_centimetres',
            'provenance':provenance,'decor':[x['decor'] for x in items]},indent=2)+'\n')
        triangles=[(np.asarray(item['vertices_m'])[face]/3.048).tolist() for item in items for face in item['faces']]
        (args.out/'native-collision-extra.json').write_text(json.dumps({'schema':'pwr-base-details-collision-v1',
            'coordinates':'ce_world_units_z_up','provenance':provenance,'triangles':triangles,
            'materials':['hard_metal_thick']*len(triangles),'objects':len(items)})+'\n')

if __name__=='__main__':main()
