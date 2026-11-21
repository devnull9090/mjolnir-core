"""Rebuild the upper Fluid Flux tile against the registered outlet and physical rocks."""
import argparse
from pathlib import Path
import tempfile

import numpy as np

import outlet_apron
from audit_flux_state import sample
from bake_eroded_river import (WORK as PREVIOUS, bake, read, rock_surface, sha256, texture,
                               verify_state_files, write)
from extend_river_contact import build


def survey(folder, work, baseline, baseline_version=35):
    registered=read(work/"terrain/terrain.geometry.json")["watercourses"][0]
    reach=np.asarray(registered["erosion_reach"]["centreline_m"])
    rocks=read(work/"dressing/flow-rocks.json")["rocks"]
    descriptor=read(folder/"flux.json")
    sealed=read(baseline/"pwr.level.json")["flux"]
    upper,lower=descriptor["domains"]
    old_upper,old_lower=sealed["domains"]
    if lower!=old_lower:
        raise ValueError("Southeast lake descriptor changed")
    for k in ("height","velocity","ground"):
        path=lower["state"][k]
        if sha256(folder/path)!=sha256(baseline/path):
            raise ValueError("Southeast lake data changed: "+path)
    mutable={"provenance","sources","state","surface_painter"}
    if "surface_scalars" in old_upper:
        if old_upper["surface_scalars"]!={"DetailWaveHeight":3}:
            raise ValueError("Unrecognized upper river material override")
        upper["surface_scalars"]=old_upper["surface_scalars"].copy()
    if {k:v for k,v in upper.items() if k not in mutable}!={k:v for k,v in old_upper.items() if k not in mutable}:
        raise ValueError("Playback, colour or simulation settings differ from the approved river")
    upper["surface_painter"]=old_upper["surface_painter"]
    write(folder/"flux.json",descriptor)
    state,old=upper["state"],old_upper["state"]
    sections=[]
    for k in ("height","velocity","ground"):
        new_image=texture(folder/state[k])
        old_image=texture(baseline/old[k])
        if not np.array_equal(new_image[-400:],old_image[-400:]):
            raise ValueError("Previously verified junction changed in "+k)
        if k=="velocity":
            depth,old_depth=new_image[...,2],old_image[...,2]
    # Intersect each outlet-camera ray with the registered physical water
    # plane. Coverage includes depth written to EXR and excludes emergent
    # hulls; it describes the hydraulic surface, not screen-space lighting.
    for y in (600,690,780,850,898):
        px=np.arange(.5,1600,4)
        xyz=outlet_apron.intersect(px,np.full_like(px,y),reach)
        _,strength,left,right=outlet_apron.profile(xyz[:,:2],reach)
        inside=(left>1.)&(right>1.)&(strength>.99)
        blocked=np.zeros(len(xyz),bool)
        for rock in rocks:
            top=rock_surface(*xyz[:,:2].T,np.asarray(rock["vertices_m"]),rock["faces"])
            blocked|=(top>=xyz[:,2]-.02)
        available=inside&~blocked
        if np.count_nonzero(available)<10:
            raise ValueError("Insufficient unoccluded physical water at scanline "+str(y))
        wet=sample(depth,state,xyz[:,:2])[0]>1.8
        old_wet=sample(old_depth,old,xyz[:,:2])[0]>1.8
        match=float(wet[available].mean())
        if match<.90:
            raise ValueError(f"Apron loses registered physical depth at scanline {y}: {match:.2%}")
        sections.append({"screen_y_px":y,"spacing_px":4,"traced_interior_samples":int(inside.sum()),
                         "emergent_hull_samples":int((inside&blocked).sum()),
                         "submerged_interior_fraction":match,
                         "previous_submerged_fraction_on_same_samples":float(old_wet[available].mean()),
                         "frame_fraction_with_water_at_ray_intersection":float(wet.mean()),
                         "depth_cm_quantiles_10_50_90":np.quantile(sample(depth,state,xyz[:,:2])[0][available],
                                                                [.1,.5,.9]).round(2).tolist()})
    proof=read(folder/"receipt.json")
    proof.update(schema="pwr-registered-outlet-flux-v1",registered_outlet_scanlines=sections,
                 approved_surface_painter=upper["surface_painter"])
    proof[f"lower_matches_playtest_{baseline_version}"]=True
    proof[f"unchanged_downstream_rows_vs_{baseline_version}"]=400
    proof["inputs"].update(authoring=sha256(Path(__file__)),survey_profile=sha256(Path(outlet_apron.__file__)))
    proof["inputs"][f"previous_{baseline_version}"]=sha256(baseline/"pwr.level.json")
    proof["junction"]["parent"]="unshifted apron solve with sealed .35 contact recipe"
    proof["descriptor_sha256"]=sha256(folder/"flux.json")
    proof["gpu_probe_sha256"]=sha256(folder/"river_flux_readback.lua")
    for domain in (upper,lower):
        verify_state_files(folder,domain["state"])
    write(folder/"receipt.json",proof)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,default=outlet_apron.WORK)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    work=args.work.resolve()
    dest=args.output or work/"water-fix"
    if dest.exists():
        raise FileExistsError(dest)
    baseline=PREVIOUS/"saturday.35/map-input"
    with tempfile.TemporaryDirectory(dir=work,prefix=".flux-apron-") as temp:
        initial,final=Path(temp)/"unshifted",Path(temp)/"published"
        initial.mkdir();final.mkdir()
        bake(initial,work/"dressing/flow-rocks.json",work)
        build(final,work,initial)
        survey(final,work,baseline)
        final.rename(dest)
    print(dest)


if __name__=="__main__":
    main()
