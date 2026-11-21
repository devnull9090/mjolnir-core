"""Trace the approved Warthog view onto survey stations on the native road."""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.spatial import cKDTree


REFERENCE_SIZE=np.array([1672,941])
# Knots follow the centres of the traffic paths, shoulder break and primary glint.
TRACE={
    "left": [(470,925),(480,840),(570,640),(650,555),(766,500),(939,479),(1130,460),(1228,453)],
    "right": [(1565,925),(1510,840),(1360,640),(1190,550),(1085,490),(1166,469),(1250,454)],
    "duff_edge": [(250,925),(270,840),(326,740),(427,640),(514,566),(632,523),(792,490)],
    "median": [(986,914),(944,840),(885,675),(871,580),(910,518),(1002,488),(1153,463)],
    "glint": [(905,776)],
}


def trace(field,pose,line,stations):
    eye=np.asarray(pose[:3])*[.01,-.01,.01]
    p,y,f=np.radians(pose[3:6])
    heading=np.array([np.cos(y),-np.sin(y)])
    forward=np.r_[heading*np.cos(p),np.sin(p)]
    right=np.array([-np.sin(y),-np.cos(y),0.])
    up=np.r_[-heading*np.sin(p),np.cos(p)]
    lens=np.tan(f/2)
    tree=cKDTree(line)
    result={}
    for name,landmarks in TRACE.items():
        entries=[]
        for point in landmarks:
            u,v=point/REFERENCE_SIZE
            ray=forward+(u-.5)*2*lens*right+(.5-v)*2*lens*(9/16)*up
            depth=np.arange(.1,180.2,.2)
            xyz=eye+depth[:,None]*ray
            hits=np.flatnonzero(xyz[:,2]<=field.sample(xyz[:,0],xyz[:,1],bounds_error=False))
            if not len(hits):
                entries.append(dict(pixel=list(point),uv=[u,v],terrain_hit=False))
                continue
            high=depth[hits[0]]
            low=max(.01,high-.2)
            for _ in range(17):
                mid=(low+high)/2
                x,y,z=eye+ray*mid
                if z<=field.sample(x,y): high=mid
                else: low=mid
            xyz=eye+ray*high
            _,idx=tree.query(xyz[:2])
            i=min(max(idx,1),len(line)-2)
            tangent=line[i+1]-line[i-1]; tangent/=np.linalg.norm(tangent)
            normal=np.array([-tangent[1],tangent[0]])
            delta=xyz[:2]-line[i]
            side=float(delta@normal)
            station=float(stations[i]+delta@tangent)
            entries.append(dict(pixel=list(point),uv=[round(u,5),round(v,5)],terrain_hit=True,
                                xyz_m=xyz.round(3).tolist(),station_m=round(station,3),side_m=round(side,3)))
        result[name]=entries
    return result


def fit_station_curve(query,marks,base,limit):
    # Distant image pixels can project well beyond the 24 m surveyed road, or
    # hit the mountains. Only fit the accessible arc and return to its grade.
    knots=sorted((e["station_m"],e["side_m"]) for e in marks if e["terrain_hit"] and 63<e["station_m"]<154 and abs(e["side_m"])<limit)
    if len(knots)<3: raise ValueError("Too few usable terrain landmarks")
    d,v=np.array(knots).T
    x=np.r_[0,d[0]-24,d[0]-9,d,d[-1]+9,d[-1]+24,max(float(np.max(query))+1,d[-1]+25)]
    y=np.r_[base,base,(base+v[0])/2,v,(base+v[-1])/2,base,base]
    return PchipInterpolator(x,y)(query)

def traffic_lanes(station, marks):
    """The two wheel centres on the safe, surveyed graded arc (metres)."""
    left = fit_station_curve(station, marks["left"], -2.86, 16.25)
    right = fit_station_curve(station, marks["right"], 2.43, 16.25)
    centre = (left + right) * .5
    half = np.clip((right - left) * .5, 1.65, 3.8)
    return centre - half, centre + half


def graded_apex(station, side, left, right):
    """Road clearance across the S-bend, with a feathered outer apron."""
    def transition(lo, hi, x):
        u = np.clip((x-lo)/(hi-lo), 0., 1.)
        return u*u*(3-2*u)
    arc = transition(53., 66., station) * (1-transition(102., 117., station))
    outside = np.maximum(left - side, side - right)
    # Nearest-station field texels are half a metre apart. Leave enough
    # shoulder at the S apex for bilinear filtering across its curved edge.
    return arc * (1-transition(2.0, 3.45, outside))

# Local pockets of washed chips and dry litter on the two shoulders. Offsets
# are metres out from the corresponding fitted wheel centre.
SHOULDER_POCKETS = {
    "left": ((96.,.95),(104.6,1.4),(112.9,.85),(117.1,1.8),(121.7,1.25),
             (126.5,1.3),(129.45,.9),(132.8,1.8)),
    "right": ((85.3,1.1),(93.1,1.25),(100.2,1.5),(104.9,1.9),(109.6,.85),
              (114.7,1.4),(118.9,1.1),(124.15,1.9),(128.2,1.1)),
}

# Surveyed low water patches: station, lateral offset, longitudinal and
# transverse half-width, angled crossfall, fine-earth taper, reflective cover.
SHALLOW_WASH = (
    (128.58,-.736,.64,.37,.24,-.9,.85),
    (121.27,-1.48,1.28,.36,.46,1.,.69),
    (117.80,.42,.72,.39,-.44,-1.,.62),
    (114.70,-.63,.81,.26,-.61,1.,.43),
    (108.25,3.06,1.17,.40,.78,1.,.62),
    (104.65,5.24,.82,.30,-.75,-1.,.53),
    (99.93,7.02,.70,.26,.22,1.,.40),
    (141.9,.90,1.18,.53,.20,1.,.68),
    (154.1,-1.30,.97,.48,-.23,-1.,.65),
)
