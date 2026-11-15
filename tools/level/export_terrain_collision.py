"""Export measured terrain as spatially ordered native standalone triangles.

The existing native splitter consumes input order, so Morton ordering keeps
successive <=8192-surface pieces local. Native compilation may split smaller;
the actual piece count and runtime frame time remain acceptance checks.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from heightfield import load_heightfield,sha256

def morton_order(points):
    low=points.min(axis=0);span=np.maximum(points.max(axis=0)-low,1e-9)
    q=np.clip((points-low)/span*65535,0,65535).astype(np.uint64)
    key=np.zeros(len(points),dtype=np.uint64)
    for bit in range(16):
        key|=((q[:,0]>>bit)&1)<<(2*bit)
        key|=((q[:,1]>>bit)&1)<<(2*bit+1)
    return np.argsort(key,kind="stable")

def architecture_parts(field, architecture, details=()):
    """Ordered fixed architecture, then individually identified base detail sets."""
    if details and not architecture:
        raise ValueError("Base detail collision requires the frozen architecture input first")
    result=[];seen=set()
    for index,path in enumerate(([architecture] if architecture else [])+list(details)):
        path=Path(path);digest=sha256(path)
        if digest in seen:raise ValueError("Duplicate architecture input would add collision twice")
        seen.add(digest);doc=json.loads(path.read_text())
        if doc.get("coordinates")!="ce_world_units_z_up":raise ValueError("Architecture coordinates mismatch")
        provenance=doc.get("provenance",{}) if index else doc
        if provenance.get("geometry_sha256")!=field.metadata["geometry_sha256"]:
            raise ValueError("Architecture transform provenance mismatch")
        if index:
            preservation=field.metadata.get("preservation",{})
            if (doc.get("schema")!="pwr-base-details-collision-v1"
                    or provenance.get("layout_sha256")!=preservation.get("layout_sha256")
                    or provenance.get("master_manifest_sha256")!=preservation.get("baseline_manifest_sha256")):
                raise ValueError("Base detail collision requires matching frozen gameplay preservation")
        points=np.asarray(doc["triangles"],dtype=float)
        if points.ndim!=3 or points.shape[1:]!=(3,3) or not np.isfinite(points).all():
            raise ValueError("Invalid architecture triangle coordinates")
        if len(doc["materials"])!=len(points):raise ValueError("Architecture material count mismatch")
        result.append((doc,{"path":str(path.resolve()),"sha256":digest,"triangles":len(points),
                            "role":"frozen_architecture" if index==0 else "base_details"}))
    return result


def export(manifest,mesh_dir,out,architecture=None,architecture_details=()):
    field=load_heightfield(manifest);mesh_dir=Path(mesh_dir)
    report_path=mesh_dir/"collision-report.json";report=json.loads(report_path.read_text())
    if report["master_manifest_sha256"]!=field.manifest_sha256:raise ValueError("Stale terrain collision proof")
    if not report["accuracy_and_mesh_budget_pass"]:raise ValueError("Terrain collision accuracy gate failed")
    arrays=np.load(mesh_dir/"collision-surface.npz",allow_pickle=False)
    vertices=arrays["vertices_m"];triangles=arrays["triangles"]
    points=vertices[triangles];order=morton_order(points.mean(axis=1)[:,:2]);points=points[order]
    ordered_triangles=triangles[order]
    normals=np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])
    if np.any(normals[:,2]<=0):raise ValueError("Terrain triangles must face upward")
    centres=points.mean(axis=1)
    road=field.sample_mask("road",centres[:,0],centres[:,1])
    walk=field.sample_mask("walkable",centres[:,0],centres[:,1])
    materials=np.where(road>.5,"tough_terrain_dirt",np.where(walk>.01,"tough_terrain_grass","hard_terrain_stone")).tolist()
    batches=[]
    for start in range(0,len(points),8192):
        p=points[start:start+8192]
        batches.append({"first_surface":start,"surfaces":len(p),"min_m":p.min(axis=(0,1)).tolist(),"max_m":p.max(axis=(0,1)).tolist()})
    doc={"schema":"pwr-native-terrain-extra-v1","coordinates":"ce_world_units_z_up","metres_per_world_unit":3.048,
         "master_manifest":str(field.path),"master_manifest_sha256":field.manifest_sha256,
         "accuracy_pass":True,"proof_sha256":sha256(report_path),"native_runtime_validated":False,
         "objects":len(batches),"skip_entries":[],"triangles":(points/3.048).tolist(),"materials":materials,
         "order":"Morton XY centroid; sequential native splitter max8192, may split smaller","candidate_batches":batches}
    architecture_count=0
    sources=[]
    for arch,source in architecture_parts(field,architecture,architecture_details):
        source["first_extra_surface"]=len(doc["triangles"])
        doc["triangles"].extend(arch["triangles"]);doc["materials"].extend(arch["materials"])
        doc["objects"]+=arch["objects"]
        architecture_count+=len(arch["triangles"]);sources.append(source)
    if sources:
        doc["architecture_sha256"]=sources[0]["sha256"]
        doc["architecture_sources"]=sources
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(doc,separators=(",",":")))
    # Candidate boundaries are useful probe locations, but are explicitly not
    # claimed as compiled instance boundaries: native tree limits may subdivide
    # earlier and shift later cut positions.
    edges=np.concatenate([ordered_triangles[:,[0,1]],ordered_triangles[:,[1,2]],ordered_triangles[:,[2,0]]])
    owners=np.tile(np.arange(len(ordered_triangles))//8192,3)
    edges.sort(axis=1);edge_order=np.lexsort((edges[:,1],edges[:,0]))
    edges=edges[edge_order];owners=owners[edge_order]
    shared=np.all(edges[:-1]==edges[1:],axis=1)&(owners[:-1]!=owners[1:])
    seams=[{"a_m":vertices[a].tolist(),"b_m":vertices[b].tolist(),"parts":[int(owners[i]),int(owners[i+1])]}
           for i in np.flatnonzero(shared) for a,b in [edges[i]]]
    import hashlib
    seams_doc={"schema":"pwr-terrain-seams-v1","master_manifest_sha256":field.manifest_sha256,
               "triangle_order_sha256":hashlib.sha256(ordered_triangles.astype("<i4").tobytes()).hexdigest(),
               "candidate_only":True,"compiled_boundaries_verified":False,"seams":seams}
    out.with_suffix(".seams.json").write_text(json.dumps(seams_doc,separators=(",",":")))
    np.savez_compressed(out.with_suffix(".ordered.npz"),vertices_m=vertices,triangles=ordered_triangles)
    receipt={"file":str(out),"sha256":sha256(out),"triangles":len(points),"candidate_batches":len(batches),
             "bytes":out.stat().st_size,"master_manifest_sha256":field.manifest_sha256,"native_runtime_validated":False,
             "candidate_seams":len(seams),"candidate_seams_path":str(out.with_suffix(".seams.json")),
             "trailing_architecture_surfaces":architecture_count,"total_extra_surfaces":len(points)+architecture_count,
             "architecture_sources":sources}
    out.with_suffix(".receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("manifest",type=Path)
    p.add_argument("--mesh-dir",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--architecture",type=Path)
    p.add_argument("--architecture-detail",type=Path,action="append",default=[],help="Append a hash-identified preserved base detail input exactly once")
    a=p.parse_args();print(json.dumps(export(a.manifest,a.mesh_dir,a.out,a.architecture,a.architecture_detail),indent=2))
