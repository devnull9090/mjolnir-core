"""Replace only the surveyed bank support triangles in Pelican Warfare's existing native physics."""
import json
from pathlib import Path
import subprocess
import numpy as np
from scipy.spatial import cKDTree
import cook_headwater_collision as c
import verify_headwater_collision as verifier
import package_pwr_headwater as package

WORK=c.W/"out/pwr/river-riparian"
BASE=c.W/"out/pwr/river-basin/native/physics"
OLD=c.W/"out/pwr/river-apron/bank/support.npz"
NEW=WORK/"cutbank/support.npz"
OUT=WORK/"native/physics"

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=json.loads((BASE/"native-collision-receipt.json").read_text())
    original=BASE/"collision_scene.bin"
    if c.filehash(original)!=report["source_binary_sha256"]:
        raise ValueError("The base native physics source has changed")
    if c.filehash(OLD)!=json.loads((BASE/"patch-report.json").read_text())["bank_support_sha256"]:
        raise ValueError("The source shell used a different bank")
    with np.load(OLD) as old,np.load(NEW) as new:
        before=old["triangles_m"].astype(float)
        after=new["triangles_m"].astype(float)
        mats=old["materials"]
        if before.shape!=after.shape or not np.array_equal(mats,new["materials"]) or not np.isfinite(after).all():
            raise ValueError("Inconsistent bank support")
    changed=np.flatnonzero(np.any(before!=after,axis=(1,2)))
    if not len(changed) or changed.max()>=108:
        raise ValueError("The new bank must retain existing rocks and their surface budget")
    doc=json.loads((BASE/"collision_scene.json").read_text())
    raw=bytearray(original.read_bytes())
    arrays=c.collision_arrays(raw,doc)
    def view(key,count,dtype):
        offset,stride,rows=arrays[key]
        return np.ndarray((rows,count),dtype=dtype,buffer=raw,offset=offset,strides=(stride,4))
    vertices=view("vertices",3,"<f4")
    surfaces=view("surfaces",2,"<i4")
    edges=view("edges",6,"<i4")
    planes=view("planes",4,"<f4")
    starts=surfaces[:,1]
    ids=np.column_stack((edges[starts,0],edges[starts,1],edges[edges[starts,2],1]))
    centers=vertices[ids].mean(axis=1)*c.UNIT
    distance,indices=cKDTree(centers).query(before.mean(axis=1))
    if max(distance)>.001 or len(np.unique(indices))!=len(indices):
        raise ValueError("Could not register the current bank to the original physical surfaces")
    current=vertices[ids[indices]].astype(float)*c.UNIT
    if np.abs(before-current).max()>.001:
        raise ValueError("Bank vertex order differs from the prior native cook")
    active=indices[changed]
    vids=ids[active]
    pids=surfaces[active,0]
    if (np.bincount(ids.ravel())[vids]!=1).any() or (np.bincount(surfaces[:,0])[pids]!=1).any():
        raise ValueError("A changed bank face shares an unrelated native vertex or plane")
    vertices[vids]=after[changed]/c.UNIT
    coords=vertices[vids].astype(float)
    normal=np.cross(coords[:,1]-coords[:,0],coords[:,2]-coords[:,0])
    lens=np.linalg.norm(normal,axis=1)
    if lens.min()<1e-7:
        raise ValueError("Degenerate toe collision")
    normal/=lens[:,None]
    planes[pids]=np.column_stack((normal,(normal*coords[:,0]).sum(axis=1)))
    (OUT/"collision_scene.bin").write_bytes(raw)
    doc["riparian_cutbank"]={"previous_scene_sha256":report["source_binary_sha256"],
        "source_support_sha256":c.filehash(OLD),"support_sha256":c.filehash(NEW),"changed_faces":len(changed)}
    scene=OUT/"collision_scene.json"
    scene.write_text(json.dumps(doc,indent=2))
    del raw,ids,centers
    with (OUT/"cook.log").open("w") as log:
        subprocess.run([package.cli,"level","collision",scene,"--paks",package.paks,"--own-bsp","--bsp-index","0",
                        "--receipt",OUT/"native-collision-receipt.json","--out",OUT/"pwr.sbsp"],stdout=log,stderr=subprocess.STDOUT,check=True)
    verifier.BASE,verifier.OUT=BASE,WORK
    verifier.main()
    proven=json.loads((OUT/"native-readback.json").read_text())
    if proven["verified_changed_faces"]!=len(changed):
        raise ValueError("Unexpected changes in the compiled native collision")
    print(doc["riparian_cutbank"],flush=True)

if __name__=="__main__":
    main()
