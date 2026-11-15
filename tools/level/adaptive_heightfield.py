"""Conforming RTIN prototype with measured errors and native table budgets.

This is an open height surface, not a packaged Halo collision BSP. Architecture,
world closure, native packing/ray probes and runtime physics remain separate.
The right-triangle hierarchy follows the RTIN concept described by Evans et al.
and Mapbox Martini: https://github.com/mapbox/martini . This implementation uses
NumPy level-wise propagation and independently audits every source grid vertex
and cell centre; hierarchy thresholds alone are not an accuracy certificate.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import numpy as np
from heightfield import load_heightfield, write_heightfield

def tolerance_grid(field, ground=.5, road=.15, shore=.25, flat=.1, cliff=None):
    result=np.full(field.heights_m.shape,ground,dtype=float)
    if cliff is not None:
        if "walkable" not in field.masks:raise ValueError("Cliff tolerance requires an explicit walkable mask")
        result=np.where(field.masks["walkable"]>.01,ground,cliff)
    for name,target in (("road",road),("shore",shore),("flat",flat),("bases",flat)):
        mask=field.masks.get(name)
        if mask is not None:
            # Any marked sample has the stricter tolerance; soft mask fringes
            # must not silently turn into a lower collision standard.
            result=np.where(mask>.01,np.minimum(result,target),result)
    if min(ground,road,shore)<=0: raise ValueError("Positive error tolerances required")
    return result

class Rtin:
    def __init__(self, heights, tolerances, forced_vertices=None):
        self.heights=np.asarray(heights,dtype=float)
        if heights.shape!=tolerances.shape or heights.ndim!=2 or heights.shape[0]!=heights.shape[1]:
            raise ValueError("RTIN requires matching square height/tolerance grids")
        self.n=heights.shape[0]-1
        n=self.n
        if n<2 or n&(n-1): raise ValueError("RTIN grid must be 2^k+1 samples per axis")
        # Each node is A,B,C with AB the hypotenuse. Children share midpoint M.
        roots=np.array([[0,0,n,n,n,0],[n,n,0,0,0,n]],dtype=np.int32)
        self.roots=roots
        levels=[];current=roots
        while abs(int(current[0,0])-int(current[0,4]))+abs(int(current[0,1])-int(current[0,5]))>1:
            levels.append(current)
            a=current[:,:2];b=current[:,2:4];c=current[:,4:];m=(a+b)//2
            children=np.empty((len(current)*2,6),dtype=np.int32)
            children[::2]=np.concatenate((c,a,m),axis=1)
            children[1::2]=np.concatenate((b,c,m),axis=1)
            current=children
        del current
        errors=np.zeros_like(self.heights)
        for nodes in reversed(levels):
            a=nodes[:,:2];b=nodes[:,2:4];c=nodes[:,4:];m=(a+b)//2
            raw=np.abs(self.heights[m[:,1],m[:,0]]-(self.heights[a[:,1],a[:,0]]+self.heights[b[:,1],b[:,0]])*.5)
            local=raw/tolerances[m[:,1],m[:,0]]
            if forced_vertices is not None:
                local=np.where(forced_vertices[m[:,1],m[:,0]],1e12,local)
            l=(a+c)//2;r=(b+c)//2
            local=np.maximum(local,np.maximum(errors[l[:,1],l[:,0]],errors[r[:,1],r[:,0]]))
            np.maximum.at(errors,(m[:,1],m[:,0]),local)
        self.errors=errors

    def mesh(self,threshold):
        nodes=[tuple(t) for t in self.roots]
        faces=[];points=[];lookup={}
        while nodes:
            ax,ay,bx,by,cx,cy=nodes.pop()
            mx,my=(ax+bx)//2,(ay+by)//2
            if abs(ax-cx)+abs(ay-cy)>1 and self.errors[my,mx]>threshold:
                nodes.extend([(cx,cy,ax,ay,mx,my),(bx,by,cx,cy,mx,my)])
                continue
            indices=[]
            for x,y in ((ax,ay),(bx,by),(cx,cy)):
                key=(x,y)
                if key not in lookup:
                    lookup[key]=len(points);points.append((x,y,self.heights[y,x]))
                indices.append(lookup[key])
            if (bx-ax)*(cy-ay)-(by-ay)*(cx-ax)<0: indices.reverse()
            faces.append(indices)
        return np.asarray(points,dtype=float),np.asarray(faces,dtype=np.int32)

    def fit_budget(self,surface_budget,edge_budget=65534,vertex_budget=65534,domain=None,triangle_nw_se=False):
        if min(surface_budget,edge_budget,vertex_budget)<4: raise ValueError("Budget is too small")
        def fits(mesh):
            v,t=mesh
            if len(t)>surface_budget or len(v)>vertex_budget: return False
            return len(unique_edges(t)[0])<=edge_budget
        def candidate(threshold):
            mesh=self.mesh(threshold)
            mesh=clip_domain(*mesh,domain) if domain is not None else mesh
            return mesh
        high=max(float(self.errors.max()),1e-12)
        low=0.0
        best=candidate(high)
        for _ in range(32):
            mid=(low+high)*.5;mesh=candidate(mid)
            if fits(mesh): high=mid;best=mesh
            else: low=mid
        return (align_leaf_diagonals(*best) if triangle_nw_se else best),high

def align_leaf_diagonals(vertices,triangles):
    """Match UE's authored NW/SE diagonal in fully refined source cells."""
    triangles=triangles.copy();p=vertices[triangles,:2]
    low=p.min(axis=1);size=p.max(axis=1)-low
    fine=np.flatnonzero(np.all(np.abs(size-1)<1e-9,axis=1))
    cells={}
    for i in fine:cells.setdefault(tuple(low[i]),[]).append(i)
    for (x,y),indices in cells.items():
        if len(indices)!=2:continue
        ids=np.unique(triangles[indices]);lookup={tuple(vertices[i,:2]):int(i) for i in ids}
        if len(lookup)!=4:continue
        bl,br,tl,tr=(lookup[k] for k in ((x,y),(x+1,y),(x,y+1),(x+1,y+1)))
        triangles[indices]=[[bl,br,tl],[br,tr,tl]]
    return vertices,triangles

def clip_domain(vertices,triangles,domain):
    """Clip the padded RTIN to original sample coordinates, without stretching."""
    xmax,ymax=domain
    valid=(vertices[:,0]<=xmax+1e-9)&(vertices[:,1]<=ymax+1e-9)
    whole=np.all(valid[triangles],axis=1)
    points=vertices.tolist();faces=triangles[whole].tolist()
    lookup={(round(p[0],9),round(p[1],9)):i for i,p in enumerate(points)}
    for face in triangles[~whole]:
        poly=[vertices[i] for i in face]
        for axis,limit in ((0,xmax),(1,ymax)):
            result=[]
            for a,b in zip(poly,poly[1:]+poly[:1]):
                ia,ib=a[axis]<=limit,b[axis]<=limit
                if ia:result.append(a)
                if ia!=ib:
                    t=(limit-a[axis])/(b[axis]-a[axis]);result.append(a+t*(b-a))
            poly=result
            if not poly:break
        ids=[]
        for point in poly:
            key=(round(float(point[0]),9),round(float(point[1]),9))
            if key not in lookup:lookup[key]=len(points);points.append(point.tolist())
            if not ids or ids[-1]!=lookup[key]:ids.append(lookup[key])
        if len(ids)>1 and ids[0]==ids[-1]:ids.pop()
        for j in range(1,len(ids)-1):
            a,b,c=(points[i] for i in (ids[0],ids[j],ids[j+1]))
            if abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))>1e-10:
                faces.append([ids[0],ids[j],ids[j+1]])
    faces=np.asarray(faces,dtype=np.int32);used=np.unique(faces)
    remap=np.full(len(points),-1,dtype=np.int32);remap[used]=np.arange(len(used))
    return np.asarray(points,dtype=float)[used],remap[faces]

def unique_edges(triangles):
    edges=np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]])
    edges.sort(axis=1)
    return np.unique(edges,axis=0,return_counts=True)

def topology(vertices,triangles,n):
    edges,counts=unique_edges(triangles)
    border=edges[counts==1]
    a,b=vertices[border[:,0],:2],vertices[border[:,1],:2]
    external=np.any(((a==0)&(b==0))|((a==n)&(b==n)),axis=1)
    u=vertices[triangles[:,1],:2]-vertices[triangles[:,0],:2]
    v=vertices[triangles[:,2],:2]-vertices[triangles[:,0],:2]
    area=u[:,0]*v[:,1]-u[:,1]*v[:,0]
    return {"vertices":len(vertices),"surfaces":len(triangles),"edges":len(edges),
            "boundary_edges":len(border),"interior_boundary_edges":int(np.count_nonzero(~external)),
            "nonmanifold_edges":int(np.count_nonzero(counts>2)),"nonpositive_triangles":int(np.count_nonzero(area<=0))}

def rasterize(vertices,triangles,dimensions,n,centres=False):
    """Independent plane rasterizer at original source samples or cell centres."""
    w,h=dimensions;offset=.5 if centres else 0.0
    shape=(h-1,w-1) if centres else (h,w)
    output=np.full(shape,np.nan)
    nx,ny=(n,n) if np.isscalar(n) else n
    p=vertices.copy();p[:,0]*=(w-1)/nx;p[:,1]*=(h-1)/ny
    for face in triangles:
        a,b,c=p[face]
        lo=np.ceil(np.minimum(np.minimum(a[:2],b[:2]),c[:2])-offset-1e-8).astype(int)
        hi=np.floor(np.maximum(np.maximum(a[:2],b[:2]),c[:2])-offset+1e-8).astype(int)
        lo=np.maximum(lo,0);hi=np.minimum(hi,[shape[1]-1,shape[0]-1])
        if np.any(hi<lo): continue
        xx=np.arange(lo[0],hi[0]+1)[None,:]+offset
        yy=np.arange(lo[1],hi[1]+1)[:,None]+offset
        den=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        u=((xx-a[0])*(c[1]-a[1])-(yy-a[1])*(c[0]-a[0]))/den
        v=((b[0]-a[0])*(yy-a[1])-(b[1]-a[1])*(xx-a[0]))/den
        mask=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)
        patch=output[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        patch[mask]=(a[2]+u*(b[2]-a[2])+v*(c[2]-a[2]))[mask]
    if np.any(~np.isfinite(output)): raise ValueError("Mesh does not cover the complete source domain")
    return output

def audit(field,vertices,triangles,n,tolerance,return_heat=False):
    actual=field.heights_m
    triangulated=field.metadata.get("surface_interpolation")=="triangle_nw_se"
    centres=(actual[1:,:-1]+actual[:-1,1:])*.5 if triangulated else (actual[:-1,:-1]+actual[1:,:-1]+actual[:-1,1:]+actual[1:,1:])*.25
    errors=[rasterize(vertices,triangles,field.dimensions,n)-actual,
            rasterize(vertices,triangles,field.dimensions,n,True)-centres]
    centre_tolerance=np.minimum.reduce([tolerance[:-1,:-1],tolerance[1:,:-1],tolerance[:-1,1:],tolerance[1:,1:]])
    normalized=max(float(np.max(np.abs(e)/t)) for e,t in zip(errors,[tolerance,centre_tolerance]))
    def stats(values):
        values=np.concatenate([v.ravel() for v in values if v.size])
        return {"samples":len(values),"max_abs_m":float(np.max(np.abs(values))),
                "rms_m":float(np.sqrt(np.mean(values*values))),"p95_abs_m":float(np.percentile(np.abs(values),95)),
                "max_above_master_m":max(0.,float(values.max())),"max_below_master_m":max(0.,float(-values.min()))}
    regions={"all":stats(errors)}
    for name,mask in field.masks.items():
        centre=np.maximum.reduce([mask[:-1,:-1],mask[1:,:-1],mask[:-1,1:],mask[1:,1:]])
        selected=[errors[0][mask>.01],errors[1][centre>.01]]
        if any(v.size for v in selected): regions[name]=stats(selected)
        if name=="road":
            selected=[errors[0][mask>=1-1e-7],errors[1][centre>=1-1e-7]]
            if any(v.size for v in selected):regions["road_lane"]=stats(selected)
    report={"regions":regions,"max_normalized_error":normalized,"tolerances_met":normalized<=1+1e-6,
            "coverage":"every master grid vertex plus every cell centre; exact overlay of axis/45-degree triangles" if triangulated else "every master grid vertex plus every bilinear cell centre; not a continuous bound"}
    if return_heat:
        heat=np.abs(errors[0])/tolerance
        centre_heat=np.abs(errors[1])/centre_tolerance
        for view in (heat[:-1,:-1],heat[1:,:-1],heat[:-1,1:],heat[1:,1:]):
            np.maximum(view,centre_heat,out=view)
        return report,heat
    return report

def build(field,terrain_budget=22000,reserve_surfaces=8000,reserve_edges=16000,grid_size=None,
          ground_error=.5,road_error=.15,shore_error=.25,refinement_iterations=3,chunked=False,cliff_error=None,hierarchy_threshold=None):
    started=time.perf_counter()
    if refinement_iterations<1: raise ValueError("At least one refinement iteration is required")
    if min(terrain_budget,reserve_surfaces,reserve_edges)<0 or reserve_edges>=65530:
        raise ValueError("Invalid mesh or reserve budget")
    tolerance=tolerance_grid(field,ground_error,road_error,shore_error,cliff=cliff_error)
    if grid_size is None:
        grid_size=2**int(np.ceil(np.log2(max(field.dimensions)-1)))+1
    w,h=field.dimensions
    if grid_size<max(w,h):raise ValueError("Working grid must preserve every original sample")
    # RTIN needs2^k+1. Padding retains original coordinates and values; resizing
    #1024->1025 previously shifted sharp terrain by up to half a source cell.
    pad=((0,grid_size-h),(0,grid_size-w))
    heights=np.pad(field.heights_m,pad,mode="edge")
    domain=(w-1,h-1)
    if not chunked and terrain_budget+reserve_surfaces>32767:
        raise ValueError("Terrain plus reserved architecture exceeds the native 32,767-surface limit before world closure")
    priority=tolerance.copy();best=None;history=[];forced=np.zeros((h,w),dtype=bool)
    for iteration in range(refinement_iterations):
        targets=np.pad(priority,pad,mode="edge")
        rtin=Rtin(heights,targets,np.pad(forced,pad,mode="edge"))
        if hierarchy_threshold is not None:
            threshold=float(hierarchy_threshold)
            v,t=clip_domain(*rtin.mesh(threshold),domain)
            if field.metadata.get("surface_interpolation")=="triangle_nw_se":v,t=align_leaf_diagonals(v,t)
            if len(t)>terrain_budget:raise ValueError(f"Required mesh {len(t)} exceeds explicit terrain budget {terrain_budget}")
        else:
            (v,t),threshold=rtin.fit_budget(terrain_budget,terrain_budget*3 if chunked else 65534-reserve_edges,
                                          terrain_budget*3 if chunked else 65534,domain=domain,
                                          triangle_nw_se=field.metadata.get("surface_interpolation")=="triangle_nw_se")
        measurements,heat=audit(field,v,t,domain,tolerance,True)
        score=measurements["max_normalized_error"]
        history.append({"iteration":iteration,"max_normalized_error":score,"surfaces":len(t)})
        if best is None or score<best[0]: best=(score,v,t,threshold,measurements)
        if measurements["tolerances_met"]: break
        if field.metadata.get("surface_interpolation")=="triangle_nw_se":
            # A source-cell saddle can be exactly linear along the alternate
            # RTIN diagonal yet differ at its centre. Error weights alone cannot
            # refine a zero midpoint residual. Force implicated corners so both
            # half-cells reach leaves, then align them to the rendered diagonal.
            z=field.heights_m
            saddle=np.abs(z[:-1,:-1]+z[1:,1:]-z[1:,:-1]-z[:-1,1:])*.5
            ct=np.minimum.reduce([tolerance[:-1,:-1],tolerance[1:,:-1],tolerance[:-1,1:],tolerance[1:,1:]])
            fail=np.maximum.reduce([heat[:-1,:-1],heat[1:,:-1],heat[:-1,1:],heat[1:,1:]])>1
            cells=(saddle>ct)&fail
            if iteration>=1:
                # After broad error redistribution, finish the remaining
                # failing cells exactly instead of globally over-refining all
                # already accurate terrain. This also handles clipped boundary
                # vertices and zero residuals along a locally affine RTIN edge.
                cells|=fail
            for view in (forced[:-1,:-1],forced[1:,:-1],forced[:-1,1:],forced[1:,1:]):view|=cells
        # Redistribute a fixed mesh budget toward measured failures. No sample
        # is called accurate just because the hierarchy's local threshold passed.
        padded=np.pad(heat,1,mode="edge")
        spread=np.maximum.reduce([padded[j:j+h,i:i+w] for j in range(3) for i in range(3)])
        priority=np.maximum(tolerance*.05,priority/np.maximum(1,spread)**.8)
    _,v,t,threshold,measurements=best
    mesh_topology=topology(v,t,np.asarray(domain))
    # A conforming vertical wall is two triangles per boundary edge, and a
    # ceiling fan adds one. Actual compiler cuts/merges still require readback.
    boundary=mesh_topology["boundary_edges"]
    closure_surfaces=boundary*3
    total_surfaces=len(t)+reserve_surfaces+closure_surfaces
    total_edges=mesh_topology["edges"]+reserve_edges+boundary*4
    budget_ok=(len(t)<=terrain_budget) if chunked else total_surfaces<=32767 and total_edges<=65534
    topology_ok=not any(mesh_topology[k] for k in ("interior_boundary_edges","nonmanifold_edges","nonpositive_triangles"))
    report={"schema":"adaptive-heightfield-proof-v1","master_manifest_sha256":field.manifest_sha256,
            "source_dimensions":field.dimensions,"adaptive_grid_size":grid_size,"hierarchy_threshold":threshold,
            "working_grid_policy":"edge padding at original spacing; mesh clipped to source extent; no resampling",
            "requested_errors_m":{"ground":ground_error,"road":road_error,"shore":shore_error,"flat":.1,"outside_walkable_mask":cliff_error},
            "collision_strategy":"standalone_static_pieces" if chunked else "single_core_bsp",
            "refinement_history":history,
            "budget":{"terrain_surfaces":terrain_budget,"reserved_surfaces":reserve_surfaces,"reserved_edges":reserve_edges,
                      "estimated_closure_surfaces":closure_surfaces,"estimated_closure_edges":boundary*4,
                      "estimated_total_surfaces":total_surfaces,"estimated_total_edges":total_edges,
                      "mesh_and_reserve_fit_native_tables":None if chunked else budget_ok,
                      "within_requested_triangle_budget":len(t)<=terrain_budget,
                      "native_piece_tables_verified":False if chunked else None,
                      "estimated_static_piece_count":int(np.ceil(len(t)/8192)) if chunked else 0,
                      "native_surface_limit":32767,"native_edge_limit":65534},
            "topology":mesh_topology,"measurement":measurements,"accuracy_and_mesh_budget_pass":budget_ok and topology_ok and measurements["tolerances_met"],
            "runtime_ready":False,"elapsed_seconds":time.perf_counter()-started,
            "limits":"Open surface only. Reservations are estimates; compiled BSP tables, architectural intersections, native ray probes and physics remain unverified."}
    world=v.copy();lo,hi=field.bounds_m
    world[:,0]=lo[0]+world[:,0]*field.spacing_m[0]
    world[:,1]=lo[1]+world[:,1]*field.spacing_m[1]
    return world,t,report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest",type=Path);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--terrain-budget",type=int,default=22000);p.add_argument("--reserve-surfaces",type=int,default=8000)
    p.add_argument("--reserve-edges",type=int,default=16000);p.add_argument("--grid-size",type=int)
    p.add_argument("--ground-error",type=float,default=.5);p.add_argument("--road-error",type=float,default=.15);p.add_argument("--shore-error",type=float,default=.25)
    p.add_argument("--refinement-iterations",type=int,default=3)
    p.add_argument("--chunked",action="store_true",help="Research static terrain pieces; does not certify native compilation")
    p.add_argument("--cliff-error",type=float,help="Error outside an explicit walkable mask")
    p.add_argument("--hierarchy-threshold",type=float,help="Direct accuracy research threshold; budget remains a hard cap")
    a=p.parse_args();field=load_heightfield(a.manifest)
    vertices,triangles,report=build(field,a.terrain_budget,a.reserve_surfaces,a.reserve_edges,a.grid_size,a.ground_error,a.road_error,a.shore_error,a.refinement_iterations,a.chunked,a.cliff_error,a.hierarchy_threshold)
    a.out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(a.out/"collision-surface.npz",vertices_m=vertices,triangles=triangles)
    (a.out/"collision-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    # A completed research report can truthfully record a failed tolerance;
    # dependent build stages must explicitly inspect accuracy_and_mesh_budget_pass.

if __name__=="__main__": main()
