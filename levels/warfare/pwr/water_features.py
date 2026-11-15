"""Derive restrained stock river spray from the final authored watercourses."""
import math
import numpy as np

SPRAY='/Game/FX/Library/Environment/PNW/Liquids/Splashes/AmbientRiverSplash/NS_PNW_AmbientRiverSplash_01.NS_PNW_AmbientRiverSplash_01'
SPLASH='/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_WaterfallSplash_01.NS_PNW_WaterfallSplash_01'


def falls(geometry):
    result=[]
    for river in geometry['watercourses']:
        line=np.asarray(river['surface_centreline_m'],dtype=float)
        for cascade in river.get('cascades',[]):
            xy=np.asarray(cascade['position_m'])
            index=int(np.argmin(np.linalg.norm(line[:,:2]-xy,axis=1)))
            end=min(len(line)-1,index+max(2,int(cascade['reach_length_m']/4)))
            point=line[end];tangent=line[min(end+1,len(line)-1)]-line[max(0,end-1)]
            yaw=math.degrees(math.atan2(-tangent[1],tangent[0]))
            normal=np.array([-tangent[1],tangent[0]])/max(np.linalg.norm(tangent[:2]),1e-6)
            effects=[]
            for side in (-.25,0,.25):
                pos=point.copy();pos[:2]+=normal*float(river['channel_width_m'])*side;pos[2]+=.15
                effects.append({'system':SPLASH if cascade['drop_m']>5 and side==0 else SPRAY,
                                'pos':(pos*np.array([100,-100,100])).tolist(),
                                'rot':[0,yaw,0],'scale':1.5})
            result.append({'pos':(line[index]*np.array([100,-100,100])).tolist(),
                           'yaw':yaw,'sheet':False,'effects':effects})
    return result
