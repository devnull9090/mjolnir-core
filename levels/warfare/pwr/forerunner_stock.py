"""Detailed shipped buttresses and matching native collision for PWR bases.

Only asset references and assembly rules are authored here. Geometry is read
from the user's installed game into the local build cache. Unreal decoration
and HEK collision use the same transforms, including the asset's offset pivot.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'tools/level'))
from b30_collision import hull_of,rotator_matrix

PILLAR='/Game/Env/HS/FR/ACR/Canyon_B_Ziggurat/FR_ACR_Ext_Canyon_B_Ziggurat_Pillar_w10_d40_h62_A/SM_FR_ACR_Ext_Canyon_B_Ziggurat_Pillar_w10_d40_h62_A'


def placements(geometry):
    palette=json.loads((HERE/'asset-palette-v3.json').read_text())
    entry=next(a for a in palette['architecture'] if a['mesh']==PILLAR)
    lo=np.asarray(entry['bounds_cm']['min']);hi=np.asarray(entry['bounds_cm']['max'])
    anchor=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
    output=[]
    for site in geometry['sites']:
        if site['role'] not in ('permanent_base','dominant_northern_citadel'):continue
        factor=1.45 if site['role']=='dominant_northern_citadel' else 1.0
        heading=site.get('heading_degrees',0)
        centre=np.asarray(site['position_m'],dtype=float)
        for index,angle in enumerate((0,120,240)):
            a=math.radians(angle);h=math.radians(heading)
            local=np.array([-math.sin(a)*1.5,20+math.cos(a)*1.5,.35])*factor
            x=local[0]*math.cos(h)-local[1]*math.sin(h)
            y=local[0]*math.sin(h)+local[1]*math.cos(h)
            target=(centre+np.array([x,y,local[2]]))*np.array([100,-100,100])
            yaw=-(heading+angle);scale=factor*1.12
            transform=rotator_matrix(0,yaw,0)
            origin=target-(anchor*scale)@transform
            output.append({'id':site['id']+'_stock_buttress_'+str(index),
                           'mesh':PILLAR+'.'+PILLAR.rsplit('/',1)[1],
                           'pos':origin.tolist(),'rot':[0,yaw,0],'scale':[scale]*3,'static':True})
    return output


def collision_parts(geometry,hull_dir):
    """Closed convex outer hulls; detail seams stay cosmetic, as stock scenery.

    These solid buttresses are behind the open base apron. Do not reuse this
    convex strategy for doors, bridges or any asset with a traversable cavity.
    """
    Path(hull_dir).mkdir(parents=True,exist_ok=True)
    points,faces=hull_of(PILLAR,str(hull_dir),96)
    result=[]
    for item in placements(geometry):
        matrix=rotator_matrix(*item['rot'])
        world=(points*np.asarray(item['scale']))@matrix+np.asarray(item['pos'])
        authoring=world*np.array([.01,-.01,.01])
        result.append({'name':item['id']+'_collision','vertices_m':authoring.tolist(),
                       'faces':[tuple(reversed(f)) for f in faces],
                       'collision':True,'material':'clip','module':'stock_buttress_hull'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geometry',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--hulls',type=Path)
    a=p.parse_args();geo=json.loads(a.geometry.read_text());a.out.parent.mkdir(parents=True,exist_ok=True)
    decor=placements(geo)
    a.out.write_text(json.dumps({'schema_version':1,'coordinates':'unreal_centimetres','decor':decor},indent=2)+'\n')
    report={'decor_instances':len(decor),'unique_meshes':len({x['mesh'] for x in decor})}
    if a.hulls:
        parts=collision_parts(geo,a.hulls)
        report.update(collision_hulls=len(parts),collision_triangles=sum(len(x['faces']) for x in parts))
    print(json.dumps(report))


if __name__=='__main__':main()
