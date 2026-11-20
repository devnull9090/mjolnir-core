"""Extend the lake's render plane into buried, zero-depth shore texels."""
from pathlib import Path
import shutil
import tempfile
import numpy as np
from scipy import ndimage
import outlet_apron as apron
from bake_eroded_river import (REPO, attach_native_probe, load_heightfield, read, sha256,
                               smooth, state_matches, texture, verify_state_files, write, write_exr)

def run(work,folder):
    source=work/"water-fix"
    desc=read(source/"flux.json"); upper=desc["domains"][0]; s=upper["state"]
    proof=read(source/"receipt.json")
    a={k:texture(source/s[k]) for k in ("height","velocity","ground")}
    orig=a["height"].copy()
    depth=a["velocity"][...,2]; cell=s["cell"]/100
    cols=s["centre"][0]/100+(np.arange(s["res"][0])+.5-s["res"][0]/2)*cell
    rows=-s["centre"][1]/100-(np.arange(s["res"][1])+.5-s["res"][1]/2)*cell
    x,y=np.meshgrid(cols,rows); f,_=apron.coordinates(np.stack((x,y),axis=-1))
    plane=142.4
    h=(orig[...,0]+s["capture"])/100
    pool=(depth>1.8)&(abs(h-plane)<.04)&(f>54)&(x>-490)&(x<-240)&(y>815)
    gap=ndimage.distance_transform_edt(~pool)*cell
    weight=(1-smooth(14,28,gap))*smooth(55,67,f)
    dry=(depth==0)&(weight>0)
    terrain=load_heightfield(work/"terrain/runtime-master.json")
    bed=terrain.sample(x[dry],y[dry])
    # Maintain the measured lake-plane continuation on dry banks. Where
    # land drops beyond its protective rim, keep the zero-depth sheet buried.
    target=np.minimum(plane,bed-.025)*100-s["capture"]
    for channel in (0,1):
        old=orig[...,channel][dry]
        a["height"][...,channel][dry]=old+(target-old)*weight[dry]
    shutil.copytree(source/"flux_state",folder/"flux_state")
    write_exr(folder/s["height"],a["height"])
    checked=texture(folder/s["height"]); a["height"]=checked
    if not np.array_equal(checked[depth>0],orig[depth>0]) or not np.array_equal(checked[~dry],orig[~dry]):
        raise ValueError("Unexpected wet or remote height edit")
    changed=np.any(checked!=orig,axis=-1)
    if not changed.any():raise ValueError("The lake contact was not corrected")
    for k in ("velocity","ground"):
        assert sha256(folder/s[k])==sha256(source/s[k])
    upper["provenance"]["dry_shore_height_source_sha256"]=sha256(Path(__file__))
    s["provenance"]=upper["provenance"].copy()
    s["height_sha256"]=sha256(folder/s["height"])
    write(folder/"flux_state/upper_river/state.json",s);write(folder/"flux.json",desc)
    probes=proof["readback_texels"].copy();sides={}
    reach=np.asarray(read(work/"terrain/terrain.geometry.json")["watercourses"][0]["erosion_reach"]["centreline_m"])
    for name,px,py in [("east_deep_fold",1410,440),("east_mid_fold",1395,464),("east_near_fold",1320,500),
                       ("west_mid_fold",330,508),("west_near_fold",390,516)]:
        xy=apron.intersect(float(px),float(py),reach)
        c=int(np.argmin(abs(cols-xy[0])));r=int(np.argmin(abs(rows-xy[1])))
        if not changed[r,c] or depth[r,c]!=0: raise ValueError("Missing dry contour probe "+name)
        probes.append((name,c,r));sides[name]={"texel":[c,r],"camera_pixel":[px,py],"old_z_m":h[r,c],
            "new_z_m":(checked[r,c,0]+s["capture"])/100,"bed_z_m":float(terrain.sample(cols[c],rows[r]))}
    attach_native_probe(folder,s,a,[],proof,samples=probes)
    for d in desc["domains"]:
        assert state_matches(d["state"],d); verify_state_files(folder,d["state"])
    proof.update(schema="pwr-basin-dry-shore-render-height-v1",dry_contact=dict(changed_cells=int(changed.sum()),
        wet_state_changes=0,source_descriptor_sha256=sha256(source/"flux.json"),shore_probes=sides),
        descriptor_sha256=sha256(folder/"flux.json"),gpu_probe_sha256=sha256(folder/"river_flux_readback.lua"),
        files={p.relative_to(folder).as_posix():sha256(p) for p in (folder/"flux_state").rglob("*") if p.is_file()})
    write(folder/"receipt.json",proof)

if __name__=="__main__":
    work=REPO/"out/pwr/river-basin";base=work/"shore-contact";base.mkdir(exist_ok=True)
    target=base/"water-fix"
    if target.exists():raise FileExistsError(target)
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        out=Path(tmp)/"ready";out.mkdir();run(work,out);out.rename(target)
    print(target)
