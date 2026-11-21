"""Check every final loose stone's inferred terrain contact using its stock highest-detail mesh."""
import json
import numpy as np

from ground_life_earth import MASTER, OUT, load, load_heightfield, sha
from outcrops_v3 import lod0_points
from verify_render_only_hism_cook import matrices


def verify():
    hf=load_heightfield(MASTER);spec=load(OUT/"hism.json")
    stock={r["path"]:r for r in load(OUT/"stock-native.json")}; groups=[]
    for index,group in enumerate(spec["groups"],1):
        mesh=stock[group["mesh"]];file=OUT/"stock"/mesh["source_file"]
        if sha(file)!=mesh["sha256"]:raise ValueError("Unexpected source scan")
        verts=lod0_points(file); xf=OUT/(spec["file"]+f".xf{index}")
        if sha(xf)!=spec["exact_sidecars"][index-1]:raise ValueError("Stale instance sidecar")
        affines=matrices(xf);bottom=[];top=[]
        for start in range(0,len(affines),50):
            mat=affines[start:start+50]
            placed=verts[None]@mat[:,:3,:3]+mat[:,None,3,:3]
            ground=100*hf.sample(placed[:,:,0]*.01,-placed[:,:,1]*.01)
            difference=placed[:,:,2]-ground
            bottom.extend(difference.min(axis=1));top.extend(difference.max(axis=1))
        bottom,top=np.array(bottom),np.array(top)
        if bottom.max()>.5 or top.min()<.6:raise ValueError(f"{group['mesh']} fails contact or visible-mass check: {bottom.max()}, {top.min()}")
        groups.append(dict(mesh=group["mesh"],instances=len(affines),stock_vertices=len(verts),source_affines_sha256=sha(xf),
                           min_bottom_to_terrain_cm=float(bottom.min()),max_bottom_to_terrain_cm=float(bottom.max()),
                           exposed_height_range_cm=[float(top.min()),float(top.max())],all_meshes_touch=True))
    doc=dict(projected_source="runtime-master native triangle terrain",groups=groups,instances=sum(g["instances"] for g in groups),
             source_hism_sha256=sha(OUT/"hism.json"),source_meshes_sha256=sha(OUT/"stock-native.json"))
    (OUT/"stone-contact-readback.json").write_text(json.dumps(doc,indent=2)+"\n")
    print(doc["instances"],[(round(g["max_bottom_to_terrain_cm"],3),np.round(g["exposed_height_range_cm"],1)) for g in groups])


if __name__=="__main__":verify()
