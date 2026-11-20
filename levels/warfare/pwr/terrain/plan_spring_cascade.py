"""Build the two spring spills and their aerated toe in registered world metres."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield

CONFIG = Path(__file__).with_name("northern-headwaters.json")
TERRAIN = ROOT / "out/pwr/river-basin/terrain/runtime-master.json"
WORK = ROOT / "out/pwr/river-riparian/cascade"
# The first row grows out of the narrow headwater channel. The falling sheets
# narrow at their lips and fan out at their toes. End below the lake's surface.
# Columns are horizontal chainage, water elevation and full wetted width (m).
PROFILE = np.array([
    [-1.8,150.10,2.30], [0,150.04,2.85], [2.8,149.84,3.75],
    [4.35,149.67,3.88], [4.9,149.42,3.94], [5.5,148.67,4.12],
    [6.05,147.94,4.34], [6.65,147.71,4.55], [7.7,147.47,4.48],
    [9.1,147.01,4.07], [10.85,146.72,4.53], [12.1,146.58,4.96],
    [13.60,146.41,5.53], [14.35,146.11,5.84], [15.15,145.41,6.22],
    [16.05,144.08,6.69], [16.62,143.09,6.92], [17.25,142.68,7.16],
    [18.15,142.52,7.08], [19.45,142.46,6.34], [21.4,142.40,5.46],
    [23.8,142.34,4.05], [26.45,142.30,3.00], [28.0,142.25,2.30],
])
ORIGIN = np.array([-396.,973.,146.])
WORLD_TO_UE = np.array([100.,-100.,100.])


def write(path, data):
    path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(t):
    t = np.clip(t, 0., 1.)
    return t*t*(3.-2.*t)


def clip_ground_faces(triangle):
    """Clip a decorative face in native grid coordinates against terrain edges."""
    def clip(poly,axis,bound):
        if not len(poly):
            return []
        out=[]
        for a,b in zip(poly,[*poly[1:],poly[0]]):
            va=a[:2]@axis-bound; vb=b[:2]@axis-bound
            if va>=0:
                out.append(a)
            if (va>0 and vb<0) or (va<0 and vb>0):
                out.append(a+(b-a)*(va/(va-vb)))
        return out
    low=np.floor(triangle[:,:2].min(axis=0)).astype(int)
    high=np.floor(triangle[:,:2].max(axis=0)).astype(int)
    for i in range(low[0],high[0]+1):
        for j in range(low[1],high[1]+1):
            poly=list(triangle)
            for axis,offset in (([1,0],i),([-1,0],-i-1),([0,1],j),([0,-1],-j-1)):
                poly=clip(poly,axis,offset)
            for polygon in (clip(poly,[1,1],i+j+1),clip(poly,[-1,-1],-i-j-1)):
                for k in range(1,len(polygon)-1):
                    tri=np.asarray([polygon[0],polygon[k],polygon[k+1]])
                    area=np.linalg.det(tri[1:,:2]-tri[0,:2])
                    if abs(area)>1e-8:
                        yield tri if area<0 else tri[::-1]


def project(world, eye=(-273.,785.,152.), pitch=-4.5376, yaw=-122.9694, fov=73):
    t, y = np.deg2rad([pitch,yaw])
    fxy = np.array([np.cos(y),-np.sin(y)])
    fwd = np.r_[fxy*np.cos(t),np.sin(t)]
    up = np.r_[-fxy*np.sin(t),np.cos(t)]
    right = np.array([-np.sin(y),-np.cos(y),0.])
    d = world-eye
    k = 800./np.tan(np.deg2rad(fov/2))
    return np.c_[800.+k*(d@right)/(d@fwd),450.-k*(d@up)/(d@fwd)]


def generate(work):
    work.mkdir(parents=True,exist_ok=True)
    field = load_heightfield(TERRAIN)
    spring = np.asarray(json.loads(CONFIG.read_text())["spring_surface_m"])
    s0 = np.r_[0,np.linalg.norm(np.diff(spring[:,:2],axis=0),axis=1).cumsum()]
    # Extend the surveyed thalweg just into the source and the receiving lake.
    pre = spring[0,:2]+(spring[0,:2]-spring[1,:2])*2/s0[1]
    post = spring[-1,:2]+(spring[-1,:2]-spring[-2,:2])*5/(s0[-1]-s0[-2])
    coords = np.vstack([pre,spring[:,:2],post])
    dist = np.r_[-2.,s0,s0[-1]+5.]
    def line(s):
        return np.array([np.interp(s,dist,coords[:,i]) for i in range(2)])
    def path(s):
        # Symmetric corner rounding keeps the falls' cross-sections aligned.
        return (line(s-.45)+2*line(s)+line(s+.45))/4
    ss = np.unique(np.r_[np.linspace(PROFILE[0,0],PROFILE[-1,0],106),PROFILE[:,0]])
    across = np.linspace(-1.,1.,35)
    mean_direction = spring[-1,:2]-spring[0,:2]
    mean_direction /= np.linalg.norm(mean_direction)
    xyz, uv, flow, faces = [], [], [], []
    for j,s in enumerate(ss):
        center = path(s)
        tangent = path(s+.15)-path(s-.15)
        tangent /= np.linalg.norm(tangent)
        # The stream turns inside its wide bed. Turning wide cross-sections
        # by the full angle of the thalweg would fold their outer corners.
        tangent = .80*mean_direction+.20*tangent
        tangent /= np.linalg.norm(tangent)
        across_xy = np.array([-tangent[1],tangent[0]])
        width = np.interp(s,PROFILE[:,0],PROFILE[:,2])
        for i,t in enumerate(across):
            # Water reaches the lip at different chainages across the ledge.
            # Channels and ribs survive at shore distance without fake spray.
            edge = abs(t)**2
            offset = (1.02*math.sin(4.05*t+.96)+.49*math.sin(7.3*t-.56)+.43*t)*smooth((s+.6)/3)
            shifted = s+offset
            z = np.interp(shifted,PROFILE[:,0],PROFILE[:,1])
            plunge = max(math.exp(-((shifted-5.60)/1.0)**2),math.exp(-((shifted-15.75)/1.54)**2))
            impact = max(math.exp(-((shifted-6.78)/1.0)**2),math.exp(-((shifted-17.9)/1.42)**2))
            plume = smooth((s-16.85)/2.7)
            fold = .105*math.sin(8.6*t+.45*math.sin(s*.46))+.056*math.cos(13.8*t-s*.22)
            z += (fold*plunge+.07*impact*(1-t*t) + .035*(1-edge))*(1-plume)
            ragged = 1+edge*(.10*math.sin(s*.92+t)+.069*math.sin(1.9*s+3.2*t))
            xy = center+across_xy*(t*.5*width*ragged)
            upper = smooth((s-2.6)/1.8)*(1-smooth((s-6.6)/2.6))
            lower = smooth((s-9.4)/3.9)*(1-smooth((s-16.7)/1.85))
            # The shoal parts the lower spill just right of centre; a thinner
            # side rill leaks along its opposite flank. Divert the water right
            # down onto the true stream bed at the exposed mineral seams.
            fissure=upper*math.exp(-((t+.48+.12*math.sin(s*.66))/.13)**2)
            fissure=max(fissure,lower*math.exp(-((t-.07-.19*math.sin(s*.46))/.25)**2))
            fissure=max(fissure,.75*lower*math.exp(-((t+.60-.07*math.cos(s*.8))/.13)**2))
            outer=smooth((abs(t)-.59)/.41)*smooth((s+1)/3)*(1-plume)
            substrate=max(float(field.sample(*xy))+.04,142.42)
            z+=(min(substrate,z)-z)*min(1.,fissure+.62*outer)
            volume=1.-max(fissure, .63*outer)
            xyz.append([*xy, z])
            uv.append([(t+1)*.5,s])
            flow.append([plunge,impact,plume,volume])
            if i and j:
                b=j*len(across)+i; a=b-1; c=b-len(across); d=c-1
                faces.extend(((d,c,b),(d,b,a)))
    water_count=len(xyz)
    sections=[0]*len(faces)
    # These flaking rock outcrops are optically registered to the physical
    # erosion surface. With maximum relief of 45 mm they create no new ledge
    # for a vehicle or foot. Reuse the installed native alpine cliff material.
    rng=np.random.default_rng(1911041)
    strata=[(2.0,-2.05,1.4,.72),(3.7,1.77,1.7,.90),(5.5,-1.50,1.42,.76),
            (5.9,.27,1.33,.60),(7.2,1.75,1.66,.97),(8.9,-1.81,1.85,1.03),
            (10.75,.86,1.65,.92),(12.50,-2.42,1.75,1.11),(12.35,2.15,1.72,1.02),
            (13.85,.27,2.23,1.07),(15.03,-1.75,1.25,.91),(14.94,2.67,2.01,1.32),
            (15.86,-3.06,1.55,1.04),(16.78,1.56,1.62,1.11)]
    across_mean=np.array([-mean_direction[1],mean_direction[0]])
    grid_origin=np.asarray(field.origin_m)
    spacing=np.asarray(field.spacing_m)
    for along,side,radius,width in strata:
        origin=path(along)+across_mean*side
        n=12
        angles=np.arange(n)*2*np.pi/n+rng.uniform(-.12,.12,n)
        rim=np.c_[np.cos(angles),np.sin(angles)]*rng.uniform(.83,1.14,(n,1))
        control=[]; local=[]
        for scale in (0.,.50,1.):
            for x,y in ([(0.,0.)] if scale==0 else rim*scale):
                pt=origin+mean_direction*(x*radius+y*width*.48)+across_mean*(y*width)
                # Submerge patch edges by 8 mm; avoid a rectangular overlay.
                control.append([*((pt-grid_origin)/spacing),.042*(1-scale*scale)-.008*scale**6])
        for k in range(n):
            ix=(k+1)%n
            local.extend([[0,1+k,1+ix],[1+k,1+n+k,1+n+ix],[1+k,1+n+ix,1+ix]])
        control=np.array(control)
        seen={}
        # The native master is piecewise planar. Crossing a native crease with
        # one decorative polygon would bridge the physical support by up to 19 cm.
        for face in local:
            for fragment in clip_ground_faces(control[face]):
                inds=[]
                for pt in fragment:
                    key=tuple(pt.round(8))
                    if key not in seen:
                        seen[key]=len(xyz)
                        xy=grid_origin+pt[:2]*spacing
                        xyz.append([*xy,float(field.sample(*xy))+pt[2]])
                        uv.append((xy*.46).tolist()); flow.append([1,1,1,1])
                    inds.append(seen[key])
                faces.append(inds);sections.append(1)
    xyz=np.asarray(xyz)
    vertices=(xyz-ORIGIN)*WORLD_TO_UE
    faces=np.asarray(faces)
    weighted=np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],vertices[faces[:,2]]-vertices[faces[:,0]])
    if np.median(weighted[:,2])<0:
        faces=faces[:,[0,2,1]]
        weighted=-weighted
    normals=np.zeros_like(vertices)
    for i in range(3):
        np.add.at(normals,faces[:,i],weighted)
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    # Unreal's native mesh builder takes clockwise fronts. Preserve up-facing
    # explicit shading normals when reversing the geometry's mathematical order.
    faces=faces[:,[0,2,1]]
    liquid=xyz[:water_count]
    ground=field.sample(liquid[:,0],liquid[:,1]).reshape(len(ss),len(across))
    center_depth=liquid[:,2].reshape(ground.shape)[:,len(across)//2]-ground[:,len(across)//2]
    if np.min(center_depth[ss>=0])<-.04:
        raise ValueError("Terrain occludes the spring thalweg")
    if not np.isfinite(normals).all() or np.min(weighted[:,2]) < 1e-5:
        raise ValueError("Invalid spring geometry")
    write(work/"surface.json",dict(origin_cm=(WORLD_TO_UE*ORIGIN).tolist(),
          positions=vertices.round(4).tolist(), normals=normals.round(6).tolist(),
          faces=faces.tolist(),sections=sections,uv=np.round(uv,5).tolist(),colors=np.round(flow,5).tolist()))
    main = (np.repeat(ss,len(across))>=0)&(np.repeat(ss,len(across))<=19.45)
    px=project(liquid[main])
    # Look diagonally from the near side of the lake back toward the spring.
    eye=np.array([-381.5,942.0,146.9]); target=np.array([-394.1,971.6,146.25]); delta=target-eye
    pitch=math.degrees(math.atan2(delta[2],np.linalg.norm(delta[:2])))
    yaw=math.degrees(math.atan2(-delta[1],delta[0]))
    proof = dict(surface_sha256=digest(work/"surface.json"), terrain_manifest_sha256=digest(TERRAIN),
        water_level_m=142.4, triangles=len(faces), vertices=len(vertices),
        center_bed_clearance_min_m=round(float(center_depth[ss>=0].min()),3),
        registered_envelope_px=np.vstack([px.min(axis=0),px.max(axis=0)]).round(1).tolist(),
        close_camera=dict(position_cm=(eye*WORLD_TO_UE).tolist(), pitch=round(pitch,4), yaw=round(yaw,4),fov=65),
        physical_changes="Retained native terrain and seated spring rocks. Thin erosion-face relief follows the bed within 45 mm.")
    write(work/"survey.json",proof)
    print(json.dumps(proof,indent=2))


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work",type=Path,default=WORK)
    generate(cli.parse_args().work)

